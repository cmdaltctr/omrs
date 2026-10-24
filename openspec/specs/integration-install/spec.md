# integration-install Specification

## Purpose
Let the web server install an allowed optional extra into its own `uv tool` environment, with a fixed list of extras, one install at a time, redacted output and a restart to use it.

## Requirements

### Requirement: The server installs only into itself and only when it can

The server SHALL report its install type as `uv-tool` when a `uv-receipt.toml` file sits in its own Python environment folder, `checkout` when it runs from a project folder with `pyproject.toml` and `uv.lock`, and `other` in all other cases. The install action SHALL be available only for `uv-tool` and only when the `uv` program is found. The action SHALL install into the server's own Python environment and nowhere else.

#### Scenario: Login item installed with uv tool

- **WHEN** the server runs from a `uv tool` environment that holds `uv-receipt.toml` and `uv` is found
- **THEN** `GET /v1/integrations` MUST report the install type `uv-tool` and `installable: true` for each allowed extra that is not installed

#### Scenario: Development checkout

- **WHEN** the server runs with `uv run omrs web` from a project folder
- **THEN** every entry MUST report `installable: false`, and `POST /v1/integrations/{extra}/install` MUST return 409 and start nothing

#### Scenario: uv not found

- **WHEN** the install type is `uv-tool` and no `uv` program is found
- **THEN** every entry MUST report `installable: false` with the reason `uv-not-found`

### Requirement: Only allowed extras can be installed

The install route SHALL accept only an extra from a fixed list held by the server: the extras declared by the installed OMRS package, without `web`. `torch` is allowed; its card shows the download size before the install. The requirements to install SHALL come from the installed OMRS package metadata for that extra. No text from the request SHALL reach the command, other than the choice of a listed extra.

#### Scenario: Unknown extra refused

- **WHEN** a request asks to install `anthropic; rm -rf ~`
- **THEN** the server MUST return 404 and MUST start no process

#### Scenario: Excluded extra refused

- **WHEN** a request asks to install `web`
- **THEN** the server MUST return 409 naming the reason `not-installable-here`, and MUST start no process

#### Scenario: Requirements come from package metadata

- **WHEN** the user installs `anthropic`
- **THEN** the command MUST install the requirements the installed package declares for `anthropic` (for example `llama-index-llms-anthropic>=0.11.0`), and MUST NOT reinstall OMRS itself

### Requirement: The install action is guarded

`POST /v1/integrations/{extra}/install` SHALL need the browser session with the `manage` scope. A bearer credential SHALL NOT pass. Only one install SHALL run at a time. The route SHALL return 202 when it starts an install, and 409 when another install runs. The install SHALL stop after 10 minutes and SHALL then report failure.

#### Scenario: Bearer token refused

- **WHEN** an MCP bearer token calls the install route
- **THEN** the server MUST return 403 and MUST start no process

#### Scenario: Second install while one runs

- **WHEN** an install of `azure` runs and the user asks to install `chroma`
- **THEN** the server MUST return 409 and the `azure` install MUST continue

#### Scenario: Install takes too long

- **WHEN** an install runs for more than 10 minutes
- **THEN** the server MUST stop the process and report the state `failed` with the reason `timed-out`

### Requirement: Install progress and result can be read

`GET /v1/integrations/install` SHALL return the state of the running or last install: `idle`, `running`, `succeeded` or `failed`, with the extra name, the start time, and at most the last 40 lines of output. The output SHALL NOT contain an API key or any value from the settings secrets. An install SHALL be `succeeded` only when `uv pip install` and the check after it both end with exit code 0. After `succeeded`, the entry SHALL report `restart-needed` until the server restarts.

#### Scenario: Successful install

- **WHEN** the install of `anthropic` ends with exit code 0 and the check after it ends with exit code 0
- **THEN** the status MUST be `succeeded`, and the `anthropic` entry MUST report `restart-needed`

#### Scenario: Failed install

- **WHEN** the install ends with a non-zero exit code
- **THEN** the status MUST be `failed` with the last output lines, and the entry MUST still report `not-installed`

#### Scenario: Status after restart

- **WHEN** the server restarts after a successful install
- **THEN** the status MUST be `idle` and the entry MUST report `available`

### Requirement: The server checks its packages after an install

After `uv pip install` ends with exit code 0, the server SHALL run `uv pip check --python <its own Python>` as an argument list with no shell, the same environment and the same time limit. When the check ends with a non-zero exit code, the install SHALL be `failed` with the reason `check-failed` and the check's exit code, its output SHALL be kept with the install output, and the entry SHALL NOT report `restart-needed`.

#### Scenario: Packages conflict after the install

- **WHEN** the install ends with exit code 0 and `uv pip check` reports a conflict with exit code 1
- **THEN** the status MUST be `failed` with the reason `check-failed`, the output MUST hold the check lines, and the entry MUST NOT report `restart-needed`

#### Scenario: The check is skipped after a failed install

- **WHEN** the install ends with a non-zero exit code
- **THEN** the server MUST NOT run `uv pip check`

### Requirement: An entry with unknown status cannot be installed

When an entry's probe fails and its availability is `unknown`, the entry SHALL report `installable: false` with the reason `status-unknown`. The install route SHALL return 409 with that reason and start no process.

#### Scenario: Probe failed

- **WHEN** the probe of the `azure` entry raises an error
- **THEN** the entry MUST report `installable: false` with the reason `status-unknown`, and `POST /v1/integrations/azure/install` MUST return 409 and start no process

### Requirement: Extra requirements stay readable

Each requirement line that the installed OMRS package declares for an allowed extra SHALL name that extra with a plain `extra == "<name>"` clause, joined to any other marker part with `and` only. No such line SHALL name the `omrs` distribution. A test SHALL read the installed metadata and fail when a line breaks this rule.

#### Scenario: A line uses or

- **WHEN** a requirement line for `anthropic` has the marker `extra == "anthropic" or extra == "all"`
- **THEN** the metadata guard test MUST fail

#### Scenario: A line names omrs

- **WHEN** a requirement line for `anthropic` is `omrs[hybrid]; extra == "anthropic"`
- **THEN** the metadata guard test MUST fail

### Requirement: The server uninstalls only an allowed, installed, unused extra

`POST /v1/integrations/{extra}/uninstall` SHALL accept only an extra from the catalogue that is installed, is not a base entry and is not `web`, under the same conditions as install: a `uv tool` install with `uv` found, the browser session with the `manage` scope, and no other job running. The server SHALL refuse an extra that the current settings use, with 409, the reason `in-use` and the setting that uses it. A setting uses an extra when it selects a backend that needs the extra, or when it names a provider, directly or through `local` or `cloud`, whose registry entry declares the extra. The effective settings and the saved `omrs.jsonc` both count. The packages to remove SHALL be the extra's own requirements from the installed OMRS metadata, without any package that a base requirement, another installed extra or another installed package requires. A requirement behind another package's extra (`extra == "x"`) SHALL count only when an installed package or the install receipt asks for that extra. A requirement from a package that the same uninstall removes SHALL NOT keep a package. When no package is left to remove, the server SHALL refuse with 409 and the reason `nothing-to-remove`. Each entry SHALL report `pending_restart` (`install`, `uninstall` or null) for an action that succeeded in this launch. The command SHALL be an argument list with no shell. No text from the request SHALL reach the command, other than the choice of a listed extra.

#### Scenario: Uninstall an unused extra

- **WHEN** Chroma is installed, `vector_store` is `lancedb`, and the user uninstalls `chroma`
- **THEN** the server MUST run `uv pip uninstall --python <own Python>` with the Chroma requirements, then `uv pip check`, and the entry MUST report `restart-needed`

#### Scenario: Extra still in use

- **WHEN** `retrieval.rerank_backend` is `torch` and the user uninstalls `torch`
- **THEN** the server MUST return 409 with the reason `in-use` naming `retrieval.rerank_backend`, and MUST start no process

#### Scenario: Shared package kept

- **WHEN** an extra lists a package that another installed package requires
- **THEN** the server MUST NOT remove that package, and the response MUST list it as kept

#### Scenario: A requirement behind an extra nobody asked for

- **WHEN** PyTorch is installed, lancedb lists `sentence-transformers` and `transformers` only under its own extras, and no installed package asks for those lancedb extras
- **THEN** the PyTorch entry MUST list both packages in `removes`

#### Scenario: Packages of one extra go together

- **WHEN** Leiden communities is installed, and `leidenalg` is the only package that requires `igraph`
- **THEN** the entry MUST list both `leidenalg` and `igraph` in `removes`

#### Scenario: Every package kept

- **WHEN** an installed package that something asks for requires every package of an installed extra
- **THEN** the server MUST return 409 with the reason `nothing-to-remove`, MUST list the packages as kept, and MUST start no process

#### Scenario: A provider setting uses the extra

- **WHEN** `answer.provider` is `anthropic`, or `answer.verify_provider` is `cloud` while `cloud_backend` names a provider that needs the extra
- **THEN** the server MUST return 409 with the reason `in-use` naming that setting, and MUST start no process

#### Scenario: A provider without an extra never blocks

- **WHEN** `answer.provider` is `openai_compatible` or `ollama`, which ship in the base install
- **THEN** no extra MUST be reported `in-use` because of that setting

#### Scenario: Pending action survives a later job

- **WHEN** an uninstall of Chroma succeeds and an install of Azure then runs in the same launch
- **THEN** the Chroma entry MUST still report `pending_restart` `uninstall`, and the Azure entry MUST report `install` after its job succeeds

#### Scenario: Base entry and web refused

- **WHEN** a request asks to uninstall `web`, `magika`, `pdf-inspector`, `llamacpp` or `openrouter`
- **THEN** the server MUST return 409 with the reason `not-uninstallable-here`, and MUST start no process

#### Scenario: Unknown extra refused

- **WHEN** a request asks to uninstall `chroma; rm -rf ~`
- **THEN** the server MUST return 404 and MUST start no process

### Requirement: The app works with any non-base extra missing

The web server SHALL start, list integrations and serve a search on a LanceDB collection when the modules of any one non-base extra are missing, provided no setting selects that extra.

#### Scenario: Each extra missing in turn

- **WHEN** the modules of `chroma`, `hybrid`, `pdf-pypdfium2`, `community-leiden`, `azure`, `anthropic` or `torch` are missing
- **THEN** the server MUST start, `GET /v1/integrations` MUST report that extra `not-installed`, and a search MUST return results

### Requirement: A saved user profile that selects an extra blocks its uninstall

The uninstall in-use check SHALL also read every user profile that is not deleted. A profile uses an extra when an enabled `read.document` step in the current revision of its ingest pipeline names a PDF reader that the in-use map ties to the extra, or when its `embed_provider` names a provider whose registry entry declares the extra. The server SHALL then refuse the uninstall with 409 and the reason `in-use`, SHALL name the profile (`id` and `title`) and the setting inside it, and SHALL start no process. A global setting that uses the extra SHALL be reported before a profile. When the server cannot read the profiles, it SHALL log a warning and apply the global check only.

#### Scenario: A profile reads PDF files with pypdfium2

- **WHEN** the user profile "Scans" has a Read document step with `pdf_reader` set to `pypdfium2`, and the user uninstalls `pdf-pypdfium2`
- **THEN** the server MUST return 409 with the reason `in-use`, the setting `pdf_reader` and the profile "Scans", and MUST start no process

#### Scenario: A disabled step does not block

- **WHEN** the only Read document step that names `pypdfium2` is disabled
- **THEN** the entry MUST NOT report `in-use` because of that profile

#### Scenario: A deleted profile does not block

- **WHEN** the profile that names `pypdfium2` is deleted
- **THEN** the entry MUST NOT report `in-use` because of that profile

#### Scenario: A profile embedding provider with an extra blocks it

- **WHEN** a user profile's `embed_provider` names a provider whose embedding registry entry declares an extra
- **THEN** that extra's entry MUST report `in-use` with the setting `embed_provider` and that profile

#### Scenario: A global setting is named first

- **WHEN** `pdf_reader` is `pypdfium2` in `omrs.jsonc` and a profile also names `pypdfium2`
- **THEN** the entry MUST report the setting `pdf_reader` with no profile

#### Scenario: Profiles cannot be read

- **WHEN** the web server has no profile catalogue
- **THEN** the catalogue MUST still answer, and only the global settings MUST decide `in-use`
