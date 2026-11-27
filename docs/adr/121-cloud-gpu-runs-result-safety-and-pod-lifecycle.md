# ADR-121: Cloud GPU Runs: Result Safety and Pod Lifecycle

- **Date:** 2026-11-27
- **Status:** Accepted
- **Deciders:** Dr Muhammad Aizat Bin Md Hawari
- **Scope:** every experiment run on a rented cloud GPU (RunPod today), not only Experiment 35.
- **Related:** [ADR-103](103-experiments-run-local-models-through-llama-cpp-gguf.md),
  [ADR-119](119-experiment-35-model-matrix-and-claim-checker.md),
  [ADR-120](120-adopting-the-experiment-35-winning-setup-as-the-app-default.md),
  PRs #231 and #234, issues #232, #233 and #235,
  `experiments/35-full-rag-benchmark-2026-11-01/prefreeze/TEST_SESSION_RUNBOOK.md`

## Context

Experiment 35 runs about 460 GPU hours on rented RTX 4090 pods, with a budget near $1,100. Before
the main run, test pods showed how results can be lost or money wasted:

- A network-mounted `/workspace` (fuse) made setup time out, and writing search indexes over the
  network risks a damaged index.
- Outputs lived only on the pod disk. A pod stop or a lost pod would have lost them.
- A killed Mac watcher sent a stop that ended the chain on the pod.
- A resume could mix stages built at two different commits without a record.
- A pod failed to stop itself once (all four stop methods failed; the cause went to the tmux pane).
- A pod kept for a fix would bill all night if the Mac went away.
- In November an idle pod billed 8 hours because nobody watched it.

These are not specific to Experiment 35. Any later cloud GPU run has the same risks.

## Decision

1. **Work on the pod's own disk.** The work folder is the container disk (`/root/<exp>-work`).
   Setup refuses a network-mounted work folder. `/workspace` holds only a spare copy.
2. **Checkpoint each stage.** Each finished stage is packed into a tarball with its stores, a
   `.commit` file and a `.sha256` file (written last, as the ready signal). The Mac pulls it and
   checks the hash. Files a background process still writes are excluded.
3. **Resume only at the same commit.** A resume skips a stage only when its tarball was built at the
   running commit. Reusing a stage from an older commit needs an explicit override
   (`--resume-from-commit`), which writes a deviation record (`resume-record.jsonl`).
4. **Off-site copy.** Every stage and the final outputs go to a private Cloudflare R2 bucket. The
   bucket-scoped key is a RunPod secret on the pod and a mode-600 file on the Mac; no key goes into
   an argument, a log or chat. The pod checks the upload before the first stage. The Mac reads each
   `.sha256` object back and compares it; any gap keeps the pod. This deviates from the local-only
   data policy on purpose (owner decision, 2026-11-27): the data stays private, never on a public
   host. **The verified R2 copy counts as the second copy on a separate device.**
5. **One owner for the stop.**
   - Mac watching: after a clean end (all pulled, hashes match, R2 verified, no hold) the Mac stops
     the pod through the RunPod API and confirms the status `EXITED`. A failure falls back to rule
     5b.
   - Mac away: the pod stops itself after the grace time. It tries every stop method in 3 rounds and
     logs each failure.
   - A pod kept on purpose (failed stage with keep-on-fail, or an unverified Mac copy) waits up to
     120 min for the Mac, then stops itself. A relaunch releases the wait.
   - Stop only. Only the owner deletes a pod, after the Mac holds verified results.
6. **Recover, do not repeat.** A signal only detaches the watcher; the chain runs on and `--attach`
   rejoins it. A deliberate stop needs a `STOP` file. `--seed-from` rebuilds a run on a new pod from
   the Mac's stage tarballs. A whole run is never repeated: rerun only the affected stage and log
   the deviation.
7. **Operating rules.** Ask the owner before creating a pod, with the live price. Never end a
   session turn while a pod exists. Keep the pod while a stage is fixed; delete it only for a wrong
   host. Pin the GPU type, cloud (secure), CUDA floor and image digest in the experiment plan.

## Consequences

- A lost pod, a lost Mac or a killed watcher loses no finished stage. The 2026-11-27 pod checks
  proved resume, attach, seed-from and the R2 check on real pods (DATA_LOCATIONS, entries of that
  date).
- Results now leave the Mac for a private bucket. R2 storage is a small standing cost.
- The Mac API stop and the kept-pod hold are tested on the Mac only; their first live use is the
  Experiment 35 main run. Their failure falls back to the older stop path; no result is lost.
- The cause of the single failed self-stop is unknown; the retries now log it.
- The rules live in the Experiment 35 harness (`prefreeze/`). A new experiment reuses those scripts
  or keeps the same rules. A harness Docker image is deferred until after Experiment 35.

## Alternatives considered

- **Network volume as the work folder.** Rejected: fuse timeouts and index damage risk.
- **Mac copy only, no off-site copy.** Rejected: the Mac is then the single point of failure for
  a $1,100 run.
- **Pod self-stop only.** Rejected: it failed once with no visible cause; the Mac, when present,
  is a more reliable owner.
- **Keep a held pod forever.** Rejected: a pod could bill all night with the Mac away.
