# Spec Delta

## ADDED Requirements

### Requirement: Answers render maths

The assistant answer text SHALL render `$...$` as inline maths and `$$...$$` as display maths, together with its GitHub-flavoured Markdown. A `[n]` marker outside a formula SHALL keep its citation behaviour. Text inside a formula SHALL NOT become a citation button.

#### Scenario: A stored eq01 chunk as an answer

- **WHEN** an answer holds the text of each stored `eq01` fixture chunk
- **THEN** every formula MUST render as KaTeX maths with 0 KaTeX error elements

#### Scenario: A citation next to a formula

- **WHEN** the answer text is `The bound $\mathcal{L}(\theta, \phi; \mathbf{x})$ holds [1]` and ordinal 1 is a returned citation
- **THEN** the formula MUST render as maths and `[1]` MUST be a citation button

### Requirement: Failed claims render inline maths

A claim in the list of claims that failed verification SHALL render inline maths. It SHALL keep only inline marks and SHALL drop block elements to their text, as before.

#### Scenario: A claim with a formula

- **WHEN** a failed claim reads `The prior is $p_{\theta}(\mathbf{z})$`
- **THEN** the claim MUST show one rendered formula and no `$` characters

#### Scenario: A claim with a heading

- **WHEN** a failed claim reads `# Heading $x$`
- **THEN** the claim MUST show no heading element and MUST show the formula as maths

### Requirement: The citation passage renders maths only

The passage text in the citation popover text view, which the Sources panel "Show passage" button also opens, SHALL render `$...$` and `$$...$$` as maths. Every other character SHALL show as plain text, with its line breaks kept. The chunk viewer SHALL keep showing the exact stored text.

#### Scenario: A passage with maths and Markdown signs

- **WHEN** the user opens a passage whose text is `*a* # b <i>c</i> $x^2$`
- **THEN** the passage MUST show `*a* # b <i>c</i>` as written and MUST show `x^2` as one rendered formula

#### Scenario: The chunk viewer shows source text

- **WHEN** the user opens the full chunk of a passage that holds `$x^2$`
- **THEN** the chunk viewer MUST show the text `$x^2$` as written
