# Spike 1.5: preset keys and router flags in llama.cpp b11941

| Item | Value |
| --- | --- |
| Change | `one-llamacpp-router`, task 1.5 |
| Build | llama.cpp b11941, `llama-server` reports `version: 0.7.0-dev (build 11941, commit 19ff817fb)` |
| Commit | `19ff817fb25e9a1b838b1d7f9f4325f7bf9779c4` (tag `b11941`, from `gh api repos/ggml-org/llama.cpp/git/ref/tags/b11941`) |
| Archive | `llama-b11941-bin-macos-arm64.tar.gz`, SHA-256 `fb5c491b35c75731019caa85d704fb839532c15dbb9bd3f6b3f75a667e7ac49a` (rechecked, matches `release-digests.txt`) |
| Help text | `<scratch>/llama-b11941/help-b11941.txt`, 753 lines, SHA-256 `649ca487aced48d55b6ce3f4dca02923380887c262a65d5c939171b30dd6a61f` |
| Source | `common/arg.cpp` (SHA-256 `fc09d12a...e2ed`, 4856 lines) and `tools/server/server-models.cpp` (SHA-256 `93af5921...aca2`, 2792 lines), read at ref `b11941` with `gh api .../contents/<path>?ref=b11941` |
| Date | 2026-11-06 |

## How obtained

1. Read `llama-server --help` output (file above). "help N" below means a line number in that file.
2. Read the two source files at tag b11941. "arg N" means `common/arg.cpp` line N. "sm N" means `tools/server/server-models.cpp` line N.
3. Parser probes. No server was started. Each probe ran the binary with the flag under test, then `--version`. Arguments parse in order, so a bad value fails before `--version` exits.
4. INI probes. No server was started. `llama-server` reads `${XDG_CONFIG_HOME:-~/.config}/llama.cpp/config.ini` through the same `common_preset_context::load_from_ini` code the router uses (arg 730-774). I wrote one key per probe to a scratch `config.ini`, ran `env -i HOME=<scratch>/spike15-home XDG_CONFIG_HOME=<scratch>/spike15-xdg llama-server --version`, and read the exit code. The scratch folders were deleted afterwards. This path calls `apply_to_params`. The router child path calls `to_args` instead (sm 322). `to_args` lives in `common/preset.cpp`, which this spike did not read (outside the brief).

Probe results (exit code, message):

| Input | Result |
| --- | --- |
| `--spec-type none` | 0 |
| `--spec-type ngram-mod,draft-mtp` | 0 |
| `--spec-type bogus` | 1, `unknown speculative type: bogus` |
| `--cache-type-k q4_1` | 0 |
| `--cache-type-k bogus` | 1, `Unsupported cache type: bogus` |
| `--parallel 0` | 1, `invalid value for n_parallel` |
| `--flash-attn true`, `--flash-attn -1` | 0 (aliases accepted) |
| `--fit auto` | 1, `unknown value for --fit: 'auto'` |
| `--n-gpu-layers 999` | 0 |
| `--embd-normalize 5` | 0 |
| `--sleep-idle-seconds 0` | 1, `cannot be 0 or less than -1` |
| `--pooling foo` | 1, `invalid value` |
| INI `c = 4096` | 0 (short name works as a key) |
| INI `ctx-size = abc`, `LLAMA_ARG_CTX_SIZE = abc` | 1 (long name and env name both recognised as keys) |
| INI `n-gpu-layers`, `gpu-layers`, `ngl`, `batch-size`, `ubatch-size`, `embd-normalize`, `cache-reuse`, `image-min-tokens`, `image-max-tokens` `= abc` | 1, `stoi: no conversion` (all keys recognised) |
| INI `parallel = 0`, `pooling = foo`, `cache-type-k = bogus`, `flash-attn = bogus`, `fit = auto`, `spec-type = bogus`, `sleep-idle-seconds = 0` | 1 (same errors as the CLI) |
| INI `cache-type-v = q5_1`, `spec-type = none` | 0 |
| INI `kv-unified = false`, `cache-prompt = off`, `embeddings = false` | 0 |
| INI `kv-unified = bogus`, `kv-unified = 2`, `cache-prompt = maybe`, `embeddings = bogus`, `embedding = bogus` | 0 (no error: bad boolean values are not refused on this path) |
| INI `no-kv-unified = true`, `no-cache-prompt = true` | 0 (not conclusive: this path sets `ignore_unknown_keys = true`, arg 763) |

## Boolean value forms (source)

- `is_truthy`: `on`, `enabled`, `true`, `1`. `is_falsey`: `off`, `disabled`, `false`, `0`. `is_autoy`: `auto`, `-1` (arg 1345-1355).
- From the environment, a two-way flag (`--x` / `--no-x`) runs `parse_bool_value`, which throws on any other word (arg 333-341, 806-807).
- From the environment, a one-way flag (no negation, for example `--embeddings`) runs only when the value is truthy (arg 800-801). A falsey value does nothing.
- On the CLI, a two-way flag takes no value; the spelling chooses true or false (arg 858-860).
- `LLAMA_ARG_NO_<NAME>` set in the environment counts as false for two-way flags (arg 127-135).

## Per-key table

INI key: the router reads `models.ini` with `load_from_ini` (sm 742). Keys are the long flag name without `--` (probes above). The short name and the env name also work. The router keeps options by env name (sm 269-284 use env names).

| Key (D4) | b11941 flag spelling | Short | Env var | Type / accepted values | b11941 default | INI line form | D4 type | Match |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ctx-size` | `--ctx-size N` | `-c` | `LLAMA_ARG_CTX_SIZE` | int; 0 = from model; no range check (arg 1649-1659) | 0, from model (help 25-26) | `ctx-size = 16384` | int 512 to 262,144 | Yes (D4 is a subset; 0 left out, omit key for model value) |
| `batch-size` | `--batch-size N` | `-b` | `LLAMA_ARG_BATCH` | int; no range check (arg 1679-1685) | 2048 (help 29-30) | `batch-size = 2048` | int 32 to 65,536 | Yes |
| `ubatch-size` | `--ubatch-size N` | `-ub` | `LLAMA_ARG_UBATCH` | int; no range check (arg 1686-1692) | 512 (help 31-32) | `ubatch-size = 512` | int 32 to 65,536, at most `batch-size` | Yes |
| `parallel` | `--parallel N` | `-np` | `LLAMA_ARG_N_PARALLEL` | int; 0 refused; -1 = auto (arg 2555-2564) | -1, auto (help 468-469) | `parallel = 1` | int 1 to 16 | Yes (D4 leaves out -1 auto; omit key for auto) |
| `embeddings` | `--embedding`, `--embeddings` | none | `LLAMA_ARG_EMBEDDINGS` | one-way flag, no `--no-embeddings` (arg 3525-3531) | disabled (help 594-596) | `embeddings = true` | boolean | Partly, see mismatch 1 |
| `pooling` | `--pooling {none,mean,cls,last,rank}` | none | `LLAMA_ARG_POOLING` | enum `none`, `mean`, `cls`, `last`, `rank` (arg 2324-2335) | model default (help 466-467) | `pooling = mean` | same enum | Yes |
| `embd-normalize` | `--embd-normalize N` | none | none (no `set_env`, arg 3320) | int; -1 none, 0 max abs int16, 1 taxicab, 2 euclidean, >2 p-norm; no range check (arg 3314-3320) | 2 (help 510-511) | `embd-normalize = 2` | -1, 0, 1, 2 | Yes (subset; p-norm left out). Key works in INI despite no env var (probe) |
| `kv-unified` | `--kv-unified` / `--no-kv-unified` | `-kvu` / `-no-kvu` | `LLAMA_ARG_KV_UNIFIED` | two-way boolean (arg 1735-1742) | enabled if slots auto (help 450-453) | `kv-unified = true` or `kv-unified = false` | boolean | Yes, see mismatch 2 for value form |
| `flash-attn` | `--flash-attn [on\|off\|auto]` | `-fa` | `LLAMA_ARG_FLASH_ATTN` | truthy, falsey or autoy word (arg 1766-1780) | `auto` (help 39-40) | `flash-attn = on` | `on`, `off`, `auto` | Yes (b11941 also takes `true`, `1`, `-1` and others) |
| `n-gpu-layers` | `--n-gpu-layers N`, also `--gpu-layers` | `-ngl` | `LLAMA_ARG_N_GPU_LAYERS` | `auto`, `all` or any int via `stoi` (arg 2810-2827) | `auto` (help 135-137) | `n-gpu-layers = all` | int 0 to 999, `all`, `auto` | Yes (subset) |
| `fit` | `--fit [on\|off]` | `-fit` | `LLAMA_ARG_FIT` | truthy or falsey word; `auto` refused (arg 2889-2902, probe) | `on` (help 152-154) | `fit = off` | `on`, `off` | Yes |
| `cache-type-k` | `--cache-type-k TYPE` | `-ctk` | `LLAMA_ARG_CACHE_TYPE_K` | `f32`, `f16`, `bf16`, `q8_0`, `q4_0`, `q4_1`, `iq4_nl`, `q5_0`, `q5_1` (arg 304-323, 2448-2460) | `f16` (help 75-78) | `cache-type-k = f16` | 5 types | Subset, see mismatch 3 |
| `cache-type-v` | `--cache-type-v TYPE` | `-ctv` | `LLAMA_ARG_CACHE_TYPE_V` | same 9 types (arg 2461-2473) | `f16` (help 79-82) | `cache-type-v = f16` | 5 types | Subset, see mismatch 3 |
| `cache-prompt` | `--cache-prompt` / `--no-cache-prompt` | none | `LLAMA_ARG_CACHE_PROMPT` | two-way boolean (arg 3622-3629) | enabled (help 618-619) | `cache-prompt = false` | boolean | Yes, see mismatch 2 for value form |
| `cache-reuse` | `--cache-reuse N` | none | `LLAMA_ARG_CACHE_REUSE` | int; no range check; needs prompt cache on (arg 3630-3639) | 0 (help 620-623) | `cache-reuse = 0` | int 0 to 65,536 | Yes |
| `image-min-tokens` | `--image-min-tokens N` | none | `LLAMA_ARG_IMAGE_MIN_TOKENS` | int; no range check (arg 2649-2655) | read from model (help 490-492) | `image-min-tokens = 256` | int 1 to 65,536 | Yes |
| `image-max-tokens` | `--image-max-tokens N` | none | `LLAMA_ARG_IMAGE_MAX_TOKENS` | int; no range check (arg 2656-2662) | read from model (help 493-495) | `image-max-tokens = 1024` | int 1 to 65,536 | Yes (D4 has no min at most max rule) |
| `spec-type` (not in D4) | `--spec-type LIST` | none | `LLAMA_ARG_SPEC_TYPE` | comma list of `none`, `draft-simple`, `draft-eagle3`, `draft-mtp`, `draft-dflash`, `draft-dspark`, `ngram-simple`, `ngram-map-k`, `ngram-map-k4v`, `ngram-mod`, `ngram-cache`; values append to the list (arg 4329-4338); repeating the flag gives no warning (arg 841) | `none` (help 390-394) | `spec-type = none` | not listed | See mismatch 4 |

## Mismatches with design D4

1. **`embeddings` is a one-way flag, not a boolean.** b11941 has `--embeddings` but no `--no-embeddings` (arg 3525-3531). From the environment, `false` does nothing (arg 800-801). On the INI path, `embeddings = false` and `embeddings = bogus` both pass with no error (probe). I could not confirm what the router's `to_args` emits for `embeddings = false`. If it emits the bare flag, a "false" entry would turn embeddings on.
   Proposed correction: keep the D4 type as boolean in the API, but the writer writes `embeddings = true` only, and leaves the key out for false. Add a test that `false` writes no line.

2. **Bad boolean words are not refused on the INI path.** `kv-unified = bogus`, `kv-unified = 2` and `cache-prompt = maybe` load with exit code 0 (probe), while the env path throws on the same words (arg 333-341). So llama.cpp will not catch a bad boolean in `models.ini`. b11941 accepts eight words: `on`, `enabled`, `true`, `1`, `off`, `disabled`, `false`, `0` (arg 1345-1351).
   Proposed correction: D4 states that the writer writes booleans as exactly `true` or `false`, and the API accepts only JSON booleans. Negated keys (`no-kv-unified`, `no-cache-prompt`) are never written.

3. **Cache type list is shorter than b11941's.** b11941 accepts nine types: `f32`, `f16`, `bf16`, `q8_0`, `q4_0`, `q4_1`, `iq4_nl`, `q5_0`, `q5_1` (arg 304-314, help 76, 80). D4 allows five. Every D4 value is accepted, so nothing D4 allows is refused.
   Proposed correction: choose one.
   1. Keep the five and add one line to D4: "deliberate subset of the nine b11941 types".
   2. Add `q4_1`, `iq4_nl`, `q5_0`, `q5_1` to match b11941.

4. **`spec-type` values are now confirmed.** D4 says the values are not confirmed for b11941. They are: `none`, `draft-simple`, `draft-eagle3`, `draft-mtp`, `draft-dflash`, `draft-dspark`, `ngram-simple`, `ngram-map-k`, `ngram-map-k4v`, `ngram-mod`, `ngram-cache` (help 390). Default `none`. The value is a comma list and is appended to the current list (arg 4334-4336). `spec-type = none` loads on the INI path (probe).
   Proposed correction: choose one.
   1. Add `spec-type` to the allow-list as a single enum value `none` only. That is all the sweep needs (pipeline-sweep D6a pins `spec-type=none`). Refuse comma lists.
   2. Leave it out of the list and update the D4 sentence to "values confirmed in spike 1.5; left out because the sweep's `none` equals the default".

5. **Reserved key list differs (see next section).** The router strips `connect` and `connect-code`, which D4's "never written" list does not name. D4 names `sleep-idle-seconds`, `log-file` and `model-url`, which the router does not strip from a model preset. The allow-list already blocks all of these, so there is no gap in practice.
   Proposed correction: add `connect`, `connect-code` to the "never written" list for completeness, and note that `sleep-idle-seconds`, `log-file` and `model-url` are valid per-model keys in b11941 that OMRS chooses not to write.

6. **Ranges are narrower than b11941 for some keys.** No value D4 allows is refused. Values b11941 accepts that D4 leaves out: `ctx-size = 0` (from model), `parallel = -1` (auto), `embd-normalize` above 2 (p-norm), negative `n-gpu-layers`. Each default is reached by leaving the key out, so OMRS loses nothing.
   Proposed correction: none needed. Optionally add to D4: "leave the key out to get the model or auto default".

7. **Gap not in D4: llama-server reads a user config file.** Before env vars and CLI flags, llama-server loads `/etc/llama.cpp/config.ini` and `${XDG_CONFIG_HOME:-~/.config}/llama.cpp/config.ini` (arg 730-774, 782-783). The probes confirmed it: every run logged `using config file`. Router children get the router's environment (sm 399, `base_env(get_environment())`). A file on the user's machine could change the router and every model without OMRS knowing.
   Proposed correction: in the router's minimal child environment, set `XDG_CONFIG_HOME` to an empty folder under `<state>/runtimes/router/`. Add a test that the router environment holds it. `/etc/llama.cpp/config.ini` cannot be moved this way; record it as a known limit.

## Reserved keys

From `unset_reserved_args` (sm 268-286).

Stripped from every model preset (sm 314, `unset_model_args = false`) and from the router's own args (sm 404):

`ssl-key-file`, `ssl-cert-file`, `api-key`, `api-key-file`, `models-dir`, `models-max`, `models-memory-margin`, `models-preset`, `models-autoload`, `connect`, `connect-code` (by env names `LLAMA_ARG_SSL_KEY_FILE`, `LLAMA_ARG_SSL_CERT_FILE`, `LLAMA_API_KEY`, `LLAMA_ARG_API_KEY_FILE`, `LLAMA_ARG_MODELS_DIR`, `LLAMA_ARG_MODELS_MAX`, `LLAMA_ARG_MODELS_MEMORY_MARGIN`, `LLAMA_ARG_MODELS_PRESET`, `LLAMA_ARG_MODELS_AUTOLOAD`, `LLAMA_ARG_CONNECT`, `LLAMA_ARG_CONNECT_CODE`).

Stripped only from the router's own args, not from a model preset (sm 280-285, 404): `model`, `mmproj`, `alias`, `hf-repo`. `log-file` is also stripped from the router's args only; a preset may set it (sm 406-407).

Overwritten in every child by the router (sm 315-319): `host` (child address), `port` (child port), `alias` (section name), `log-colors`.

Router CLI args win: after load, the router merges its own args over every model preset (sm 771-775).

Preset-only keys (not CLI flags) in b11941 (arg 4831-4849): `load-on-startup`, `stop-timeout`, `dedup-cache-models`. D4 does not allow them.

`GET /v1/models` shows each model's `args` and a `preset` INI with reserved keys, host, port, alias and tags removed (sm 2149-2161).

Comparison with D4 "never written" (`host`, `port`, `api-key`, `api-key-file`, `models-*`, `sleep-idle-seconds`, `hf-repo`, `alias`, `log-file`, `ssl-*`, `model-url`):

| Key | Router strips from model preset | In D4 list |
| --- | --- | --- |
| `host`, `port` | Overwritten (sm 315-316) | Yes |
| `api-key`, `api-key-file` | Yes | Yes |
| `models-*` (dir, max, memory-margin, preset, autoload) | Yes | Yes |
| `ssl-key-file`, `ssl-cert-file` | Yes | Yes (`ssl-*`) |
| `alias` | Overwritten (sm 317) | Yes |
| `hf-repo` | No (router args only) | Yes |
| `log-file` | No (preset may set it, sm 406) | Yes |
| `sleep-idle-seconds` | No (no env var, so it cannot be in the env-named list) | Yes |
| `model-url` | No | Yes |
| `connect`, `connect-code` | Yes | No |

## Router flags

| Flag | Env var | Default | Meaning | Source |
| --- | --- | --- | --- | --- |
| `--models-max N` | `LLAMA_ARG_MODELS_MAX` | 4 | Most models loaded at the same time. `0` = unlimited. No range check in the parser. At startup the router fails if more `load-on-startup` models than `models_max` are set. | help 639-641; arg 3704-3710; sm 914-917 |
| `--models-memory-margin N` | `LLAMA_ARG_MODELS_MEMORY_MARGIN` | 0 (disabled) | MiB of device memory to keep free per device. The router unloads least recently used models until a new one fits. No range check in the parser. | help 642-644; arg 3711-3717 |
| `--models-autoload` / `--no-models-autoload` | `LLAMA_ARG_MODELS_AUTOLOAD` | enabled | Load a model on first request. With autoload off, a request for a model that is not running gets `model is not loaded`. A request can override with query `autoload=true` or `autoload=1`. | help 645-648; arg 3718-3725; sm 1949-1974 |
| `--sleep-idle-seconds SECONDS` | none | -1 (disabled) | Seconds idle before the server sleeps. `0` and values below -1 are refused. In the router a sleeping child keeps running and wakes on the next request. | help 731-732; arg 3865-3874; sm 1436, 1581 |

## Could not confirm

1. What `common_preset::to_args` (in `common/preset.cpp`, not read) emits for a boolean key with value `false`, for a one-way flag such as `embeddings = false`, and for a bad boolean word. The INI probes used `apply_to_params`, not `to_args`. A router start with a scratch `models.ini` would show the child `args` in `GET /v1/models` (sm 2151) without loading a model.
2. Whether the router's preset context refuses unknown keys. The probes ran on the config-file path, which sets `ignore_unknown_keys = true` (arg 763). So negated keys (`no-kv-unified = true`) were not proven to work.
3. How `--models-memory-margin` is enforced. It is not referenced by name in `server-models.cpp`; the logic is in a file this spike did not read.
4. Runtime effect of `spec-type = none` appended to the default list `none` (arg 4336). It parses; behaviour was not run.
