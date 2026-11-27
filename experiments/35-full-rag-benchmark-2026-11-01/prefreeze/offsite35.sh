#!/usr/bin/env bash
# Off-site copy for pod_test_session.sh (sourced, never run on its own).
#
# A lost pod or a lost Mac must not lose results. After each stage tarball and at the end of
# the chain, the files go to a private Cloudflare R2 bucket with `curl --aws-sigv4`.
# The key pair goes to curl on standard input (`-K -`): never in an argument, the log or a
# file. Needs curl 7.75 or newer.
#
# Environment: R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ENDPOINT (from the RunPod
# secrets, see launch35.sh), R2_PREFIX (results folder name and pod id, from session.env),
# R2_BUCKET (default omrs-exp35-results), OFFSITE_REQUIRED (1: refuse to start without a
# working off-site copy), OFFSITE_BACKOFF (seconds to wait between the 3 tries, default "2 6"),
# OFFSITE_CONNECT_TIMEOUT (default 30 s) and OFFSITE_MAX_TIME (default 7200 s for one try: a
# stalled connection ends and uses the retry path; a multi-GB stage tarball fits).
# The caller sets WORK, OUT_DIR, DRY_RUN, NAME, SESSION_LOG, TARBALL, RUN_COMMIT, STAGE_OUT
# and the log, refuse and run functions.
#
# A copy that fails 3 times goes to $WORK/offsite.pending (file, tab, key); finish retries
# the list once and writes the keys that still fail to $OUT_DIR/offsite-failed.txt.

R2_BUCKET="${R2_BUCKET:-omrs-exp35-results}"
OFFSITE_ON=0
OFFSITE_FAILS=0
OFFSITE_PENDING="${WORK:-}/offsite.pending"
OFFSITE_BACKOFF="${OFFSITE_BACKOFF:-2 6}"
OFFSITE_CONNECT_TIMEOUT="${OFFSITE_CONNECT_TIMEOUT:-30}"
OFFSITE_MAX_TIME="${OFFSITE_MAX_TIME:-7200}"

# offsite_put <file> <key>: PUT the file to <bucket>/<key>; up to 3 tries with a back-off.
offsite_put() {
  local try=0 wait
  # shellcheck disable=SC2206 # OFFSITE_BACKOFF is a list of numbers
  local -a waits=($OFFSITE_BACKOFF)
  while [ "$try" -lt 3 ]; do
    if printf 'user = "%s:%s"\n' "$R2_ACCESS_KEY_ID" "$R2_SECRET_ACCESS_KEY" \
      | curl -fsS --connect-timeout "$OFFSITE_CONNECT_TIMEOUT" --max-time "$OFFSITE_MAX_TIME" \
        --aws-sigv4 "aws:amz:auto:s3" -K - -T "$1" \
        "$R2_ENDPOINT/$R2_BUCKET/$2" >/dev/null; then
      return 0
    fi
    wait="${waits[$try]:-0}"
    try=$((try + 1))
    [ "$try" -ge 3 ] || sleep "$wait"
  done
  return 1
}

# offsite_url <dir>: the printable address of the folder of the objects (no key, no host).
offsite_url() { printf 'r2://%s/%s/%s' "$R2_BUCKET" "$R2_PREFIX" "$1"; }

# offsite_send <label|""> <folder> <file>...: upload each file under $R2_PREFIX/<folder>/ in
# order. After a failure the files that follow are queued untried: a .sha256 file never goes
# up before its tarball. Status 1 when one file failed.
offsite_send() {
  local label="$1" dir="$2" file failed=0
  shift 2
  for file in "$@"; do
    if [ "$failed" = 0 ] && offsite_put "$file" "$R2_PREFIX/$dir/$(basename "$file")"; then
      continue
    fi
    failed=1
    printf '%s\t%s\n' "$file" "$R2_PREFIX/$dir/$(basename "$file")" >>"$OFFSITE_PENDING"
  done
  if [ "$failed" = 1 ]; then
    OFFSITE_FAILS=$((OFFSITE_FAILS + 1))
    return 1
  fi
  [ -z "$label" ] || log "== $label: off-site copy in $(offsite_url "$dir/$(basename "$1")")"
}

# offsite_setup: decide whether the off-site copy is on. Refuse (exit 2) when it is required
# and a value is missing or the probe upload fails. Call it before the first stage.
offsite_setup() {
  local v missing=""
  for v in R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY R2_ENDPOINT R2_PREFIX; do
    [ -n "${!v:-}" ] || missing="$missing $v"
  done
  if [ -z "$missing" ]; then
    OFFSITE_ON=1
  elif [ "${OFFSITE_REQUIRED:-0}" = 1 ]; then
    refuse "OFFSITE_REQUIRED=1 and these values are empty:$missing"
  else
    log "no off-site copy: R2 is not configured (the container disk, the spare and the Mac hold the results)"
    return 0
  fi
  [ "${OFFSITE_REQUIRED:-0}" = 1 ] || return 0
  if [ "$DRY_RUN" = 1 ]; then
    log "  [dry-run] off-site probe: upload the commit and the date to $(offsite_url probe.txt)"
    return 0
  fi
  printf '%s %s\n' "$RUN_COMMIT" "$(date -u +%F)" >"$WORK/offsite-probe.txt"
  offsite_put "$WORK/offsite-probe.txt" "$R2_PREFIX/probe.txt" \
    || refuse "off-site probe upload failed: $(offsite_url probe.txt). Check the R2 secrets and the bucket."
  log "off-site probe uploaded to $(offsite_url probe.txt)"
}

# offsite_stage <tag>: upload tarball, commit file, sha256 (last) under the active prefix.
# Call it after a stage is packed and on every path that skips a done stage (resume, seed,
# spare restore): a new pod writes a new prefix. The marker <tag>.tgz.offsite holds the
# prefix and the hash of the last complete upload, so the same copy is not sent twice.
offsite_stage() {
  [ "$OFFSITE_ON" = 1 ] || return 0
  local tgz="$STAGE_OUT/$1.tgz" want
  want="$R2_PREFIX $(stored_hash "$tgz")"
  [ "$(cat "$tgz.offsite" 2>/dev/null)" != "$want" ] || return 0
  if offsite_send "$NAME" stage-out "$tgz" "$tgz.commit" "$tgz.sha256"; then
    printf '%s\n' "$want" >"$tgz.offsite"
  else
    log "== $NAME: off-site copy FAILED (kept for a retry at the end)"
  fi
}

# offsite_stage_dry <tag>: say what offsite_stage would do.
offsite_stage_dry() {
  [ "$OFFSITE_ON" = 1 ] || return 0
  log "  [dry-run] off-site: upload to $(offsite_url stage-out/): $1.tgz, $1.tgz.commit," \
    "$1.tgz.sha256 (last)"
}

# offsite_retry: try each pending copy once more (3 tries each); keep the ones that fail.
offsite_retry() {
  [ "$OFFSITE_ON" = 1 ] && [ "$DRY_RUN" != 1 ] && [ -s "$OFFSITE_PENDING" ] || return 0
  local file key total=0 done_n=0 blocked=0 keep="$OFFSITE_PENDING.next"
  : >"$keep"
  while IFS=$'\t' read -r file key; do
    total=$((total + 1))
    # After one failure every later entry stays pending: a .sha256 file never goes up
    # before its tarball, and a final checksum never before its log.
    if [ "$blocked" = 0 ] && offsite_put "$file" "$key"; then
      done_n=$((done_n + 1))
    else
      blocked=1
      printf '%s\t%s\n' "$file" "$key" >>"$keep"
    fi
  done <"$OFFSITE_PENDING"
  mv "$keep" "$OFFSITE_PENDING"
  log "== finish: off-site retry: $done_n of $total pending copies done"
  OFFSITE_FAILS=$(grep -c . "$OFFSITE_PENDING" || true)
  cut -f2 "$OFFSITE_PENDING" >"$OUT_DIR/offsite-failed.txt"
}

# offsite_final: upload the outputs tarball, a snapshot of the chain log, then the .sha256
# to $R2_PREFIX/final/. Call it after the tarball exists and before the wait for the Mac.
offsite_final() {
  [ "$OFFSITE_ON" = 1 ] || return 0
  if [ "$DRY_RUN" = 1 ]; then
    log "  [dry-run] off-site: upload $TARBALL, $SESSION_LOG (as test-session.log) and" \
      "$TARBALL.sha256 to $(offsite_url final/)"
    return 0
  fi
  local -a files=("$TARBALL")
  local snap="$WORK/offsite-final/test-session.log" lost=0
  if [ -f "$SESSION_LOG" ]; then
    if mkdir -p "$WORK/offsite-final" && cp "$SESSION_LOG" "$snap"; then
      files+=("$snap")
    else
      lost=1
    fi
  fi
  if [ "$lost" = 1 ]; then
    # No snapshot of the log: send the tarball, keep the log and the checksum pending.
    offsite_put "$TARBALL" "$R2_PREFIX/final/$(basename "$TARBALL")" \
      || printf '%s\t%s\n' "$TARBALL" "$R2_PREFIX/final/$(basename "$TARBALL")" >>"$OFFSITE_PENDING"
    printf '%s\t%s\n%s\t%s\n' "$SESSION_LOG" "$R2_PREFIX/final/test-session.log" \
      "$TARBALL.sha256" "$R2_PREFIX/final/$(basename "$TARBALL").sha256" >>"$OFFSITE_PENDING"
    log "== finish: off-site copy of the final outputs FAILED (the log snapshot failed; kept in $OFFSITE_PENDING)"
  elif offsite_send "" final "${files[@]}" "$TARBALL.sha256"; then
    log "== finish: off-site copy of the final outputs in $(offsite_url final/)"
  else
    log "== finish: off-site copy of the final outputs FAILED (kept in $OFFSITE_PENDING)"
  fi
  OFFSITE_FAILS=$(grep -c . "$OFFSITE_PENDING" 2>/dev/null || true)
  log "== finish: off-site copies failed: ${OFFSITE_FAILS:-0}"
}
