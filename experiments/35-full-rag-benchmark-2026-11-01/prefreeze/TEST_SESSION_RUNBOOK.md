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
- The folder holds `inputs/`, `watcher.pid`, `test-session.log`, `watch-summary.txt` and the outputs tarball with its `.sha256`.
- `inputs/` holds the inputs tarball, its `.sha256` and the examples, exactly as sent to the pod.
- The outputs tarball is `test-session-out.tgz` from the chain. If the chain wrote none, it is `watcher-out.tgz`, packed from `/workspace/exp35-test/out`.
- Record the copy and its SHA-256 in `DATA/omrs/DATA_LOCATIONS.md`.
