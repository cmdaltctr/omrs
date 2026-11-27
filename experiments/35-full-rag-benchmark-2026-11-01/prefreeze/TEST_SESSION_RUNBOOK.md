# Test pod session runbook (Experiment 35, task 9.2)

This runbook is for the operator's agent. The agent creates and deletes the pod with the RunPod MCP tools. `mac_watch35.py` does the work between create and delete. It never creates or deletes a pod.

## Caps and the turn rule

- Stop at 15 h after create, or at $18 total spend (RunPod plus OpenRouter). The first cap reached applies.
- The watcher stops itself at 15.5 h (`--wall-cap-h`). The chain on the pod stops its stages 15 h after the chain starts. The chain starts a few minutes after create (pod start and copy), so the 15 h after create rule above still applies.
- The watcher cannot see spend. You must read the spend.
- Stay in your turn from create until `list-pods` shows the pod is gone. Do not end the turn while a pod exists.

## Before the go

1. Push the session commit `COMMIT` to `origin`. The pod clones it from there.
2. Check out `COMMIT` in a worktree. Run every command below from its `experiments/35-full-rag-benchmark-2026-11-01` folder.
3. Put the classifier examples file (JSON) on the Mac. Write down its path.
4. Run the dry run with a placeholder pod id:

   ```bash
   uv run --no-sync python prefreeze/mac_watch35.py --pod-id DRYRUN --ssh-host 203.0.113.1 \
     --ssh-port 22 --commit "$COMMIT" --examples <examples.json> --dry-run
   ```

5. Make sure the dry run exits 0 and shows no `PROBLEM:` line. Fix each problem on the Mac first.
6. Make sure the dry run lists 91 input files (about 279 MB before compression). Investigate any other count.
7. Get the owner's go.

## Session order

1. Read the live price and stock for one RTX 4090 on secure cloud (`get-capacity`). Quote the price.
2. Do the create within 10 minutes of that read. If the price changed, quote again and wait for the go.
3. Run `uv run --no-sync python prefreeze/create_pod35.py`. Keep the JSON it prints.
4. Call `create-pod` once with that JSON, unchanged. Write down the pod id.
5. Read the pod back with `get-pod`. Compare the image digest, GPU, 120 GB container disk, `/workspace` volume (the spare copy) and port `22/tcp` with the JSON.
6. If a value differs, delete the pod at once. Do not start the watcher.
7. Start the watcher as a background task at once. `caffeinate -i` keeps the Mac awake:

   ```bash
   caffeinate -i uv run --no-sync python prefreeze/mac_watch35.py --pod-id <id> \
     --commit "$COMMIT" --examples <examples.json>
   ```

8. The watcher reads the pod from the RunPod API every 15 s (step 2b). It waits for the public IP and the public port of `22/tcp`, up to 15 minutes. It prints `not ready yet` for each wait. The key comes from `RUNPOD_API_KEY`, else from `apikey` in `~/.runpod/config.toml`. The watcher never prints the key.
9. If no public address comes in 15 minutes, the watcher exits 13. Delete the pod. The RunPod SSH proxy cannot carry `scp`, so the watcher does not use it. To give the address yourself, add `--ssh-host <publicIp> --ssh-port <port>`.

10. Read the watcher output while it runs. It prints one line for each stage start and end.
11. Read `list-pod-billing` every 2 hours. Add the OpenRouter session spend.
12. If the total spend reaches $18, stop the run on purpose: `touch <results folder>/STOP`, then `kill -TERM "$(cat <results folder>/watcher.pid)"`.
    The first output line names the results folder. Do not use `pgrep` or `pkill`: they also match the `caffeinate` and `uv` parents.
    The watcher then stops the chain, pulls the outputs and prints `DELETE_POD_NOW`. It ignores a second signal, so the pull finishes.
    A signal without the `STOP` file only detaches the watcher. The chain runs on. See exit code 15.
13. Wait for the watcher to exit. Its last line is `DELETE_POD_NOW <id>`.
14. Delete the pod with `delete-pod` and that id. Do this for every exit code except 14.
    Exit 14 ends with `KEEP_POD <id>`: the pod stays up for a fix. Follow "Resume after a failure".
15. If the watcher process ended without the `DELETE_POD_NOW` or `KEEP_POD` line, delete the pod all the same.
16. Read `list-pods`. Confirm that the pod is gone. If it is not gone, delete it again and read again.
    Skip this step after exit 14: the pod stays up on purpose for "Resume after a failure".
17. Remove nothing else: no other pod, volume, template, secret or SSH key.
18. Read `list-pod-billing` for the real cost of the session.
19. Report the exit code, the `RESULT` line, the results folder and the cost.

## Exit codes

Delete the pod only when the last line is `DELETE_POD_NOW <id>`. When the last line is `KEEP_POD <id>`, keep the pod and read the reason on that line.
A `KEEP_POD` line follows exit code 14, a final pull that did not end `ok`, an `OFFSITE_NOT_VERIFIED` line, a stage tarball that the Mac lacks, and every `--attach` that did not succeed.
Fix the cause, then resume or attach.

| Code | Meaning | Extra action |
| ---: | --- | --- |
| 0 | `TEST_SESSION_DONE`, outputs pulled, SHA-256 matches | None. |
| 1 | Internal error in the watcher | Report the error line. |
| 2 | Refused before any remote step | Fix the `REFUSED:` line on the Mac before the next pod. |
| 3 | `POD_STOP_FAILED`: the pod did not stop itself after 3 rounds of the stop methods, 30 s apart (`STOP_RETRY_S`). The log holds one `pod stop: <method> exit <code>: <error>` line for each failed try | Delete at once. The GPU still bills. Report the `pod stop:` lines. |
| 4 | No SSH within 15 minutes | Report it. |
| 5 | A pod setup step failed (copy, SHA-256, clone, launch) | Report the `remote step failed` line. |
| 6 | A `STOP:` line in the chain log | Read the `STOP:` line in the pulled log. Fix on the Mac. |
| 7 | The tmux session ended without `TEST_SESSION_DONE` | Read the end of the pulled log. |
| 8 | No new log byte for 30 minutes | Read the last stage in the pulled log. |
| 9 | Wall-clock cap reached | Report the stages that did not run. |
| 10 | No SSH for 10 minutes while watching | Outputs are probably lost. Report it. |
| 11 | The pull failed, or the SHA-256 differs | Keep the files as they are. Report it. |
| 12 | Stopped on purpose: a signal after `touch <results folder>/STOP` | Report why you stopped it. |
| 13 | No public IP for `22/tcp` within 15 minutes (step 2b) | Report it. Nothing was copied. |
| 14 | The chain logged `POD_KEPT:` (`--keep-pod-on-fail`, a stage failed or a signal stopped the chain) | Keep the pod. Follow "Resume after a failure". Delete the pod yourself when you stop. |
| 15 | Detached: a signal (SIGTERM, SIGINT or SIGHUP) without a `STOP` file. The chain runs on. No pull, no `PULLED`. | Keep the pod. Rejoin with the `--attach` command that the watcher printed. See "When the Mac goes away". |

After codes 8, 9 and 12 (not 15) the watcher first sends `tmux kill-session -t exp35` to the pod. The chain then stops its stage and writes the tarball. The watcher waits up to 3 minutes for the tarball, then pulls. If the stop fails or times out, the watcher pulls anyway.

## Where the work lives

- All work runs on the container disk in `/root/exp35-work`. The container disk is local on every host.
- The folder holds `inputs/`, `passages/`, `ragas-venv/`, `omrs/` (the checkout), `session.env`, `test-session.log` and the outputs in `exp35-test/out`.
- The `/workspace` volume is network storage on some hosts. The setup stage refuses it as a work folder.
- After each stage ends `ok`, the chain packs the new files of that stage into `/root/exp35-work/stage-out/<NN>-<stage>.tgz`. `NN` is the stage number in the stages file, counted from 1.
- The chain writes the `.sha256` file last. The watcher pulls a tarball only when it sees the `.sha256` file.
- The watcher pulls each stage tarball to the Mac as the stage ends. It checks the SHA-256 on the Mac.
- Setup stages (marked `!`) and background launchers such as `gpulog` get no tarball. They run again on every resume.
- The chain copies each tarball to the spare folder `/workspace/exp35-stage-out`. The spare copy is optional. A failed copy does not stop the chain.

## Where the results go

- The watcher writes `~/Development/DATA/omrs/experiments/35-full-rag-benchmark-2026-11-01/test-session-<UTC date>/`. It never overwrites an existing folder.
- The folder name comes from the stages file: `verify_session_stages.txt` gives `verify-session-<UTC date>/`.
- The folder holds `inputs/`, `watcher.pid`, `test-session.log`, `watch-summary.txt` and the outputs tarball with its `.sha256`.
- `inputs/` holds the inputs tarball, its `.sha256`, the examples and the `--extra-input` file, exactly as sent to the pod.
- The outputs tarball is `test-session-out.tgz` from the chain. If the chain wrote none, it is `watcher-out.tgz`, packed from `/root/exp35-work/exp35-test/out`.
- Record the copy and its SHA-256 in `DATA/omrs/DATA_LOCATIONS.md`.
- The outputs tarball holds no index store (`stores/` folders). Every JSON, JSONL, log and summary file, `environment.json` and the seal records are in the tarball.
- The stage tarballs are in `stage-out/` of the results folder. Each one holds the files of its stage, with the index stores.
- The watcher writes `STOP_GRACE_MIN=120` into `session.env`. The chain then waits up to 120 minutes for `PULLED` before it stops the pod. The watcher's pull takes at most 110 minutes (copy time limits of 10 min for the log and 45 min for each of two tarball tries), so a slow copy ends before the stop. A Mac that stops answering costs at most 2 h of GPU time.

## Fix check variant

The fix check session checks the four fixes of 2026-11-24 on a short second pod. It uses the same machinery: `pod_setup35.sh`, `launch35.sh`, the `pod_test_session.sh` chain and `mac_watch35.py`. The chain stops the pod only after the last check ends and the Mac has pulled the outputs.

- The stages are in `prefreeze/verify_session_stages.txt`. The watcher writes `STAGES_FILE` into `/root/exp35-work/session.env`, and `launch35.sh` reads it.
- Every stage runs at `COMMIT`. No stage checks out another commit.
- Section 4 needs the FinanceBench answers of the 2026-11-24 session. The watcher sends them as `--extra-input`.

### Before the go

1. Do steps 1 to 3 of "Before the go" above.
2. Cut the FinanceBench answers and the seal record (about 1 MB) out of the session tarball:

   ```bash
   (
     cd ~/Development/DATA/omrs/experiments/35-full-rag-benchmark-2026-11-01/test-session-2026-11-24
     tar -czf "$TMPDIR/fb-answers.tgz" --include 'out/s/financebench/answer' \
       --include 'out/s/financebench/closedbook-rag' --include 'out/s/financebench/rebuild.json' \
       --include 'out/s/environment.json' @test-session-out.tgz
   )
   ```

   The subshell keeps the shell in the Experiment 35 checkout for the next command.

3. Run the dry run with the two extra options:

   ```bash
   uv run --no-sync python prefreeze/mac_watch35.py --pod-id DRYRUN --ssh-host 203.0.113.1 \
     --ssh-port 22 --commit "$COMMIT" --examples <examples.json> \
     --stages verify_session_stages.txt --extra-input "$TMPDIR/fb-answers.tgz" --dry-run
   ```

4. Make sure the dry run exits 0, lists 91 input files, and shows `fb-answers.tgz` in the SHA-256 check.
5. Make sure the dry run shows `STAGES_FILE=/root/exp35-work/omrs/.../verify_session_stages.txt` and the folder `verify-session-<UTC date>`.

### Session

Do the session order above. In step 7, start the watcher with the two extra options:

```bash
caffeinate -i uv run --no-sync python prefreeze/mac_watch35.py --pod-id <id> \
  --ssh-host <publicIp> --ssh-port <port> --commit "$COMMIT" --examples <examples.json> \
  --stages verify_session_stages.txt --extra-input "$TMPDIR/fb-answers.tgz"
```

### Stages, times and pass marks

The sections run in the order 1, 3, 3b, 4, 2: the cheapest and the budget-critical checks first. Times are expected minutes on one RTX 4090. Section 3b repeats the G2 rebuild check on the final code, because the store fix (bcd11389) changed how chunks are written after the last G2 pass (owner decision, 2026-11-24). Its times come from the same stages in the 2026-11-24 test session.

| Stage | Section | Timeout | Expected | Pass mark |
| --- | --- | ---: | ---: | --- |
| `setup` | Setup (as the test session) | 60 min | 23 min | `ok`. A failure stops the chain. |
| `ocr-walmart-20x` | 1. OCR fix (0bebdb1d) | 105 min | 25 min | `20/20 passes`: 29 pages each, each pass under 300 s. |
| `fs-rate-1200` | 3. Store speed (bcd11389) | 60 min | 25 min | `ok`. The six `[rate] files` lines stay flat in s/file. |
| `s-fs-c1024` | 3b. G2 rebuild check: shared index | 25 min | 10 min | `ok`. About 675 files, so compaction runs about ten times. |
| `g2-fs-build` | 3b. G2 rebuild check: rebuild | 25 min | 10 min | `ok`. |
| `g2-fs-check` | 3b. G2 rebuild check: compare | 15 min | 2 min | `ok`: `[rebuild] freshstack: 40 questions match`. `s/freshstack/rebuild.json` reports `"ok": true`, with no mismatches and no incomplete questions. A difference exits 3 and fails the stage. |
| `fb-unpack` | 4. Answers copy | 10 min | 1 min | `ok` (87 files). |
| `ragas-closedbook-fb` | 4. Closed-book Ragas (b98f536f) | 20 min | 5 min | `ok`, with no exit 6. |
| `kinds-fb-c512` | 4. Claim kinds (b98f536f) | 15 min | 4 min | `ok`. |
| `fs-c2048-ingest` | 2. Reranker fix (eb70e807) | 50 min | 8 min | `ok`. |
| `fs-c2048-seal` | 2. | 15 min | 2 min | `ok`. |
| `fs-c2048-r0.6b` | 2. | 30 min | 3 min | `ok`, queries 76293427 and 77759618 included. |
| `fs-c2048-r4b` | 2. | 30 min | 8 min | `ok`, as above. |
| `fs-c2048-r8b` | 2. | 30 min | 14 min | `ok`, as above. |

- Expected total: about 140 min of stages, plus about 10 min for the pod start, the copy, the pull and the stop. That is about 2.5 h, or about $2.23 at $0.89/h.
- Upper bound: the stage timeouts add up to 490 min (8.2 h). With the start and the pull, that is about 8.4 h, or about $7.50.
- Hosted calls (Ragas on 20 questions, claim kinds on 20 answers) add a few cents of OpenRouter spend.
- Pass mark of the whole check (2026-11-24 notes): every stage `ok`, the per-file store time flat, and `s/freshstack/rebuild.json` reports identical ranked results (`"ok": true`).
- Store speed for the budget: the `[rate] files` lines give seconds per file for each block of 200 files. Block 1 includes the engine start. The old rate was about 2 s per file at 3,300 files.

## P2 session

The P2 session measures the build speed and checks answers before the freeze. It uses the same machinery as the test session. The stages are in `prefreeze/p2_session_stages.txt`. The results folder is `p2-session-<UTC date>/`.

The session also runs the classifier re-gate (task 8.7, owner decision 2026-11-24). The first gate failed on refusal recall. The re-gate classifies a new sample of 100 claims (seed 20261142) with the re-pinned prompt and examples. The watcher sends the sample as `--extra-input`. It arrives as `/workspace/inputs/sample.json`, and its SHA-256 is checked on the pod. The stage `gate2-classify` copies it to `gate2/` and writes `gate2/sample-kinds.jsonl` there. The output tarball brings it back.

### Before the go

1. Do steps 1 to 3 of "Before the go" above.
2. Name the re-gate sample folder:

   ```bash
   GATE2=~/Development/DATA/omrs/experiments/35-full-rag-benchmark-2026-11-01/test-session-2026-11-24/gate2
   ```

3. Run the dry run from the Experiment 35 folder:

   ```bash
   uv run --no-sync python prefreeze/mac_watch35.py --pod-id DRYRUN --commit "$COMMIT" \
     --examples classify-examples.json --stages p2_session_stages.txt \
     --extra-input "$GATE2/sample.json" --dry-run
   ```

4. Make sure the dry run exits 0, shows no `PROBLEM:` line and shows the `step 2b: GET` line.
5. Make sure the dry run shows `STAGES_FILE=/root/exp35-work/omrs/.../p2_session_stages.txt` and the folder `p2-session-<UTC date>`.
6. Make sure the dry run names `sample.json` among the inputs it sends.

### Session

Do the session order above. In step 7, start the watcher with the stages file:

```bash
caffeinate -i uv run --no-sync python prefreeze/mac_watch35.py --pod-id <id> \
  --commit "$COMMIT" --examples classify-examples.json --stages p2_session_stages.txt \
  --extra-input "$GATE2/sample.json"
```

After the pull, copy `out/gate2/sample-kinds.jsonl` from the session tarball to `$GATE2/`. Then run `refusals35.py gate --out-dir "$GATE2" --labels <claim_kinds-L1.json>` on the Mac.

### Stages, times and pass marks

The re-gate and the quick checks run first, then the full build. The stage timeouts add up to 895 min, inside the 15 h session cap, so the cap never cuts a stage short. Times are expected minutes on one RTX 4090.

| Stage | Timeout | Expected | Pass mark |
| --- | ---: | ---: | --- |
| `setup` | 60 min | 23 min | `ok`. A failure stops the chain. |
| `gate2-classify` | 15 min | 2 min | `ok`. `gate2/sample-kinds.jsonl` holds 100 rows of one classifier version. The first gate took 1 min 40 s. |
| `rate-e0.6b-c1024`, `rate-e8b-c1024`, `rate-e4b-c512`, `rate-e4b-c2048` | 35 min each | 13 min each | `ok`. About 2,750 files each (1,200 sampled plus the gold files). The `[rate] files` lines stay flat in s/file. |
| `seal-e4b-c512`, `seal-e0.6b-c1024`, `seal-e4b-c2048` | 10 min each | under 1 min | `ok`. |
| `recheck-<shape>` (15 stages) | 10 min each | 2.5 min each | `ok`. In `r/freshstack/answer/<setup>/run1/`, every `answer-summary.json` has `failed` 0 and every judge summary has `errors` 0 (task 10.1). |
| `fsfull-e8b-c512` | 8 h | about 4 h | `ok`. 49,506 files. The `[rate]` lines give the full-build rate for the budget. |
| `fsfull-seal` | 20 min | 4 min | `ok`. |

- The recheck covers every answer-setup shape: each chunk size, reranker off and 0.6b, hybrid off and on, and the three `-t20k` setups. Chunk sizes 512 and 2048 read the `e4b` samples. The session builds no `e4b-c1024`, so chunk size 1024 reads the smallest index the session builds at that size, `e0.6b-c1024`.
- Full-build estimate: `e4b-c1024` ingested 0.25 s per file on 2026-11-24. `e8b-c512` took 1.16 times as long as `e4b-c1024` on the test session's timing slice. That gives about 0.29 s per file, 4.0 h for 49,506 files. The 8 h timeout is twice that figure.
- Expected total: about 6 h of stages, plus about 15 min for the pod start, the copy, the pull and the stop. That is about $5.60 at $0.89/h. The upper bound is the 15 h cap plus the pull, about $14.
- Hosted calls: 15 recheck stages, each with answers and two judges on two questions, and 100 classifier calls in `gate2-classify`. That is a few cents of OpenRouter spend.
- The rate stages had 40 min each until the re-gate was added (2026-11-24). They took 13 min each, so 35 min still gives more than twice that time.

## Freeze check

The freeze check runs the final code on the RTX 4090 once before the freeze (readiness review S2). The last pod ran commit `0868c308`. The store fixes, OCR off (A6), the answer cap (A7) and file-type routing off (A13) came later. The check uses the same machinery as the test session. Its stages are in `prefreeze/freeze_check_stages.txt`. The results folder is `freeze-check-<UTC date>/`. It needs one extra input, `kinds-recheck-input.json`, for the claim-kind recheck (owner, 2026-11-26).

### Before the go

1. Do steps 1 to 3 of "Before the go" above. `COMMIT` is the freeze candidate. The examples file is the committed `classify-examples.json`.
2. Make sure the GLM-5.3 base URL file `~/.config/omrs/secrets/zai-exp35.base_url` exists, mode 600, one line (amendment A15). The watcher checks its SHA-256 against `plan.json` and sends it to the pod's mode-600 `/root/exp35-work/.zai_env` over ssh standard input. It never prints the value.
3. Make the recheck input (Mac only, reads the owner's gate-2 labels):

```bash
D=~/Development/DATA/omrs/experiments/35-full-rag-benchmark-2026-11-01
uv run --no-sync python prefreeze/kinds_recheck35.py prepare --gate2 "$D/test-session-2026-11-24/gate2" \
  --examples classify-examples.json --out "$D/freeze-check-inputs/kinds-recheck-input.json"
```

4. Run the dry run from the Experiment 35 folder:

```bash
uv run --no-sync python prefreeze/mac_watch35.py --pod-id DRYRUN --commit "$COMMIT" \
  --examples classify-examples.json --stages freeze_check_stages.txt \
  --extra-input "$D/freeze-check-inputs/kinds-recheck-input.json" --dry-run
```

5. Make sure the dry run exits 0, shows no `PROBLEM:` line, lists 91 input files and shows the `/root/exp35-work/.zai_env` step with no value.
6. Make sure the dry run shows `STAGES_FILE=/root/exp35-work/omrs/.../freeze_check_stages.txt` and the folder `freeze-check-<UTC date>`.

### Session

Do the session order above. In step 7, start the watcher with the stages file and a 4.5 h wall cap:

```bash
caffeinate -i uv run --no-sync python prefreeze/mac_watch35.py --pod-id <id> \
  --commit "$COMMIT" --examples classify-examples.json --stages freeze_check_stages.txt \
  --extra-input "$D/freeze-check-inputs/kinds-recheck-input.json" --wall-cap-h 4.5
```

### Stages and times

Times are expected minutes on one RTX 4090, from the 2026-11-24 sessions. The stage timeouts add up to 911 min. The 4.5 h wall cap stops the session first.

| Stages | Expected | What they show |
| --- | ---: | --- |
| `setup`, `context`, `gpulog` | 4 to 23 | The freeze candidate sets up. Both setup checks stop the chain on failure. |
| `dry-resolved`, `check-dry` | 1 | Routing off, OCR off and the 2,048-token cap resolve on the pod. |
| `fs-rate`, `fs-rate-seal`, `check-fs-rate` | 12 | Build rate on the 2,747-file sample, and the chunk count of every file. |
| `s-fb`, `s-bio`, `s-fs` | 10 | The smoke indexes: 10 questions per core dataset. |
| `g2-*-build`, `check-chunks*`, `g2-*-check` | 15 | G2 under the B3 guards. |
| `search-*` | 5 | The reranker-on, hybrid-on setup `e4b-c1024-r0.6b-hon`. |
| `answer-*`, `determinism-*` | 6 | Answers with the cap, then G1 before any judge call (S3). |
| `closedbook-*` | 3 | Both closed-book prompts. |
| `judge-*` | 6 | GLM-5.3 and Clef-Flash. |
| `ragas-*` | 35 | Ragas on the RAG answers and on both closed-book sets. |
| `kinds-*` | 3 | Claim kinds. |
| `kinds-recheck`, `check-kinds-recheck` | 2 | The fixed claim-kind prompt on the 96 gate-2 claims that are not prompt examples, against the owner's gate-2 labels (`recheck/recheck-summary.json`). Informational: this sample informed the fix, so a pass is optimistic. Gate 3 runs on fresh labels after the freeze. The check fails only on a missing kind. |
| `vram8-build`, `vram8-search` | 5 | The 8B embedder and the 8B reranker in one search. |
| `join`, `check-*`, `collect` | 2 | The smoke join and the pass rule. |

- Expected total: about 105 to 125 min of stages, plus about 15 min for pod start, copy, pull and stop. That is about 2.3 h, or about $2.05 at $0.89/h.
- Upper bound: the 4.5 h wall cap plus the pull, about 4.8 h, or about $4.30. If the Mac stops answering, the chain waits up to 2 h more for `PULLED` (about $1.80).
- Hosted calls: 30 RAG answers, 60 closed-book answers, Ragas on 90 answer sets, 30 claim-kind sets and GLM-5.3 on 30 answers. At the section 17 rates per answer this is about $0.80. The 2026-11-24 answers cost about a quarter of the answer rate.
- `analyse35.py` does not run. It has no smoke or dry-run mode, and it refuses before any read while half B is locked.

### Pass rule

The check passes when every stage ends `ok` and each check below holds. Each `check-*` stage tests its row on the pod and prints one line per finding. Paths are under `out/` in the session tarball.

| # | File | Field and value |
| ---: | --- | --- |
| 1 | `dry/freshstack-ingest.txt`, `dry/financebench-ingest.txt` | `resolved.file_type_routing` false, `resolved.ocr_fallback_enabled` false, `resolved.answer_max_output_tokens` 2048, `role_problems` empty |
| 2 | `fsrate/freshstack/e4b-c1024/ingest-summary.json` | `files` equals `samples.fsrate.files` of `prefreeze/fs_chunks_c1024_expected.json` (2,747 files, 6,696 chunks); `failed` empty; no file with 0 chunks |
| 3 | `test-session.log`, `[rate] files` lines of `fs-rate` | Blocks 2 to 14 stay within 20% of each other. Record the total s/file. The 2026-11-24 value was 0.25 s/file. |
| 4 | `s/freshstack/e4b-c1024/ingest-summary.json`, `rb/freshstack/e4b-c1024/ingest-summary.json` | `files` equals `samples.s.files` (386 files, 916 chunks) |
| 5 | `ingest-summary.json` of FinanceBench and BioASQ in `s` and `rb` | `failed` empty; no file with 0 chunks |
| 6 | every `*/*/e*-c*/index-fingerprint.json` (8 files) | `tokenizer.sha256` `83cdf8c3a34f68862319cb1810ee7b1e2c0a44e0864ae930194ddb76bb7feb8d`, `tokenizer.revision` `5cf2132a…` |
| 7 | `s/financebench/e4b-c1024/index-fingerprint.json`, `rb/financebench/e4b-c1024/index-fingerprint.json` | `unpaged_chunks` 0. The seal refused no chunk. |
| 8 | `s/<dataset>/rebuild.json` (3 files) | `ok` true, `setup` `e4b-c1024-roff-hoff`, `mismatches` empty, `incomplete` empty, `questions_compared` 10 |
| 9 | `s/<dataset>/search/e4b-c1024-r0.6b-hon/run1/search-summary.json` and `vram/freshstack/search/e8b-c1024-r8b-hon/run1/search-summary.json` | `closed_missing` empty |
| 10 | `s/<dataset>/{answer,closedbook-own,closedbook-rag}/e4b-c1024-r0.6b-hon/run1/answer-summary.json` (9 files) | `missing` 0, `answered` 10, `closed_missing` empty |
| 11 | `s/finish-reasons.json` | `ok` true: every answered row has a finish reason for each reply, and no reply is above 2,048 output tokens. Record the counts per file (`stop`, `length`). |
| 12 | `s/<dataset>/answer/e4b-c1024-r0.6b-hon/run1/determinism.json` (3 files) | `ok` true |
| 13 | `s/<dataset>/answer/e4b-c1024-r0.6b-hon/run1/judge-chat-summary.json` and `judge-clef_flash-summary.json` (6 files) | `missing` 0, `closed_claims` 0, `not_judged` 0 |
| 14 | `s/<dataset>/{answer,closedbook-own,closedbook-rag}/e4b-c1024-r0.6b-hon/run1/ragas-summary.json` (9 files) | `errors` 0, `not_judged` 0, `unjudged_open` empty |
| 15 | `s/<dataset>/answer/e4b-c1024-r0.6b-hon/run1/claimkinds-summary.json` (3 files) | `closed_missing` empty |
| 16 | `s/join.json` | `ok` true, `smoke` true, `failures` empty |
| 17 | `gpu.csv` | Record the peak `memory.used` during `vram8-search`. The stage `ok` is the pass. |
| 18 | `recheck/recheck-summary.json` | Record the gate figures and the recall and precision per kind. Informational only: the stage `ok` (every claim has a kind) is the pass, never the score. This sample informed the fix, so a pass is optimistic. Gate 3 runs on fresh labels after the freeze. |

### On a failure

Fix forward. Do not re-run the whole check.

1. Read the `STOP:` line or the failed stage in the pulled `test-session.log`.
2. Fix the cause on the Mac. Write a test that fails first, then make it pass.
3. Commit and push the fix. The new commit is the freeze candidate.
4. If only a `check-*` stage failed, and the fix is in the check, run that check on the Mac against the unpacked tarball. Replace `$OUT_DIR` with the unpacked `out` folder. No pod is needed.
5. Otherwise, copy `freeze_check_stages.txt` to `freeze_rerun_stages.txt`. Keep `setup`, `context`, `gpulog`, the failed stages, the stages they read from, and their `check-*` stages. Delete the other lines. For example, a failed `ragas-fs` needs `s-fs`, `search-fs` and `answer-fs` again, because the pod starts empty.
6. Add the new file to `FILES` in `prefreeze/test_session_stages.py`, and run the prefreeze tests.
7. Dry-run it as in "Before the go", with `--stages freeze_rerun_stages.txt`. Then run it on a new pod.
8. To fix on the same pod and keep the finished stages, use "Resume after a failure" below.

### Resume after a failure

Use this when a stage failed, the cause is fixable, and the pod must keep its finished stages.

1. Start the first launch with `--keep-pod-on-fail`. The watcher writes `KEEP_POD_ON_FAIL=1` into `session.env`.
2. Wait for the `POD_KEPT:` line in the chain log. The chain stops without stopping the pod.
3. Check that the watcher pulled every stage tarball of the finished stages. Look for `stage tarball <tag>.tgz pulled` lines.
4. Fix the cause on the Mac. Write a test that fails first, then make it pass.
5. Commit and push the fix. Use the new commit as `COMMIT`.
   Each stage tarball has a `<tag>.tgz.commit` file. It holds the commit that made the tarball.
   A stage made at an older commit runs again, unless you name that commit in step 6.
   Name the old commit only for stages that the fix does not touch.
6. Start the watcher again with the same `--pod-id` and `--stages`. Add `--resume` and the new `--commit`.
   To keep the stages of the old commit, add `--resume-from-commit <old sha>` (the full 40-character SHA).
   The flag needs `--resume`.
7. The watcher writes `RESUME=1` into `session.env`. With the flag, it also writes `RESUME_FROM_COMMIT=<old sha>`.
   It moves the old `test-session.log` aside as `.attempt<k>`.
8. The chain runs the `!` stages and the background launchers again. It skips each stage that has a matching tarball made at the new commit.
   It also skips each matching tarball made at `RESUME_FROM_COMMIT`.
   Every other stage runs again.
9. Read `== <stage>: SKIPPED (resume, done in <tag>.tgz)` for each stage made at the new commit.
   Read `== <stage>: SKIPPED (resume, done in <tag>.tgz at <old sha>, this run is <new sha>; RESUME_FROM_COMMIT)` for each stage kept from the old commit.
   Read `== <stage>: done at <old sha or unknown>, this run is <new sha>: running it again` for each stage that runs again.
   Read the `resumed:` names in the `finish` line at the end.
   `resume-record.jsonl` in the outputs holds one line for each stage kept from the old commit. It is the deviation record for the report (prereg section 20).
10. If a tarball hash does not match, the chain logs `tarball hash mismatch` and runs the stage again.
11. If the pod was deleted, its spare copy is gone. Start a new pod and use `--seed-from` (see "When the Mac goes away").
12. A fresh launch refuses to start when `stage-out/` holds tarballs. Move the folder aside, or use `--resume`.
13. Delete the pod yourself when the run is done or you give up. The watcher never deletes a pod.
14. The layout test `freeze_layout_stages.txt` proves this procedure. It stops once on purpose at `resume-probe` and resumes. About 45 min and $0.70.

### When the Mac goes away

The chain keeps running when the Mac is off. Each finished stage stays on the pod as a tarball. The chain stops the pod after `STOP_GRACE_MIN` minutes without a pull.

1. When the chain ends, it copies three files to the spare folder `/workspace/exp35-stage-out`: `test-session-out.tgz`, `test-session.log` and `test-session-out.tgz.sha256`. The `.sha256` file is last. The spare folder exists only when `/workspace` is a mount.
2. The chain log path is `SESSION_LOG`. The default is `$WORK/test-session.log`.

The pod still runs and the chain still runs:

1. Start the watcher with the same `--pod-id`, `--commit` and `--stages`. Add `--attach`.
2. The watcher uses the earlier results folder. It refuses when `pod-id.txt` names another pod or is missing.
3. The watcher refuses when no tmux session `exp35` runs on the pod. It then prints `KEEP_POD`. The pod and its stage tarballs stay as they are.
4. The watcher does not copy the inputs. It does not write `session.env`. It does not launch the chain.
5. The watcher pulls only the stage tarballs that the results folder does not hold. It then ends as in a normal run.
6. Do not use `--attach` with `--resume` or `--seed-from`.

The pod is stopped, not deleted:

1. Restart the pod from the RunPod console.
2. Start the watcher with `--resume` and the same arguments. Follow "Resume after a failure".

The pod or its volume is lost, and the Mac holds the stage tarballs:

1. Create a new pod. Use its id as `--pod-id`.
2. Leave the old results folder as it is. The watcher never overwrites a folder. On the same day, it makes `test-session-<date>-seed<n>` (the next free `n`) for the new session. `--resume` and `--attach` find the newest folder that recorded their `--pod-id`.
3. Start the watcher with the new `--pod-id`, the same `--commit` and `--stages`. Add `--seed-from <absolute path of the old results folder>`.
4. The watcher checks the SHA-256 of each stage tarball in the old `stage-out/`. A mismatch is a `PROBLEM` and nothing starts.
5. The watcher copies the inputs. It then copies each `<tag>.tgz`, `<tag>.tgz.commit` and `<tag>.tgz.sha256` to the new pod and to the new results folder.
6. The watcher writes `RESUME=1` into `session.env`. It writes `seed-from.txt` into the new results folder. The file names the old folder and lists each seeded tag with its SHA-256 and commit.
7. The chain runs the `!` stages again. For each stage that it skips, it unpacks the tarball first and logs `== <stage>: unpacked <tag>.tgz (seeded)`.
8. To use a newer `--commit`, add `--resume-from-commit <old sha>` only for stages the fix does not touch.
9. Do not use `--seed-from` with `--resume` or `--attach`.

### Off-site copy in Cloudflare R2

The chain uploads each finished stage and the final outputs to a private R2 bucket. A lost pod or a lost Mac then loses no result.

Policy: by owner decision on 2026-11-27, experiment results go to a private R2 bucket. This protects the main run. The data still never goes to a public host.

Before the go:

1. Make sure these RunPod account secrets exist: `r2-exp35-key-id`, `r2-exp35-secret` and `r2-exp35-endpoint`. `create_pod35.py` gives them to the pod as `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` and `R2_ENDPOINT`.
2. Make sure the Mac file `~/.config/omrs/secrets/r2-exp35.env` exists, mode 600. It holds three lines: `R2_ACCESS_KEY_ID=`, `R2_SECRET_ACCESS_KEY=` and `R2_ENDPOINT=`. Never type a value in a command or a chat.
3. Run the dry run. It shows `PROBLEM:` when the file is missing, is not mode 600, or lacks a name.

In the session:

1. The watcher writes `OFFSITE_REQUIRED=1` and `R2_PREFIX=<results folder name>/<pod id>` into `session.env`.
2. The bucket is `omrs-exp35-results`. After each stage, the chain uploads `<tag>.tgz`, `<tag>.tgz.commit` and `<tag>.tgz.sha256` (last) to `<prefix>/stage-out/`.
3. At the end, the chain uploads `test-session-out.tgz`, `test-session.log` and `test-session-out.tgz.sha256` (last) to `<prefix>/final/`.
4. Before the first stage, the chain uploads `<prefix>/probe.txt`. The chain refuses to start (exit 2) when a value is empty or the probe fails. This also proves that `curl` on the pod supports `--aws-sigv4`.
5. Each upload has 3 tries. A copy that fails 3 times goes to `/root/exp35-work/offsite.pending`. The chain retries the list once at the end. It logs `== <stage>: off-site copy FAILED (kept for a retry at the end)` and `== finish: off-site copies failed: <n>`. The keys that still fail are in `offsite-failed.txt` in the outputs.
6. At the end, the watcher reads each `.sha256` object of the stage and final tarballs that the Mac holds. It compares each one with the local file.
7. Read `off-site: <n> stage, <m> final verified in r2://<bucket>/<prefix>`.
8. If you read `!!! OFFSITE_NOT_VERIFIED: <names>`, the last line is `KEEP_POD`. Do not delete the pod. The pod may hold the only copy.
9. `--no-offsite` turns the upload and the check off, for a test or a deliberate local-only run. The summary then reads `off-site: OFF (--no-offsite)`.

If the pod and the Mac copies are both lost, fetch an object by hand. Read the key pair from the key file. Do not type it:

```bash
set -a; . ~/.config/omrs/secrets/r2-exp35.env; set +a
printf 'user = "%s:%s"\n' "$R2_ACCESS_KEY_ID" "$R2_SECRET_ACCESS_KEY" \
  | curl -fsS --aws-sigv4 "aws:amz:auto:s3" -K - -o <tag>.tgz \
    "$R2_ENDPOINT/omrs-exp35-results/<prefix>/stage-out/<tag>.tgz"
```

Then check the file with its `.sha256` object. The watcher does not restore from R2. Use `--seed-from` for a new pod.
