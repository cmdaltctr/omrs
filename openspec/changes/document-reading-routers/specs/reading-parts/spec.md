## ADDED Requirements

### Requirement: A page rule descriptor SHALL declare whether the rule adds pages

A page rule descriptor SHALL carry the fact `adds_pages`, default false, beside `drops_pages`, `sends_direct`, `has_post_check` and `has_degrade`. The `register()` line SHALL carry the same fact, and the pin test SHALL fail when they differ. A rule that returns pages in `add` without the fact SHALL fail its tests.

#### Scenario: Pin catches a missing fact

- **GIVEN** a descriptor with `adds_pages` true and a `register()` line without it
- **WHEN** the pin test runs
- **THEN** it SHALL fail and name the rule and the fact

### Requirement: Page renderers SHALL be an ordered list behind the shared registry

Page renderers SHALL be held by the shared registry helper in `integrations/pdf/page_images/`, one `register()` line each. A renderer SHALL NOT be a reading part: it has no descriptor and no entry-point group. The first available renderer SHALL render a page at 150 DPI with the long side at most 1,568 px, as a PNG.

#### Scenario: First renderer missing

- **GIVEN** the first renderer is unavailable and the second is installed
- **WHEN** a page is rendered
- **THEN** the second renderer SHALL render it

#### Scenario: No renderer

- **GIVEN** no renderer is available
- **WHEN** an image router needs a page image
- **THEN** the router SHALL degrade with the reason `renderer-missing`
