# Design

## Context

See proposal.md, "Why", for the motivation. The current state that shapes the approach:

- **Engines are folders.** The host builds `<workers dir>/engines/<name>/.venv/bin/python -m omrs_ocr_worker_core` and never branches on engine names (`src/omrs/integrations/ocr_worker/routes.py`).
  - A worker is one subprocess that reads JSON Lines on standard input.
  - The host closes a worker with SIGTERM, then SIGKILL (`client.py`, `close`).
  - The client pool runs one parse at a time per engine (`pool.py`).
- **The PyTorch engine** (`ocr-workers/engines/dots-mocr/`) has these parts:
  - `engine.py`: renders a page with pypdfium2 at 200 DPI, with a long side of at least 1,600 px, sends the upstream `prompt_layout_all_en` prompt, and caps output at 8,192 new tokens.
  - `layout.py`: turns the layout JSON into Markdown. It is pure Python.
  - `fetch.py` and `patches.py`: download the pinned revision and patch the model code.
  - **Pure parts:** `layout.py`, the prompt and the render step need no PyTorch.
- **The engine fingerprint feeds every document's index identity** (`core/ingestion/source_state.py`). Changing the backend re-indexes documents on their next ingest.
- **The app's managed llama.cpp server** (`transports/api/llamacpp_server.py`) has three limits:
  - It lives in the web transport only.
  - It serves one chat server.
  - It accepts only a binary named `llama-server`, with fixed flags (no `--mmproj`).

  So it cannot serve an OCR worker.
- **Experiment 41 arm D4** gives the evidence:
  - Setup: llama.cpp build 11941 with our Q8_0 conversion, the bf16 projector, and the flags `--temp 0 -c 24576 -np 1`.
  - Text: it matched the PyTorch backend (median Dice 1.00).
  - Memory: peak client plus server was 17.3 GiB.
  - Speed: the T-control showed no speed gain.

## Goals / Non-Goals

**Goals:**

- Run dots.mocr with no PyTorch in any OCR engine environment.
- Keep the text output as close to the PyTorch backend as Experiment 41 measured.
- Make the runtime and model files reproducible: pinned, hashed, and owned by the engine folder.
- Switch with one setting before cut-over, and roll back the same way.

**Non-Goals:**

- Faster OCR. Experiment 41 showed no gain, and this change does not chase one.
- Any change to PaddleOCR-VL, the protocol, the host, or the settings keys.
- Sharing the llama.cpp server with chat or decision models.
- Windows support, and testing on Linux hardware. The Linux binary is pinned but runs untested.
- Publishing the converted model. The repository stays private (licence clause 4.4).

## Decisions

### D1. A new engine folder for the transition, renamed to `dots-mocr` at cut-over

- **During the transition:** the new engine lives in `ocr-workers/engines/dots-mocr-llamacpp`, with package `omrs_ocr_dots_mocr_llamacpp` and entry point `dots-mocr-llamacpp`. The operator switches with `ocr_engine_primary = "dots-mocr-llamacpp"`.
- **At cut-over:**
  - Delete the PyTorch folder.
  - Move the new folder to `engines/dots-mocr`.
  - Rename the package to `omrs_ocr_dots_mocr` and the entry point to `dots-mocr`.
- Settings that name `dots-mocr`, the default included, keep working after one re-provision.
- **Rejected: a backend switch inside the existing folder.** PyTorch would stay in that lockfile until cut-over, and one environment would carry two runtimes.
- **Rejected: keeping the new name for good.** It would break every saved `ocr_engine_primary = "dots-mocr"` and change the docs for no benefit.

### D2. The worker owns its llama.cpp server

- **Start:** the engine starts `llama-server` as a child process on the first parse.
- **Reuse:** it reuses the server for the life of the worker.
- **Stop:** it stops the server on SIGTERM and on normal exit.
- The host stays engine-agnostic.
- **Rejected: the host's `LlamacppServer`.** It lives in the web transport, so the CLI and MCP could not use it. It also has fixed flags and serves one chat server.
- **Rejected: an external server URL**, such as the Llama app router on port 9931. That router keeps one model loaded (`--models-max 1`), so OCR would unload the chat and embedding models. It also puts the OCR result outside the pinned build.

### D3. A pinned llama.cpp release, fetched at provisioning

- Provisioning downloads `llama-b11941-bin-macos-arm64.tar.gz` (or `-ubuntu-x64` on Linux) from the `ggml-org/llama.cpp` GitHub release `b11941`.
- It checks the archive against a pinned SHA-256, then unpacks it into `<engine cache>/llama.cpp/`.
- The engine reads the server's reported build and refuses anything other than 11941.
- **Rejected: the system `llama-server`.** Homebrew updates it (build 11960 on this machine), which would change the output and the fingerprint without warning. Gotcha 16 records build-specific Metal fixes.
- **Rejected: the Llama app binary.** It is a different program (`llama serve`) and is not on every machine.
- macOS x64 and Windows are not pinned.

### D4. Our own conversion, from a private Hugging Face repository

- The fetch step downloads `dots-mocr-Q8_0.gguf` (SHA-256 `6017b184…`) and `dots-mocr-mmproj-bf16.gguf` (SHA-256 `63f415f9…`) from `cmdaltctr/omrs-ocr-gguf-converted`, at a pinned commit. It checks both hashes.
- The model card names the source: `rednote-hilab/dots.mocr` at `e539fbb5`, converted and quantised with llama.cpp build 11941.
- **Rejected: `lodrick-the-lafted/dots.mocr-gguf`.** Its tensors match ours, but the operator does not control it, and its projector was never compared.
- **Rejected: converting at provisioning.** The llama.cpp converter needs PyTorch, which defeats the change.
- **Cost:** a private repository needs a Hugging Face token at provisioning. The error message names `hf auth login` and `HF_TOKEN`.

### D5. Same request and server flags as Experiment 41 arm D4

- **Server:** `llama-server -m <model> --mmproj <projector> --host 127.0.0.1 --port <free> --temp 0 -c 24576 -np 1 --image-min-tokens 4 --image-max-tokens 14400`.
  - The image-token flags do nothing on build 11941 (Experiment 41, OI-10). They stay so the command matches the evidence.
- **Request:** one OpenAI-style chat request per page to `/v1/chat/completions`:
  - the PNG as a base64 `image_url`, then the prompt;
  - `temperature 0`, `max_tokens 8192`, `stream false`.
- **Token cap:** a page counts as capped when `usage.completion_tokens` is 8,192 or more. A capped page returns empty Markdown, as the PyTorch backend does.

### D6. Copy the pure code, and pin the copies during the transition

- The new package copies the prompt, the render settings and `layout.py` from the PyTorch engine.
- A test asserts that the two copies are identical until cut-over, in the same way the protocol copy test works. Afterwards one copy remains.
- **Rejected: importing the PyTorch engine package.** That would pull its PyTorch dependencies into the new environment.

### D7. Fingerprint

| Field | Value |
| --- | --- |
| `backend_id` | `dots_mocr_llamacpp` (kept after the rename, because it names the backend) |
| `model` | (`cmdaltctr/omrs-ocr-gguf-converted`, `<commit>`) |
| `pipeline` | (`dots-mocr-layout`, `prompt_layout_all_en+llamacpp-b11941+q8_0+layout-1`) |
| `declared_packages` | worker core, engine, `pypdfium2`, `pillow` |

A change of build, quantisation or converter version changes the pipeline revision, so indexes stay honest.

### D8. Server lifecycle details

- **Port:** bind a socket to port 0 to get a free loopback port, release it, and pass it to the server. If the server fails to bind, retry once with a new port.
- **Health:** poll `/health` every 0.5 s, for up to 180 s.
- **Log:** server output goes to `<engine cache>/llama-server.log`, capped at 1 MB and rotated once.
- **Stop:** SIGTERM to the server, wait 10 s, then SIGKILL. A SIGTERM handler and `atexit` both call the stop.
- **Stale server:** a pid file `<engine cache>/llama-server.pid` records the pid and the binary path. At start, if that pid is alive and its command line holds the engine's own binary path, the engine stops it. Any other pid is left alone.

### D9. The real-document check before cut-over

The check runs through the app's OCR path (`build_ocr_routes` with primary `dots-mocr-llamacpp`), not the experiment client. Evidence goes to the engine's `SMOKE_RESULTS.md` and `smoke_evidence/`.

1. **Parity.** Use the 20 T-control pages from Experiment 41, plus `eq01` p2 and p3. Compare with Experiment 41 arm D4, which used the same model, build and flags:
   - each page Dice 0.99 or more;
   - at least 18 of the 22 pages identical.

   Compare with the PyTorch text (T-control):
   - median Dice 0.99 or more.
2. **End to end.** Ingest three real PDFs into a scratch collection with the CLI, using scratch `LANCEDB_URI` and `OMRS_CONFIG_DIR`. Never use `~/.omrs`. The three PDFs:
   - `eq01` (maths);
   - `io06` (scanned Latin);
   - `rf06` (Spanish handwriting).

   The checks:
   - Search finds a known phrase from an OCR page of each PDF.
   - KaTeX 0.16.22 renders every formula on the `eq01` pages.
3. **App view.** The Integrations page lists `dots-mocr-llamacpp` as ready. Browser check at 1,280 px and 390 px.
4. **Clean exit.** After the CLI exits and after the web app stops, no llama.cpp process started by the engine is left.
5. **Record.** Seconds per page, peak memory of the worker plus the server, and the llama.cpp build.

The operator reads the results and confirms before cut-over. A failed rule stops the change at this point. It does not loosen the rule.

## Risks / Trade-offs

- [Switching re-indexes every document in each collection] → Recorded in the proposal and the docs. The operator chooses when to switch, and the switch is one setting.
- [A killed worker leaves a server holding about 17 GiB] → The pid-file clean-up in D8. A test kills a worker and checks that the next start stops the old server.
- [The private repository blocks provisioning on a machine without a token] → The error names `hf auth login` and `HF_TOKEN`. Making the repository public is a later operator decision.
- [Gatekeeper blocks the downloaded binary on macOS] → Python downloads carry no quarantine attribute. The smoke test runs the binary, and the error message names `xattr -d com.apple.quarantine` if it is blocked.
- [The Linux binary runs untested, and it is a CPU build] → Recorded as a limit. CI tests the engine against a fake server only.
- [Memory pressure when the chat and decision models also run] → The peak of 17.3 GiB is recorded in the docs. The server lives only as long as its worker.
- [A new llama.cpp build is needed later] → It goes in a new change: a new pin, a new pipeline revision and a re-index. The build check refuses a silent upgrade.
- [Transition-period code copies drift] → The D6 test fails on any difference.

## Migration Plan

1. **Build:** add `dots-mocr-llamacpp` beside `dots-mocr`. The default stays `dots-mocr` on PyTorch.
2. **Provision and check:** provision the new engine, then run the D9 check.
3. **Operator confirms.** Before that, rollback is to set `ocr_engine_primary` back to `dots-mocr`.
4. **Cut over:** remove the PyTorch engine, rename the folders (D1), update the tests, docs and specs, and write the ADR.
5. **Live app:** provision the new engine in `~/.omrs/ocr-workers`, with operator approval. The next ingest re-indexes.
6. **Rollback after cut-over:** revert the cut-over commit and re-provision the PyTorch engine. Its model cache copy stays in `~/Development/DATA/omrs`. That re-indexes again.

## Open Questions

- **Which Linux tarball:** the CPU build or the Vulkan build. This is deferrable, because macOS arm64 is the only validated platform and either pin fits D3.
