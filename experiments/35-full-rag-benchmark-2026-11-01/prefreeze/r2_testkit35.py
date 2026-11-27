"""A fake ``curl`` for the off-site tests: it plays Cloudflare R2 with a folder.

Not a test module. The stub records each call (``curl.argv``: the arguments; ``curl.stdin``:
what the ``-K -`` config held; ``curl.calls``: ``PUT``/``GET`` and the bucket path of each
try; ``curl.ok``: the same for each try that worked). A PUT copies the file into
``<tmp>/bucket/<bucket>/<key>``; a GET prints that file. ``curl.fail`` holds a count of
calls that fail with exit 22 before the stub works again. ``curl.fail-match`` holds a
text: every call whose path holds it fails. ``curl.mirror`` holds a pod work folder: a GET
then serves the file that an upload of it would have made (``stage-out/<f>`` or ``final/<f>``
of the key maps to ``<mirror>/stage-out/<f>`` or ``<mirror>/<f>``). ``curl.corrupt`` holds a
text: a GET whose path holds it returns other bytes. No test reaches a network host.
"""

from __future__ import annotations

import os
from pathlib import Path

BUCKET = "omrs-exp35-results"
KEY_ID = "r2id-SECRET-ACCESS-111"
SECRET = "r2sec-SECRET-VALUE-222"  # noqa: S105 - a stand-in, never a real key
ENDPOINT = "https://acct123abc.fake-r2.invalid"
R2 = {"R2_ACCESS_KEY_ID": KEY_ID, "R2_SECRET_ACCESS_KEY": SECRET, "R2_ENDPOINT": ENDPOINT}
SECRETS = (KEY_ID, SECRET)

_CURL = r"""#!/usr/bin/env bash
T="@T@"
args=("$@")
printf '%s\n' "$*" >> "$T/curl.argv"
put=""; cfg=0; url=""; i=0
while [ "$i" -lt "$#" ]; do
  case "${args[$i]}" in
    -T) put="${args[$((i + 1))]}"; i=$((i + 2)); continue ;;
    -K | --aws-sigv4) [ "${args[$i]}" = -K ] && cfg=1; i=$((i + 2)); continue ;;
    -*) ;;
    *) url="${args[$i]}" ;;
  esac
  i=$((i + 1))
done
[ "$cfg" = 1 ] && cat >> "$T/curl.stdin"
path="${url#https://*/}"
verb=GET; [ -n "$put" ] && verb=PUT
echo "$verb $path" >> "$T/curl.calls"
if [ -f "$T/curl.fail-match" ] && [[ "$path" == *"$(cat "$T/curl.fail-match")"* ]]; then exit 22; fi
if [ -f "$T/curl.fail" ]; then
  n=$(cat "$T/curl.fail")
  if [ "$n" -gt 0 ]; then echo $((n - 1)) > "$T/curl.fail"; exit 22; fi
fi
if [ "$verb" = PUT ]; then
  mkdir -p "$(dirname "$T/bucket/$path")" && cp "$put" "$T/bucket/$path" || exit 26
elif [ -f "$T/curl.mirror" ]; then
  m="$(cat "$T/curl.mirror")"
  case "$path" in
    */stage-out/*) src="$m/stage-out/${path##*/stage-out/}" ;;
    *) src="$m/${path##*/final/}" ;;
  esac
  [ -f "$src" ] || exit 22
  if [ -f "$T/curl.corrupt" ] && [[ "$path" == *"$(cat "$T/curl.corrupt")"* ]]; then
    echo "other bytes"
  else
    cat "$src"
  fi
else
  [ -f "$T/bucket/$path" ] || exit 22
  cat "$T/bucket/$path"
fi
echo "$verb $path" >> "$T/curl.ok"
"""


def install(tmp: Path) -> str:
    """Write the stub; return the ``PATH`` that puts it first."""
    folder = tmp / "r2-bin"
    folder.mkdir(exist_ok=True)
    (folder / "curl").write_text(_CURL.replace("@T@", str(tmp)), encoding="utf-8")
    (folder / "curl").chmod(0o755)
    return f"{folder}:{tmp / 'bin'}:{os.environ['PATH']}"


def lines(tmp: Path, name: str) -> list[str]:
    """Return the lines of a stub log, or none."""
    path = tmp / name
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def bucket(tmp: Path, *parts: str) -> Path:
    """Return the path of an object in the fake bucket."""
    return tmp.joinpath("bucket", BUCKET, *parts)
