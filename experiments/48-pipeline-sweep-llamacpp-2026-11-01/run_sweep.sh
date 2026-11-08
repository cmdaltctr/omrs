#!/usr/bin/env bash
# Run the whole Experiment 48 sweep overnight (change tasks 5.1 to 5.5).
#
# One command, from the experiment folder:
#   SWEEP_GGUF_DIR=<folder of the four GGUF files> nohup ./run_sweep.sh > output/sweep.log 2>&1 &
#
# Each Python step writes the scratch output/config/omrs.jsonc and starts
# OMRS's managed router (state in output/state); the router stops when that
# step exits (task 3.5). This script starts and stops no server itself. It
# resumes every stage and never deletes an output. Stop it with the word
# RUNSTOP:  touch output/RUNSTOP  (checked between stages). Runs on macOS and
# Linux; it holds a caffeinate assertion only where caffeinate exists.
#
# A failed stage stops the sweep with a nonzero exit (set -e). Output that
# came from a --limit smoke run stops it before the first stage: the file
# existence checks below would otherwise skip stages the smoke run only
# sampled. Move that output aside and run again.

set -euo pipefail
cd "$(dirname "$0")" || exit 1
mkdir -p output/logs

log() { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }

limited="$(grep -lE '"limit": [0-9]+' output/.done-*.json output/timing-*.jsonl \
  output/token-counts.json 2>/dev/null || true)"
if [[ -n "$limited" ]]; then
  log "FATAL: these files came from a --limit run: $(echo "$limited" | tr '\n' ' ')"
  log "Move output/ aside (and its scratch index), then run again."
  exit 1
fi

check_stop() {
  if [[ -e output/RUNSTOP ]]; then log "RUNSTOP found; exiting cleanly."; exit 0; fi
}

CAFFEINATE=""
if command -v caffeinate > /dev/null 2>&1; then
  caffeinate -dimsu &
  CAFFEINATE=$!
  trap 'kill "$CAFFEINATE" 2>/dev/null || true' EXIT
fi

# Stop before any router start when OMRS refuses the scratch settings.
if ! uv run --no-sync python run_part_a.py --dry-run; then
  log "FATAL: the scratch omrs.jsonc dry run failed; see above"; exit 1
fi

# --- Part A: full pipeline, then determinism, then the two arms (5.1, 5.2)
check_stop
[[ -e output/.done-answers-verify.json ]] || uv run --no-sync python run_part_a.py --resume
check_stop
[[ -e output/determinism.jsonl ]] || uv run --no-sync python run_part_a.py --mode determinism
check_stop
for model in 0.6b 8b; do
  [[ -e output/arms-$model.jsonl ]] || uv run --no-sync python run_part_a.py --mode arms --model $model
  check_stop
done

# --- Part B: one model at a time, a fresh router per model (5.3)
for model in 0.6b 4b 8b; do
  [[ -e output/timing-$model.jsonl ]] && grep -q financebench output/timing-$model.jsonl && continue
  check_stop
  uv run --no-sync python run_timing.py --model $model
done

# --- Token counts and extrapolation (5.4)
check_stop
[[ -e output/token-counts.json ]] || uv run --no-sync python run_timing.py --tokenize
[[ -e output/estimates.json ]] || uv run --no-sync python run_timing.py --extrapolate

# --- Part C: exact against fast, fresh router starts (5.5)
check_stop
[[ -e output/part-c-exact-financebench.jsonl ]] || uv run --no-sync python run_timing.py --part-c --stage exact
check_stop
[[ -e output/part-c-fast-financebench.jsonl ]] || uv run --no-sync python run_timing.py --part-c --stage fast
[[ -e output/part-c.json ]] || uv run --no-sync python run_timing.py --part-c --stage compare

log "sweep complete; outputs:"
ls -la output/*.jsonl output/*.json 2>/dev/null || true
