# Spec Delta

## ADDED Requirements

### Requirement: Maths renders through one shared renderer in the base build

The web workspace SHALL render LaTeX maths between `$...$` and `$$...$$` with `remark-math` 6.0.0, `rehype-katex` 7.0.1 and `katex` 0.16.22. `web/package.json` SHALL list all three in `dependencies` at these exact versions, and the lock file SHALL hold one copy of `katex`. Every surface that renders maths SHALL take its plugins and KaTeX options from one shared module.

#### Scenario: The pins are exact

- **WHEN** the front-end dependencies are read from `web/package.json`
- **THEN** `remark-math`, `rehype-katex` and `katex` MUST be listed in `dependencies` as `6.0.0`, `7.0.1` and `0.16.22` with no range prefix

#### Scenario: One KaTeX copy

- **WHEN** `npm ls katex` runs in `web/` after `npm ci`
- **THEN** it MUST list exactly one `katex` version, 0.16.22

### Requirement: Maths needs no network and no integration

The KaTeX stylesheet SHALL load through `app.css` into the `vendor` layer, and the build SHALL bundle the KaTeX fonts into the build output. The page SHALL request no maths file from any host other than the OMRS server. Maths rendering SHALL NOT appear in the Integrations catalogue and SHALL offer no Install button.

#### Scenario: Fonts load from the OMRS server

- **WHEN** the workspace shows a formula with the network limited to the OMRS server
- **THEN** every KaTeX stylesheet and font request MUST go to the OMRS server and the formula MUST render in the KaTeX fonts

#### Scenario: The stylesheet sits in the vendor layer

- **WHEN** the cascade test reads `app.css`
- **THEN** the KaTeX stylesheet import MUST carry `layer(vendor)`

#### Scenario: No catalogue entry

- **WHEN** the user opens the Integrations page
- **THEN** no entry for maths, KaTeX, `remark-math` or `rehype-katex` MUST be listed

### Requirement: A formula that cannot be parsed stays local

When KaTeX cannot parse a formula, the surface SHALL show that formula's LaTeX source in the error colour token and SHALL render the rest of the text normally. A parse failure SHALL NOT throw into React and SHALL NOT replace the surface with an error state.

#### Scenario: A broken inline formula

- **WHEN** an answer reads `Before $\frac{a}{$ after`
- **THEN** the answer MUST show one error element whose text is the formula source
- **AND** the text `after` MUST still render and the rest of the page MUST keep working

### Requirement: Maths keeps HTML out

Maths rendering SHALL keep the rule that HTML in model or document text is shown as text. KaTeX SHALL run with `trust` off, so a formula cannot create a link, an image, a class, an id, a style or a data attribute through a KaTeX command.

#### Scenario: Raw HTML next to maths

- **WHEN** an answer contains `$x$ <b>raw</b><script>window.__x = 1</script>`
- **THEN** the formula MUST render as maths, no `b` or `script` element MUST be created, and the tags MUST show as text

#### Scenario: A link command in a formula

- **WHEN** an answer contains `$\href{javascript:alert(1)}{x}$`
- **THEN** no `a` element MUST be created

### Requirement: A wide display formula scrolls in its own box

A display formula wider than its container SHALL scroll sideways inside its own box. The page SHALL NOT scroll sideways because of a formula.

#### Scenario: A long formula on a phone-width window

- **WHEN** an answer with the longest `eq01` display formula is shown at a 390 px wide window
- **THEN** the formula box MUST scroll sideways and the page MUST have no horizontal scroll
