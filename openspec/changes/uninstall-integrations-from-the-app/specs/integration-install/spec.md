## ADDED Requirements

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
