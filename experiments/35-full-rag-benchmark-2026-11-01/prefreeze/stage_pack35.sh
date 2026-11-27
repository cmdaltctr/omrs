#!/usr/bin/env bash
# Per-stage tarballs for pod_test_session.sh (sourced, never run on its own).
#
# After a stage ends ok, the chain packs the files the stage wrote under $OUT_DIR into
# $STAGE_OUT/<tag>.tgz and writes <tag>.tgz.sha256 last. The sha256 file is the "ready"
# signal: the Mac pulls each ready tarball, so a pod stop loses no finished stage. With
# SPARE_DIR set, both files are copied there too. A relaunch with RESUME=1 skips a stage
# whose tarball matches its hash (see resume_skip). The caller sets WORK, OUT_DIR,
# STAGE_OUT, STAGE_MARK, BG_FILES, SPARE_DIR, BACKGROUND_PIDS, DRY_RUN, NAME and the log, run and
# checksum functions.

# bg_lines: how many lines the background-pid file holds (a launcher stage adds one).
bg_lines() {
  local n
  n="$(grep -c . "$BACKGROUND_PIDS" 2>/dev/null || true)"
  echo "${n:-0}"
}

# stored_hash <tgz>: the hash recorded in <tgz>.sha256; status 1 when the file is missing.
stored_hash() {
  local want
  [ -f "$1" ] && [ -f "$1.sha256" ] || return 1
  read -r want _ <"$1.sha256" || return 1
  printf '%s' "$want"
}

# tar_matches <tgz>: the tarball has a .sha256 file and its hash is the recorded one.
tar_matches() {
  local want got
  want="$(stored_hash "$1")" || return 1
  read -r got _ < <(checksum "$1")
  [ -n "$want" ] && [ "$got" = "$want" ]
}

# record_background_files: a stage that started a background process leaves files that
# keep changing (gpulog writes gpu.csv every second). List what it wrote, relative to the
# parent of $OUT_DIR, in $BG_FILES; pack_stage leaves those files out of every tarball.
record_background_files() {
  (cd "$(dirname "$OUT_DIR")" && find "$(basename "$OUT_DIR")" -type f -newer "$STAGE_MARK") \
    >>"$BG_FILES" 2>/dev/null
}

# pack_stage <tag>: pack the files newer than the start marker. A stage that wrote no file
# gets an empty archive (10240 zero bytes), which still marks the stage as done.
pack_stage() {
  local tgz="$STAGE_OUT/$1.tgz" list="$STAGE_OUT/.pack-list" parent base hash
  parent="$(dirname "$OUT_DIR")"
  base="$(basename "$OUT_DIR")"
  if (cd "$parent" && find "$base" -type f -newer "$STAGE_MARK" -print0 >"$list") \
    && drop_background_files "$list" \
    && if [ -s "$list" ]; then (cd "$parent" && tar -czf "$tgz.tmp" --null -T "$list")
    else head -c 10240 /dev/zero | gzip >"$tgz.tmp"; fi \
    && mv "$tgz.tmp" "$tgz" \
    && (cd "$STAGE_OUT" && checksum "$1.tgz") >"$tgz.sha256.tmp" \
    && mv "$tgz.sha256.tmp" "$tgz.sha256"; then
    read -r hash _ <"$tgz.sha256"
    log "== $NAME: packed $1.tgz $hash"
    spare_copy "$1"
  else
    rm -f "$tgz.tmp" "$tgz.sha256.tmp"
    # A failed pack can leave the only copy of a built index unprotected: count the stage
    # as failed, so the chain exits 1 and KEEP_POD_ON_FAIL keeps the pod.
    FAILED+=("$NAME:pack")
    log "== $NAME: PACK FAILED (the stage runs again on a resume)"
  fi
  rm -f "$list"
}

# drop_background_files <list>: remove the paths of $BG_FILES from the NUL-separated list.
drop_background_files() {
  [ -s "$BG_FILES" ] || return 0
  tr '\0' '\n' <"$1" | grep -vxFf "$BG_FILES" | tr '\n' '\0' >"$1.kept" || true
  mv "$1.kept" "$1"
}

# spare_copy <tag>: copy the tarball, then its sha256, to SPARE_DIR. A failure is logged only.
spare_copy() {
  [ -n "$SPARE_DIR" ] || return 0
  if mkdir -p "$SPARE_DIR" && cp "$STAGE_OUT/$1.tgz" "$SPARE_DIR/" \
    && cp "$STAGE_OUT/$1.tgz.sha256" "$SPARE_DIR/"; then
    log "== $NAME: spare copy in $SPARE_DIR"
  else
    log "== $NAME: spare copy FAILED (the tarball stays on the container disk only)"
  fi
}

# pack_dry_run <tag>: say what pack_stage and spare_copy would do.
pack_dry_run() {
  log "  [dry-run] pack the files the stage writes under $OUT_DIR into $STAGE_OUT/$1.tgz," \
    "then $1.tgz.sha256 (only when it ends ok and starts no background process)"
  [ -z "$SPARE_DIR" ] || log "  [dry-run] copy $1.tgz and $1.tgz.sha256 to $SPARE_DIR"
}

# resume_skip <tag>: status 0 when the stage is already done and need not run. The local
# tarball counts first; else the spare copy is restored into $STAGE_OUT and unpacked.
# A tarball whose hash does not match never skips the stage.
resume_skip() {
  local tgz="$STAGE_OUT/$1.tgz" spare="${SPARE_DIR:+$SPARE_DIR/$1.tgz}" seen=0
  if [ -f "$tgz.sha256" ]; then
    seen=1
    if tar_matches "$tgz"; then
      log "== $NAME: SKIPPED (resume, done in $1.tgz)"
      return 0
    fi
  fi
  if [ -n "$spare" ] && [ -f "$spare.sha256" ]; then
    seen=1
    if tar_matches "$spare" && tar -xzf "$spare" -C "$(dirname "$OUT_DIR")" \
      && cp "$spare" "$tgz" && cp "$spare.sha256" "$tgz.sha256"; then
      log "== $NAME: RESTORED from $spare, SKIPPED (resume)"
      return 0
    fi
  fi
  [ "$seen" = 0 ] || log "== $NAME: tarball hash mismatch, running it again"
  return 1
}
