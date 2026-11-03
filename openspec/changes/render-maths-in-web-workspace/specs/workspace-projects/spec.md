# Spec Delta

## ADDED Requirements

### Requirement: Search results render maths

Each Knowledge Base search result SHALL render `$...$` and `$$...$$` in its passage text as maths. Every other character SHALL show as plain text, exactly as stored, with its indentation, trailing spaces and line breaks kept, so OCR text is not read as Markdown. Text in inline code or a fenced code block SHALL stay as written, so `$x$` in a code sample renders no maths.

#### Scenario: A result from eq01

- **WHEN** a search returns a stored `eq01` fixture chunk
- **THEN** the result MUST show every formula as KaTeX maths with 0 KaTeX error elements

#### Scenario: Markdown signs stay as written

- **WHEN** a search result passage reads `*a* # b [d](e) $x$`
- **THEN** the result MUST show `*a* # b [d](e)` as written and MUST show `x` as one rendered formula
