## ADDED Requirements

### Requirement: The PaddleOCR-VL engine reads text through a declared llama.cpp runtime

The `paddleocr-vl` engine SHALL declare a llama.cpp runtime for its text-reading step: build 11941, the pinned Q8_0 model and projector with their SHA-256, and the flags `--temp 0 --image-min-tokens 144 --image-max-tokens 1280 -c 8192 -np 1`. It SHALL send its text-reading requests to the server at `OMRS_OCR_RUNTIME_URL`. Its layout step SHALL stay in PaddlePaddle. The worker SHALL NOT start a model server.

#### Scenario: The declared runtime matches the pins

- **WHEN** the host reads the `paddleocr-vl` manifest
- **THEN** the declared build SHALL be 11941
- **AND** the declared model SHA-256 SHALL be `2bda93a416339f2d9f06accae505600544a9e72cc159d0cd1af4c0f679866e1c` and the projector SHA-256 SHALL be `204d757d7610d9b3faab10d506d69e5b244e32bf765e2bab2d0167e65e0a058a`

#### Scenario: Text reading uses the passed URL

- **GIVEN** `OMRS_OCR_RUNTIME_URL` names a running server
- **WHEN** the worker parses a page
- **THEN** its text-reading requests SHALL go to that server
- **AND** its layout step SHALL run without that server

#### Scenario: Missing URL

- **GIVEN** `OMRS_OCR_RUNTIME_URL` is not set
- **WHEN** the worker receives a parse request
- **THEN** it SHALL return a parse error that names `OMRS_OCR_RUNTIME_URL`

### Requirement: PaddleOCR-VL stays the fallback engine on llama.cpp

Moving PaddleOCR-VL's text-reading step to llama.cpp SHALL NOT change the route order: dots.mocr SHALL stay primary and PaddleOCR-VL SHALL stay fallback. Its `backend_id` SHALL stay `paddleocr_vl`.

#### Scenario: Default routes unchanged

- **WHEN** the host reads the routes from the default settings
- **THEN** the primary engine SHALL be `dots-mocr` and the fallback engine SHALL be `paddleocr-vl`
