#!/usr/bin/env bash
# Chain for the Experiment 35 test pod session (task 9.2; task 9.1a, H-32).
# pod_prefreeze.sh is the record of the earlier session and does not change.
#
# Start it inside the pod under nohup or tmux, so a closed terminal does not end it:
#   nohup bash experiments/35-full-rag-benchmark-2026-11-01/prefreeze/pod_test_session.sh > /workspace/test-session.log 2>&1 &
#   (from the repository root)
#   (or run it in a tmux session)
#
# It runs each stage of STAGES_FILE in order, from the Experiment 35 folder. A failed
# stage is logged and the chain goes on. On every exit (the end, a failure, a TERM,
# HUP or INT signal) the `finish` trap runs once: it writes the outputs to
# $WORK/test-session-out.tgz with its SHA-256, then stops this pod with runpodctl, so
# billing for the GPU ends. The pod volume keeps the tarball: copy it to the Mac,
# then delete the pod.
#
# STAGES_FILE: one stage per line, "<name> <command...>"; blank lines and lines that
# start with # are skipped. Every Experiment 35 stage passes --prefreeze (task 5.7)
# and writes into OUT_DIR, never into the main output folder. The command may use
# $OUT_DIR. Each command runs with `bash -c` and no standard input.
#
# Required environment: OUT_DIR (the smoke output folder), STAGES_FILE, and the
# RunPod pod values RUNPOD_POD_ID and RUNPOD_API_KEY (the check runs before any stage).
# Optional: WORK (default /workspace), DRY_RUN=1 (print every command, run none).
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXP35="$(cd "$HERE/.." && pwd)"
WORK="${WORK:-/workspace}"
TARBALL="$WORK/test-session-out.tgz"
DRY_RUN="${DRY_RUN:-0}"
FAILED=()
FINISHED=0

log() { printf '[%s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }
run() { if [ "$DRY_RUN" = 1 ]; then log "  [dry-run] $*"; else "$@"; fi; }

need() {
  for v in "$@"; do
    [ -n "${!v:-}" ] || { log "STOP: environment variable $v is not set"; exit 2; }
  done
}

check_stop_tool() {
  if [ "$DRY_RUN" = 1 ]; then
    log "  [dry-run] check that runpodctl, RUNPOD_API_KEY and RUNPOD_POD_ID exist"
    return 0
  fi
  command -v runpodctl >/dev/null 2>&1 || { log "STOP: runpodctl is not on PATH"; exit 2; }
  need RUNPOD_API_KEY RUNPOD_POD_ID
}

checksum() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1"; else shasum -a 256 "$1"; fi
}

run_stages() {
  local line name cmd
  while IFS= read -r line <&3 || [ -n "$line" ]; do
    case "$line" in '' | '#'*) continue ;; esac
    name="${line%% *}"
    cmd="${line#* }"
    log "== $name: start"
    if [ "$DRY_RUN" = 1 ]; then
      log "  [dry-run] $cmd"
    elif (cd "$EXP35" && bash -c "$cmd" </dev/null); then
      log "== $name: ok"
    else
      log "== $name: FAILED"
      FAILED+=("$name")
    fi
  done 3<"$STAGES_FILE"
}

finish() {
  [ "$FINISHED" = 1 ] && return 0
  FINISHED=1
  log "== finish: failed stages: ${FAILED[*]:-none}"
  if [ "$DRY_RUN" != 1 ]; then
    mkdir -p "$WORK"
    printf '%s\n' ${FAILED[@]+"${FAILED[@]}"} >"$OUT_DIR/failed-stages.txt"
    [ -f "$EXP35/output/run-records.jsonl" ] && cp -p "$EXP35/output/run-records.jsonl" "$OUT_DIR/"
  fi
  run tar -czf "$TARBALL" -C "$(dirname "$OUT_DIR")" "$(basename "$OUT_DIR")" \
    || log "tarball FAILED; the outputs stay in $OUT_DIR"
  [ "$DRY_RUN" = 1 ] || checksum "$TARBALL" >"$TARBALL.sha256"
  log "TEST_SESSION_DONE: copy $TARBALL (+ .sha256) to the Mac, then delete the pod"
  run runpodctl stop pod "$RUNPOD_POD_ID"
}

main() {
  need OUT_DIR STAGES_FILE
  check_stop_tool
  export OUT_DIR
  export SESSION_PID=$$
  trap finish EXIT
  trap 'exit 143' TERM HUP INT
  log "test pod session: work $WORK, out $OUT_DIR, dry-run $DRY_RUN"
  run_stages
  finish
  [ "${#FAILED[@]}" -eq 0 ] || exit 1
}

main "$@"
