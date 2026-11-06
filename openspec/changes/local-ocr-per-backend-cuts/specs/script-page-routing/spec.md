## ADDED Requirements

### Requirement: Detect mode escalates every non-Latin local OCR result

Under `detect`, a local OCR page result that the detector marks non-Latin SHALL escalate to the OCR engine list with the reason `non_latin_output`, whatever its confidence and whichever listed backend read it. No backend SHALL be exempt from this check. The confidence cut SHALL still apply to every other local result.

#### Scenario: Confident non-Latin output escalates

- **GIVEN** `detect`, the default backend list and a local result of 400 Devanagari letters with confidence 0.95
- **WHEN** the post-check runs
- **THEN** the page SHALL escalate with the reason `non_latin_output`

#### Scenario: Latin output follows the cut

- **GIVEN** `detect` and a Latin local result with confidence 0.95
- **WHEN** the post-check runs
- **THEN** the page SHALL keep its local text

#### Scenario: No backend is exempt

- **GIVEN** `detect`, `OCR_LOCAL_BACKENDS=indra,pp-ocrv6-small`, and an Indra result of 400 Devanagari letters with confidence 0.95
- **WHEN** the post-check runs
- **THEN** the page SHALL get the reason `non_latin_output` from Indra
- **AND** the page SHALL pass to `pp-ocrv6-small`

## REMOVED Requirements

### Requirement: Detect mode escalates a non-Latin local OCR result

**Reason**: The rule exempted a backend whose declared scripts held the page's output script. This change removes declared scripts (operator decision, 2026-11-06), so the exemption has nothing to read. The replacement requirement "Detect mode escalates every non-Latin local OCR result" keeps the check for every backend.

**Migration**: An operator who lists a backend that reads non-Latin scripts well, such as Indra, sets `ocr_non_latin_routing` to `off` and lets the confidence cut decide.
