## MODIFIED Requirements

### Requirement: Settings follow one source order

Each setting SHALL come from the first of these sources, highest first: an explicit per-operation option or launch option, the process environment (`env`), the `.env` file (`dotenv`), `omrs.jsonc` (`config-file`), the YAML defaults and profile bundle, then the code default (`default`). A value from `env` or `dotenv` SHALL lock its field in the Settings page. A value from `config-file` SHALL NOT lock its field.

#### Scenario: .env wins over the file

- **WHEN** `.env` sets `LLAMACPP_ROUTER_URL` and `omrs.jsonc` sets `llamacpp_router_url` to another address
- **THEN** the `.env` address MUST be used and the field MUST report the source `dotenv`

#### Scenario: Process environment named apart from .env

- **WHEN** the shell exports `OLLAMA_BASE_URL` and `.env` does not set it
- **THEN** the field MUST report the source `env`

#### Scenario: File value stays editable

- **WHEN** `omrs.jsonc` sets `ollama_base_url` and neither the environment nor `.env` sets it
- **THEN** the field MUST report the source `config-file` and a page save MUST succeed

### Requirement: Identity, storage, secret and internal keys are read-only on the page

The read-only keys SHALL be `embed_provider`, `embed_model`, `local_backend`, `cloud_backend`, `llamacpp_embed_model`, `openrouter_embed_model`, every key under `embedding.`, `vector_store`, `lancedb_uri`, `chroma_persist_dir`, `chroma_mode`, `collection_name`, every secret field, every internal field, `ingestion.ingest_extensions` and `metadata.keyword_rules`. `llamacpp_models` SHALL be written only through the Router panel routes, not through the configuration save.

#### Scenario: Identity key refused

- **WHEN** a request asks the server to write `embed_model`
- **THEN** the server MUST answer 400 and MUST NOT change the file

#### Scenario: Storage key refused

- **WHEN** a request asks the server to write `lancedb_uri`
- **THEN** the server MUST answer 400 and MUST NOT change the file

#### Scenario: Workers folder is writable

- **WHEN** a request asks the server to write `ocr_workers_dir` with a folder that holds `engines/`
- **THEN** the server MUST write the key and MUST NOT answer 400 for a read-only key

#### Scenario: Model list not written by the configuration save

- **WHEN** a request to `PUT /v1/settings/configuration` holds `llamacpp_models`
- **THEN** the server MUST answer 400 and MUST NOT change the file
