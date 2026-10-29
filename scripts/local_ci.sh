#!/usr/bin/env bash
# Local equivalent of the PR-blocking CI jobs. Run before pushing to
# catch failures without spending workflow minutes.
#
# Covers: ruff, ruff format, import-linter, OpenSpec strict validation,
# the GitHub workflow files (skipped when actionlint is absent), the OpenAPI contract, the torch-free default-install check, and the
# full fast suite and the clean-base tripwire under the same env vars CI sets, the frontend gates,
# and the web wheel asset check (skipped when npm is absent).
#
# Deliberately excluded (not replicable without mutating the venv):
#   - floors matrix (uv sync --resolution lowest-direct per extra)
#   - extras jobs (community-leiden, torch) and the Coverage job's chroma check
#   - retrieval-quality tiers and the macOS-only slow suite
# If a change touches dependency floors or an optional extra, let CI
# carry those jobs — or replicate with a throwaway venv.

set -euo pipefail
cd "$(dirname "$0")/.."

step() { printf '\n== %s ==\n' "$1" >&2; }

# Temporary paths that later steps create. One EXIT trap removes them all,
# because a second `trap ... EXIT` would replace the first.
junit=""
wheel_dir=""
web_log=""
web_pid=""
cleanup() {
  # Stop the background frontend job (its whole process group) when an
  # earlier step fails, so no npm or vitest process stays behind.
  if [ -n "$web_pid" ]; then kill -- -"$web_pid" 2>/dev/null || true; fi
  rm -rf ${junit:+"$junit"} ${wheel_dir:+"$wheel_dir"} ${web_log:+"$web_log"}
}
trap cleanup EXIT

step "ruff check (whole repo)"
uv run --no-sync ruff check .

step "ruff format --check (whole repo)"
uv run --no-sync ruff format --check .

step "import-linter contracts"
uv run --no-sync lint-imports

step "OpenSpec validate --all --strict"
openspec validate --all --strict

step "GitHub workflows (actionlint)"
# CI does not lint its own workflow files, so a broken ci.yml shows only after
# a push. Install with `brew install actionlint` on each new machine.
if command -v actionlint >/dev/null 2>&1; then
  actionlint
  echo "OK: workflow files pass actionlint"
else
  echo "SKIPPED: actionlint not found. Install it with: brew install actionlint" >&2
fi

step "OpenAPI contract"
uv run --no-sync python -c "import yaml; from openapi_spec_validator import validate; validate(yaml.safe_load(open('src/omrs/transports/api/openapi.yaml')))"
echo "OpenAPI contract valid"

step "default install is torch-free"
packages="$(uv pip list)"
if printf '%s\n' "$packages" | grep -qiE '^(torch|transformers)([[:space:]]|$)'; then
  echo "FAIL: torch or transformers found in default install" >&2
  exit 1
fi
echo "OK: default install is torch-free"

# The frontend gates and the web wheel check share nothing with the Python
# suite, so they run in the background while it runs. Their output is held in
# a log and printed after the tripwire, so the two outputs do not mix. The
# tests never read the built assets: they serve from temporary folders.
step "frontend gates and web wheel assets (started in the background)"
# CI runs the frontend job; the release workflow runs the wheel check.
# The wheel goes to a temporary directory, so dist/ stays untouched.
if command -v npm >/dev/null 2>&1; then
  web_log="$(mktemp)"
  wheel_dir="$(mktemp -d)"
  set -m # own process group, so cleanup can stop npm and its children
  (
    set -e
    (cd web && npm ci && npm run lint && npm run typecheck && npm test && npm run build)
    uv build --wheel --out-dir "$wheel_dir"
    uv run --no-sync python scripts/check_web_wheel.py "$wheel_dir"/*.whl
    echo "OK: wheel contains the web workspace assets"
  ) >"$web_log" 2>&1 &
  web_pid=$!
  set +m
  echo "running (output follows the tripwire)"
else
  echo "SKIPPED: npm not found. Install Node 22 or later to run the frontend gates and the web wheel check." >&2
fi

# The fast suite runs in parallel when pytest-xdist is installed (about three
# times faster; --dist loadfile comes from pyproject.toml). It writes a JUnit
# report. The clean-base tripwire runs as its own step and reads its executed
# count from that report through OMRS_TRIPWIRE_JUNIT, so it does not run the
# suite again.
# OMRS_CI_WORKERS caps the workers (default 8, as in CI). A machine with
# more cores can raise it, for example OMRS_CI_WORKERS=16.
parallel=()
if uv run --no-sync python -c "import xdist" >/dev/null 2>&1; then
  parallel=(-n auto --maxprocesses="${OMRS_CI_WORKERS:-8}")
fi
junit="$(mktemp)"

step "fast suite (CI env${parallel:+, parallel})"
PDF_READER=pypdf \
EMBED_PROVIDER=local \
LOCAL_BACKEND=ollama \
EMBED_MODEL=nomic-embed-text \
OLLAMA_BASE_URL=http://localhost:11434 \
METADATA_LLM_PROVIDER=local \
  uv run --no-sync pytest -m "not slow" --tb=short -q ${parallel[@]+"${parallel[@]}"} \
    --deselect tests/test_clean_base_tripwire.py --junitxml="$junit"

step "clean-base tripwire (CI env)"
PDF_READER=pypdf \
EMBED_PROVIDER=local \
LOCAL_BACKEND=ollama \
EMBED_MODEL=nomic-embed-text \
OLLAMA_BASE_URL=http://localhost:11434 \
METADATA_LLM_PROVIDER=local \
OMRS_TRIPWIRE_JUNIT="$junit" \
  uv run --no-sync pytest tests/test_clean_base_tripwire.py --tb=short -q

step "frontend gates and web wheel assets"
if [ -n "$web_pid" ]; then
  web_status=0
  wait "$web_pid" || web_status=$?
  web_pid=""
  cat "$web_log"
  if [ "$web_status" -ne 0 ]; then
    echo "FAIL: frontend gates or web wheel check (exit $web_status)" >&2
    exit "$web_status"
  fi
else
  echo "SKIPPED: npm not found (see the step above)." >&2
fi

step "pyright (advisory — CI runs it non-blocking)"
if command -v npx >/dev/null 2>&1; then
  npx --yes pyright@1.1.412 src || echo "pyright findings (advisory, same as CI)"
else
  echo "npx not available — skipped"
fi

printf '\n== local CI passed ==\n' >&2
