# Evidence

- `test-ids-diff.txt`: the fast-suite test IDs added by this change (`diff` of the sorted
  `pytest -m "not slow" --collect-only -q` output before and after). It adds 155 IDs and
  removes none. 32 of the new tests need fastapi.
- The full before and after ID lists are not kept in git. Existing test parameters hold
  fake AWS keys, and the gitleaks pre-commit hook refuses those lines.
