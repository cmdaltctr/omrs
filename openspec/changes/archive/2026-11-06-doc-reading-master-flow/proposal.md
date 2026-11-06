# Proposal: master execution order for the document-reading and dots-mocr flow

## Why

Six pieces of written work now interlock: the `dots-mocr-llamacpp-backend` change (tasks 3.4 and 3.7 open, groups 4 and 5 held), `skip-blank-pages-before-worker`, the image-based rescue gate (Experiment 43, branch unmerged), a not-yet-written default flip (`page-routing-default`), a pre-registered routing re-test, and `paddleocr-vl-llamacpp-backend`. Two earlier orderings would have failed, and this change records the fix:

- **Blank pages on the llama.cpp engine.** Task 4.1 of `skip-blank-pages-before-worker` was written against `dots-mocr-llamacpp`, which exists only on the unmerged `feat/dots-mocr-llamacpp-backend` branch (checked 2026-11-02: `v3` holds `dots-mocr` PyTorch and `paddleocr-vl` only). In this flow the blank-page change runs first, so its task 4.1 verifies on the PyTorch engine with a same-engine baseline.
- **The default flip and its evidence.** The 2026-11-02 handoff recorded the rule "re-test on new documents before any default change". On 2026-11-02 the operator confirmed a different order: flip the default first, accepting the `rf06` 10-page page-mode run (page 29 found, worker pages Dice 1.0) as sufficient evidence. Design D2 records the decision; the pre-registered re-test stops being a gate.

This change records one order with gates, so any agent can pick the work up and follow it without re-deriving the plan.

## What Changes

- A task order only (tasks.md groups 1 to 6). No code, no capability deltas.
- Twelve gates, each a hard stop where the operator decides.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None.

## Impact

- No code. Each group names the change or experiment whose own tasks carry the detail.
- The order (operator-confirmed 2026-11-02): apply blank-page skipping → `page-routing-default` (page mode default, document mode removed) → re-run #161 (dots-mocr task 3.4 redo) → proposals A, B, C in that order → close out the rescue gate → task 3.7 (dots-mocr cut-over).
- Parked, not in this flow: `paddleocr-vl-llamacpp-backend` (its own gate: after the dots-mocr cut-over merges); Experiment 44; Experiments 35 and 35a; the Ollama and MLX `model`-field runs beyond the small commit in the dots-mocr group 4.
