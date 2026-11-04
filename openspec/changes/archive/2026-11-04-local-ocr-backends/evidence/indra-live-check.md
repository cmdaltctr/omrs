# Indra live check on io01 and io02 (task 7.5)

Date: 2026-11-04. The operator approved this run and the weights download on 2026-11-04.

## Question

Does the real page unit, with `OCR_LOCAL_BACKENDS=indra,pp-ocrv6-small`, keep the pages with Indra that `ordered-list-simulation.md` predicts?

## Setup

### Versions

| Part | Version |
| --- | --- |
| Branch and commit | `feat/local-ocr-backends` at `d3510fa1` |
| Python | 3.14.9, macOS 27.2, arm64 |
| indra-ocr | 1.1.2 |
| onnxruntime | 1.28.0 (Experiment 46 used 1.31.1) |
| pdf-inspector | 1.17.0 |
| pypdfium2 | 5.12.1 |
| Indra weights | `datalab-to/indra-ocr` revision `bd02167fdf2005a19962cc15188f8496a2c87d3b` (tag v1.1.0) |
| PP-OCRv6 model | `pp-ocrv6-small@oar-ocr-v0.7.0`, read from the pdf-inspector user cache |

### Weights check

1. `huggingface_hub.snapshot_download` fetched the full revision into `<scratch>/hf`. The full revision has 27 files (102.0 MB). Its tree hash is `8953b8d6cdd86de20ca2508db573f17fe4fcef8772ff05dd0bf4710bb1e04043`.
2. The expected hash in Experiment 46 `plan.json` covers 12 files (76.1 MB). These are the files `indra_ocr.model_dir()` downloads: `*.onnx`, `meta.json`, `lm.npz` and `lm_*.npz`, without the five maths files.
3. The check copied those 12 files into `<scratch>/weights`. It then applied the Experiment 46 rule (`run_arm.tree_sha256`): the SHA-256 of the sorted `<file sha>  <relative path>` lines.
4. Result: `1a9ef1fc65c0546f63b89eed936e524077ba94dcd1d7689de89265b158b9324f`, 12 files, 76.1 MB. This is equal to the expected value.

### Settings

The script built `EffectiveSettings` directly and the reader with `factory.build_pdf_reader("pdf_inspector", settings, ocr_client=None)`. The reader was `OcrRoutedPdfInspector`.

| Setting | Value |
| --- | --- |
| `pdf_reader` | `pdf_inspector` |
| `ocr_fallback_enabled` | `true` |
| `ocr_routing_unit` | `page` |
| `ocr_local_backends` | `("indra", "pp-ocrv6-small")` |
| `ocr_non_latin_routing` | `off` |
| `ocr_maths_routing_enabled` | `true` (default) |
| `ocr_local_min_confidence` | not set, so each backend uses its own cut (0.90 for both) |
| `ocr_local_offline` | `true` |
| `ocr_local_model_directory` | `<user cache>/pdf-inspector/models/pp-ocrv6-small/oar-ocr-v0.7.0` |
| OCR engine | none (`ocr_client=None`) |

### Environment

| Variable | Value |
| --- | --- |
| `HOME`, `OMRS_CONFIG_DIR`, `OMRS_STATE_DIR`, `XDG_*` | folders under `<scratch>/home` |
| `HF_HOME` | `<scratch>/hf`, with `HF_HUB_OFFLINE=1` |
| `INDRA_OCR_MODEL_DIR` | `<scratch>/weights` |
| `PDFIUM_LIB_PATH` | `liteparse/libpdfium.dylib` in the worktree environment |
| `ORT_DYLIB_PATH` | `onnxruntime/capi/libonnxruntime.1.28.0.dylib` in the worktree environment |

The two library paths follow `docs/guides/ingestion.md` (local tier runtime table). The run used no OCR engine, no Ollama and no network after the download.

### Inputs

The PDFs come from the Experiment 33 corpus in the data store (`33-ocr-routing-natural-positive-2026-09-17/corpus/natural/`):

| Document | SHA-256 | Script |
| --- | --- | --- |
| `io01.pdf` | `a00589f5f675aa111d4ed5261401fa6b43a02efc46a46e193d6cb4b7169c3c01` | Devanagari |
| `io02.pdf` | `deb63aa687c2b2a4525e5846b33dfff2b498b52a2f2379cd48e8e1a774def0b0` | Arabic |

### Method

1. A script in `<scratch>/scripts` called `load_data` on each PDF once and timed the call.
2. Spies on `run_rules`, `chain._read_one` and `chain.read_local_pages` recorded the rule plan, each backend's raw page reads and the final outcome of each page. The spies change no behaviour.
3. For each emitted page document, the script recorded the page number, `ocr_backend` and the page-source counts.
4. A second script compared the live outcome with two predictions from the Experiment 46 data (`pages.json`, `output/arm_b.jsonl`, `output/summary.json`):
   - **Fixed cut.** Indra keeps a page when its Experiment 46 confidence is 0.90 or more and the output script is Arabic or Devanagari. This is the shipped rule.
   - **Simulation.** Indra keeps a page when the Experiment 46 leave-one-document-out `kept` flag is true and the output script is Arabic or Devanagari. `ordered-list-simulation.md` used this rule.

## Results

### Counts per document

| Document | Pages | Flagged | Kept by Indra | Kept by PP-OCRv6 | Unresolved | Seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| io01 | 49 | 49 | 48 | 0 | 1 (page 1) | 7.9 |
| io02 | 16 | 16 | 14 | 0 | 2 (pages 1, 16) | 5.2 |

- The rule plan dropped no page and sent no page direct. All flagged pages went to the local tier.
- Indra read all pages in one call: 49 pages in 4.09 s for io01 (this includes the model load), and 16 pages in 1.76 s for io02. PP-OCRv6 read only the pages Indra passed on: 1 page in 0.62 s, and 2 pages in 0.35 s.
- Each document emitted one page document for each page: 49 for io01 and 16 for io02. Every page document has `ocr_backend: indra_ocr`. The counts are `ocr_pages_local` 48 and 14, `ocr_pages_unresolved` 1 and 2, and 0 for native, worker and blank.
- Each unresolved page kept the Indra text, because Indra was the first backend that returned text for it.

### Unresolved pages

| Page | Indra confidence | Indra output script | PP-OCRv6 confidence | Reason |
| --- | ---: | --- | ---: | --- |
| io01 page 1 | 0.861 | no verdict (62 characters) | 0.597 | `low_confidence` |
| io02 page 1 | 0.881 | Arabic | 0.565 | `low_confidence` |
| io02 page 16 | 0.740 | Arabic | 0.654 | `low_confidence` |

The live PP-OCRv6 confidences for io02 pages 1 and 16 are equal to the stored Experiment 33 values to six decimal places.

### Comparison with the prediction

This table counts only the pages in the Experiment 46 sample. io01 page 1 is not in the sample, so it has no prediction.

| Script (document) | Pages in sample | Live: kept by Indra | Fixed cut 0.90 | Simulation |
| --- | ---: | ---: | ---: | ---: |
| Devanagari (io01) | 48 | 48 | 48 | 44 |
| Arabic (io02) | 16 | 14 | 14 | 14 |

- **Fixed cut 0.90:** no difference on any of the 64 pages.
- **Simulation:** four differences, all in io01. They are given below.

| Page | Live | Simulation | Experiment 46 confidence | Live confidence | Reason |
| --- | --- | --- | ---: | ---: | --- |
| io01 page 2 | kept by Indra | to engine | 0.942 | 0.940 | cut |
| io01 page 24 | kept by Indra | to engine | 0.940 | 0.947 | cut |
| io01 page 47 | kept by Indra | to engine | 0.941 | 0.956 | cut |
| io01 page 48 | kept by Indra | to engine | 0.944 | 0.945 | cut |

The simulation used the leave-one-document-out cut. For io01 that cut is 0.95, because it comes from the other eight documents (`summary.json`, `loo_cuts`). The shipped backend uses the registered cut 0.90. All four pages have a confidence between 0.90 and 0.95 in both runs. No difference comes from a render difference or a script verdict.

### Confidence agreement

The live run renders each page from the PDF with pypdfium2 at 1600 px on the long side. Experiment 46 read the Experiment 33 page images. The onnxruntime version is also different.

| Document | Median difference | Largest difference |
| --- | ---: | ---: |
| io01 | 0.003 | 0.016 (page 16: 0.957 to 0.972) |
| io02 | 0.003 | 0.049 (page 16: 0.788 to 0.740) |

No page moved across the 0.90 cut. The pages nearest the cut in io02 (Experiment 46 to live) were page 1 (0.885 to 0.881), page 7 (0.908 to 0.904) and page 2 (0.903 to 0.904). Each stayed on the same side of the cut. The live output script was the same as the Experiment 46 output script on every sampled page.

## Conclusion

The live page unit keeps 48 of 49 io01 pages and 14 of 16 io02 pages with Indra. PP-OCRv6 keeps none. On the 64 sampled pages, the live result is equal to the fixed-cut prediction. It differs from `ordered-list-simulation.md` on four io01 pages. The cause of each difference is the cut: the simulation used a leave-one-document-out cut of 0.95 for io01, and the shipped backend uses 0.90.

## Limits

1. Two documents only, one for each script. Each document comes from one source.
2. Another process ran the local CI suite on the same machine during the run (load average about 8). The times show one run each, and they include the page scan and the Indra model load.
3. The run used onnxruntime 1.28.0 and Python 3.14.9 from the worktree environment. Experiment 46 used onnxruntime 1.31.1 and Python 3.12.15.
4. No OCR engine was connected, so the escalated pages count unresolved. With an engine, these three pages would go to the engine.
5. The check measures where the pages go. It does not measure text quality (recall) again.
