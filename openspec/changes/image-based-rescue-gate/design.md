# Design

## Context

- **Where the fault sits.** `pdf_inspector` flags pages that need OCR. When it extracts no text, the rescue chain (ADR-066, `integrations/pdf/pdf_inspector.py`) takes text from LiteParse, then pypdf. TDR-024 then sets the flagged-page count to zero because text came back. Nothing checks the rescued text against the page. `rf06` shows 4 flagged pages before the rescue and 0 after it. See proposal.md, Why.
- **Why the text-only check failed.** Experiment 42 asked Clef-flash "is this readable writing?". The labels ask "does the text match the page?". The 11 healthy pages it flagged were faithful copies of non-prose pages. Its report records the mismatch as the main lesson. A single flagged page also routed six short usable documents.
- **What changed.** Clef-Flash is a 9B image-text-to-text model (Qwen3.5 base). The `ggml-org/Clef-Flash-GGUF` repo carries `mmproj-Clef-Flash-Q8_0.gguf` (0.62 GB). llama.cpp took text support in PR #29831 and image input in PR #29969, both before the pinned build b11941. This is from the model card and the repository notes. Task 1 proves it on the pinned build.
- **Files.** Pinned to revision `a5a18a6e`: `Clef-Flash-Q8_0.gguf` (SHA-256 `25f801e2…`, 9,657,260,288 bytes) and `mmproj-Clef-Flash-Q8_0.gguf` (SHA-256 `9dd8bc27…`, 624,229,728 bytes). They live in `~/Development/DATA/omrs/ocr-models/clef-flash/`, outside git.
- **Runtime record.** ADR-074 and ADR-103 run decision models on `llama-server` with Q8_0 or higher, bound to `127.0.0.1`, one request at a time. ADR-109 gives OMRS a managed runtime for production use. This experiment runs `llama-server` by hand, as Experiment 42 did.
- **Gate record.** G1 to G3 and the 0.10 margin come from Experiments 38 and 42. Gate thresholds `0.5` and `0.10` stay fixed.
- **Routing unit.** Experiment 40 is reserved for page versus document routing. The page unit (ADR-069) routes only flagged pages, so a false flag costs one page. This change reports both units and does not choose.

## Goals / Non-Goals

**Goals:**

- Find out whether an image-based fidelity question lets a local model catch junk text layers (`rf06`, `rf07` and similar) without flagging faithful pages.
- Cover handwriting properly. Experiment 42 excluded most of it.
- Keep every threshold, wording and render setting frozen before the confirmation documents are scored.
- Leave a clear route to production if the gate passes.

**Non-Goals:**

- Changing TDR-024, the reader chain, the `0.5` and `0.10` thresholds or any default.
- Choosing page or document routing (Experiment 40).
- Hosted Clef-Flash, or other models. Hosted Jev with images runs only as a control arm (D10). It is not a candidate for adoption.
- Running the production integration: where the check runs, caching, index identity, the managed runtime entry. A PASS opens that change.
- Fixing the CUDA build gap for Experiment 35a.

## Decisions

### D1. The question tests fidelity to the page

Treatment question (draft, final wording frozen at the end of Stage 1): "Does the text match the text written or printed on the page image?" The model gets the page image and the first 2,000 characters of the rescued page text, the same head as Experiments 38 and 42. Up to three wordings are written into `protocol.md` before Stage 1 starts, and Stage 1 picks one by the gates. The request type stays `noul` with options `["no", "yes"]`, so the result is one probability, as in Experiment 38.

Alternative: ask "is this text readable?" with an image added. Rejected, because that is the question that failed.

### D2. Arms

| Arm | What it is | Flag rule |
| --- | --- | --- |
| Control | Production today (TDR-024) | never flags |
| Comparator | Experiment 38 word check (candidate A), code unchanged | below its frozen threshold |
| Reference row | Experiment 42 text-only Clef-flash scores | reported from `summary.json`, not rerun |
| Treatment | Clef-Flash Q8_0 plus `mmproj`, image and text, wording from D1 | `P(yes)` below a threshold frozen after Stage 1 |
| Hosted control | TypeSafe Jev `jev-1.14.0` with images (D10), same page render, same text head and same wording as the Treatment, operator-approved documents only | `P(yes)` below its own threshold, fitted by the same rule on Stage 1 approved pages and frozen with the Treatment amendment before Stage 2 |

The hosted control is a post-verdict control. It shows how far a hosted image model gets on the same input. It does not set the verdict, it does not choose the wording, and it is not a candidate for adoption, because production stays local-first. The report gives it a separate table.

Why no text-only rerun: Experiment 42 already measured it on 68 documents with a frozen threshold. A rerun would repeat a known FAIL.

### D3. Two stages

- **Stage 1, development.** The 40 Experiment 38 documents and the 68 Experiment 42 documents. They are seen, so the threshold and the render settings may be fitted on them. The Stage 1 output is a dated amendment to `plan.json` holding the wording, threshold and render settings.
- **Stage 2, confirmation.** New documents that appear in no earlier experiment. Include more handwriting: archive records like `rf06` and `rf07`, Sevilla-type collections, and mixed print with notes. Size targets follow Experiment 42: at least 1,000 healthy pages (so G3 has at least 20 pages under its 2% ceiling), junk text layers from at least six documents, and no document holding more than 15% of the junk pages. The exact list goes into `protocol.md`.

Alternative: one stage on all documents. Rejected, because fitting and testing on the same pages overstates the result, which is why Experiment 42 existed.

### D4. Render settings

The page renders as PNG from the PDF, with the long side and the DPI fixed in `plan.json` after a short Stage 1 trial. Start from these values: 150 DPI, long side at most 1,568 px. The TypeSafe image limits (D10) allow 280 to 1,568 px on each side, so one render at most 1,568 px serves the Treatment and the hosted control. The final long side SHALL stay at most 1,568 px for that reason. The llama.cpp flags `--image-min-tokens` and `--image-max-tokens` follow the dots.mocr values already in use (`4` and `14400`) if the Clef projector accepts them, otherwise the defaults. Task 1 checks both. Context size and `-b/-ub` follow Experiment 42 decision A5 (`8192`), with the large-input bug from llama.cpp issue #30073 in mind.

### D5. Labels

Pages keep the Experiment 33 label (Gemini reference transcription, token recall rule, thresholds `0.50` and the frozen grey band). Two exceptions get a second reference from dots.mocr on the operator's machine: pages labelled `ambiguous`, and every page of a document the protocol lists as handwritten. The two must give the same class. The dots.mocr transcription is scored with the same token rule. This brings back pages such as `rf06` p29, which dots.mocr reads correctly.

The operator checks a stratified sample by eye before Stage 2 is scored: pages across `junk`, `healthy`, handwritten and relabelled classes. The sample size and the error bound go into `plan.json` first. Experiment 42 waived this check, so its labels are untested by a person.

Alternative: dots.mocr as the only reference. Rejected, because the same engine would then label the pages that a later OCR step would fix, and the two would agree by construction.

### D6. Routing rules reported

For every arm the report shows two document rules and one page rule: a document routes at 10% flagged pages (the current gate), a document routes at one flagged page, and each flagged page routes alone (page unit). Each rule shows its OCR cost in pages. This answers the Experiment 42 problem (one false flag sent a whole document) without choosing the unit.

### D7. Runtime and checks

External `llama-server`, build b11941 (the pinned build), `127.0.0.1`, one request at a time, Metal on this Mac. Before scoring: record the build number, check both SHA-256 values against `plan.json`, and run a smoke test of two requests on one page image (right text and wrong text). The answers must differ in the expected direction. The smoke test also proves the projector is loaded, so text-only scores can never pass as image scores. Timing runs on the same 40 fixed pages as before, with nothing else on the GPU.

### D8. Production route if the gate passes (not built here)

For the follow-up change, not for this one: the check would run inside the reader chain right after a rescue returns text, per page, behind a setting that defaults to off. Pages the check flags count as pages needing OCR again, so the existing gate and OCR routes handle them. The Clef-Flash server would be a managed runtime of OMRS (ADR-109), with the two model files hash-checked before each start, like the dots.mocr engine. This sketch is here so the experiment measures what production would need (latency per page, memory with both engines loaded, image size).

### D9. Operator decisions needed before the run

1. **Gate priority.** Gates G1 and G2 primary and G3 secondary, as in Experiment 42, or all three primary as in Experiment 38. Recommended: G1 and G2 primary. G3 reads one false flag as a failure, but under the page unit a false flag costs one page.
2. **Stage 2 documents.** Approval to download new open-licence PDFs (size to be stated in `protocol.md`).
3. **Second reference.** Confirm dots.mocr as the second transcriber for handwritten and ambiguous pages.
4. **Hosted Jev image arm.** Approve the hosted control (D10) and name the documents whose page images may leave the machine. The default is open-licence documents only. `rf06` and `rf07` stay excluded unless the operator names them.

### D10. Hosted Jev image control

**API facts.** Read from docs.typesafe.ai on 2026-11-02 (`images.md`, `models.md`, `api/system-one.md`, `legal.md`). Each fact is recorded again in `plan.json` before the run.

- **Model.** "Jev 1.13 and Jev 1.14 both accept images." The arm sends the versioned id `jev-1.14.0`, which `jev-latest` points to today. The models table lists the input of both as "Text", so the image path rests on the images page alone. The smoke test proves it.
- **Status.** "Images and Box questions aren't yet up to our standards to call ready for production." The docs also say the format, answers and limits "can change between releases".
- **Opt-in.** "send the `TypeSafe-Danger-Zone-Images: true` header with each request that contains an image".
- **How images go.** "Each image is listed once, in the request's top-level `assets` map." The asset is `{"type": "image", "format": "png", "data_base64": ...}`, with "no `data:` prefix". A multipart upload is the other way. Image URLs: not stated.
- **Limits.** "PNG or JPEG, still images only." "16 MiB per image file." "280 to 1568 pixels each." Request body "32 MiB". Image count per request: not stated as a number; it "depends on these limits and on the context length" (64k per request, 32k per question).
- **Answer.** "A Noul answer is a single number representing the probability that the answer is yes". "Each response's `model` field gives the versioned ID that answered".
- **Price.** "\$42 / \$0.042" per Btok / per Mtok of input. "There is no separate charge for images." Tokens per image: not stated. Stage 1 measures it from `usage.input_tokens`.
- **Rate limits.** "Rate limits are set per organization." A request over a limit "returns `429 Too Many Requests`". Numbers: not stated in the docs.
- **Data retention.** The legal page links a Data Processing Agreement and a Privacy Policy, with a "commitment not to train models on user data". Zero data retention is offered "for enterprise customers". The retention period: not stated in the docs read.

**Request shape.** One request per page, to `POST https://api.typesafe.ai/v1/systemone`, with `Authorization: Bearer <key>` and `TypeSafe-Danger-Zone-Images: true`. The body holds `"model": "jev-1.14.0"`, a `state` with the page image reference and the 2,000-character text head, an `assets` map with one base64 PNG, and one `noul` question with the frozen wording. The PNG is the same file the Treatment reads.

**Pinning and drift.** The script records the returned `model` for every page. It stops when any page returns a model id other than `jev-1.14.0`. It reuses the pattern of `experiments/38-rescue-quality-signal-2026-09-30/jev_hosted.py`: the key comes from `TYPESAFE_API_KEY` only and is never written to output, logs or error text; errors report the HTTP status only, because a body can echo page text; HTTP 429, 500, 502, 503, 504 and 529 retry with exponential backoff (and `retry-after` when sent); a stop on model change keeps finished pages and names the new id.

**Privacy cost.** Page images leave the machine with this arm. `rf06` and `rf07` hold named-person records. The arm runs only on documents the operator approves by name in a dated `plan.json` amendment. The default list is open-licence documents only. `rf06` and `rf07` are excluded unless the operator names them. The script refuses any page whose document is not on the list. Responses go to gitignored `output/`.

Alternative: leave the hosted model out, as first planned. Rejected by the operator, who holds a TypeSafe key and wants a hosted reference beside the local result.

## Risks / Trade-offs

- **The image path fails on b11941** (projector not loaded, token limits, large-input bug) → Task 1 smoke test stops the run early. The fallback is a build the Clef-Flash repo names, with the build recorded in `plan.json`.
- **Speed.** An image adds many tokens. Text-only took 0.69 s per page. Images may take several seconds per page, and 1,000 pages may take an hour or more → measure in Task 1, report it, and run the long scoring in the background while the Mac is free.
- **Second-reference cost.** dots.mocr takes 10 to 45 s per page. Labelling about 300 to 500 pages takes hours → run overnight, resume from checkpoints, restrict the second reference to handwritten and ambiguous pages (D5). The same step can run on a CUDA host later.
- **Label noise on handwriting.** Two engines can agree and still be wrong → the operator sample bounds this, and the report states the label error rate.
- **Memory.** Clef-Flash (about 10 GB) and dots.mocr (about 7 to 17 GB) must not run at the same time on this Mac → run the label step and the scoring step in sequence.
- **Overfit to handwriting.** A small handwritten set can pass by luck → Stage 2 has a minimum number of handwritten documents, and the report gives intervals, not only point rates.
- **Experiment 40 may change the unit.** → D6 reports both units, so the result stays usable.
- **The hosted model can change without notice.** Image support is marked not ready for production, and an alias can move → pin `jev-1.14.0`, record the returned id per page, and stop on a change (D10).
- **Hosted cost.** Tokens per image are not stated → measure `usage.input_tokens` on the Stage 1 approved pages, state the cost of Stage 2 in `plan.json` before the run, and stop if it exceeds that figure.
- **Rate limits.** Limits are per organisation and not stated in the docs → one request at a time, backoff on 429, and resume from checkpoints.
- **Fewer pages in the hosted arm.** Approval by name can leave out the personal-record documents → the report states the page and document counts of the hosted arm and compares arms only on shared pages.

## Migration Plan

None. The change adds experiment files only. A PASS opens a follow-up OpenSpec change and an ADR. A FAIL is recorded in the report, issue #161 stays open, and the next idea (for example a text layer versus OCR agreement check with the local PP-OCR tier) needs its own proposal.

## Open Questions

- Whether the Clef-Flash projector accepts the dots.mocr token limits (answered by Task 1).
- Whether the `/v1/systemone` route of `llama-server` b11941 takes images in the `images` field or needs an OpenAI-style message (answered by Task 1).
