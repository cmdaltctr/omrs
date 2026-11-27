#!/usr/bin/env bash
# Start of the Experiment 35 test pod session over SSH (task 9.2, gap G7).
#
# RunPod gives the create-time environment of the pod (the two secrets and the image
# pin) to process 1 only. A shell that comes in over SSH does not have it. This script
# copies the named values from /proc/1/environ into its own environment without
# printing them, then starts pod_test_session.sh. The chain's pre-check names any value
# that is still empty and stops before the first stage. It never prints a value.
#
# The Mac runs it inside tmux, from the repository checked out at COMMIT:
#   tmux new-session -d -s exp35 'bash <repo>/experiments/35-full-rag-benchmark-2026-11-01/prefreeze/launch35.sh > /root/exp35-work/test-session.log 2>&1'
#
# All work stays on the container disk, in WORK (default /root/exp35-work). /workspace is
# network storage on many hosts, so it holds only a spare copy of the stage tarballs.
# Optional: SESSION_ENV (default $WORK/session.env: names and plain values, never
# a key; for example COMMIT, STOP_GRACE_MIN, RESUME and KEEP_POD_ON_FAIL), ZAI_ENV
# (default $WORK/.zai_env: the mode-600 file with OMRS_EXP35_ZAI_BASE_URL that the Mac
# watcher writes over ssh standard input), PROC1_ENVIRON (default /proc/1/environ).
# Defaults when unset: WORK=/root/exp35-work, OUT_DIR=$WORK/exp35-test/out,
# STAGES_FILE=<this folder>/test_session_stages.txt. SPARE_DIR=/workspace/exp35-stage-out
# only when /workspace is a mount point (MOUNTPOINT_CMD, default "mountpoint -q", is the
# test); a SPARE_DIR that is already set, even empty, wins.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="${WORK:-/root/exp35-work}"
SESSION_ENV="${SESSION_ENV:-$WORK/session.env}"
ZAI_ENV="${ZAI_ENV:-$WORK/.zai_env}"
PROC1_ENVIRON="${PROC1_ENVIRON:-/proc/1/environ}"
NAMES=(OPENROUTER_API_KEY OMRS_EXP35_ZAI_KEY EXP35_POD_IMAGE RUNPOD_POD_ID RUNPOD_API_KEY)

if [ -f "$SESSION_ENV" ]; then
  set -a
  # shellcheck source=/dev/null
  . "$SESSION_ENV"
  set +a
fi
if [ -f "$ZAI_ENV" ]; then
  set -a
  # shellcheck source=/dev/null
  . "$ZAI_ENV"
  set +a
fi

# A non-empty value in process 1 wins over the shell's value. Nothing is printed.
if [ -r "$PROC1_ENVIRON" ]; then
  while IFS= read -r -d '' entry || [ -n "$entry" ]; do
    for name in "${NAMES[@]}"; do
      case "$entry" in "$name"=?*) export "${entry?}" ;; esac
    done
  done <"$PROC1_ENVIRON"
else
  echo "launch35: $PROC1_ENVIRON cannot be read; the pre-check names each missing value"
fi

export WORK
if [ -z "${SPARE_DIR+x}" ]; then
  # shellcheck disable=SC2086 # MOUNTPOINT_CMD is a command with its own arguments
  if ${MOUNTPOINT_CMD:-mountpoint -q} /workspace >/dev/null 2>&1; then
    SPARE_DIR=/workspace/exp35-stage-out
  else
    SPARE_DIR=""
  fi
fi
export SPARE_DIR
export OUT_DIR="${OUT_DIR:-$WORK/exp35-test/out}"
export STAGES_FILE="${STAGES_FILE:-$HERE/test_session_stages.txt}"
exec bash "$HERE/pod_test_session.sh"
