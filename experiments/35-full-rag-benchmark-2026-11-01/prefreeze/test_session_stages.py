"""Checks on test_session_stages.txt, the content of the test pod session (task 9.2, G6),
and on verify_session_stages.txt, the fix check session that runs through the same chain.

No stage runs. The test reads the file as pod_test_session.sh does, parses every
``run_arms.py`` call with the runner's own parser, runs ``--help`` of the other
scripts to check that they start from the Experiment 35 folder and take the options
each line gives, and checks the rules of the 2026-11-23 session plan: the rebuild
check of the three core datasets (G16), own folders for the recheck, throughput and
VRAM runs (G17), FinanceBench in three chunk sizes (G24), the task stages, and that
no line holds a key. The general checks run on both files.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import pytest
from tests._exp35_fixtures import load

HERE = Path(__file__).resolve().parent
EXP35 = HERE.parent
STAGES_FILE = HERE / "test_session_stages.txt"
VERIFY_FILE = HERE / "verify_session_stages.txt"
#: Each stages file with the fewest runner calls it must hold.
FILES = {STAGES_FILE: 101, VERIFY_FILE: 14}
BOTH = pytest.mark.parametrize("path", list(FILES), ids=["test", "verify"])
OUT = "/workspace/exp35-test/out"
#: What the chain and launch35.sh give every stage.
PROVIDED = {
    "OUT_DIR": OUT,
    "WORK": "/workspace",
    "COMMIT": "c" * 40,
    "BACKGROUND_PIDS": "/workspace/background.pids",
}
#: Scripts and subcommands that other agents add for the session (2026-11-23). An
#: entry passes while it is missing. Remove it when it lands: the check is then strict.
PENDING_FROM_OTHER_AGENTS = frozenset(
    {
        # every script has landed (2026-11-23)
    }
)
#: Values the owner records before go. The chain refuses to start while one holds TODO.
OWNER_VALUES = frozenset({"HF_REV_0_6B", "HF_REV_4B", "HF_REV_8B"})
#: Scripts whose ``--help`` only parses (argparse); others are checked for presence only.
HELP_SAFE = frozenset(
    {
        "rebuild35.py",
        "join35.py",
        "refusals35.py",
        "rerank_check35.py",
        "idle_repro35.py",
        "prefreeze/verify35.py",
    }
)
SUBCOMMANDS = frozenset({"rerank_check35.py", "refusals35.py", "prefreeze/verify35.py"})
CORE = ("financebench", "bioasq", "freshstack")
RECHECK = ("77536364", "77762811")
CONTROL = frozenset({"&&", "||", ";", "|", "&"})
RUNNER = ["uv", "run", "--no-sync", "python", "run_arms.py"]
_STAGE = re.compile(r"^(!?)([A-Za-z0-9._-]+)(?:@(\d+[smh]))? (.+)$")
_DEF = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")
_VAR = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?")
_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

cli35 = load("cli35")


@dataclass(frozen=True)
class Stage:
    index: int
    name: str
    fatal: bool
    timeout: str | None
    command: str


@dataclass(frozen=True)
class Call:
    stage: Stage
    env: tuple[tuple[str, str], ...]
    words: tuple[str, ...]

    @property
    def start(self) -> int:
        """Where the runner command starts: 0, after a wrapper's ``--``, or -1 for none."""
        words = list(self.words)
        return next((i for i in range(len(words)) if words[i : i + len(RUNNER)] == RUNNER), -1)

    @property
    def runner(self) -> bool:
        return self.start >= 0


@cache
def _read(path: Path = STAGES_FILE) -> tuple[tuple[Stage, ...], dict[str, str]]:
    stages: list[Stage] = []
    values: dict[str, str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line or line.startswith("#"):
            continue
        if found := _DEF.match(line):
            values[found[1]] = found[2]
            continue
        found = _STAGE.match(line)
        assert found, f"line {number} is neither a stage nor a value: {line[:60]}"
        stages.append(Stage(len(stages), found[2], found[1] == "!", found[3], found[4]))
    return tuple(stages), values


def _expand(text: str, path: Path = STAGES_FILE) -> tuple[str, set[str]]:
    known = {**PROVIDED, **_read(path)[1]}
    unknown: set[str] = set()

    def value(match: re.Match[str]) -> str:
        if match[1] not in known:
            unknown.add(match[1])
            return match[0]
        return known[match[1]]

    return _VAR.sub(value, text), unknown


def _split(stage: Stage, path: Path = STAGES_FILE) -> list[Call]:
    lexer = shlex.shlex(_expand(stage.command, path)[0], posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    calls, current = [], []
    for token in [*lexer, ";"]:
        if token not in CONTROL:
            current.append(token)
            continue
        env = []
        while current and _ASSIGN.match(current[0]):
            env.append(tuple(current.pop(0).split("=", 1)))
        cut = next((i for i, t in enumerate(current) if set(t) <= set("<>&")), len(current))
        if current[:cut]:
            calls.append(Call(stage, tuple(env), tuple(current[:cut])))
        current = []
    return calls


@cache
def _calls(path: Path = STAGES_FILE) -> tuple[Call, ...]:
    return tuple(call for stage in _read(path)[0] for call in _split(stage, path))


@cache
def _runs(path: Path = STAGES_FILE) -> tuple[tuple[Call, Any], ...]:
    """Every runner call with its parsed arguments (the runner's own parser)."""
    return tuple(
        (call, cli35.parse_args(list(call.words[call.start + len(RUNNER) :])))
        for call in _calls(path)
        if call.runner
    )


def _folder(path: Any) -> str:
    return str(path).removeprefix(OUT + "/").split("/")[0] if path else ""


def _opts(words: tuple[str, ...]) -> dict[str, str]:
    return {w: words[i + 1] for i, w in enumerate(words[:-1]) if w.startswith("--")}


def _script(call: Call) -> tuple[str, str, tuple[str, ...]] | None:
    """Return (script, subcommand, the script's arguments) for a call of a .py or .sh file."""
    for i, word in enumerate(call.words):
        if word.endswith((".py", ".sh")) and not word.startswith("-"):
            has_sub = word in SUBCOMMANDS and i + 1 < len(call.words)
            rest = call.words[i + 1 + has_sub :]
            rest = rest[: rest.index("--")] if "--" in rest else rest  # a wrapped command
            return word, call.words[i + 1] if has_sub else "", rest
    return None


def _at(call: Call) -> int:
    """Return the place of *call* in the session: stages in order, calls in line order."""
    return _calls().index(call)


def _help(key: tuple[str, str, tuple[tuple[str, str], ...]]) -> tuple[int, str]:
    script, sub, env = key
    base = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    argv = [sys.executable, script, *([sub] if sub else []), "--help"]
    found = subprocess.run(
        argv, cwd=EXP35, env={**base, **dict(env)}, capture_output=True, text=True, timeout=120
    )
    return found.returncode, found.stdout + found.stderr


@BOTH
def test_every_stage_has_a_unique_name_and_its_own_timeout(path: Path) -> None:
    stages = _read(path)[0]
    names = [s.name for s in stages]
    assert len(names) == len(set(names)), "a stage name repeats"
    assert [s.name for s in stages if s.timeout is None] == []


def test_the_values_are_the_question_list_the_gguf_folder_and_the_owner_pins() -> None:
    values = _read()[1]
    assert set(values) == {"FS_QIDS", "SWEEP_GGUF_DIR", *OWNER_VALUES}
    qids = values["FS_QIDS"].split(",")
    assert len(qids) == len(set(qids)) == 40 and all(q.isdigit() for q in qids)
    assert tuple(qids[-2:]) == RECHECK
    assert values["SWEEP_GGUF_DIR"].startswith("/")
    for name in OWNER_VALUES:
        assert values[name] == "TODO" or re.fullmatch(r"[0-9a-f]{40}", values[name]), name


def test_setup_and_context_run_first_and_only_they_stop_the_chain() -> None:
    stages = _read()[0]
    assert [s.name for s in stages[:2]] == ["setup", "context"]
    assert [s.name for s in stages if s.fatal] == ["setup", "context"]
    assert "prefreeze/pod_setup35.sh" in stages[0].command
    assert "context35.py" in stages[1].command and "$OUT_DIR/context35.json" in stages[1].command


@BOTH
def test_every_runner_call_parses_and_writes_a_prefreeze_run_under_out_dir(path: Path) -> None:
    runs = _runs(path)
    assert len(runs) >= FILES[path]
    for call, args in runs:
        where = f"stage {call.stage.name}"
        assert args.prefreeze, where
        assert str(args.out_dir).startswith(OUT + "/"), where
        assert args.index_from is None or str(args.index_from).startswith(OUT + "/"), where
        assert "output" not in str(args.out_dir), where


@BOTH
def test_no_line_holds_a_key_or_names_one(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for bad in ("API_KEY", "ZAI_KEY", "sk-or-", "rpa_", "Bearer", "RUNPOD_SECRET", "secrets/"):
        assert bad not in text, bad


@BOTH
def test_every_variable_is_given_by_the_chain_or_defined_in_the_file(path: Path) -> None:
    unknown = {name for stage in _read(path)[0] for name in _expand(stage.command, path)[1]}
    assert unknown == set()


@BOTH
def test_every_script_exists_or_is_pending_and_takes_its_options(path: Path) -> None:
    keys, problems = {}, []
    for call in _calls(path):
        found = _script(call)
        if found is None or found[0] == "run_arms.py":
            continue
        script, sub, _ = found
        named = f"{script} {sub}".strip()
        if not (EXP35 / script).is_file():
            if named not in PENDING_FROM_OTHER_AGENTS and script not in PENDING_FROM_OTHER_AGENTS:
                problems.append(f"{call.stage.name}: {script} does not exist")
            continue
        if script in HELP_SAFE:
            keys.setdefault((script, sub, tuple(sorted(call.env))), []).append(call)
    with ThreadPoolExecutor(max_workers=8) as pool:
        helps = dict(zip(keys, pool.map(_help, keys), strict=True))
    for key, calls in keys.items():
        code, text = helps[key]
        named = f"{key[0]} {key[1]}".strip()
        if code != 0:
            if named not in PENDING_FROM_OTHER_AGENTS:
                problems.append(f"{named}: --help exits {code}: {text[-300:]}")
            continue
        for call in calls:
            for word in _script(call)[2]:
                flag = word.split("=", 1)[0]
                if flag.startswith("--") and not re.search(rf"(?<![\w-]){flag}(?![\w-])", text):
                    problems.append(f"{call.stage.name}: {named} takes no {flag}")
    assert problems == []


def test_the_rebuild_check_covers_each_core_dataset_from_both_sides() -> None:
    runs = _runs()
    for dataset in CORE:
        mine = [(c, a) for c, a in runs if a.dataset == dataset]
        built = {(a.stage, _folder(a.out_dir)) for c, a in mine if a.index == "e4b-c1024"}
        assert {("ingest", "rb"), ("seal", "rb")} <= built, dataset
        sides = {
            (_folder(a.index_from), _folder(a.out_dir)): _at(c)
            for c, a in mine
            if a.stage == "search" and a.setup == "e4b-c1024-roff-hoff"
        }
        assert set(sides) == {("s", "chk"), ("rb", "rbs")}, dataset
        compare = [c for c in _calls() if "rebuild35.py" in c.words and dataset in c.words]
        assert len(compare) == 1, dataset
        opts = _opts(compare[0].words)
        path = f"{dataset}/search/e4b-c1024-roff-hoff/run1/search.jsonl"
        assert (opts["--a"], opts["--b"]) == (f"{OUT}/chk/{path}", f"{OUT}/rbs/{path}")
        assert (opts["--out-dir"], opts["--dataset"]) == (f"{OUT}/s", dataset)
        sealed = max(
            _at(c)
            for c, a in mine
            if a.stage == "seal" and _folder(a.out_dir) in ("s", "rb") and a.index == "e4b-c1024"
        )
        later = [
            _at(c)
            for c, a in mine
            if _folder(a.out_dir) == "s" and a.stage not in ("ingest", "seal")
        ]
        assert sealed < min(sides.values()) <= max(sides.values()) < _at(compare[0]), dataset
        assert _at(compare[0]) < min(later), dataset


def test_recheck_throughput_and_vram_read_s_or_t_and_write_their_own_folder() -> None:
    runs = _runs()
    own = {"r": {"s"}, "tput": {"s"}, "vram": {"t"}, "chk": {"s", "sl"}, "rbs": {"rb"}}
    for call, args in runs:
        folder = _folder(args.out_dir)
        if folder in own:
            assert _folder(args.index_from) in own[folder], call.stage.name
        else:
            assert args.index_from is None, call.stage.name
    recheck = {(a.setup, a.stage) for _, a in runs if _folder(a.out_dir) == "r"}
    shapes = {
        f"e4b-c{c}-r{r}-h{h}"
        for c in (512, 1024, 2048)
        for r in ("off", "0.6b")
        for h in ("off", "on")
    }
    assert recheck == {(s, stage) for s in shapes for stage in ("answer", "judge")}
    assert {tuple(a.qids) for _, a in runs if _folder(a.out_dir) == "r"} == {RECHECK}
    tput = {a.setup for _, a in runs if _folder(a.out_dir) == "tput"}
    assert tput == {f"e4b-c{c}-r{r}-hoff" for c in (512, 1024, 2048) for r in ("0.6b", "4b", "8b")}
    assert {a.setup for _, a in runs if _folder(a.out_dir) == "vram"} == {"e8b-c1024-r8b-hon"}
    joins = [c for c in _calls() if "join35.py" in c.words]
    assert sorted(_opts(c.words)["--out-dir"] for c in joins) == [f"{OUT}/s", f"{OUT}/sl"]


def test_each_core_dataset_answers_in_three_chunk_sizes_through_every_answer_stage() -> None:
    runs = _runs()
    setups = {f"e4b-c{c}-r0.6b-hon" for c in (512, 1024, 2048)}
    for dataset in CORE:
        smoke = [a for _, a in runs if a.dataset == dataset and _folder(a.out_dir) == "s"]
        for stage in ("search", "answer", "judge", "ragas", "claimkinds"):
            found = {a.setup for a in smoke if a.stage == stage and a.answers == "answer"}
            assert found == setups, (dataset, stage)
        assert {a.judges for a in smoke if a.stage == "judge"} == {"chat,clef_flash"}
        assert {(a.stage, a.answers) for a in smoke if a.setup == "e4b-c1024-r0.6b-hon"} >= {
            ("closedbook", "answer"),
            ("ragas", "closedbook-rag"),
        }


@BOTH
def test_each_dataset_uses_one_selection_in_each_folder(path: Path) -> None:
    seen: dict[tuple[str, str], set[tuple[Any, ...]]] = {}
    for _, a in _runs(path):
        selection = (a.limit, a.corpus_sample, tuple(a.qids or ()), str(a.passages_dir))
        seen.setdefault((a.dataset, _folder(a.out_dir)), set()).add(selection)
    assert {k: v for k, v in seen.items() if len(v) != 1} == {}


def test_calibration_stages_carry_their_start_concurrency_so_the_chain_can_halve_it() -> None:
    flags = {
        "answer": ("--answer-concurrency", "16"),
        "closedbook": ("--answer-concurrency", "16"),
        "judge": ("--chat-concurrency", "4"),
        "ragas": ("--ragas-concurrency", "16"),
        "claimkinds": ("--classify-concurrency", "16"),
    }
    for call, args in _runs():
        if _folder(args.out_dir) not in ("s", "sl") or args.stage not in flags:
            continue
        flag, value = flags[args.stage]
        assert _opts(call.words).get(flag) == value, call.stage.name
        assert call.stage.command.count("run_arms.py ") == 1, call.stage.name


def test_the_task_stages_are_present_in_their_order() -> None:
    stages, runs = _read()[0], _runs()
    by_name = {s.name: s for s in stages}
    order = ["rerank-pool", "rerank-0.6b", "rerank-4b", "rerank-8b"]
    assert [by_name[n].index for n in order] == sorted(by_name[n].index for n in order)
    for size in ("0.6b", "4b", "8b"):
        words = by_name[f"rerank-{size}"].command
        assert [w in words for w in ("llamacpp", "reference", "verdict")] == [True] * 3
    (full,) = [(c, a) for c, a in runs if _folder(a.out_dir) == "fsfull" and a.stage == "ingest"]
    found = (full[1].dataset, full[1].index, full[0].stage.timeout)
    assert found == ("freshstack", "e4b-c1024", "6h")
    assert (full[1].limit, full[1].qids, full[1].corpus_sample) == (None, None, None)
    idle = [c for c in _calls() if "idle_repro35.py" in c.words]
    assert sorted(_opts(c.words)["--out"] for c in idle) == [f"{OUT}/idle", f"{OUT}/idle-held"]
    assert [("--hold" in c.words) for c in idle] == [False, True]
    ragas_s = [c.stage.index for c, a in runs if a.stage == "ragas" and _folder(a.out_dir) == "s"]
    assert max(ragas_s) < min(c.stage.index for c in idle)
    sample = [c for c in _calls() if "refusals35.py" in c.words and "sample" in c.words]
    assert {_opts(sample[0].words)[k] for k in ("--seed", "--n")} == {"20261112", "100"}
    kinds = [
        c.stage.index for c, a in runs if a.stage == "claimkinds" and _folder(a.out_dir) == "s"
    ]
    assert max(kinds) < sample[0].stage.index
    assert "refusals35.py" in stages[-1].command and " classify " in stages[-1].command


def test_legal_stages_skip_when_its_data_is_absent_and_stay_out_of_the_core_folders() -> None:
    legal = {c.stage.name for c, a in _runs() if a.dataset == "legal"}
    assert legal, "no Legal RAG Bench stage"
    for stage in _read()[0]:
        if stage.name in legal or "/sl" in stage.command:
            assert stage.command.startswith("[ -d /workspace/passages/legal ] || exit 77; "), (
                stage.name
            )
    for _, a in _runs():
        if a.dataset == "legal":
            assert _folder(a.out_dir) in ("sl", "t", "rb", "chk", "rbs")


def test_the_reranker_entries_come_from_the_candidates_file_not_plan_json() -> None:
    """Task 4B.3: rerankers are test inputs until the 15.10 check passes."""
    line = next(
        row
        for row in STAGES_FILE.read_text(encoding="utf-8").splitlines()
        if row.startswith("rerank-entries@")
    )
    assert "prefreeze/rerank_candidates.json" in line
    assert '["runtime"]["models"]' not in line
