# web-ui-stack Specification

## Purpose
The Tailwind v4 + shadcn-style component stack for the web workspace: build wiring, the token bridge, and the primitive set with its visual and accessibility contract.

## Requirements

### Requirement: Status labels meet WCAG AA

`web/src/styles/tokens.css` SHALL define `--status-error-label`, `--status-warning-label`, `--status-success-label` and `--status-info-label` as 60% of the status colour mixed with 40% of `--text-primary`, declared once so both themes follow `--text-primary`. The bridge SHALL expose them as `text-status-*-label`, and badges SHALL use them for text.

#### Scenario: Badges read the label tokens

- **WHEN** a status badge renders its text
- **THEN** the text MUST use the `text-status-*-label` utility that the bridge exposes for that status

### Requirement: Each status label has AA contrast on its tint

Each label SHALL have a contrast ratio of at least 4.5:1 on its status colour at 10% opacity over the canvas, elevated and muted surfaces, in light and dark themes.

#### Scenario: A palette change lowers a label contrast

- **WHEN** a status colour, surface colour, text colour or mix percentage changes so that any label falls below 4.5:1 on its tint in either theme
- **THEN** the token test MUST fail

### Requirement: The elevation token and dark variant follow the theme

`tokens.css` SHALL define `--shadow-floating` for both themes, exposed as the `shadow-floating` utility. The Tailwind `dark` variant SHALL apply when `data-theme="dark"` is set, or when the system prefers dark and `data-theme="light"` is not set.

#### Scenario: Dark variant with the system preference

- **WHEN** the system prefers dark and `data-theme` is unset
- **THEN** `dark:` utilities MUST apply

#### Scenario: Light override

- **WHEN** the system prefers dark and `data-theme="light"` is set
- **THEN** `dark:` utilities MUST NOT apply

### Requirement: The shadcn CLI is configured

`web/components.json` SHALL configure the shadcn new-york style with TypeScript and CSS variables so `npx shadcn@latest add <component>` installs into the project's component directory using the bridged tokens.

#### Scenario: Adding a primitive later

- **WHEN** a maintainer runs the shadcn add command for a new primitive
- **THEN** the generated files MUST land in `web/src/components/ui/` and compile against the token bridge without manual edits

### Requirement: The first primitive set ships with the OpenChamber treatment

`web/src/components/ui/` SHALL provide button, badge, card, dialog, input, select, label, tooltip, separator and table primitives styled with the OpenChamber palette and geometry from the design reference: tinted primary buttons (10/16/22% light, 16/22/30% dark rest/hover/pressed with saturated border and label colour), flat cards with 1px borders, 10px control radius, 36px default control height, and 150ms transitions.

#### Scenario: Primary button rendering

- **WHEN** a default button renders in light theme
- **THEN** its fill, border and text MUST use the accent tint tokens at the documented strengths

#### Scenario: Badge variants

- **WHEN** a status badge renders for each status token
- **THEN** fill and border MUST derive from that status colour, the text MUST use that status's label token, and the value MUST be visible as text

### Requirement: Primitives keep the Radix accessibility contract

Dialog, select, tooltip and label primitives SHALL keep their Radix behaviour: focus trapping, Escape to close, focus return, aria attributes and keyboard navigation. Icon-only controls SHALL carry an accessible name.

#### Scenario: Dialog keyboard flow

- **WHEN** a user opens a dialog ported from Radix and presses Escape
- **THEN** the dialog MUST close and focus MUST return to the trigger

### Requirement: Tailwind builds with preflight and the token bridge

The web build SHALL compile Tailwind CSS v4 through `@tailwindcss/vite` and SHALL expose the semantic custom properties from `web/src/styles/tokens.css` to utility classes through a `@theme inline` block that holds no literal colours. Tailwind's preflight reset SHALL load into the `base` cascade layer. Light and dark themes SHALL switch through the `prefers-color-scheme` and `data-theme` mechanisms.

#### Scenario: Utility classes read the tokens

- **WHEN** a component uses a bridged utility class such as a surface or accent colour
- **THEN** the rendered value MUST come from the `tokens.css` custom property in the active theme

#### Scenario: A bridge alias points at a missing token

- **WHEN** an alias in the `@theme inline` block references a custom property that `tokens.css` does not declare
- **THEN** the bridge test MUST fail

#### Scenario: Preflight is loaded

- **WHEN** the app builds
- **THEN** Tailwind's preflight rules MUST be present in the `base` layer of the generated stylesheet

### Requirement: Only two stylesheets exist, loaded through one layered entry

`web/src/styles/tokens.css` and `web/src/styles/app.css` SHALL be the only stylesheets in `web/src`. `app.css` SHALL declare the cascade layers `theme, base, vendor, components, utilities` in that order, SHALL load Tailwind's theme, preflight and utilities into their layers, and SHALL import third-party stylesheets into the `vendor` layer.

#### Scenario: A utility beats a vendor rule

- **WHEN** an element carries a Tailwind utility and also matches a vendor rule for the same property, including a rule with higher specificity
- **THEN** the utility MUST win

#### Scenario: Another stylesheet is added

- **WHEN** a `.css` file other than `tokens.css` and `app.css` exists under `web/src`
- **THEN** the cascade test MUST fail

### Requirement: Only the entry file imports CSS

Overrides that must target a third-party library's own class names SHALL live in `app.css` under the `components` layer. Only `main.tsx` SHALL import CSS (`tokens.css`, then `app.css`); components SHALL NOT import stylesheets.

#### Scenario: A component imports a stylesheet

- **WHEN** a component file contains a `.css` import
- **THEN** the cascade test MUST fail, because the rule would sit outside every layer and override utilities

### Requirement: The accordion primitive keeps the Radix accessibility contract

`web/src/components/ui/` SHALL provide an accordion primitive that allows several sections open at once. It SHALL keep the Radix behaviour: each header is a button with `aria-expanded` and `aria-controls`, Enter and Space toggle a section, the arrow keys, Home and End move focus between headers, and closed content is hidden from assistive technology.

#### Scenario: Header state

- **WHEN** a section is closed and the user opens it
- **THEN** its header MUST report `aria-expanded="true"` and its content MUST be visible

#### Scenario: Arrow keys move between headers

- **WHEN** focus is on a section header and the user presses the Down arrow
- **THEN** focus MUST move to the next section header

#### Scenario: Closed content is hidden

- **WHEN** a section is closed
- **THEN** its content MUST NOT be reachable by Tab or exposed to a screen reader

### Requirement: The accordion header shows an icon, focus and open state

The accordion primitive SHALL let a header show a leading icon that is hidden from assistive technology, so the title stays the accessible name. The accordion primitive SHALL use the shared semantic tokens, show a visible focus ring and carry the open state as text or an icon that changes with the state.

#### Scenario: Header icon does not change the name

- **WHEN** a section header shows a leading icon and the title "Operations"
- **THEN** the header's accessible name MUST be "Operations"

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

Maths rendering SHALL keep the rule that HTML in model or document text is shown as text. KaTeX SHALL run with `trust` off, so a formula cannot create a link, an image or a script element through a KaTeX command.

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

### Requirement: A dollar sign that is not maths stays text

A single `$` pair SHALL render as a formula only when no space follows the opening dollar sign, no space comes before the closing dollar sign, and no digit follows the closing dollar sign. Otherwise the text, with every space, SHALL show as written. A `$$` pair SHALL not be changed by this rule.

#### Scenario: Dollar amounts

- **WHEN** text reads `It costs $5 and $10, or $40 more. A ton of coal is another $`
- **THEN** no formula SHALL render
- **AND** every space SHALL stay

#### Scenario: Shell variables

- **WHEN** text reads `echo $HOME and $PATH`
- **THEN** no formula SHALL render

#### Scenario: Two formulas in one sentence

- **WHEN** text reads `a $x$, b $y$.`
- **THEN** two formulas SHALL render

### Requirement: A formula's size is limited

KaTeX SHALL run with a maximum size of 20 em, so a formula cannot draw a rule or box larger than that.

#### Scenario: An oversized rule

- **WHEN** text holds `$\rule{5000em}{5000em}$`
- **THEN** the rendered rule SHALL be no larger than 20 em in either direction
