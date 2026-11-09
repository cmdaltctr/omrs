# Tasks: ONNX Pod Thread Cap

## 1. Session construction and tests

- [x] 1.1 Add unit tests that drive the real lazy constructor and record explicit ONNX options. Verify they fail on the uncapped code and cover CPU ceilings and fallback affinity.
- [x] 1.2 Implement the private capped-session subclass at `_get_magika_instance()` and verify the new tests and existing Magika tests pass.
- [x] 1.3 Update the fast-suite tripwire count by test-ID diff. Verify the selected counts and prove removing the cap fails the new test.
- [x] 1.4 Run the real acceptance-corpus label-equality test and verify capped and uncapped labels match.

## 2. Pod measurement and decision record

- [x] 2.1 Quote live pod pricing before creation. Measure uncapped, eight-thread and twelve-thread sessions on one pod, with a ten-file control pass. Verify outputs and delete the pod in the same turn.
- [x] 2.2 Add ADR-118 with the selected cap, alternatives and before/after evidence. Add a dated addendum to the existing pod summary or a sibling note and verify the values against the outputs.

## 3. Integration gates and review

- [x] 3.1 Run `./scripts/local_ci.sh` and `openspec validate --all --strict`. Verify all checks pass and tick completed tasks with evidence.
- [x] 3.2 Scan changed tracked files for the old project identity. Commit, push and open a PR into `v3` that closes #201. Verify CI completes and handle every CodeRabbit thread. Leave the PR unmerged.

## Workflow follow-up

- Archive the change after the user merges the PR and the post-merge evidence is available.
