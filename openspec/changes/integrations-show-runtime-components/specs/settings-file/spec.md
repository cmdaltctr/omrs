## MODIFIED Requirements

### Requirement: Identity, storage, secret and internal keys are read-only on the page

The read-only keys SHALL be `embed_provider`, `embed_model`, `local_backend`, `cloud_backend`, `llamacpp_embed_url`, `llamacpp_embed_model`, `openrouter_embed_model`, every key under `embedding.`, `vector_store`, `lancedb_uri`, `chroma_persist_dir`, `chroma_mode`, `collection_name`, every secret field, every internal field, `ingestion.ingest_extensions` and `metadata.keyword_rules`.

#### Scenario: Identity key refused

- **WHEN** a request asks the server to write `embed_model`
- **THEN** the server MUST answer 400 and MUST NOT change the file

#### Scenario: Storage key refused

- **WHEN** a request asks the server to write `lancedb_uri`
- **THEN** the server MUST answer 400 and MUST NOT change the file

#### Scenario: Workers folder is writable

- **WHEN** a request asks the server to write `ocr_workers_dir` with a folder that holds `engines/`
- **THEN** the server MUST write the key and MUST NOT answer 400 for a read-only key

## ADDED Requirements

### Requirement: The server checks the OCR workers folder before it saves it

Before it writes `ocr_workers_dir`, the server SHALL expand `~` and check that the folder exists and holds an `engines/` folder. It SHALL refuse a relative path. An empty value SHALL clear the key. The server SHALL store the value with the home folder as `~`. A refusal SHALL answer 400 with a reason that does not hold the submitted value, and SHALL NOT change the file.

#### Scenario: Folder without engines

- **WHEN** a request writes `ocr_workers_dir` with a folder that has no `engines/` folder
- **THEN** the server MUST answer 400 and MUST NOT change the file

#### Scenario: Home folder stored as tilde

- **WHEN** a request writes a folder under the user's home folder
- **THEN** `omrs.jsonc` MUST hold the path with `~` in place of the home folder

#### Scenario: Clear the folder

- **WHEN** a request writes `ocr_workers_dir` with an empty value
- **THEN** the key MUST be removed from `omrs.jsonc`
