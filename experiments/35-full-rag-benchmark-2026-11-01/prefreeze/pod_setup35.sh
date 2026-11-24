#!/usr/bin/env bash
# Prepare one RunPod RTX 4090 pod for Experiment 35 before the test session chain runs
# (task 9.2, gap G4). Every step checks before it acts, so a second run repeats no work.
#
# plan.json gives each GGUF file and its SHA-256, the llama.cpp build and the dataset
# pins; datasets35.py and prepare35.py check the data. This script holds only what
# plan.json cannot: the Hugging Face revision of each GGUF file (the runtime block
# refuses other fields), the tokenizer file hash and the uv version.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXP="$(cd "$HERE/.." && pwd)"
REPO="$(cd "$EXP/../.." && pwd)"
PLAN="$EXP/plan.json"
UV_VERSION="0.13.5"
INPUTS_TGZ="exp35-inputs.tgz"
DATA_ROOT="${EXP35_DATA_DIR:-$HOME/Development/DATA/omrs}"
GGUF_DIR="${SWEEP_GGUF_DIR:-$DATA_ROOT/benchmarks/gguf}"
SCRATCH="$HOME/exp35-local/setup"

usage() {
  cat <<'EOF'
Usage: bash prefreeze/pod_setup35.sh --commit <sha> --inputs <dir> [options] [--dry-run]

Prepares one RunPod RTX 4090 pod (Linux x86-64) for Experiment 35. Steps, in order:
  0. Check the inputs folder: exp35-inputs.tgz and its .sha256 file, copied from
     the Mac with scp (never through git: the repository is public).
  1. Check that `git rev-parse HEAD` equals --commit.
  2. Check that nvidia-smi lists exactly one RTX 4090 and host CUDA 12.8 or newer.
  3. Install uv (pinned version) if it is missing; uv sync --frozen --extra web
     --extra llamacpp; check that plan.json names the llama.cpp build OMRS installs.
  4. omrs llamacpp install --flavour cuda (the pinned CUDA build).
  5. Fetch each plan.json runtime model at its pinned revision into SWEEP_GGUF_DIR,
     then each reranker candidate of prefreeze/rerank_candidates.json at its
     revision (test inputs for the task 15.10 check, not pins). A file already
     there is kept when its SHA-256 matches; any other SHA-256 stops the script.
  6. Cache the Qwen3 tokenizer (arms.py model and revision) and check its SHA-256.
  7. Unpack the tarball into EXP35_DATA_DIR; check it with datasets35.py.
  8. Run prepare35.py per passage dataset; check each tree hash against plan.json.
  9. Build the Ragas venv from the locked `ragas` group (uv export, uv pip sync).
 10. Build the reference venv (torch extra) and check that torch sees the GPU.

Options:
  --commit <sha>        Required. The commit the pod must be on.
  --inputs <dir>        Required. Folder with exp35-inputs.tgz and its .sha256 file.
  --passages-dir <dir>  Default /workspace/passages (the stage lines use it).
  --ragas-venv <dir>    Default /workspace/ragas-venv (the stage lines use it).
  --ref-venv <dir>      Default $HOME/exp35-ref-venv (container disk).
  --dry-run             Print every step, URL and SHA-256. Download nothing, install
                        nothing, write nothing. Files already present are hashed.
  -h, --help            Show this help.

Environment: EXP35_DATA_DIR (default ~/Development/DATA/omrs), SWEEP_GGUF_DIR (default
<data>/benchmarks/gguf), HF_TOKEN (optional; never printed).
EOF
}

COMMIT="" INPUTS="" DRY_RUN=0 TGZ="" TGZ_SHA=""
PASSAGES="/workspace/passages" RAGAS_VENV="/workspace/ragas-venv" REF_VENV="$HOME/exp35-ref-venv"
while [ $# -gt 0 ]; do
  case "$1" in
    --commit|--inputs|--passages-dir|--ragas-venv|--ref-venv)
      [ $# -ge 2 ] || { usage >&2; exit 2; }
      case "$1" in
        --commit) COMMIT="$2" ;; --inputs) INPUTS="$2" ;; --passages-dir) PASSAGES="$2" ;;
        --ragas-venv) RAGAS_VENV="$2" ;; --ref-venv) REF_VENV="$2" ;;
      esac
      shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'pod_setup35: unknown argument: %s\n\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

PROBLEMS=0
say() { printf '%s\n' "$*"; }
step() { printf '\n== Step %s: %s\n' "$1" "$2"; }
die() { printf '\npod_setup35: STOP: %s\n' "$*" >&2; exit 1; }
# A dry run counts a problem and reports it at the end; a real run stops on it.
problem() {
  if [ "$DRY_RUN" -eq 1 ]; then PROBLEMS=$((PROBLEMS + 1)); printf '  PROBLEM: %s\n' "$*"
  else die "$*"; fi
}
run() {
  if [ "$DRY_RUN" -eq 1 ]; then say "  [dry-run] would run: $*"; else say "  \$ $*"; "$@"; fi
}
# Succeeds when the nvidia-smi listing ($1) holds exactly one GPU and it is an RTX 4090.
gpu_is_single_4090() {
  [ "$(printf '%s\n' "$1" | grep -c .)" -eq 1 ] && printf '%s\n' "$1" | grep -q 'RTX 4090'
}
# Succeeds when the host CUDA version ($1, from the nvidia-smi header) is 12.8 or newer.
cuda_at_least() {
  [ -n "$1" ] && printf '12.8\n%s\n' "$1" | sort -V -C
}

# --- Python helper: plan.json, hashes and downloads (huggingface_hub after uv sync) ---
read -r -d '' HELPER <<'PY' || true
import hashlib, json, sys
from pathlib import Path

REPO, EXP, CMD, ARGS = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
sys.path[:0] = [REPO, EXP]
# Hugging Face revision of each GGUF file (repository/file). plan.json gives the SHA-256.
REVISIONS = {
    "Qwen/Qwen3-Embedding-0.6B-GGUF/Qwen3-Embedding-0.6B-Q8_0.gguf":
        "370f27d7550e0def9b39c1f16d3fbaa13aa67728",  # gitleaks:allow (HF revision)
    "Qwen/Qwen3-Embedding-4B-GGUF/Qwen3-Embedding-4B-Q8_0.gguf":
        "f4602530db1d980e16da9d7d3a70294cf5c190be",  # gitleaks:allow (HF revision)
    "Qwen/Qwen3-Embedding-8B-GGUF/Qwen3-Embedding-8B-Q8_0.gguf":
        "69d0e58a13e463cd99a9b83e3f5fee7c10265fab",  # gitleaks:allow (HF revision)
    "ggml-org/Clef-Flash-GGUF/Clef-Flash-Q8_0.gguf":
        "a5a18a6e13bb36573a5f11385a1e7b9a0c868e9e",  # gitleaks:allow (HF revision)
}
# tokenizer.json at arms.TOKENIZER_REVISION (Experiment 48 plan.json frozen list).
TOKENIZER_SHA256 = "83cdf8c3a34f68862319cb1810ee7b1e2c0a44e0864ae930194ddb76bb7feb8d"

def fail(msg):
    print(msg, file=sys.stderr); sys.exit(1)

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def sha(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()

def url(repo, rev, name):
    return f"https://huggingface.co/{repo}/resolve/{rev}/{name}"

def datasets():
    import datasets35
    return datasets35

def guarded(fn, *args):
    try:
        return fn(*args)
    except datasets().DatasetError as error:
        fail(str(error))

if CMD == "sha":
    print(sha(ARGS[0]))
elif CMD == "models":
    missing = []
    for m in load(ARGS[0])["runtime"]["models"]:
        key = f"{m['repository']}/{m['file']}"
        if key not in REVISIONS:
            missing.append(key); continue
        rev = REVISIONS[key]
        print("\t".join([m["file"], m["repository"], rev, m["sha256"], url(m["repository"], rev, m["file"])]))
    if missing:
        fail("plan.json runtime models with no pinned revision in pod_setup35.sh: " + ", ".join(missing))
elif CMD == "candidates":
    # Reranker test inputs for the task 15.10 check; the file holds each revision.
    for c in load(ARGS[0])["candidates"]:
        m, rev = c["entry"], c["revision"]
        note = "candidate for the task 15.10 check, not pinned"
        print("\t".join([m["file"], m["repository"], rev, m["sha256"], url(m["repository"], rev, m["file"]), note]))
elif CMD == "build":
    from omrs.integrations.llamacpp_runtime import pins
    builds = sorted({m["build"] for m in load(ARGS[0])["runtime"]["models"]})
    if builds != [pins.LLAMA_BUILD]:
        fail(f"plan.json runtime builds are {builds}; this OMRS installs b{pins.LLAMA_BUILD}")
    print(pins.LLAMA_BUILD)
elif CMD == "fetch":
    from huggingface_hub import hf_hub_download
    repo, name, rev, folder, want = ARGS
    got = Path(hf_hub_download(repo_id=repo, filename=name, revision=rev, local_dir=Path(folder) / ".download"))
    found = sha(got)
    if found != want:
        got.unlink()
        fail(f"SHA-256 differs for the download of {name}\n    expected {want}\n    found    {found}")
    got.replace(Path(folder) / name)
elif CMD == "tokenizer":
    import arms
    model, rev = arms.TOKENIZER_MODEL, arms.TOKENIZER_REVISION
    print(f"  {model} tokenizer.json\n    url      {url(model, rev, 'tokenizer.json')}")
    print(f"    sha256   {TOKENIZER_SHA256}")
    if ARGS[:1] != ["--dry-run"]:
        from huggingface_hub import hf_hub_download, try_to_load_from_cache
        cached = try_to_load_from_cache(repo_id=model, filename="tokenizer.json", revision=rev)
        path = cached if isinstance(cached, str) else hf_hub_download(model, "tokenizer.json", revision=rev)
        found = sha(path)
        if found != TOKENIZER_SHA256:
            fail(f"SHA-256 differs: {path}\n    expected {TOKENIZER_SHA256}\n    found    {found}")
        print(f"    SHA-256 matches: {path}")
elif CMD == "data":
    ds, plan = datasets(), load(ARGS[0])
    root = ds.data_root()
    for name in ("financebench", "freshstack", "bioasq"):
        guarded(ds.verify_inputs, root, ds.input_hashes(name, plan))
    manifest = next(k for k in ds.EXPECTED_SHA256["financebench"] if k.endswith("PDFS_MANIFEST.json"))
    pdfs = [(root / manifest).parent / "pdfs" / f"{n}.pdf" for n in sorted(load(root / manifest)["files"])]
    guarded(ds.verify_inputs, root, ds.pdf_hashes(root, pdfs))
    print(f"  FinanceBench ({len(pdfs)} PDFs), FreshStack and BioASQ inputs match their pins")
    rows = guarded(ds.freshstack_corpus, root, guarded(ds.freshstack_pin, plan))
    print(f"  FreshStack corpus: {len(rows)} rows at the pinned revision")
    legal = list(((plan["pins"]["datasets"].get("legal") or {}).get("sha256")) or {})
    if any((root / f).exists() for f in legal):
        guarded(ds.verify_inputs, root, guarded(ds.input_hashes, "legal", plan))
        print("  Legal RAG Bench inputs match their pins")
    else:
        print("  Legal RAG Bench: not in the inputs (this session leaves it out, decision D1)")
elif CMD == "passage-datasets":
    plan, root = load(ARGS[0]), datasets().data_root()
    legal = list(((plan["pins"]["datasets"].get("legal") or {}).get("sha256")) or {})
    print(" ".join(["freshstack", "bioasq"] + (["legal"] if any((root / f).exists() for f in legal) else [])))
elif CMD == "passages-pin":
    import arms
    keys = ("pins", "datasets", ARGS[1], "passages_tree_sha256")
    print(guarded(lambda: arms.pinned(load(ARGS[0]), *keys, error=datasets().DatasetError)))
elif CMD == "passages-check":
    guarded(datasets().check_passages, Path(ARGS[0]), ARGS[1], load(ARGS[2]))
else:
    fail(f"unknown helper command {CMD}")
PY

PY=""
pick_python() {
  if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then PY="python3"
  else die "no Python found. Install python3, then run again."; fi
}
py() { PYTHONDONTWRITEBYTECODE=1 "$PY" -u -c "$HELPER" "$REPO" "$EXP" "$@"; }

# check_sha <path> <expected> <what to do>: stop (dry run: count) on a missing file or another hash.
check_sha() {
  local path="$1" expected="$2" found
  if [ ! -f "$path" ]; then problem "missing file: $path (expected SHA-256 $expected)"; return 0; fi
  found="$(py sha "$path")"
  if [ "$found" = "$expected" ]; then say "    SHA-256 matches: $path"; return 0; fi
  problem "SHA-256 differs: $path
    expected $expected
    found    $found
    $3"
}

# --- Step 0: preflight and the inputs tarball ---
cd "$REPO"
[ -f "$PLAN" ] || die "$PLAN not found; run this script from a checkout of the repository."
[ -n "$COMMIT" ] || { usage >&2; die "--commit <sha> is required."; }
if [ "$DRY_RUN" -eq 0 ] && [ "$(uname -s)" != "Linux" ]; then
  die "a real run installs into $HOME and /workspace, so it runs only on the Linux pod. Use --dry-run here."
fi
pick_python
say "pod_setup35: Experiment 35 pod preparation$([ "$DRY_RUN" -eq 1 ] && printf ' (DRY RUN: nothing is downloaded, installed or written)')"
say "  repository  $REPO"
say "  data root   $DATA_ROOT"
say "  GGUF folder $GGUF_DIR"
for tool in git curl tar; do
  command -v "$tool" >/dev/null 2>&1 || problem "$tool is not installed (install it, then run again)."
done
if [ "$DRY_RUN" -eq 0 ] && ! command -v nvidia-smi >/dev/null 2>&1; then
  die "nvidia-smi not found: this pod has no NVIDIA driver. Delete it and create an RTX 4090 pod."
fi
if [ -n "${HF_TOKEN:-}" ]; then say "  HF_TOKEN    set (value not shown)"
else say "  HF_TOKEN    not set (the pinned repositories are public)"; fi
step 0 "check the inputs tarball copied from the Mac"
TGZ="$INPUTS/$INPUTS_TGZ"
if [ -z "$INPUTS" ] || [ ! -f "$TGZ" ] || [ ! -f "$TGZ.sha256" ]; then
  problem "the inputs folder ${INPUTS:-<not given>} must hold $INPUTS_TGZ and $INPUTS_TGZ.sha256 (copy them from the Mac with scp)."
else
  TGZ_SHA="$(awk '{print $1; exit}' "$TGZ.sha256")"
  say "  $TGZ"
  check_sha "$TGZ" "$TGZ_SHA" "Copy it from the Mac again with scp (never through git)."
fi

# --- Step 1: commit ---
step 1 "check the commit"
HEAD_SHA="$(git rev-parse HEAD)"
say "  HEAD $HEAD_SHA, expected $COMMIT"
[ "$HEAD_SHA" = "$(git rev-parse --verify --quiet "$COMMIT^{commit}" || printf '%s' "$COMMIT")" ] \
  || die "HEAD is $HEAD_SHA, not $COMMIT. Check out the session commit and run again."

# --- Step 2: GPU and host CUDA ---
step 2 "check the GPU and the host CUDA version"
if [ "$DRY_RUN" -eq 1 ]; then
  say "  [dry-run] would run: nvidia-smi --query-gpu=name,memory.total --format=csv,noheader"
  say "  [dry-run] would read the CUDA version from the nvidia-smi header (12.8 or newer)"
else
  GPUS="$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader)" || die "nvidia-smi failed."
  CUDA="$(nvidia-smi 2>/dev/null | sed -n 's/.*CUDA Version: *\([0-9][0-9.]*\).*/\1/p' | head -n 1 || true)"
  gpu_is_single_4090 "$GPUS" || die "nvidia-smi lists: $GPUS. Experiment 35 runs on exactly one RTX 4090. Delete this pod."
  cuda_at_least "$CUDA" || die "host CUDA is ${CUDA:-unknown}; the pinned llama.cpp CUDA build needs 12.8 or newer. Delete this pod."
  say "  GPU $GPUS, host CUDA $CUDA"
fi

# --- Step 3: uv and the locked environment ---
step 3 "install the locked Python environment"
if ! command -v uv >/dev/null 2>&1; then
  run bash -c "curl -LsSf https://astral.sh/uv/$UV_VERSION/install.sh | env UV_NO_MODIFY_PATH=1 sh"
  export PATH="$HOME/.local/bin:$PATH"
fi
[ "$DRY_RUN" -eq 1 ] || say "  $(uv --version)"
run uv sync --frozen --extra web --extra llamacpp || die "uv sync failed (message above)."
pick_python
if [ "$DRY_RUN" -eq 1 ] && ! "$PY" -c 'import omrs' 2>/dev/null; then
  say "  [dry-run] would check the plan.json llama.cpp build against OMRS after uv sync"
elif BUILD="$(py build "$PLAN")"; then say "  plan.json and OMRS both pin llama.cpp b$BUILD"
else problem "plan.json and OMRS name different llama.cpp builds (message above)."; fi

# --- Step 4: pinned llama.cpp CUDA build ---
# LLAMACPP_ROUTER_SERVER=external stops the install from fetching the shipped model list.
step 4 "install the pinned llama.cpp CUDA build"
[ "$DRY_RUN" -eq 1 ] || mkdir -p "$SCRATCH"
run env OMRS_CONFIG_DIR="$SCRATCH/config" OMRS_STATE_DIR="$SCRATCH/state" LLAMACPP_ROUTER_SERVER=external \
  uv run --no-sync omrs llamacpp install --flavour cuda \
  || die "omrs llamacpp install --flavour cuda failed. Read the reason above (for example cuda-device-missing)."

# --- Step 5: GGUF files ---
step 5 "fetch the plan.json GGUF files and the reranker candidates at their pinned revisions"
ROWS="$(py models "$PLAN")" || problem "a plan.json runtime model has no pinned revision (named above)."
CANDIDATES="$(py candidates "$HERE/rerank_candidates.json")" \
  || problem "prefreeze/rerank_candidates.json cannot be read (message above)."
[ "$DRY_RUN" -eq 1 ] || mkdir -p "$GGUF_DIR"
while IFS=$'\t' read -r file repo rev sha url note <&3; do
  [ -n "$file" ] || continue
  say "  $file"; [ -z "$note" ] || say "    $note"; say "    url      $url"; say "    sha256   $sha"
  if [ -f "$GGUF_DIR/$file" ]; then
    check_sha "$GGUF_DIR/$file" "$sha" "Delete the file and run the script again."; continue
  fi
  if [ "$DRY_RUN" -eq 1 ]; then say "    [dry-run] would download it, check the SHA-256, then move it into place"; continue; fi
  py fetch "$repo" "$file" "$rev" "$GGUF_DIR" "$sha" || die "download or SHA-256 check failed: $url (message above)."
  say "    SHA-256 matches: $GGUF_DIR/$file"
done 3<<<"$ROWS
$CANDIDATES"

# --- Step 6: tokenizer ---
step 6 "cache the Qwen3 tokenizer at its pinned revision"
if [ "$DRY_RUN" -eq 1 ]; then py tokenizer --dry-run
else py tokenizer || die "the tokenizer download or its SHA-256 check failed (message above)."; fi

# --- Step 7: data ---
step 7 "unpack the Experiment 35 data and check it against the pins"
MARK="$DATA_ROOT/.exp35-inputs.sha256"
if [ "$DRY_RUN" -eq 1 ]; then
  say "  [dry-run] would unpack $TGZ into $DATA_ROOT (skipped when $MARK holds its SHA-256)"
  say "  [dry-run] would check FinanceBench, FreshStack, BioASQ (and Legal RAG Bench if present) with datasets35.py"
else
  if [ -f "$MARK" ] && [ "$(cat "$MARK")" = "$TGZ_SHA" ]; then say "  already unpacked ($MARK)"
  else
    mkdir -p "$DATA_ROOT"
    run tar -xzf "$TGZ" -C "$DATA_ROOT" --no-same-owner || die "tar could not unpack $TGZ."
    printf '%s\n' "$TGZ_SHA" >"$MARK"
  fi
  EXP35_DATA_DIR="$DATA_ROOT" py data "$PLAN" \
    || die "the Experiment 35 data does not match its pins (message above). Rebuild the tarball on the Mac."
fi

# --- Step 8: passages ---
step 8 "prepare the passage files and check their tree hashes"
if [ "$DRY_RUN" -eq 1 ]; then DATASETS="freshstack bioasq"; say "  (Legal RAG Bench only when the inputs hold it)"
else DATASETS="$(EXP35_DATA_DIR="$DATA_ROOT" py passage-datasets "$PLAN")"; fi
for ds in $DATASETS; do
  say "  $ds -> $PASSAGES/$ds"
  if pin="$(py passages-pin "$PLAN" "$ds" 2>&1)"; then say "    plan pin $pin"; else problem "$pin"; fi
  if [ "$DRY_RUN" -eq 0 ] && py passages-check "$PASSAGES" "$ds" "$PLAN" >/dev/null 2>&1; then
    say "    already prepared; the tree hash matches the pin"; continue
  fi
  run env EXP35_DATA_DIR="$DATA_ROOT" uv run --no-sync python "$EXP/prepare35.py" --dataset "$ds" \
    --passages-dir "$PASSAGES" || die "prepare35.py failed for $ds (message above)."
  [ "$DRY_RUN" -eq 1 ] || py passages-check "$PASSAGES" "$ds" "$PLAN" \
    || die "the $ds passage tree differs from plan.json (message above)."
done

# --- Step 9: Ragas venv from the locked `ragas` group ---
step 9 "build the Ragas environment from the locked ragas group"
REQ="$SCRATCH/ragas-requirements.txt"
PYVER="$("$PY" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])')"
if [ "$DRY_RUN" -eq 1 ] || [ ! -x "$RAGAS_VENV/bin/python" ]; then
  run uv venv "$RAGAS_VENV" --python "$PYVER" || die "uv venv failed for $RAGAS_VENV."
fi
run uv export --frozen --only-group ragas --no-emit-project --quiet --output-file "$REQ" \
  || die "uv export of the ragas group failed (message above)."
run uv pip sync --python "$RAGAS_VENV/bin/python" --require-hashes "$REQ" \
  || die "uv pip sync into $RAGAS_VENV failed (message above)."
if [ "$DRY_RUN" -eq 0 ]; then
  want="$(sed -n 's/^ragas==\([^ ;\\]*\).*/\1/p' "$REQ" | head -n 1)"
  got="$("$RAGAS_VENV/bin/python" -c 'import ragas; print(ragas.__version__)')" || die "ragas does not import in $RAGAS_VENV."
  [ "$got" = "$want" ] || die "$RAGAS_VENV holds ragas $got; the lock pins $want."
  say "  ragas $got in $RAGAS_VENV (Python $PYVER)"
fi

# --- Step 10: reference venv (reranker check reference, task 15.10) ---
step 10 "build the reference environment (torch extra) and check it sees the GPU"
run env UV_PROJECT_ENVIRONMENT="$REF_VENV" uv sync --frozen --no-dev --extra torch \
  || die "uv sync of the reference environment failed (message above)."
if [ "$DRY_RUN" -eq 0 ]; then
  "$REF_VENV/bin/python" -c 'import sys, torch; print("  torch", torch.__version__, "CUDA", torch.version.cuda); sys.exit(0 if torch.cuda.is_available() else 1)' \
    || die "torch in $REF_VENV sees no CUDA device; the reranker reference needs the GPU."
fi

say ""
if [ "$DRY_RUN" -eq 1 ]; then
  if [ "$PROBLEMS" -gt 0 ]; then
    say "pod_setup35: DRY RUN found $PROBLEMS problem(s), listed as PROBLEM above. A real run would stop at the first one."
    exit 1
  fi
  say "pod_setup35: DRY RUN finished with no problem."
else
  say "pod_setup35: the pod is ready. Export these before the stage lines:"
  say "  export SWEEP_GGUF_DIR=\"$GGUF_DIR\" EXP35_DATA_DIR=\"$DATA_ROOT\""
  say "  passages $PASSAGES, Ragas venv $RAGAS_VENV, reference venv $REF_VENV"
fi
