## MODIFIED Requirements

### Requirement: Detect mode escalates a non-Latin local OCR result

Under `detect`, a local OCR page result that the detector marks non-Latin SHALL escalate to the OCR engine list with the reason `non_latin_output`, whatever its confidence, unless the backend that read it declares the page's output script among the scripts it may keep. The confidence cut SHALL still apply to every other local result. A backend with no script filter, such as `pp-ocrv6-small`, SHALL get the reason as before this change.

#### Scenario: Confident non-Latin output escalates

- **GIVEN** `detect`, the default backend list and a local result of 400 Devanagari letters with confidence 0.95
- **WHEN** the post-check runs
- **THEN** the page SHALL escalate with the reason `non_latin_output`

#### Scenario: Latin output follows the cut

- **GIVEN** `detect` and a Latin local result with confidence 0.95
- **WHEN** the post-check runs
- **THEN** the page SHALL keep its local text

#### Scenario: A backend that may keep the script keeps the page

- **GIVEN** `detect`, `OCR_LOCAL_BACKENDS=indra,pp-ocrv6-small`, and an Indra result of 400 Devanagari letters with confidence 0.95
- **WHEN** the post-check runs
- **THEN** the page SHALL NOT get the reason `non_latin_output`
- **AND** Indra SHALL keep the page
