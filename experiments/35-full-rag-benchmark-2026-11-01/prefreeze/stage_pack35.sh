#!/usr/bin/env bash
# Per-stage tarballs for pod_test_session.sh (sourced, never run on its own).
#
# After a stage ends ok, the chain packs the files the stage wrote under $OUT_DIR into
# $STAGE_OUT/<tag>.tgz and writes <tag>.tgz.sha256 last. The sha256 file is the "ready"
# signal: the Mac pulls each ready tarball, so a pod stop loses no finished stage. Before
# the .sha256, pack_stage writes <tag>.tgz.commit: the commit the chain runs from. With
# SPARE_DIR set, all three files are copied there too. A relaunch with RESUME=1 skips a
# stage whose tarball matches its hash and was made at the same commit (see resume_skip).
# <tag>.tgz.unpacked is a marker: the files of the tarball are in place under $OUT_DIR. A pod
# that holds only the tarballs (a seeded new pod) has no marker, so resume_skip unpacks first.
# The caller sets WORK, OUT_DIR, STAGE_OUT, STAGE_MARK, BG_FILES, SPARE_DIR,
# BACKGROUND_PIDS, DRY_RUN, NAME, RUN_COMMIT (the full commit SHA of the repository the
# chain runs from), RESUME_FROM_COMMIT (optional) and the log, run and checksum functions.

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
    && mv "$tgz.tmp" "$tgz" && touch "$tgz.unpacked" \
    && printf '%s\n' "$RUN_COMMIT" >"$tgz.commit.tmp" && mv "$tgz.commit.tmp" "$tgz.commit" \
    && (cd "$STAGE_OUT" && checksum "$1.tgz") >"$tgz.sha256.tmp" \
    && mv "$tgz.sha256.tmp" "$tgz.sha256"; then
    read -r hash _ <"$tgz.sha256"
    log "== $NAME: packed $1.tgz $hash"
    spare_copy "$1"
  else
    rm -f "$tgz.tmp" "$tgz.commit.tmp" "$tgz.sha256.tmp"
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

# spare_copy <tag>: copy the tarball, its commit file, then its sha256, to SPARE_DIR.
# A failure is logged only.
spare_copy() {
  [ -n "$SPARE_DIR" ] || return 0
  if mkdir -p "$SPARE_DIR" && cp "$STAGE_OUT/$1.tgz" "$SPARE_DIR/" \
    && cp "$STAGE_OUT/$1.tgz.commit" "$SPARE_DIR/" \
    && cp "$STAGE_OUT/$1.tgz.sha256" "$SPARE_DIR/"; then
    log "== $NAME: spare copy in $SPARE_DIR"
  else
    log "== $NAME: spare copy FAILED (the tarball stays on the container disk only)"
  fi
}

# pack_dry_run <tag>: say what pack_stage and spare_copy would do.
pack_dry_run() {
  log "  [dry-run] pack the files the stage writes under $OUT_DIR into $STAGE_OUT/$1.tgz," \
    "then $1.tgz.commit (holds $RUN_COMMIT), then $1.tgz.sha256" \
    "(only when it ends ok and starts no background process)"
  [ -z "$SPARE_DIR" ] \
    || log "  [dry-run] copy $1.tgz, $1.tgz.commit and $1.tgz.sha256 to $SPARE_DIR"
}

# commit_verdict <tgz>: set TAR_COMMIT (the commit in <tgz>.commit; empty without one) and
# VERDICT: "same" (the tarball was made at RUN_COMMIT), "override" (it was made at the
# commit the owner named in RESUME_FROM_COMMIT) or "other".
commit_verdict() {
  TAR_COMMIT=""
  [ ! -f "$1.commit" ] || read -r TAR_COMMIT <"$1.commit" || true
  if [ "$TAR_COMMIT" = "$RUN_COMMIT" ]; then
    VERDICT=same
  elif [ -n "$TAR_COMMIT" ] && [ "$TAR_COMMIT" = "${RESUME_FROM_COMMIT:-}" ]; then
    VERDICT=override
  else
    VERDICT=other
  fi
}

# note_override <tag> <tgz>: log a skip that RESUME_FROM_COMMIT allowed, and add one line to
# $OUT_DIR/resume-record.jsonl (the final tarball carries it: the deviation record).
note_override() {
  local hash
  hash="$(stored_hash "$2")"
  log "== $NAME: SKIPPED (resume, done in $1.tgz at ${TAR_COMMIT:0:7}, this run is" \
    "${RUN_COMMIT:0:7}; RESUME_FROM_COMMIT)"
  printf '{"stage": "%s", "tag": "%s", "tarball_commit": "%s", "run_commit": "%s", "sha256": "%s"}\n' \
    "$NAME" "$1" "$TAR_COMMIT" "$RUN_COMMIT" "$hash" >>"$OUT_DIR/resume-record.jsonl"
}

# unpack_once <tag>: unpack the local tarball unless its .unpacked marker exists, then touch
# the marker. Status 1 when the unpack fails.
unpack_once() {
  local tgz="$STAGE_OUT/$1.tgz"
  [ ! -f "$tgz.unpacked" ] || return 0
  tar -xzf "$tgz" -C "$(dirname "$OUT_DIR")" && touch "$tgz.unpacked" \
    && log "== $NAME: unpacked $1.tgz (seeded)"
}

# restore_spare <tag>: unpack the spare tarball and copy it, its commit file, then its
# sha256 into $STAGE_OUT.
restore_spare() {
  local tgz="$STAGE_OUT/$1.tgz" spare="$SPARE_DIR/$1.tgz"
  tar -xzf "$spare" -C "$(dirname "$OUT_DIR")" && cp "$spare" "$tgz" && touch "$tgz.unpacked" \
    && { [ ! -f "$spare.commit" ] || cp "$spare.commit" "$tgz.commit"; } \
    && cp "$spare.sha256" "$tgz.sha256"
}

# resume_skip <tag>: status 0 when the stage is already done and need not run. The local
# tarball counts first; else the spare copy is restored into $STAGE_OUT and unpacked.
# A tarball whose hash does not match never skips the stage. A tarball with a matching hash
# skips it only when its commit is RUN_COMMIT, or is the one in RESUME_FROM_COMMIT (the
# owner says the fix did not touch the stage; note_override records it).
resume_skip() {
  local tgz="$STAGE_OUT/$1.tgz" spare="${SPARE_DIR:+$SPARE_DIR/$1.tgz}" seen=0 other=0 old
  if [ -f "$tgz.sha256" ]; then
    seen=1
    if tar_matches "$tgz"; then
      commit_verdict "$tgz"
      case "$VERDICT" in
        same | override)
          if ! unpack_once "$1"; then
            log "== $NAME: unpack of $1.tgz FAILED, running it again"
            return 1
          fi
          if [ "$VERDICT" = same ]; then
            log "== $NAME: SKIPPED (resume, done in $1.tgz)"
          else
            note_override "$1" "$tgz"
          fi
          return 0
          ;;
      esac
      other=1 old="${TAR_COMMIT:0:7}"
    fi
  fi
  if [ -n "$spare" ] && [ -f "$spare.sha256" ]; then
    seen=1
    if tar_matches "$spare"; then
      commit_verdict "$spare"
      if [ "$VERDICT" = other ]; then
        other=1 old="${TAR_COMMIT:0:7}"
      elif restore_spare "$1"; then
        if [ "$VERDICT" = same ]; then
          log "== $NAME: RESTORED from $spare, SKIPPED (resume)"
        else
          note_override "$1" "$tgz"
        fi
        return 0
      fi
    fi
  fi
  if [ "$other" = 1 ]; then
    log "== $NAME: done at ${old:-unknown}, this run is ${RUN_COMMIT:0:7}: running it again"
  elif [ "$seen" = 1 ]; then
    log "== $NAME: tarball hash mismatch, running it again"
  fi
  return 1
}
