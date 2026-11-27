#!/usr/bin/env bash
# Sourced by pod_test_session.sh. The hold after a POD_KEPT line (owner 2026-11-27).
#
# A kept pod bills for ever when the Mac is away. After either POD_KEPT path the chain
# waits up to KEEP_HOLD_MIN minutes (default 120; 0 = no wait, no stop: the pod runs on),
# polling every PULL_POLL_S seconds, for the Mac to take over. Then it stops the pod: stop
# only, never terminate. The /workspace volume and the R2 copies stay.
#
# The Mac takes over when one of these is true. Each one is a file test, so a poll costs nothing.
#   $HOLD_RELEASED exists   The watcher writes it before a relaunch (release_hold_cmd in
#                           watch_stages35.py). A relaunch starts a new tmux session, and the
#                           launch refuses while this chain's session lives, so the watcher
#                           must end this chain first. It is also the way to release by hand.
#   session.env is newer    A relaunch rewrites session.env. This covers a relaunch that does
#   than $HOLDING           not come from the watcher. $HOLDING is made when the hold starts.
# A tmux kill-session needs no test: the process ends, and the pod stays.
# --attach does not release the hold: it only pulls and watches. The hold runs on and stops the pod.
# main() deletes both markers at every start, so a marker of an earlier run cannot end a new hold.

# hold_for_mac: call after a POD_KEPT line. Return 0 when the Mac took over or there is no hold.
# On a timeout it logs, clears KEPT and calls stop_pod (STOP_OK, or exit 3 when the stop fails).
hold_for_mac() {
  local polls=$((KEEP_HOLD_MIN * 60 / PULL_POLL_S)) env="${SESSION_ENV:-$WORK/session.env}"
  [ "$KEEP_HOLD_MIN" -gt 0 ] || return 0
  if [ "$DRY_RUN" = 1 ]; then
    log "  [dry-run] POD_KEPT: hold up to $KEEP_HOLD_MIN min for the Mac, then stop the pod"
    KEPT=0
    stop_pod
    return 0
  fi
  log "POD_KEPT: holding up to $KEEP_HOLD_MIN min for the Mac, then the pod stops itself (the volume and R2 copies stay)"
  : >"$HOLDING"
  while [ "$polls" -gt 0 ]; do
    sleep "$PULL_POLL_S"
    polls=$((polls - 1))
    if [ -e "$HOLD_RELEASED" ] || [ "$env" -nt "$HOLDING" ]; then
      rm -f "$HOLDING"
      log "POD_KEPT: the Mac took over; the pod stays"
      return 0
    fi
  done
  rm -f "$HOLDING"
  log "POD_KEPT: no Mac after $KEEP_HOLD_MIN min: stopping the pod"
  KEPT=0
  stop_pod
}
