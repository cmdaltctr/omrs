#!/usr/bin/env bash
# Chain for the Experiment 35 test pod session (task 9.2; task 9.1a, H-32).
# pod_prefreeze.sh is the record of the earlier session and does not change.
#
# Start it inside the pod under tmux (or nohup), so a closed terminal does not end it.
# The Mac starts it through launch35.sh, which first copies the pod's create-time
# values from process 1 (gap G7):
#   tmux new-session -d -s exp35 'bash <repo>/experiments/35-full-rag-benchmark-2026-11-01/prefreeze/launch35.sh > /workspace/test-session.log 2>&1'
#
# It runs each stage of STAGES_FILE in order, from the Experiment 35 folder. On every
# exit (the end, a failure, a TERM, HUP or INT signal) the `finish` trap runs once: it
# stops the background processes of the stages, writes the outputs to
# $WORK/test-session-out.tgz with its SHA-256, waits up to STOP_GRACE_MIN minutes for
# the Mac's $WORK/PULLED marker, then stops this pod, so billing for the GPU ends.
# Create the pod with a volume disk at /workspace: a stop clears the container disk,
# the volume keeps the tarball (G10).
#
# STAGES_FILE holds one item per line; blank lines and lines that start with # are
# skipped. All lines are checked before the first stage runs.
#   NAME=value               a literal value (no expansion), exported to later stages;
#                            a value that holds TODO stops the session before it starts
#   [!]name[@time] command   a stage; the command runs with `bash -c`, no standard input
# "!" stops the chain when the stage fails (setup stages, G5); other failures are
# logged and the chain goes on. "@time" (90s, 45m or 6h) is the stage timeout (G23).
# After SESSION_CAP (default 15h) no stage starts, and a stage never runs past it.
# Exit 77 marks a stage as skipped (its input is absent). A stage with exactly one
# "run_arms.py " call runs once more when it exits 5 (rate-limit stop: each
# --*-concurrency value halved, plus --resume) or 4 or 6 (plus --resume) (G15).
# Every Experiment 35 stage passes --prefreeze (task 5.7) and writes into $OUT_DIR,
# never into the main output folder. A stage can add a PID to $BACKGROUND_PIDS.
#
# Required environment: OUT_DIR, STAGES_FILE and, checked before any stage, the RunPod
# values RUNPOD_POD_ID and RUNPOD_API_KEY, the hosted keys OPENROUTER_API_KEY and
# OMRS_EXP35_ZAI_KEY, and the image pin EXP35_POD_IMAGE. No value is printed.
# Optional: WORK (default /workspace), SESSION_CAP (default 15h), STOP_GRACE_MIN
# (default 0), PULL_POLL_S (default 10), DRY_RUN=1 (print every command, run none).
# Exit codes: 0 every stage ok or skipped; 1 a stage failed, timed out or did not
# start in time; 2 refused before the first stage; 3 the pod stop failed.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXP35="$(cd "$HERE/.." && pwd)"
WORK="${WORK:-/workspace}"
TARBALL="$WORK/test-session-out.tgz"
PULLED="$WORK/PULLED"
BACKGROUND_PIDS="$WORK/background.pids"
DRY_RUN="${DRY_RUN:-0}"
SESSION_CAP="${SESSION_CAP:-15h}"
STOP_GRACE_MIN="${STOP_GRACE_MIN:-0}"
PULL_POLL_S="${PULL_POLL_S:-10}"
REST_V2="https://api.runpod.io/v2"
REST_V1="https://rest.runpod.io/v1"
FAILED=()
SKIPPED=()
FINISHED=0
STOP_OK=0
DEADLINE=0
NAME=""
FATAL=0
LIMIT=0
CMD=""

log() { printf '[%s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }
run() { if [ "$DRY_RUN" = 1 ]; then log "  [dry-run] $*"; else "$@"; fi; }
refuse() { log "STOP: $*"; exit 2; }

need() {
  for v in "$@"; do
    [ -n "${!v:-}" ] || refuse "environment variable $v is not set"
  done
}

# seconds <time>: print 90s, 45m, 6h or a plain number as seconds; status 1 if malformed.
seconds() {
  local n="${1%[smh]}"
  case "$n" in '' | *[!0-9]*) return 1 ;; esac
  case "$1" in
    *h) echo $((10#$n * 3600)) ;;
    *m) echo $((10#$n * 60)) ;;
    *) echo $((10#$n)) ;;
  esac
}

checksum() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1"; else shasum -a 256 "$1"; fi
}

is_value() {
  local name="${1%%=*}"
  [ "$name" != "$1" ] || return 1
  case "$name" in [A-Z]*) ;; *) return 1 ;; esac
  case "$name" in *[!A-Z0-9_]*) return 1 ;; esac
}

# parse_stage <line>: set NAME, FATAL, LIMIT (seconds, 0 for none) and CMD; status 1 if malformed.
parse_stage() {
  local head="${1%% *}"
  CMD="${1#* }"
  [ "$CMD" != "$1" ] && [ -n "$CMD" ] || return 1
  FATAL=0
  LIMIT=0
  if [ "${head#!}" != "$head" ]; then
    FATAL=1
    head="${head#!}"
  fi
  NAME="${head%%@*}"
  if [ "$NAME" != "$head" ]; then
    LIMIT="$(seconds "${head#*@}")" && [ "$LIMIT" -gt 0 ] || return 1
  fi
  case "$NAME" in '' | *[!A-Za-z0-9._-]*) return 1 ;; esac
}

check_stages() {
  local line number=0
  while IFS= read -r line || [ -n "$line" ]; do
    number=$((number + 1))
    case "$line" in '' | '#'*) continue ;; esac
    if is_value "$line"; then
      case "$line" in *TODO*) refuse "stages file line $number: ${line%%=*} still holds TODO" ;; esac
      continue
    fi
    parse_stage "$line" || refuse "stages file line $number is neither a stage nor a value"
  done <"$STAGES_FILE"
}

precheck() {
  [ -r "$STAGES_FILE" ] || refuse "stages file $STAGES_FILE cannot be read"
  local cap
  cap="$(seconds "$SESSION_CAP")" || refuse "SESSION_CAP $SESSION_CAP is not a time (for example 15h)"
  DEADLINE=$(($(date +%s) + cap))
  case "$STOP_GRACE_MIN" in '' | *[!0-9]*) refuse "STOP_GRACE_MIN is not a whole number" ;; esac
  case "$PULL_POLL_S" in '' | 0 | *[!0-9]*) refuse "PULL_POLL_S is not a number above 0" ;; esac
  check_stages
  if [ "$DRY_RUN" = 1 ]; then
    log "  [dry-run] check timeout, runpodctl or curl, and RUNPOD_API_KEY, RUNPOD_POD_ID," \
      "OPENROUTER_API_KEY, OMRS_EXP35_ZAI_KEY and EXP35_POD_IMAGE"
    return 0
  fi
  command -v timeout >/dev/null 2>&1 || refuse "timeout is not on PATH"
  command -v runpodctl >/dev/null 2>&1 || command -v curl >/dev/null 2>&1 \
    || refuse "neither runpodctl nor curl is on PATH, so the pod cannot stop itself"
  need RUNPOD_API_KEY RUNPOD_POD_ID OPENROUTER_API_KEY OMRS_EXP35_ZAI_KEY EXP35_POD_IMAGE
}

# halve <command>: the command with each "--<role>-concurrency N" value halved (at least 1).
halve() {
  local rest="$1" out="" re='--([a-z]+)-concurrency ([0-9]+)' n
  while [[ $rest =~ $re ]]; do
    n=$((10#${BASH_REMATCH[2]} / 2))
    [ "$n" -ge 1 ] || n=1
    out="$out${rest%%"${BASH_REMATCH[0]}"*}--${BASH_REMATCH[1]}-concurrency $n"
    rest="${rest#*"${BASH_REMATCH[0]}"}"
  done
  printf '%s' "$out$rest"
}

one_runner_call() {
  local rest="${1#*run_arms.py }"
  [ "$rest" != "$1" ] || return 1
  case "$rest" in *run_arms.py*) return 1 ;; esac
}

# time_left: print the seconds the stage may run (its own timeout within the session cap).
time_left() {
  local left=$((DEADLINE - $(date +%s)))
  if [ "$LIMIT" -gt 0 ] && [ "$LIMIT" -lt "$left" ]; then left="$LIMIT"; fi
  echo "$left"
}

attempt() {
  (cd "$EXP35" && timeout -k 60 "$2" bash -c "$1" </dev/null)
}

# run_stage: run the parsed stage; status 1 when a "!" stage failed (stop the chain).
run_stage() {
  local limit rc again=""
  limit="$(time_left)"
  if [ "$limit" -le 0 ]; then
    log "== $NAME: SKIPPED, the session cap ($SESSION_CAP) is used up"
    FAILED+=("$NAME:cap")
    return 0
  fi
  log "== $NAME: start (timeout ${limit}s)"
  if [ "$DRY_RUN" = 1 ]; then
    log "  [dry-run] $CMD"
    return 0
  fi
  attempt "$CMD" "$limit"
  rc=$?
  if one_runner_call "$CMD"; then
    case "$rc" in
      5) again="$(halve "$CMD")" && log "== $NAME: exit 5 (rate-limit stop): once more, half the concurrency, --resume" ;;
      4 | 6) again="$CMD" && log "== $NAME: exit $rc: once more with --resume" ;;
    esac
  fi
  if [ -n "$again" ]; then
    again="${again/run_arms.py /run_arms.py --resume }"
    limit="$(time_left)"
    if [ "$limit" -gt 0 ]; then
      log "  $again"
      attempt "$again" "$limit"
      rc=$?
    fi
  fi
  case "$rc" in
    0) log "== $NAME: ok" ;;
    77) log "== $NAME: SKIPPED (exit 77, its input is absent)" && SKIPPED+=("$NAME") ;;
    124) log "== $NAME: FAILED, stopped at its timeout (${limit}s)" && FAILED+=("$NAME:timeout") ;;
    *) log "== $NAME: FAILED (exit $rc)" && FAILED+=("$NAME") ;;
  esac
  if [ "$FATAL" = 1 ] && [ "$rc" != 0 ] && [ "$rc" != 77 ]; then
    log "== chain STOPPED: $NAME is marked with ! and failed"
    return 1
  fi
}

run_stages() {
  local line
  while IFS= read -r line <&3 || [ -n "$line" ]; do
    case "$line" in '' | '#'*) continue ;; esac
    if is_value "$line"; then
      export "${line?}"
      continue
    fi
    parse_stage "$line"
    run_stage || break
  done 3<"$STAGES_FILE"
}

stop_background() {
  local pid
  [ -f "$BACKGROUND_PIDS" ] || return 0
  while IFS= read -r pid; do
    case "$pid" in '' | *[!0-9]*) continue ;; esac
    if [ "$DRY_RUN" = 1 ]; then log "  [dry-run] kill $pid"; continue; fi
    kill "$pid" 2>/dev/null && log "stopped background process $pid"
  done <"$BACKGROUND_PIDS"
  [ "$DRY_RUN" = 1 ] || rm -f "$BACKGROUND_PIDS"
}

wait_for_pull() {
  local polls=$((STOP_GRACE_MIN * 60 / PULL_POLL_S))
  [ "$STOP_GRACE_MIN" -gt 0 ] || return 0
  if [ "$DRY_RUN" = 1 ]; then
    log "  [dry-run] wait up to $STOP_GRACE_MIN min for $PULLED"
    return 0
  fi
  log "waiting up to $STOP_GRACE_MIN min for $PULLED before the stop"
  while [ ! -e "$PULLED" ] && [ "$polls" -gt 0 ]; do
    sleep "$PULL_POLL_S"
    polls=$((polls - 1))
  done
  if [ -e "$PULLED" ]; then
    log "PULLED seen: the Mac has the tarball"
  else
    log "no $PULLED after $STOP_GRACE_MIN min: stopping anyway (the volume keeps the tarball)"
  fi
}

# rest_stop <url> [<body>]: POST with the key on standard input, never in the arguments.
rest_stop() {
  local args=(-fsS -X POST -H @- -o /dev/null "$1")
  command -v curl >/dev/null 2>&1 || return 1
  [ -z "${2:-}" ] || args+=(-H 'Content-Type: application/json' --data "$2")
  printf 'Authorization: Bearer %s\n' "$RUNPOD_API_KEY" | curl "${args[@]}"
}

# stop_pod: the new runpodctl syntax, then the old one, then the REST API (G8).
stop_pod() {
  local id="${RUNPOD_POD_ID:-<RUNPOD_POD_ID>}" how=""
  if [ "$DRY_RUN" = 1 ]; then
    log "  [dry-run] runpodctl pod stop $id; else runpodctl stop pod $id; else POST" \
      "$REST_V2/pods/$id/action, then $REST_V1/pods/$id/stop (key from RUNPOD_API_KEY)"
    STOP_OK=1
    return 0
  fi
  if runpodctl pod stop "$id"; then
    how="runpodctl pod stop"
  elif runpodctl stop pod "$id"; then
    how="runpodctl stop pod"
  elif rest_stop "$REST_V2/pods/$id/action" '{"action":"stop"}'; then
    how="REST $REST_V2"
  elif rest_stop "$REST_V1/pods/$id/stop"; then
    how="REST $REST_V1"
  fi
  if [ -n "$how" ]; then
    STOP_OK=1
    log "pod stop sent with: $how"
  else
    log "POD_STOP_FAILED: no stop command worked and the GPU still bills." \
      "Delete pod $id from the Mac now."
  fi
}

finish() {
  [ "$FINISHED" = 1 ] && return 0
  FINISHED=1
  log "== finish: failed stages: ${FAILED[*]:-none}; skipped: ${SKIPPED[*]:-none}"
  stop_background
  if [ "$DRY_RUN" != 1 ]; then
    mkdir -p "$WORK" "$OUT_DIR"
    printf '%s\n' ${FAILED[@]+"${FAILED[@]}"} >"$OUT_DIR/failed-stages.txt"
    printf '%s\n' ${SKIPPED[@]+"${SKIPPED[@]}"} >"$OUT_DIR/skipped-stages.txt"
    [ -f "$EXP35/output/run-records.jsonl" ] && cp -p "$EXP35/output/run-records.jsonl" "$OUT_DIR/"
  fi
  run tar -czf "$TARBALL" -C "$(dirname "$OUT_DIR")" "$(basename "$OUT_DIR")" \
    || log "tarball FAILED; the outputs stay in $OUT_DIR"
  [ "$DRY_RUN" = 1 ] || checksum "$TARBALL" >"$TARBALL.sha256"
  log "TEST_SESSION_DONE: copy $TARBALL (+ .sha256) to the Mac, touch $PULLED, then delete the pod"
  wait_for_pull
  stop_pod
}

main() {
  need OUT_DIR STAGES_FILE
  precheck
  export OUT_DIR WORK BACKGROUND_PIDS
  export SESSION_PID=$$
  if [ "$DRY_RUN" != 1 ]; then
    mkdir -p "$WORK" "$OUT_DIR"
    rm -f "$PULLED" "$BACKGROUND_PIDS"
  fi
  trap finish EXIT
  trap 'exit 143' TERM HUP INT
  log "test pod session: work $WORK, out $OUT_DIR, cap $SESSION_CAP, dry-run $DRY_RUN"
  run_stages
  finish
  [ "$STOP_OK" = 1 ] || exit 3
  [ "${#FAILED[@]}" -eq 0 ] || exit 1
}

main "$@"
