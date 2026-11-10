#!/usr/bin/env bash
# Chain for the Experiment 35 pre-freeze pod session (master tasks 6.3 and 6.5).
# Run it once on the RunPod RTX 4090 pod, from anywhere. It never ends the pod: the
# operator copies the outputs back and deletes the pod (no process inside a pod can
# stop its own billing).
#
# Stages, each skipped when its marker exists in $WORK/done (so a rerun resumes):
#   judges   background download of the two judge GGUF files (pinned revision, SHA-256)
#   setup    Experiment 48 pod_setup.sh (commit check, uv sync, CUDA llama.cpp b11941,
#            the four Experiment 48 GGUF files, corpora, frozen-hash check)
#   data     LLM-AggreFact test split placed and hash-checked
#   partc    Part C: slices, token counts of the three full corpora, exact against fast
#   measure  20 real answers and their Ragas judging, priced (measure_answers.py)
#   clef     full LLM-AggreFact test split on Clef-Flash, then scored
#   granite  the same on Granite Guardian 3.3 8B, then scored
# A failed stage is logged and the chain goes on, except `setup` and `data`, which
# stop it. The wall-clock cap (TIME_CAP_H) skips stages that cannot start in time and
# bounds the two long ones with `timeout`. They resume from their own files.
#
# Required environment: COMMIT (git sha the pod must be on), INPUTS_DIR (the folder
# the Mac copied over), OPENROUTER_API_KEY, ANSWER_HOST, JUDGE_HOST.
# Optional: WORK (default /workspace/prefreeze), TIME_CAP_H (default 6), DRY_RUN=1.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
EXP35="$REPO/experiments/35-full-rag-benchmark-2026-11-01"
EXP48="$REPO/experiments/48-pipeline-sweep-llamacpp-2026-11-01"
WORK="${WORK:-/workspace/prefreeze}"
DONE="$WORK/done"
OUT="$EXP35/output/prefreeze"
DATA_ROOT="$HOME/Development/DATA/omrs"
TIME_CAP_H="${TIME_CAP_H:-6}"
DRY_RUN="${DRY_RUN:-0}"
STARTED="$(date +%s)"
DEADLINE=$((STARTED + TIME_CAP_H * 3600))
FAILED=()

log() { printf '[%s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }
run() { if [ "$DRY_RUN" = 1 ]; then log "  [dry-run] $*"; else "$@"; fi; }
remaining() { echo $((DEADLINE - $(date +%s))); }
done_marker() { [ -e "$DONE/$1" ]; }
mark() { [ "$DRY_RUN" = 1 ] || touch "$DONE/$1"; }

need() {
  for v in "$@"; do
    [ -n "${!v:-}" ] || { log "STOP: environment variable $v is not set"; exit 2; }
  done
}

# stage <name> <fatal 0|1> <command...>
stage() {
  local name="$1" fatal="$2"
  shift 2
  if done_marker "$name"; then log "== $name: already done"; return 0; fi
  if [ "$(remaining)" -le 0 ]; then
    log "== $name: SKIPPED, the ${TIME_CAP_H} h cap is used up"
    FAILED+=("$name:cap")
    return 0
  fi
  log "== $name: start (cap leaves $(($(remaining) / 60)) min)"
  if "$@"; then
    mark "$name"
    log "== $name: ok"
    return 0
  fi
  log "== $name: FAILED"
  FAILED+=("$name")
  if [ "$fatal" = 1 ]; then finish; exit 1; fi
  return 0
}

# --- judge GGUF files: public repositories, pinned revision, SHA-256 checked -------
fetch_judges() {
  if [ "$DRY_RUN" = 1 ]; then
    log "  [dry-run] would download the two judge GGUF files (about 18 GB) and check SHA-256"
    return 0
  fi
  mkdir -p "$DATA_ROOT/benchmarks/gguf"
  cd "$REPO" && PYTHONDONTWRITEBYTECODE=1 uv run --no-sync python - "$DATA_ROOT/benchmarks/gguf" <<'PY'
import hashlib, sys
from huggingface_hub import hf_hub_download

dest = sys.argv[1]
PINS = (
    ("ggml-org/Clef-Flash-GGUF", "a5a18a6e13bb36573a5f11385a1e7b9a0c868e9e",
     "Clef-Flash-Q8_0.gguf",
     "25f801e2a27610b0ccc0cb1558d7eda3d7a304e34e2c4a04e3079357ff7d906e"),
    ("ibm-granite/granite-guardian-3.3-8b-GGUF", "8c87479a2dc329e4e362a6e5dda7e7de3e0372b2",
     "granite-guardian-3.3-8b-Q8_0.gguf",
     "356fc80d343a699a3d12316de161d4341ee2d11f7057123dabb158804e876bc5"),
)
for repo, rev, name, want in PINS:
    path = hf_hub_download(repo, name, revision=rev, local_dir=dest)
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 22), b""):
            digest.update(block)
    if digest.hexdigest() != want:
        sys.exit(f"SHA-256 differs for {name}: {digest.hexdigest()}")
    print("judge file ok", name, flush=True)
PY
}

stage_setup() {
  cd "$REPO" || return 1
  if ! command -v uv >/dev/null 2>&1; then
    run bash -c 'curl -LsSf https://astral.sh/uv/install.sh | sh' || return 1
    export PATH="$HOME/.local/bin:$PATH"
  fi
  run bash "$EXP48/pod_setup.sh" --commit "$COMMIT" --inputs "$INPUTS_DIR"
}

stage_data() {
  local target="$DATA_ROOT/benchmarks/llm-aggrefact"
  run mkdir -p "$target/data"
  run cp -p "$INPUTS_DIR/llm-aggrefact/MANIFEST.json" "$target/MANIFEST.json"
  run cp -p "$INPUTS_DIR/llm-aggrefact/data/test-00000-of-00001.parquet" "$target/data/"
  [ "$DRY_RUN" = 1 ] && return 0
  python3 - "$target" <<'PY'
import hashlib, json, sys
from pathlib import Path

base = Path(sys.argv[1])
manifest = json.loads((base / "MANIFEST.json").read_text())
for name, meta in manifest["files"].items():
    path = base / name
    if not path.is_file():
        continue
    found = hashlib.sha256(path.read_bytes()).hexdigest()
    if found != meta["sha256"]:
        sys.exit(f"SHA-256 differs for {name}: {found}")
    print("aggrefact file ok", name, flush=True)
PY
}

stage_partc() {
  cd "$EXP48" || return 1
  export SWEEP_GGUF_DIR="${SWEEP_GGUF_DIR:-$DATA_ROOT/benchmarks/gguf}"
  run uv run --no-sync python run_timing.py --model 4b || return 1
  run uv run --no-sync python run_timing.py --part-c --stage exact || return 1
  run uv run --no-sync python run_timing.py --part-c --stage fast || return 1
  run uv run --no-sync python run_timing.py --part-c --stage compare || return 1
  run mkdir -p "$OUT/partc"
  run cp -p output/part-c.json output/part-c-exact-speed.json output/part-c-fast-speed.json \
    output/timing-4b.jsonl "$OUT/partc/"
  # The full-corpus token count comes last and has its own limit: on 8 Nov the
  # FreshStack chunking alone ran 71 minutes without ending. It resumes from its file.
  run timeout 5400 uv run --no-sync python run_timing.py --tokenize || {
    log "   token count did not finish in 90 min; Part C speeds are kept"
    FAILED+=("partc-tokenize")
    return 0
  }
  run cp -p output/token-counts.json "$OUT/partc/"
}

stage_measure() {
  cd "$REPO" || return 1
  export SWEEP_GGUF_DIR="${SWEEP_GGUF_DIR:-$DATA_ROOT/benchmarks/gguf}"
  local venv="$WORK/ragas-venv" version
  if [ ! -x "$venv/bin/python" ]; then
    version="$(.venv/bin/python -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
    run uv venv "$venv" --python "$version" || return 1
    run uv pip install --python "$venv/bin/python" "ragas==0.4.3" "langchain-community==0.3.31" || return 1
  fi
  run mkdir -p "$OUT"
  run uv run --no-sync python "$HERE/measure_answers.py" --resume \
    --prices "$INPUTS_DIR/prices.json" --answer-host "$ANSWER_HOST" \
    --judge-host "$JUDGE_HOST" --ragas-venv "$venv"
}

# stage_aggrefact <strategy> : run (bounded by the cap), then score what exists
stage_aggrefact() {
  local strategy="$1" left
  cd "$REPO" || return 1
  export SWEEP_GGUF_DIR="${SWEEP_GGUF_DIR:-$DATA_ROOT/benchmarks/gguf}"
  left="$(remaining)"
  run timeout "$left" uv run --no-sync python "$HERE/run_aggrefact.py" \
    --strategy "$strategy" --resume --out-dir "$OUT"
  local code=$?
  # 124 means the cap stopped it: keep the partial file and score it as partial.
  if [ "$code" -ne 0 ] && [ "$code" -ne 124 ]; then return 1; fi
  if [ "$code" -eq 124 ]; then
    log "   $strategy stopped by the cap; its scores will say partial"
    run uv run --no-sync python "$HERE/score_aggrefact.py" --strategy "$strategy" \
      --out-dir "$OUT" --allow-partial
    return 1
  fi
  run uv run --no-sync python "$HERE/score_aggrefact.py" --strategy "$strategy" --out-dir "$OUT"
}

finish() {
  log "== finish: failed stages: ${FAILED[*]:-none}"
  [ "$DRY_RUN" = 1 ] && { log "dry run complete"; return 0; }
  mkdir -p "$OUT"
  printf '%s\n' "${FAILED[@]:-}" >"$OUT/failed-stages.txt"
  (cd "$EXP35/output" && tar -czf "$WORK/prefreeze-out.tgz" prefreeze) \
    && sha256sum "$WORK/prefreeze-out.tgz" >"$WORK/prefreeze-out.tgz.sha256"
  date -u +%FT%TZ >"$WORK/DONE"
  log "PREFREEZE_DONE: copy $WORK/prefreeze-out.tgz (+ .sha256) back, then delete the pod"
}

main() {
  need COMMIT INPUTS_DIR OPENROUTER_API_KEY ANSWER_HOST JUDGE_HOST
  mkdir -p "$DONE" "$OUT"
  log "pre-freeze chain: cap ${TIME_CAP_H} h, work $WORK, dry-run $DRY_RUN"
  # The two judge downloads run beside the setup, which is network bound too.
  if ! done_marker judges; then
    (fetch_judges && mark judges) >"$WORK/judges.log" 2>&1 &
    JUDGES_PID=$!
  fi
  stage setup 1 stage_setup
  stage data 1 stage_data
  if [ -n "${JUDGES_PID:-}" ]; then
    log "waiting for the judge downloads"
    wait "$JUDGES_PID" || { log "judge download FAILED, see $WORK/judges.log"; FAILED+=(judges); }
    cat "$WORK/judges.log"
  fi
  stage partc 0 stage_partc
  stage measure 0 stage_measure
  if done_marker judges || [ "$DRY_RUN" = 1 ]; then
    stage clef 0 stage_aggrefact clef_flash
    stage granite 0 stage_aggrefact granite_guardian
  else
    log "judge files missing: skipping the AggreFact stages"
  fi
  finish
}

main "$@"
