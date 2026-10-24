## ADDED Requirements

### Requirement: The server uninstalls only an allowed, installed, unused extra

`POST /v1/integrations/{extra}/uninstall` SHALL accept only an extra from the catalogue that is installed, is not a base entry and is not `web`, under the same conditions as install: a `uv tool` install with `uv` found, the browser session with the `manage` scope, and no other job running. The server SHALL refuse an extra that the current settings use, with 409, the reason `in-use` and the setting that uses it. The packages to remove SHALL be the extra's own requirements from the installed OMRS metadata, without any package that a base requirement, another installed extra or another installed package requires. The command SHALL be an argument list with no shell. No text from the request SHALL reach the command, other than the choice of a listed extra.

#### Scenario: Uninstall an unused extra

- **WHEN** Chroma is installed, `vector_store` is `lancedb`, and the user uninstalls `chroma`
- **THEN** the server MUST run `uv pip uninstall --python <own Python>` with the Chroma requirements, then `uv pip check`, and the entry MUST report `restart-needed`

#### Scenario: Extra still in use

- **WHEN** `retrieval.rerank_backend` is `torch` and the user uninstalls `torch`
- **THEN** the server MUST return 409 with the reason `in-use` naming `retrieval.rerank_backend`, and MUST start no process

#### Scenario: Shared package kept

- **WHEN** an extra lists a package that another installed package requires
- **THEN** the server MUST NOT remove that package, and the response MUST list it as kept

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
