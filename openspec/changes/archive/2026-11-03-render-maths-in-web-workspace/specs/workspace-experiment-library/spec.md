# Spec Delta

## ADDED Requirements

### Requirement: Experiment Markdown files render maths

An experiment file shown as rendered Markdown SHALL render `$...$` as inline maths and `$$...$$` as display maths. It SHALL still render no raw HTML.

#### Scenario: A report with a formula

- **WHEN** the user opens a `report.md` that contains `$$\log p_{\theta}(\mathbf{x})$$` on its own lines
- **THEN** the file view MUST show one display formula rendered as maths

#### Scenario: HTML in a report stays text

- **WHEN** the user opens a `report.md` that contains `$x$ <script>window.__x = 1</script>`
- **THEN** the formula MUST render as maths and no `script` element MUST be created
