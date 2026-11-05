"""Tests for the dots-mocr parity script on llama.cpp (task 3.3, design D9 item 1).

Change dots-mocr-llamacpp-backend.
The script is not an installable package, so the tests load it by path. They
never start a llama-server, never parse a real page and never use the network.
The reference folders are tiny fakes written under ``tmp_path``.
"""

from __future__ import annotations

import importlib.util
import json
import statistics
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ENGINE_DIR = REPO_ROOT / "ocr-workers" / "engines" / "dots-mocr"
SCRIPT = ENGINE_DIR / "parity_check.py"
EXP41_DIR = REPO_ROOT / "experiments" / "41-ocr-runtimes-2026-10-30"


def _load(name: str, path: Path) -> ModuleType:
    """Load *path* as module *name* without writing bytecode next to it."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # a dataclass in the script looks its module up here
    saved = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = saved
    return module


@pytest.fixture(name="parity")
def _parity() -> ModuleType:
    """Return the parity script as a module."""
    return _load("dots_llamacpp_parity", SCRIPT)


def _entry(
    key: str, dice_d4: float = 1.0, identical: bool = True, dice_t: float = 1.0
) -> dict[str, Any]:
    """Return one finished page entry as the script stores it."""
    doc, page = key.split(":")
    return {
        "doc": doc,
        "page": int(page),
        "status": "ok",
        "seconds": 1.0,
        "chars": 10,
        "dice_d4": dice_d4,
        "identical_d4": identical,
        "dice_tcontrol": dice_t,
    }


def _entries(parity: ModuleType, **changes: dict[str, Any]) -> list[dict[str, Any]]:
    """Return 22 perfect entries; *changes* maps a page key to field overrides."""
    entries = []
    for key in parity.PAGES:
        entry = _entry(key)
        entry.update(changes.get(key, {}))
        entries.append(entry)
    return entries


# ── plan only ───────────────────────────────────────────────────────────────


def test_plan_only_touches_nothing(
    parity: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without ``--run`` the script prints the plan and writes, spawns and makes nothing."""

    def refuse(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("the plan-only run must not do this")

    monkeypatch.setattr("tempfile.mkdtemp", refuse)
    monkeypatch.setattr("tempfile.TemporaryDirectory", refuse)
    monkeypatch.setattr("subprocess.Popen", refuse)
    monkeypatch.setattr("os.replace", refuse)
    monkeypatch.setattr(Path, "write_text", refuse)
    monkeypatch.setattr(Path, "mkdir", refuse)
    before = sorted(p.name for p in parity.EVIDENCE_DIR.iterdir())
    assert parity.main([]) == 0
    assert sorted(p.name for p in parity.EVIDENCE_DIR.iterdir()) == before
    out = capsys.readouterr().out
    assert "parity.json" in out
    assert "eq01:3" in out
    assert "22 pages" in out


# ── Dice and tokeniser ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("", ""),
        ("alpha beta gamma", "alpha beta gamma"),
        ("alpha beta gamma", "alpha beta delta"),
        ("The $x^2 + \\alpha$ term", "the x 2 term"),
        ("one one two", "one two two"),
        ("text", ""),
    ],
)
def test_dice_matches_experiment_41(parity: ModuleType, a: str, b: str) -> None:
    """The script scores two texts exactly as Experiment 41's ``analysis.py`` does."""
    sys.path.insert(0, str(EXP41_DIR))
    try:
        analysis = _load("exp41_analysis", EXP41_DIR / "analysis.py")
    finally:
        sys.path.remove(str(EXP41_DIR))
    tokens = analysis.exp33_tokens()
    assert parity.text_dice(a, b) == analysis.dice(tokens(a), tokens(b))


def test_tokeniser_is_pinned_by_hash(parity: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    """A changed Experiment 33 tokeniser file stops the run."""
    monkeypatch.setattr(parity, "BUILD_LABELS_SHA256", "0" * 64)
    parity.exp33_tokens.cache_clear()
    with pytest.raises(SystemExit, match="tokeniser"):
        parity.text_dice("a", "b")
    parity.exp33_tokens.cache_clear()


# ── rules ───────────────────────────────────────────────────────────────────


def test_rules_all_pass(parity: ModuleType) -> None:
    """Perfect pages pass the three rules and the overall verdict."""
    result = parity.evaluate_rules(_entries(parity))
    assert result["rule1_dice_d4_min"]["pass"] is True
    assert result["rule2_identical_d4"]["pass"] is True
    assert result["rule3_median_dice_tcontrol"]["pass"] is True
    assert result["pass"] is True


def test_rule1_fails_when_one_page_is_0_98(parity: ModuleType) -> None:
    """One page at 0.98 against D4 fails rule 1 only."""
    result = parity.evaluate_rules(_entries(parity, **{"io07:28": {"dice_d4": 0.98}}))
    assert result["rule1_dice_d4_min"]["pass"] is False
    assert result["rule1_dice_d4_min"]["failing"] == ["io07:28"]
    assert result["rule2_identical_d4"]["pass"] is True
    assert result["pass"] is False


def test_rule2_fails_with_five_non_identical_pages(parity: ModuleType) -> None:
    """Five non-identical pages leave 17 of 22 identical: rule 2 fails, rule 1 holds."""
    changes = {k: {"identical_d4": False, "dice_d4": 0.995} for k in parity.PAGES[:5]}
    result = parity.evaluate_rules(_entries(parity, **changes))
    assert result["rule2_identical_d4"]["identical"] == 17
    assert result["rule2_identical_d4"]["pass"] is False
    assert result["rule1_dice_d4_min"]["pass"] is True
    assert result["pass"] is False


def test_rule2_passes_with_four_non_identical_pages(parity: ModuleType) -> None:
    """Four non-identical pages leave exactly 18 identical: rule 2 holds."""
    changes = {k: {"identical_d4": False, "dice_d4": 0.995} for k in parity.PAGES[:4]}
    result = parity.evaluate_rules(_entries(parity, **changes))
    assert result["rule2_identical_d4"]["identical"] == 18
    assert result["rule2_identical_d4"]["pass"] is True


def test_rule3_fails_when_median_is_below_0_99(parity: ModuleType) -> None:
    """A median of 0.98 against the T-control text fails rule 3 only."""
    changes = {k: {"dice_tcontrol": 0.98} for k in parity.PAGES[:12]}
    result = parity.evaluate_rules(_entries(parity, **changes))
    assert result["rule3_median_dice_tcontrol"]["median"] == statistics.median(
        [0.98] * 12 + [1.0] * 10
    )
    assert result["rule3_median_dice_tcontrol"]["pass"] is False
    assert result["rule1_dice_d4_min"]["pass"] is True
    assert result["pass"] is False


def test_an_unfinished_run_cannot_pass(parity: ModuleType) -> None:
    """Twenty-one perfect pages are not enough: the verdict needs all 22."""
    result = parity.evaluate_rules(_entries(parity)[:21])
    assert result["complete"] is False
    assert result["pass"] is False


def test_a_failed_page_fails_rule_1(parity: ModuleType) -> None:
    """A page that raised has no Dice and counts as a failure."""
    broken = {"doc": "io01", "page": 13, "status": "error", "error": "boom"}
    entries = _entries(parity)
    entries[3] = broken
    result = parity.evaluate_rules(entries)
    assert result["rule1_dice_d4_min"]["pass"] is False
    assert "io01:13" in result["rule1_dice_d4_min"]["failing"]


# ── page list and references ────────────────────────────────────────────────


def test_page_list_has_22_entries(parity: ModuleType) -> None:
    """The list is the 20 T-control pages plus eq01 pages 2 and 3."""
    pages = parity.PAGES
    assert len(pages) == 22
    assert len(set(pages)) == 22
    assert {p.split(":")[0] for p in pages} == {
        "eq01",
        "io01",
        "io02",
        "io04",
        "io07",
        "mp05",
        "rf06",
        "rf07",
    }
    assert "eq01:2" in pages and "eq01:3" in pages
    assert sum(not p.startswith("eq01:") for p in pages) == 20


def _write_page(folder: Path, key: str, text: str) -> None:
    """Write *text* as the stored page of *key* under *folder*."""
    doc, page = key.split(":")
    target = folder / doc / f"p{int(page):03d}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def test_references_read_the_fake_folders(parity: ModuleType, tmp_path: Path) -> None:
    """D4 and T-D0 come from the Experiment 41 folder, named as ``p<NNN>.md``."""
    out = tmp_path / "output"
    _write_page(out / "D4", "io01:13", "from d4")
    _write_page(out / "T-D0", "io01:13", "from t-control")
    _write_page(tmp_path / "exp37", "io01:13", "from d0 (must lose to T-D0)")
    refs = parity.load_references("io01:13", out, tmp_path / "exp37")
    assert refs.d4 == "from d4"
    assert refs.tcontrol == "from t-control"
    assert refs.tcontrol_source == "T-D0"


def test_references_fall_back_to_experiment_37_d0(parity: ModuleType, tmp_path: Path) -> None:
    """A page that T-D0 never ran (eq01 page 3) takes the Experiment 37 PyTorch text."""
    out = tmp_path / "output"
    _write_page(out / "D4", "eq01:3", "from d4")
    _write_page(tmp_path / "exp37", "eq01:3", "from d0")
    refs = parity.load_references("eq01:3", out, tmp_path / "exp37")
    assert refs.tcontrol == "from d0"
    assert refs.tcontrol_source == "exp37-D0"


def test_a_missing_d4_text_stops_the_run(parity: ModuleType, tmp_path: Path) -> None:
    """No D4 text means no reference: the script stops and does not invent one."""
    with pytest.raises(SystemExit, match="D4"):
        parity.load_references("io01:13", tmp_path / "output", tmp_path / "exp37")


# ── collect, checkpoint and resume ──────────────────────────────────────────


def _fake_refs(parity: ModuleType) -> Callable[[str], Any]:
    """Return a reference loader whose texts are the same for every page."""
    return lambda _key: parity.References("alpha beta gamma", "alpha beta gamma", "T-D0")


def test_collect_scores_and_checkpoints_each_page(parity: ModuleType, tmp_path: Path) -> None:
    """Each finished page is on disk before the next one starts."""
    path = tmp_path / "parity.json"
    seen: list[int] = []

    def parse(doc: str, page: int) -> str:
        if path.is_file():
            seen.append(len(json.loads(path.read_text())["pages"]))
        return "alpha beta gamma"

    pages = parity.PAGES[:3]
    result = parity.collect(parse, _fake_refs(parity), path, pages=pages)
    assert seen == [1, 2]
    assert list(result["pages"]) == list(pages)
    first = result["pages"][pages[0]]
    assert first["dice_d4"] == 1.0
    assert first["identical_d4"] is True
    assert first["dice_tcontrol"] == 1.0
    assert first["chars"] == len("alpha beta gamma")
    assert not path.with_suffix(".json.tmp").exists()


def test_the_returned_result_carries_the_rule_verdicts_the_summary_prints(
    parity: ModuleType, tmp_path: Path
) -> None:
    """``run`` prints ``result["pass"]`` and each ``rule*`` key; the return value must hold them."""
    path = tmp_path / "parity.json"
    pages = parity.PAGES[:2]
    result = parity.collect(lambda d, p: "alpha beta gamma", _fake_refs(parity), path, pages=pages)
    saved = json.loads(path.read_text())
    assert "pass" in result and "complete" in result
    assert {k for k in result if k.startswith("rule")} == {k for k in saved if k.startswith("rule")}
    assert result["pass"] == saved["pass"]


def test_a_stopped_run_keeps_its_progress(parity: ModuleType, tmp_path: Path) -> None:
    """A crash on page 3 leaves pages 1 and 2 in the file."""
    path = tmp_path / "parity.json"

    def parse(doc: str, page: int) -> str:
        if f"{doc}:{page}" == parity.PAGES[2]:
            raise KeyboardInterrupt
        return "alpha beta gamma"

    with pytest.raises(KeyboardInterrupt):
        parity.collect(parse, _fake_refs(parity), path, pages=parity.PAGES[:3])
    assert list(json.loads(path.read_text())["pages"]) == list(parity.PAGES[:2])


def test_resume_skips_finished_pages(parity: ModuleType, tmp_path: Path) -> None:
    """``resume`` parses only the pages that are not in the file."""
    path = tmp_path / "parity.json"
    pages = parity.PAGES[:4]
    parity.collect(lambda d, p: "alpha beta gamma", _fake_refs(parity), path, pages=pages[:2])
    asked: list[tuple[str, int]] = []

    def parse(doc: str, page: int) -> str:
        asked.append((doc, page))
        return "alpha beta gamma"

    result = parity.collect(parse, _fake_refs(parity), path, pages=pages, resume=True)
    assert len(asked) == 2
    assert [f"{d}:{p}" for d, p in asked] == list(pages[2:])
    assert list(result["pages"]) == list(pages)


def test_an_existing_file_needs_resume(parity: ModuleType, tmp_path: Path) -> None:
    """Without ``resume`` an existing result file is never overwritten."""
    path = tmp_path / "parity.json"
    path.write_text('{"pages": {}}', encoding="utf-8")
    with pytest.raises(SystemExit, match="--resume"):
        parity.collect(lambda d, p: "x", _fake_refs(parity), path, pages=parity.PAGES[:1])
    assert path.read_text(encoding="utf-8") == '{"pages": {}}'


def test_a_parse_error_is_recorded_and_the_run_goes_on(parity: ModuleType, tmp_path: Path) -> None:
    """An engine error on one page is stored as an error entry; later pages still run."""
    path = tmp_path / "parity.json"
    pages = parity.PAGES[:2]

    def parse(doc: str, page: int) -> str:
        if f"{doc}:{page}" == pages[0]:
            raise RuntimeError("server gone")
        return "alpha beta gamma"

    result = parity.collect(parse, _fake_refs(parity), path, pages=pages)
    assert result["pages"][pages[0]]["status"] == "error"
    assert "server gone" in result["pages"][pages[0]]["error"]
    assert result["pages"][pages[1]]["status"] == "ok"


@pytest.fixture(autouse=True)
def _no_bytecode_leak() -> Iterator[None]:
    """Fail loud if a test left a ``__pycache__`` in the engine folder."""
    yield
    assert not (ENGINE_DIR / "__pycache__").exists()
