#!/bin/zsh
# Run the whole Experiment 43 sweep overnight (change tasks 5.1 to 5.5).
#
# One command, from the experiment folder:
#   nohup ./run_sweep.sh > output/sweep.log 2>&1 &
#
# It holds a caffeinate assertion, starts and stops the router between
# stages, resumes every stage, and never deletes an output. Stop it with
# the word RUNSTOP:  touch output/RUNSTOP  (checked between stages).

set -u
cd "$(dirname "$0")"
mkdir -p output/logs

ROUTER_LOG=output/logs/router.log
RUNNING_PRESET=""

log() { print -r -- "[$(date +%H:%M:%S)] $*"; }

stop_router() {
  /usr/bin/pkill -f "llama serve --models-preset" 2>/dev/null
  RUNNING_PRESET=""
  sleep 3
}

start_router() {
  preset=$1
  if [[ "$RUNNING_PRESET" == "$preset" ]]; then return; fi
  stop_router
  log "starting router: $preset"
  llama serve --models-preset "$preset" --host 127.0.0.1 --port 18080 >> "$ROUTER_LOG" 2>&1 &
  # Wait for the server to answer /health, up to 10 minutes (model loads).
  for _ in {1..120}; do
    if curl -sf http://127.0.0.1:18080/health > /dev/null 2>&1; then
      RUNNING_PRESET="$preset"; log "router up ($preset)"; return
    fi
    sleep 5
  done
  log "FATAL: router did not come up on $preset; see $ROUTER_LOG"; exit 1
}

check_stop() {
  if [[ -e output/RUNSTOP ]]; then log "RUNSTOP found; exiting cleanly."; stop_router; exit 0; fi
}

caffeinate -dimsu &
CAFFEINATE=$!
trap 'stop_router; kill $CAFFEINATE 2>/dev/null' EXIT

# --- Part A: full pipeline, then determinism, then the two arms (5.1, 5.2)
start_router router.ini
check_stop
[[ -e output/.done-answers-verify.json ]] || uv run --no-sync python run_part_a.py --resume
check_stop
[[ -e output/determinism.jsonl ]] || uv run --no-sync python run_part_a.py --mode determinism
check_stop
for model in 0.6b 8b; do
  [[ -e output/arms-$model.jsonl ]] || uv run --no-sync python run_part_a.py --mode arms --model $model
  check_stop
done

# --- Part B: one model at a time (5.3)
for model in 0.6b 4b 8b; do
  short=${model//./}
  [[ -e output/timing-$model.jsonl ]] && grep -q financebench output/timing-$model.jsonl && continue
  start_router router-$model.ini
  check_stop
  uv run --no-sync python run_timing.py --model $model
done

# --- Token counts and extrapolation (5.4)
start_router router-4b.ini
check_stop
[[ -e output/token-counts.json ]] || uv run --no-sync python run_timing.py --tokenize
[[ -e output/estimates.json ]] || uv run --no-sync python run_timing.py --extrapolate

# --- Part C: exact against fast (5.5)
[[ -e output/part-c-exact-financebench.jsonl ]] || { start_router router-4b.ini; check_stop
  uv run --no-sync python run_timing.py --part-c --stage exact; }
[[ -e output/part-c-fast-financebench.jsonl ]] || { start_router router-4b-fast.ini; check_stop
  uv run --no-sync python run_timing.py --part-c --stage fast; }
[[ -e output/part-c.json ]] || uv run --no-sync python run_timing.py --part-c --stage compare

stop_router
log "sweep complete; outputs:"
ls -la output/*.jsonl output/*.json 2>/dev/null
kill $CAFFEINATE 2>/dev/null
