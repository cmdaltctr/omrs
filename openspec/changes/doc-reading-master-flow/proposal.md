# Proposal: master execution order for the document-reading and dots-mocr flow

## Why

Six pieces of written work now interlock: the `dots-mocr-llamacpp-backend` change (tasks 3.4 and 3.7 open, groups 4 and 5 held), `skip-blank-pages-before-worker`, the image-based rescue gate (Experiment 43, branch unmerged), a not-yet-written default flip (`page-routing-default`), a pre-registered routing re-test, and `paddleocr-vl-llamacpp-backend`. Two orderings fail silently:

- **Blank pages before the dots-mocr merge.** Task 4.1 of `skip-blank-pages-before-worker` measures with `dots-mocr-llamacpp`, which exists only on the unmerged `feat/dots-mocr-llamacpp-backend` branch. A worktree forked from `v3` cannot run it (checked 2026-11-02: `v3` holds `dots-mocr` PyTorch and `paddleocr-vl` only).
- **The default flip before evidence.** The only real-document evidence for page routing is one 10-page `rf06` extract (6 content pages). The 2026-11-02 handoff records the operator's rule: re-test on new documents before any default change.

This change records one order with gates, so any agent can pick the work up and follow it without re-deriving the plan.

## What Changes

- A task order only (tasks.md groups 0 to 7). No code, no capability deltas.
- Eight gates, each a hard stop where the operator decides.
- A supersession note: this order replaces the phase order in `~/Development/DATA/omrs/handoffs/2026-11-02-ORCHESTRATOR-PROMPT.md` (kept for background).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None.

## Impact

- No code. Each group names the change or experiment whose own tasks carry the detail.
- The order: live page mode by hand (operator) → redo dots-mocr task 3.4 → finish and merge dots-mocr → apply blank-page skipping → pre-registered routing re-test on new documents → default-flip gate → close the rescue gate → PaddleOCR-VL.
- Parked, not in this flow: proposals `ordered-reader-and-ocr-lists`, `non-latin-script-routing`, `document-reading-routers`; Experiment 44; Experiments 35 and 35a; the Ollama and MLX `model`-field runs beyond the small commit in the dots-mocr group 4.
