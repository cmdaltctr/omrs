# OMRS OCR workers

This folder holds the isolated OCR engines that OMRS calls for scanned
PDFs, gate-selected PDFs, escalated pages and maths pages. OpenSpec change
`modular-ocr-workers-dots-mocr` sets the layout (design D1 to D9).

```
ocr-workers/
  README.md        this file
  provision.py     provisions one engine: python3 provision.py <engine>
  core/            omrs-ocr-worker-core: protocol, framing, capabilities, engine contract
  engines/
    dots-mocr/     first engine of the default list (llama.cpp, licence gate)
    paddleocr-vl/  second engine of the default list (PaddlePaddle)
```

## How OMRS talks to an engine

Each engine runs as a local subprocess in its own environment. OMRS and the
engine exchange JSON Lines over standard input and standard output:

- OMRS writes one request object per line.
- The engine writes one terminal response object per line. Nothing else goes
  to standard output.
- All logs go to standard error.

The protocol lives in `core/src/omrs_ocr_worker_core/protocol.py`. OMRS keeps
a byte-identical copy in `src/omrs/integrations/ocr_worker/protocol.py`. The
same rule applies to `validation.py`. A test fails if the copies differ by one
byte. Do not make one import the other.

OMRS starts an engine with this command, from the engine folder:

```bash
<OCR_WORKERS_DIR>/engines/<engine>/.venv/bin/python -m omrs_ocr_worker_core
```

The core loads the one engine that the environment registers. An environment
with zero engines, or with more than one, reports itself unavailable.

## Engine list

OMRS reads two settings:

| Setting           | Default                  | Meaning                                  |
| ----------------- | ------------------------ | ---------------------------------------- |
| `OCR_WORKERS_DIR` | empty                    | This folder. Empty makes every engine unavailable. |
| `OCR_ENGINES`     | `dots-mocr,paddleocr-vl` | Ordered engine list. The first available engine serves every OCR dispatch. A later engine serves it only when every engine above is unavailable before dispatch. A list of one engine means no fallback. |

`OCR_ENGINE_PRIMARY` and `OCR_ENGINE_FALLBACK` stay readable as aliases. The
primary is the first entry and the fallback is the second entry. An empty
`OCR_ENGINE_FALLBACK` gives a list of one engine. When `OCR_ENGINES` is also
set in the same source, the list wins. See
[Configuration](../docs/guides/configuration.md#ocr-fallback-and-isolated-engines).

Every engine resolves from `OCR_WORKERS_DIR` and the engine name only.
`OCR_WORKER_COMMAND` and `OCR_WORKER_ENV_DIR` were removed; start-up refuses
either variable.

## Provisioning

Run the provisioning script for each engine you want:

```bash
python3 ocr-workers/provision.py paddleocr-vl
python3 ocr-workers/provision.py dots-mocr --accept-model-licence
python3 ocr-workers/provision.py paddleocr-vl --python 3.11
python3 ocr-workers/provision.py dots-mocr --accept-model-licence --dry-run
```

The script:

1. Rejects an unknown engine name.
2. Stops before it installs anything when the engine needs licence acceptance
   and you did not give `--accept-model-licence`. The error names the licence
   file.
3. Rejects any Python outside `>=3.11,<3.14`.
4. Runs `uv sync --locked` in the engine folder. It never changes the OMRS
   main environment.
5. Runs the engine's `omrs-ocr-fetch` script, if the engine has one, to
   download the pinned files and check their hashes. `--dry-run` skips
   this step.

Do not run `uv sync` from the repository root to provision an engine. That
command installs the OMRS main environment.

### Model cache

Each engine keeps its weights in `<engine folder>/.model-cache/`. This folder
is gitignored. To keep weights outside a worktree, set `OMRS_OCR_MODEL_CACHE`.
Engine `<name>` then uses `$OMRS_OCR_MODEL_CACHE/<name>/`.

## Runtime block

An engine that needs a `llama-server` does not start one. It declares the
server in its `pyproject.toml`. OMRS starts or adopts the server, and the
engine is a client of it. Several OMRS processes share one server. The last
process to leave stops it. A server with no request for 10 minutes stops.

```toml
[tool.omrs-ocr.runtime]
program = "llama.cpp/llama-server"
build = 11941
flags = ["--temp", "0", "-c", "24576", "-np", "1", "--image-min-tokens", "4", "--image-max-tokens", "14400"]

[[tool.omrs-ocr.runtime.files]]
flag = "-m"
path = "models/dots-mocr-Q8_0.gguf"
sha256 = "<64 hex digits>"

[[tool.omrs-ocr.runtime.files]]
flag = "--mmproj"
path = "models/dots-mocr-mmproj-bf16.gguf"
sha256 = "<64 hex digits>"
```

| Key       | Meaning                                                                           |
| --------- | --------------------------------------------------------------------------------- |
| `program` | Path of the `llama-server` binary. Its file name must be `llama-server`.           |
| `build`   | The llama.cpp build number that OMRS requires.                                     |
| `flags`   | Fixed flags, as a list of strings.                                                 |
| `files`   | The model files. Each has a `flag` (`-m` or `--mmproj`), a `path` and a `sha256`.  |

Rules:

1. `program` and every `path` are relative to the engine cache. The cache is
   `$OMRS_OCR_MODEL_CACHE/<engine>`, or `<engine folder>/.model-cache`. An
   absolute path, a `..` part or a link that leaves the cache is refused.
2. `flags` must not hold `--host`, `--port`, `-m`, `--model`, `--mmproj`,
   `-hf`, `--hf-repo`, `--api-key`, `--sleep-idle-seconds`, `--log-file` or a
   flag that starts with `--model-url`. OMRS adds `--host 127.0.0.1` and
   `--port <n>` itself.
3. Before each start, OMRS runs `<program> --version` and compares the build.
   A different build fails with `wrong-build`. OMRS also hashes each declared
   file. A changed file fails with `file-changed`, and the reason names the
   file. OMRS checks hashes at a start, not when it adopts a running server.
4. An engine with no block does not change. PaddleOCR-VL has no block.

OMRS starts the worker with `OMRS_OCR_RUNTIME_URL=http://127.0.0.1:<port>` in
its environment. The worker sends its model requests to that address. If the
server moves to a new port, OMRS restarts the worker with the new address.
The `--capabilities` probe needs no server and starts none.

If a runtime fails before dispatch, the route is unavailable for that request
and the usual fallback rule applies. If the operator presses Stop on a
runtime while a parse runs, OMRS sends that request once to the fallback
route. A worker failure after dispatch stays a structured error with no retry.

To use a server that you run yourself, set `OCR_RUNTIME_URL`. OMRS then
starts nothing and gives that address to every engine that declares a
runtime. The build check still runs. OMRS cannot check model files on an
external server, and the Integrations page says: "External server. Model
files are not checked." One external address serves one llama.cpp engine at a
time. See [Configuration](../docs/guides/configuration.md#local-llamacpp-server).

## Engines

### dots-mocr (first in the default list)

- Runs on llama.cpp. See
  [ADR-113](../docs/adr/113-dots-mocr-runs-on-llama-cpp.md). The engine
  environment holds the worker core, pypdfium2, Pillow and huggingface-hub.
- Model: our GGUF conversion of `rednote-hilab/dots.mocr` at revision
  `e539fbb52280393adc081b289ec597430a0f9031`. The model `dots-mocr-Q8_0.gguf`
  (1.9 GB) and the projector `dots-mocr-mmproj-bf16.gguf` (2.5 GB) come from
  the private Hugging Face repository `cmdaltctr/omrs-ocr-gguf-converted` at a
  pinned commit.
- Runtime: llama.cpp release `b11941` (macOS on Apple silicon, or the Linux
  x86-64 CPU build). The engine declares it in its runtime block, and OMRS
  runs it.
- Pins: `src/omrs_ocr_dots_mocr/pins.py` holds the commit and every SHA-256.
  A test checks that the runtime block holds the same values.
- Needs `--accept-model-licence`. Read `engines/dots-mocr/LICENCE-NOTES.md`
  first. It records clauses 3.3(c), 5.2, 8 and 9 of the model licence.
- Needs a Hugging Face token at provisioning, because the repository is
  private. Run `hf auth login` or set `HF_TOKEN`. The error names both.
- Peak memory 17.3 GiB (worker plus server) over 257 pages in Experiment 41.
  On a machine with little memory, set `OCR_ENGINES=paddleocr-vl`.
- Parses offline. OMRS checks both model file hashes before it starts the
  server.
- An engine provisioned before the move to llama.cpp stops working until you
  provision it again. The fingerprint changed, so the next ingest re-indexes
  each document once.

### paddleocr-vl (second in the default list)

- PaddleOCR-VL 1.6 document pipeline on the CPU PaddlePaddle runtime.
- Apache-2.0. No licence flag.
- `engines/paddleocr-vl/DATA_LOCATIONS.md` names the preserved weight copy.

## Add an engine

A new engine needs one folder and one name in `OCR_ENGINES`. OMRS code does not
change. The stub engine in `tests/fixtures/ocr_worker/stub_engine/` has the
same parts.

1. Create `engines/<name>/`. Use a plain folder name: letters, digits, `.`,
   `_` and `-`.
2. Add `engines/<name>/pyproject.toml` with:
   - `requires-python = ">=3.11,<3.14"`;
   - `omrs-ocr-worker-core` in `dependencies`, with
     `[tool.uv.sources] omrs-ocr-worker-core = { path = "../../core" }`;
   - the model runtime packages;
   - one entry point:
     `[project.entry-points."omrs.ocr_engine"] <name> = "<module>:ENGINE"`;
   - if the model licence adds terms: `[tool.omrs-ocr] licence-file = "..."`
     and `requires-acceptance = true`;
   - if the engine downloads weights: `[project.scripts] omrs-ocr-fetch = "..."`.
   - if the engine needs a `llama-server`: `[tool.omrs-ocr.runtime]` (see
     [Runtime block](#runtime-block)). The engine does not start the server.
3. Add the engine module. Its `ENGINE` object has:
   - `name`: the folder name;
   - `backend_id`: the diagnostic name, for example `dots_mocr`;
   - `declared_packages`: every package whose version changes the output;
   - `pipeline` and `model`: `(identity, revision)` pairs;
   - `parse(pdf, pages) -> list[str]`: one Markdown string per page. Return
     `""` for a page the engine cannot read.
   Import model code inside `parse`, never at module level.
4. Add `engines/<name>/.gitignore` with `.venv/`, `.model-cache/` and
   `.ocr-pages-*`.
5. Run `uv lock` in `engines/<name>/` and commit `uv.lock`.
6. If the licence adds terms, add the licence file that step 2 names.
7. Provision the engine: `python3 ocr-workers/provision.py <name>`.
8. Add `<name>` to `OCR_ENGINES`, for example `OCR_ENGINES=<name>,paddleocr-vl`.
