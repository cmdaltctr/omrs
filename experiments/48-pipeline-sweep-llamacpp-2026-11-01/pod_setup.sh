#!/usr/bin/env bash
# Prepare one RunPod RTX 4090 pod for Experiment 48 (change pipeline-sweep-llamacpp,
# task 3.6, design D9). Run it from the repository root on the pod.
#
# plan.json is the source of every frozen SHA-256 and of the GGUF SHA-256.
# pod_inputs.json says where each input comes from and where it goes on the pod.
# This script copies no hash into itself.
set -euo pipefail

EXP_REL="experiments/48-pipeline-sweep-llamacpp-2026-11-01"
PLAN="$EXP_REL/plan.json"
POD_INPUTS="$EXP_REL/pod_inputs.json"
# The runners read Path.home() / "Development/DATA/omrs", so the pod uses the same path.
DATA_ROOT="$HOME/Development/DATA/omrs"
# Scratch settings and state for the install step (design D2: both inside output/).
SCRATCH="$EXP_REL/output/pod-setup"

usage() {
  cat <<'EOF'
Usage: experiments/48-pipeline-sweep-llamacpp-2026-11-01/pod_setup.sh --commit <sha> --inputs <dir> [--dry-run]

Prepares one RunPod RTX 4090 pod (Linux x86-64) for Experiment 48. Run it from the
repository root. Steps, in order:
  1. Check that `git rev-parse HEAD` equals --commit. Stop if not.
  2. uv sync --frozen --extra web --extra llamacpp
  3. omrs llamacpp install --flavour cuda (pinned b11941 CUDA build). Stop on failure.
  4. Check that nvidia-smi lists exactly one GPU and that it is an RTX 4090.
     Print its name and memory.
  5. Fetch the four GGUF files at their pinned revisions into SWEEP_GGUF_DIR.
     Check each SHA-256 against plan.json.
  6. Place the other inputs: Experiment 3 corpus and Experiment 2 ground truth
     (from the repository), FinanceBench (Hugging Face and GitHub at pinned
     revisions, then prepare_financebench.py), BioASQ (Hugging Face, pinned
     revision), the embedding tokenizer (Hugging Face cache), and the inputs
     from the --inputs folder.
  7. Check every input in the plan.json "frozen" list. Stop on any difference.

Options:
  --commit <sha>  Required. The commit the pod must be on.
  --inputs <dir>  Folder with the inputs that exist only on the measurement Mac.
                  Required for a real run.
  --dry-run       Print every step, URL and expected SHA-256. Download nothing,
                  install nothing, write nothing. Hashes the local files it can
                  read, to preview step 7.
  -h, --help      Show this help.

Inputs that only exist on the Mac (copy them with runpodctl):
  On the Mac:
    mkdir -p ~/pod-inputs/freshstack ~/pod-inputs/financebench
    cp ~/Development/DATA/omrs/experiments/freshstack-corpus/langchain_manifest.jsonl ~/pod-inputs/freshstack/
    cp ~/Development/DATA/omrs/benchmarks/financebench/PDFS_MANIFEST.json ~/pod-inputs/financebench/
    runpodctl send ~/pod-inputs        # prints a one-time code
  On the pod:
    cd /workspace && runpodctl receive <code>   # gives /workspace/pod-inputs
  Then pass --inputs /workspace/pod-inputs.

Environment:
  HF_TOKEN        Optional. huggingface_hub reads it. The script never prints it.
  SWEEP_GGUF_DIR  Optional. GGUF folder. Default: the gguf_dir in pod_inputs.json.
EOF
}

COMMIT=""
INPUTS=""
DRY_RUN=0
while [ $# -gt 0 ]; do
  case "$1" in
    --commit) [ $# -ge 2 ] || { usage >&2; exit 2; }; COMMIT="$2"; shift 2 ;;
    --inputs) [ $# -ge 2 ] || { usage >&2; exit 2; }; INPUTS="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'pod_setup: unknown argument: %s\n\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

PROBLEMS=0
say() { printf '%s\n' "$*"; }
step() { printf '\n== Step %s: %s\n' "$1" "$2"; }
die() { printf '\npod_setup: STOP: %s\n' "$*" >&2; exit 1; }
# In a dry run a problem is counted and reported at the end; in a real run it stops.
problem() {
  if [ "$DRY_RUN" -eq 1 ]; then
    PROBLEMS=$((PROBLEMS + 1)); printf '  PROBLEM: %s\n' "$*"
  else
    die "$*"
  fi
}
run() {
  if [ "$DRY_RUN" -eq 1 ]; then say "  [dry-run] would run: $*"; else say "  \$ $*"; "$@"; fi
}
# Succeeds when the nvidia-smi listing ($1) holds exactly one GPU and it is an RTX 4090.
gpu_is_single_4090() {
  [ "$(printf '%s\n' "$1" | grep -c .)" -eq 1 ] && printf '%s\n' "$1" | grep -q 'RTX 4090'
}

# --- Python helper (stdlib, plus huggingface_hub for downloads and the cache) ---
read -r -d '' HELPER <<'PY' || true
import hashlib, json, sys
from pathlib import Path

def fail(msg):
    print(f"pod_setup helper: {msg}", file=sys.stderr); sys.exit(1)

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()

def place(to, exp, data):
    for prefix, base in (("EXP/", exp), ("DATA/", data), ("REPO/", ".")):
        if to.startswith(prefix):
            return Path(base) / to[len(prefix):]
    fail(f"path {to!r} has no EXP/, DATA/ or REPO/ prefix")

def resolve(plan, pods, ident):
    entry = next((e for e in pods["inputs"] if e["id"] == ident), None)
    if entry is None:
        fail(f"pod_inputs.json has no input {ident!r}")
    out = dict(entry)
    if "frozen" in entry:
        frozen = {f["name"]: f for f in plan["frozen"]}
        if entry["frozen"] not in frozen:
            fail(f"plan.json frozen list has no {entry['frozen']!r}")
        out.setdefault("revision", frozen[entry["frozen"]].get("revision", ""))
        if entry.get("frozen_kind") != "id-list":
            out.setdefault("sha256", frozen[entry["frozen"]]["sha256"])
    rev, repo = out.get("revision", ""), out.get("repository", "")
    if out["how"] in ("hf-dataset", "hf-cache", "github") and not rev:
        fail(f"input {ident!r} has no pinned revision")
    if out["how"] == "hf-dataset":
        out["url"] = f"https://huggingface.co/datasets/{repo}/resolve/{rev}/{out['file']}"
    elif out["how"] == "hf-cache":
        out["url"] = f"https://huggingface.co/{repo}/resolve/{rev}/{out['file']}"
    elif out["how"] == "github":
        out["url"] = f"https://raw.githubusercontent.com/{repo}/{rev}/{out['folder']}/<name>.pdf"
    return out

def frozen_check(plan, pods, exp, data, report):
    bad = 0
    for item in plan["frozen"]:
        name, expected = item["name"], item["sha256"]
        entry = next((e for e in pods["inputs"] if e.get("frozen") == name), None)
        entry = entry or next((e for e in pods["inputs"] if "frozen_prefix" in e
                               and name.startswith(e["frozen_prefix"])), None)
        path, found, note = None, "", ""
        if entry is None:
            note = "no pod path in pod_inputs.json"
        elif entry["how"] == "hf-cache":
            try:
                from huggingface_hub import try_to_load_from_cache
            except ImportError:
                note = "huggingface_hub not installed yet (step 2)"
            else:
                cached = try_to_load_from_cache(repo_id=entry["repository"], filename=entry["file"],
                                                revision=item["revision"])
                path = Path(cached) if isinstance(cached, str) else None
                note = "" if path else "not in the Hugging Face cache"
        elif "frozen_prefix" in entry:
            path = place(entry["to"], exp, data) / name[len(entry["frozen_prefix"]):]
        else:
            path = place(entry["to"], exp, data)
        if path is not None and not path.is_file():
            note, path = f"missing: {path}", None
        if path is not None and entry.get("frozen_kind") == "id-list":
            ids = sorted(json.loads(line)["freshstack_id"]
                         for line in path.read_text(encoding="utf-8").split("\n") if line.strip())
            found = hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest()
            if "documents" in item and len(ids) != item["documents"]:
                note = f"{len(ids)} documents, plan.json records {item['documents']}"
        elif path is not None:
            found = sha256_file(path)
        status = "MATCH" if found == expected and not note else ("MISSING" if not found else "DIFFERS")
        bad += status != "MATCH"
        print(f"  {status:<8} {name}\n           expected {expected}\n           found    {found or '-'}")
        print(f"           path     {path or '-'}" + (f"\n           note     {note}" if note else ""))
    print(f"  {len(plan['frozen']) - bad} of {len(plan['frozen'])} frozen inputs match")
    if bad and not report:
        sys.exit(1)

def main(cmd, args):
    if cmd == "sha":
        print(sha256_file(args[0]))
    elif cmd == "field":
        print(resolve(load(args[0]), load(args[1]), args[2]).get(args[3], ""))
    elif cmd == "pod-field":
        print(load(args[0])[args[1]])
    elif cmd == "operator-ids":
        print("\n".join(e["id"] for e in load(args[0])["inputs"] if e["how"] == "operator"))
    elif cmd == "place":
        print(place(args[0], args[1], args[2]))
    elif cmd == "gguf":
        plan, pods = load(args[0]), load(args[1])
        revs = {g["file"]: g for g in pods["gguf"]}
        models = plan["runtime"]["models"]
        if {m["file"] for m in models} != set(revs):
            fail("pod_inputs.json gguf list does not match the plan.json runtime models")
        for m in models:
            g = revs[m["file"]]
            url = f"https://huggingface.co/{m['repository']}/resolve/{g['revision']}/{m['file']}"
            print("\t".join([m["file"], m["repository"], g["revision"], m["sha256"], str(g["bytes"]), url]))
    elif cmd == "pdfs":
        manifest, repo, rev, folder = load(args[0]), args[1], args[2], args[3]
        if (manifest.get("repository"), manifest.get("commit")) != (repo, rev):
            fail(f"PDFS_MANIFEST.json names {manifest.get('repository')}@{manifest.get('commit')}, "
                 f"pod_inputs.json names {repo}@{rev}")
        for name, entry in sorted(manifest["files"].items()):
            url = f"https://raw.githubusercontent.com/{repo}/{rev}/{folder}/{name}.pdf"
            print("\t".join([name, entry["sha256"], str(entry["bytes"]), url]))
    elif cmd == "hf-download":
        from huggingface_hub import hf_hub_download
        repo_type, repo, filename, rev, dest = args
        if dest == "-":
            print(hf_hub_download(repo_id=repo, filename=filename, revision=rev, repo_type=repo_type))
            return
        if not dest.endswith(filename):
            fail(f"{dest} does not end with {filename}")
        local_dir = dest[: -len(filename)] or "."
        print(hf_hub_download(repo_id=repo, filename=filename, revision=rev, repo_type=repo_type,
                              local_dir=local_dir))
    elif cmd == "frozen-check":
        frozen_check(load(args[0]), load(args[1]), args[2], args[3], report="--report" in args)
    else:
        fail(f"unknown command {cmd}")

main(sys.argv[1], sys.argv[2:])
PY

PY=""
pick_python() {
  if [ -x .venv/bin/python ]; then PY=".venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then PY="python3"
  else die "no Python found. Install python3 or run step 2 (uv sync) first."
  fi
}
py() { PYTHONDONTWRITEBYTECODE=1 "$PY" -u -c "$HELPER" "$@"; }
field() { py field "$PLAN" "$POD_INPUTS" "$1" "$2"; }
placed() { py place "$(field "$1" to)" "$EXP_REL" "$DATA_ROOT"; }

# Stop (or, in a dry run, count) when a file's SHA-256 differs; name the file and both hashes.
check_sha() {
  local path="$1" expected="$2" found
  if [ ! -f "$path" ]; then problem "missing file: $path (expected SHA-256 $expected)"; return 0; fi
  found="$(py sha "$path")"
  if [ "$found" = "$expected" ]; then say "    SHA-256 matches: $path"; return 0; fi
  problem "SHA-256 differs: $path
    expected $expected
    found    $found
    Delete the file and run the script again."
}

# Download $1 (URL) to $2 through a .part file; check it before the rename.
fetch_url() {
  local url="$1" dest="$2" expected="$3" found
  mkdir -p "$(dirname "$dest")"
  curl -fsSL --retry 3 -o "$dest.part" "$url" || die "download failed: $url"
  found="$(py sha "$dest.part")"
  [ "$found" = "$expected" ] || die "SHA-256 differs for $url
    expected $expected
    found    $found"
  mv "$dest.part" "$dest"
}

nearest_dir() { local d="$1"; while [ ! -d "$d" ]; do d="$(dirname "$d")"; done; printf '%s' "$d"; }
file_bytes() { if [ -f "$1" ]; then wc -c <"$1" | tr -d ' '; else printf '0'; fi; }

# --- Preflight ---
[ -f "$PLAN" ] && [ -f "$POD_INPUTS" ] || die "run this from the repository root ($PLAN not found)."
[ -n "$COMMIT" ] || { usage >&2; die "--commit <sha> is required."; }
if [ "$DRY_RUN" -eq 0 ]; then
  [ "$(uname -s)" = "Linux" ] || die "a real run writes into $DATA_ROOT, so it runs only on the Linux pod. Use --dry-run here."
  [ -n "$INPUTS" ] || die "--inputs <dir> is required for a real run (see --help)."
fi
pick_python
say "pod_setup: Experiment 48 pod preparation$([ "$DRY_RUN" -eq 1 ] && printf ' (DRY RUN: nothing is downloaded, installed or written)')"
say "  repository root  $(pwd -P)"
say "  data root        $DATA_ROOT"
say "  python helper    $PY"
# ps: OMRS identifies its own router process with `ps -o command=` (procps on Debian/Ubuntu).
for tool in git uv curl ps; do
  command -v "$tool" >/dev/null 2>&1 || problem "$tool is not installed (install it, then run again)."
done
if [ -n "${HF_TOKEN:-}" ]; then say "  HF_TOKEN         set (value not shown)"
else say "  HF_TOKEN         not set (the pinned repositories are public, so none is needed)"; fi

say "  inputs folder    ${INPUTS:-<not given>}"
if [ -z "$INPUTS" ] || [ ! -d "$INPUTS" ]; then
  problem "inputs folder ${INPUTS:-<not given>} does not exist. Copy the Mac-only inputs with runpodctl (see --help)."
fi
for ident in $(py operator-ids "$POD_INPUTS"); do
  src="$INPUTS/$(field "$ident" from)"
  say "  operator input   $ident: $src"
  say "    Mac source $(field "$ident" mac_source)"
  say "    sha256     $(field "$ident" sha256)"
  if [ -n "$INPUTS" ] && [ -d "$INPUTS" ]; then check_sha "$src" "$(field "$ident" sha256)"; fi
done

# --- Step 1: commit ---
step 1 "check the commit"
HEAD_SHA="$(git rev-parse HEAD)"
say "  HEAD     $HEAD_SHA"
say "  expected $COMMIT"
[ "$HEAD_SHA" = "$(git rev-parse --verify --quiet "$COMMIT^{commit}" || printf '%s' "$COMMIT")" ] \
  || die "HEAD is $HEAD_SHA, not $COMMIT. Check out the frozen commit and run again."
say "  commit matches"

# --- Step 2: Python environment ---
step 2 "install the Python environment"
run uv sync --frozen --extra web --extra llamacpp
pick_python

# --- Step 3: pinned llama.cpp CUDA build ---
# LLAMACPP_ROUTER_SERVER=external stops the install from fetching the shipped model
# list at the current Hugging Face revision; step 5 fetches the pinned GGUF files.
step 3 "install the pinned llama.cpp CUDA build"
run env OMRS_CONFIG_DIR="$SCRATCH/config" OMRS_STATE_DIR="$SCRATCH/state" LLAMACPP_ROUTER_SERVER=external \
  uv run --no-sync omrs llamacpp install --flavour cuda \
  || die "omrs llamacpp install --flavour cuda failed. Read the reason above (for example cuda-device-missing)."

# --- Step 4: GPU ---
step 4 "check the GPU"
if [ "$DRY_RUN" -eq 1 ]; then
  say "  [dry-run] would run: nvidia-smi --query-gpu=name,memory.total --format=csv,noheader"
else
  command -v nvidia-smi >/dev/null 2>&1 || die "nvidia-smi not found. This pod has no NVIDIA driver; pick an RTX 4090 pod."
  GPUS="$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader)" || die "nvidia-smi failed."
  [ -n "$GPUS" ] || die "nvidia-smi lists no GPU."
  gpu_is_single_4090 "$GPUS" || die "nvidia-smi lists: $GPUS. The plan measures one RTX 4090 pod (amendment A3); pick that pod class."
  say "  GPU: $GPUS"
fi

# --- Step 5: GGUF files ---
step 5 "fetch the four GGUF files"
SWEEP_GGUF_DIR="${SWEEP_GGUF_DIR:-$(py place "$(py pod-field "$POD_INPUTS" gguf_dir)" "$EXP_REL" "$DATA_ROOT")}"
export SWEEP_GGUF_DIR
say "  folder: $SWEEP_GGUF_DIR"
say "  operator: export SWEEP_GGUF_DIR=\"$SWEEP_GGUF_DIR\""
GGUF_ROWS="$(py gguf "$PLAN" "$POD_INPUTS")"
missing_bytes=0
while IFS=$'\t' read -r file repo rev sha bytes url <&3; do
  [ "$(file_bytes "$SWEEP_GGUF_DIR/$file")" = "$bytes" ] || missing_bytes=$((missing_bytes + bytes))
done 3<<<"$GGUF_ROWS"
free_kib="$(df -Pk "$(nearest_dir "$SWEEP_GGUF_DIR")" | awk 'NR==2 {print $4}')"
need_kib=$((missing_bytes / 1024 + 1048576))
say "  disk: need $((need_kib / 1048576)) GiB (GGUF still to fetch plus 1 GiB for the rest), free $((free_kib / 1048576)) GiB"
[ "$free_kib" -ge "$need_kib" ] || problem "not enough disk space for the GGUF files. Pick a pod with a larger container disk."
while IFS=$'\t' read -r file repo rev sha bytes url <&3; do
  dest="$SWEEP_GGUF_DIR/$file"
  say "  $file"
  say "    url      $url"
  say "    sha256   $sha"
  say "    bytes    $bytes"
  if [ "$DRY_RUN" -eq 1 ]; then continue; fi
  if [ -f "$dest" ]; then check_sha "$dest" "$sha"; continue; fi
  py hf-download model "$repo" "$file" "$rev" "$dest" >/dev/null || die "download failed: $url"
  check_sha "$dest" "$sha"
done 3<<<"$GGUF_ROWS"

# --- Step 6: other inputs ---
step 6 "place the other inputs"
for ident in exp3-corpus exp2-ground-truth; do
  src="$(py place "$(field "$ident" from)" "$EXP_REL" "$DATA_ROOT")"
  dst="$(placed "$ident")"
  say "  $ident: copy $src -> $dst"
  if [ -d "$src" ]; then run mkdir -p "$dst"; run cp -pR "$src"/. "$dst"/
  else run cp -p "$src" "$dst"; fi
done

for ident in $(py operator-ids "$POD_INPUTS"); do
  dst="$(placed "$ident")"
  say "  $ident: copy $INPUTS/$(field "$ident" from) -> $dst"
  if [ "$DRY_RUN" -eq 0 ]; then
    mkdir -p "$(dirname "$dst")"; cp -p "$INPUTS/$(field "$ident" from)" "$dst"
    check_sha "$dst" "$(field "$ident" sha256)"
  fi
done

for ident in financebench-questions bioasq-corpus embedding-tokenizer; do
  how="$(field "$ident" how)"
  url="$(field "$ident" url)"
  sha="$(field "$ident" sha256)"
  if [ "$how" = "hf-cache" ]; then dst="-"; else dst="$(placed "$ident")"; fi
  say "  $ident ($(field "$ident" repository) @ $(field "$ident" revision))"
  say "    url      $url"
  say "    sha256   $sha"
  say "    to       $(field "$ident" to)"
  if [ "$DRY_RUN" -eq 1 ]; then continue; fi
  repo_type="dataset"; [ "$how" = "hf-cache" ] && repo_type="model"
  got="$(py hf-download "$repo_type" "$(field "$ident" repository)" "$(field "$ident" file)" \
    "$(field "$ident" revision)" "$dst")" || die "download failed: $url"
  check_sha "$got" "$sha"
done

# FinanceBench PDFs: names and SHA-256 come from PDFS_MANIFEST.json (checked above).
PDF_REPO="$(field financebench-pdfs repository)"
PDF_REV="$(field financebench-pdfs revision)"
PDF_DIR="$(placed financebench-pdfs)"
PDF_MANIFEST="$(placed financebench-pdfs-manifest)"
say "  financebench-pdfs ($PDF_REPO @ $PDF_REV) -> $PDF_DIR"
if [ "$DRY_RUN" -eq 1 ] && [ -n "$INPUTS" ] && [ -f "$INPUTS/$(field financebench-pdfs-manifest from)" ]; then
  PDF_MANIFEST="$INPUTS/$(field financebench-pdfs-manifest from)"
fi
if [ -f "$PDF_MANIFEST" ]; then
  say "    names and SHA-256 from $PDF_MANIFEST"
  PDF_ROWS="$(py pdfs "$PDF_MANIFEST" "$PDF_REPO" "$PDF_REV" "$(field financebench-pdfs folder)")"
  while IFS=$'\t' read -r name sha bytes url <&3; do
    say "    $url  sha256 $sha"
    [ "$DRY_RUN" -eq 1 ] && continue
    if [ -f "$PDF_DIR/$name.pdf" ]; then check_sha "$PDF_DIR/$name.pdf" "$sha"
    else fetch_url "$url" "$PDF_DIR/$name.pdf" "$sha"; fi
  done 3<<<"$PDF_ROWS"
  say "    $(printf '%s\n' "$PDF_ROWS" | wc -l | tr -d ' ') PDFs"
else
  problem "PDFS_MANIFEST.json not found (in the inputs folder or at $PDF_MANIFEST), so the PDF list cannot be printed."
  say "    url pattern $(field financebench-pdfs url)"
fi

say "  financebench-selection: prepare_financebench.py copies the 5 frozen PDFs into $EXP_REL/output/financebench/pdfs"
if [ "$DRY_RUN" -eq 1 ]; then
  say "  [dry-run] would run: (cd $EXP_REL && uv run --no-sync python prepare_financebench.py)"
else
  (cd "$EXP_REL" && uv run --no-sync python prepare_financebench.py) || die "prepare_financebench.py failed."
fi

# --- Step 7: frozen-input hash check ---
step 7 "check every frozen input against plan.json"
if [ "$DRY_RUN" -eq 1 ]; then
  say "  [dry-run] preview against the files on this machine (read only; a fresh pod shows MISSING here)"
  py frozen-check "$PLAN" "$POD_INPUTS" "$EXP_REL" "$DATA_ROOT" --report
else
  py frozen-check "$PLAN" "$POD_INPUTS" "$EXP_REL" "$DATA_ROOT" \
    || die "frozen-input check failed. The lines marked DIFFERS or MISSING name each file and both hashes."
fi

say ""
if [ "$DRY_RUN" -eq 1 ]; then
  if [ "$PROBLEMS" -gt 0 ]; then
    say "pod_setup: DRY RUN found $PROBLEMS problem(s), listed as PROBLEM above. A real run would stop at the first one."
    exit 1
  fi
  say "pod_setup: DRY RUN finished with no problem."
else
  say "pod_setup: the pod is ready. Run this in your shell before the runners:"
  say "  export SWEEP_GGUF_DIR=\"$SWEEP_GGUF_DIR\""
fi
