# Test pod session runbook (Experiment 35, task 9.2)

This runbook is for the operator's agent. The agent creates and deletes the pod with the RunPod MCP tools. `mac_watch35.py` does the work between create and delete. It never creates or deletes a pod.

## Caps and the turn rule

- Stop at 15 h after create, or at $18 total spend (RunPod plus OpenRouter). The first cap reached applies.
- The watcher stops itself at 15.5 h (`--wall-cap-h`). The chain on the pod stops its stages at 15 h.
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
5. Read the pod back with `get-pod`. Compare the image digest, GPU, `/workspace` volume and port `22/tcp` with the JSON.
6. If a value differs, delete the pod at once. Do not start the watcher.
7. Wait for SSH. Read `get-pod` until it shows `publicIp` and the public port mapped to port 22.
8. If SSH has no public port after 15 minutes, delete the pod.
9. Start the watcher as a background task. `caffeinate -i` keeps the Mac awake:

   ```bash
   caffeinate -i uv run --no-sync python prefreeze/mac_watch35.py --pod-id <id> \
     --ssh-host <publicIp> --ssh-port <port> --commit "$COMMIT" --examples <examples.json>
   ```

10. Read the watcher output while it runs. It prints one line for each stage start and end.
11. Read `list-pod-billing` every 2 hours. Add the OpenRouter session spend.
12. If the total spend reaches $18, stop the watcher: `kill -TERM "$(cat <results folder>/watcher.pid)"`.
    The first output line names the results folder. Do not use `pgrep` or `pkill`: they also match the `caffeinate` and `uv` parents.
    The watcher then pulls the outputs and prints `DELETE_POD_NOW`. It ignores a second signal, so the pull finishes.
13. Wait for the watcher to exit. Its last line is `DELETE_POD_NOW <id>`.
14. Delete the pod with `delete-pod` and that id. Do this for every exit code.
15. If the watcher process ended without the `DELETE_POD_NOW` line, delete the pod all the same.
16. Read `list-pods`. Confirm that the pod is gone. If it is not gone, delete it again and read again.
17. Remove nothing else: no other pod, volume, template, secret or SSH key.
18. Read `list-pod-billing` for the real cost of the session.
19. Report the exit code, the `RESULT` line, the results folder and the cost.

## Exit codes

Every code ends with `DELETE_POD_NOW <id>`. Delete the pod for every code.

| Code | Meaning | Extra action |
| ---: | --- | --- |
| 0 | `TEST_SESSION_DONE`, outputs pulled, SHA-256 matches | None. |
| 1 | Internal error in the watcher | Report the error line. |
| 2 | Refused before any remote step | Fix the `REFUSED:` line on the Mac before the next pod. |
| 3 | `POD_STOP_FAILED`: the pod did not stop itself | Delete at once. The GPU still bills. |
| 4 | No SSH within 15 minutes | Report it. |
| 5 | A pod setup step failed (copy, SHA-256, clone, launch) | Report the `remote step failed` line. |
| 6 | A `STOP:` line in the chain log | Read the `STOP:` line in the pulled log. Fix on the Mac. |
| 7 | The tmux session ended without `TEST_SESSION_DONE` | Read the end of the pulled log. |
| 8 | No new log byte for 30 minutes | Read the last stage in the pulled log. |
| 9 | Wall-clock cap reached | Report the stages that did not run. |
| 10 | No SSH for 10 minutes while watching | Outputs are probably lost. Report it. |
| 11 | The pull failed, or the SHA-256 differs | Keep the files as they are. Report it. |
| 12 | Stopped by a signal (SIGTERM, SIGINT or SIGHUP) | Report why you stopped it. |

## Where the results go

- The watcher writes `~/Development/DATA/omrs/experiments/35-full-rag-benchmark-2026-11-01/test-session-<UTC date>/`. It never overwrites an existing folder.
- The folder name comes from the stages file: `verify_session_stages.txt` gives `verify-session-<UTC date>/`.
- The folder holds `inputs/`, `watcher.pid`, `test-session.log`, `watch-summary.txt` and the outputs tarball with its `.sha256`.
- `inputs/` holds the inputs tarball, its `.sha256`, the examples and the `--extra-input` file, exactly as sent to the pod.
- The outputs tarball is `test-session-out.tgz` from the chain. If the chain wrote none, it is `watcher-out.tgz`, packed from `/workspace/exp35-test/out`.
- Record the copy and its SHA-256 in `DATA/omrs/DATA_LOCATIONS.md`.

## Fix check variant

The fix check session checks the four fixes of 2026-11-24 on a short second pod. It uses the same machinery: `pod_setup35.sh`, `launch35.sh`, the `pod_test_session.sh` chain and `mac_watch35.py`. The chain stops the pod only after the last check ends and the Mac has pulled the outputs.

- The stages are in `prefreeze/verify_session_stages.txt`. The watcher writes `STAGES_FILE` into `/workspace/session.env`, and `launch35.sh` reads it.
- Every stage runs at `COMMIT`. No stage checks out another commit.
- Section 4 needs the FinanceBench answers of the 2026-11-24 session. The watcher sends them as `--extra-input`.

### Before the go

1. Do steps 1 to 3 of "Before the go" above.
2. Cut the FinanceBench answers (about 1 MB) out of the session tarball:

   ```bash
   cd ~/Development/DATA/omrs/experiments/35-full-rag-benchmark-2026-11-01/test-session-2026-11-24
   tar -czf "$TMPDIR/fb-answers.tgz" --include 'out/s/financebench/answer' \
     --include 'out/s/financebench/closedbook-rag' --include 'out/s/financebench/rebuild.json' \
     @test-session-out.tgz
   ```

3. Run the dry run with the two extra options:

   ```bash
   uv run --no-sync python prefreeze/mac_watch35.py --pod-id DRYRUN --ssh-host 203.0.113.1 \
     --ssh-port 22 --commit "$COMMIT" --examples <examples.json> \
     --stages verify_session_stages.txt --extra-input "$TMPDIR/fb-answers.tgz" --dry-run
   ```

4. Make sure the dry run exits 0, lists 91 input files, and shows `fb-answers.tgz` in the SHA-256 check.
5. Make sure the dry run shows `STAGES_FILE=/workspace/omrs/.../verify_session_stages.txt` and the folder `verify-session-<UTC date>`.

### Session

Do the session order above. In step 9, start the watcher with the two extra options:

```bash
caffeinate -i uv run --no-sync python prefreeze/mac_watch35.py --pod-id <id> \
  --ssh-host <publicIp> --ssh-port <port> --commit "$COMMIT" --examples <examples.json> \
  --stages verify_session_stages.txt --extra-input "$TMPDIR/fb-answers.tgz"
```

### Stages, times and pass marks

The sections run in the order 1, 3, 4, 2: the cheapest and the budget-critical checks first. Times are expected minutes on one RTX 4090.

| Stage | Section | Timeout | Expected | Pass mark |
| --- | --- | ---: | ---: | --- |
| `setup` | Setup (as the test session) | 60 min | 23 min | `ok`. A failure stops the chain. |
| `ocr-walmart-20x` | 1. OCR fix (0bebdb1d) | 105 min | 25 min | `20/20 passes`: 29 pages each, each pass under 300 s. |
| `fs-rate-1200` | 3. Store speed (bcd11389) | 60 min | 25 min | `ok`. The six `[rate] files` lines stay flat in s/file. |
| `fb-unpack` | 4. Answers copy | 10 min | 1 min | `ok` (87 files). |
| `ragas-closedbook-fb` | 4. Closed-book Ragas (b98f536f) | 20 min | 5 min | `ok`, with no exit 6. |
| `kinds-fb-c512` | 4. Claim kinds (b98f536f) | 15 min | 4 min | `ok`. |
| `fs-c2048-ingest` | 2. Reranker fix (eb70e807) | 50 min | 8 min | `ok`. |
| `fs-c2048-seal` | 2. | 15 min | 2 min | `ok`. |
| `fs-c2048-r0.6b` | 2. | 30 min | 3 min | `ok`, queries 76293427 and 77759618 included. |
| `fs-c2048-r4b` | 2. | 30 min | 8 min | `ok`, as above. |
| `fs-c2048-r8b` | 2. | 30 min | 14 min | `ok`, as above. |

- Expected total: about 118 min of stages, plus about 10 min for the pod start, the copy, the pull and the stop. That is about 2.2 h, or about $1.96 at $0.89/h.
- Upper bound: the stage timeouts add up to 425 min (7.1 h). With the start and the pull, that is about 7.3 h, or about $6.50.
- Hosted calls (Ragas on 20 questions, claim kinds on 20 answers) add a few cents of OpenRouter spend.
- Pass mark of the whole check (2026-11-24 notes): every stage `ok`, and the per-file store time flat.
- Store speed for the budget: the `[rate] files` lines give seconds per file for each block of 200 files. Block 1 includes the engine start. The old rate was about 2 s per file at 3,300 files.
