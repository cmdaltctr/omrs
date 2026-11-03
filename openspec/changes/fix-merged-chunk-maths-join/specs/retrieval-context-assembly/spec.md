## ADDED Requirements

### Requirement: A merge never puts text on the same line as a display-maths fence

A display-maths fence is a line that holds only `$$`. When assembly joins two chunk texts that have no exact overlap to remove, and the left text ends with a display-maths fence or the right text starts with one, the join SHALL be one line break. Every other join SHALL stay as the merge rules above define it. A text that already ends or starts with a line break SHALL get no extra line break.

#### Scenario: A closing fence is followed by prose

- **GIVEN** adjacent chunks, the first ending with a line that holds only `$$` and the second starting with `where again the term`
- **WHEN** assembly merges them without an overlap match
- **THEN** the merged text SHALL hold `$$`, a line break, then `where again the term`
- **AND** no line of the merged text SHALL hold `$$` followed by other text

#### Scenario: An opening fence follows prose

- **GIVEN** adjacent chunks, the first ending with `which can be rewritten as:` and the second starting with a line that holds only `$$`
- **WHEN** assembly merges them without an overlap match
- **THEN** the merged text SHALL hold a line break between the two

#### Scenario: Other joins are unchanged

- **GIVEN** adjacent chunks whose first text ends with `first chunk ends here.` and whose second text starts with `Second chunk starts here.`
- **WHEN** assembly merges them without an overlap match
- **THEN** the merged text SHALL join them with one space, as before

#### Scenario: A one-line display formula is unchanged

- **GIVEN** adjacent chunks, the first ending with `$$ x^2 $$` on one line
- **WHEN** assembly merges them without an overlap match
- **THEN** the merged text SHALL join them with one space, as before

#### Scenario: A fence line that ends in a space

- **GIVEN** adjacent chunks, the first ending with a line that holds `$$` and a trailing space, and the second starting with prose
- **WHEN** assembly merges them without an overlap match
- **THEN** the join SHALL be one line break after the trailing space

#### Scenario: A break that is already there is kept as it is

- **GIVEN** adjacent chunks, the first ending with a line that holds only `$$` followed by a newline
- **WHEN** assembly merges them without an overlap match
- **THEN** the merged text SHALL equal the two texts joined directly, with no line break added

#### Scenario: Overlap removal is unchanged

- **GIVEN** adjacent chunks with an exact suffix and prefix match inside the overlap budget
- **WHEN** assembly merges them
- **THEN** the merged text SHALL equal the first text followed by the second text without the matched prefix, as before

#### Scenario: Merging loses no text

- **WHEN** a line break is added at a join
- **THEN** every character of both chunk texts SHALL still be present in order
- **AND** only whitespace SHALL be added
