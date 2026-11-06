# src/omrs/core/ingestion (indexing)

Reading, chunking and writing documents into the store.

## What belongs here

- The ingestion pipeline (`pipeline.py`), the chunker and the document backends.
- Document backends register in `backends/registry.py`.

## What it must not import

- `omrs.core.retrieval` (contract `ingestion-and-retrieval-stay-independent`).

## Rules

1. `ingest_path_async` in `pipeline.py` is the only entry point. All ingestion is async.
2. `content_type` metadata wins over the file extension when the chunker picks a strategy.
3. Use markdown chunking when the suffix is `.md` or the reader set `text_format == "markdown"` (ADR-055). A PDF that emits markdown keeps its headings only through `text_format`.
4. PDF readers come from `integrations/pdf/factory.py`. Tests run with `PDF_READER=pypdf`.
5. The `ocr_local_backends` list, with each backend's effective cut and local model, enters the PDF `parser` block only (`ocr_identity.local_backends_payload`, called from `reader_identity.pdf_parser_payload`; identity schema 8, ADR-114). A cut or model change re-indexes PDF sources only. Other sources keep their digest. `build_ingestion_context` resolves the entry once per operation (`IngestionContext.local_ocr_backends`), so a failed model probe runs once, not once per PDF source.

## Links

- [Root AGENTS.md](../../../../AGENTS.md)
- [Ingestion guide](../../../../docs/guides/ingestion.md)
