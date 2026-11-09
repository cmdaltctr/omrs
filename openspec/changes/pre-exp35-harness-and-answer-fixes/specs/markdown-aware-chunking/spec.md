## ADDED Requirements

### Requirement: The Markdown splitter is built once per set of splitter inputs

The model-token-aware Markdown path SHALL reuse one splitter for every document and every fit step that asks for the same tokenizer, capacity and overlap, instead of building a new splitter for each document. A change in any of the three inputs SHALL give a separate splitter. Reuse SHALL NOT change the chunks, their offsets or their order.

#### Scenario: Documents with the same settings share one splitter

- **GIVEN** three Markdown documents split with the same tokenizer, capacity and overlap
- **WHEN** the model-token-aware path splits them
- **THEN** the splitter SHALL be built once
- **AND** the chunks SHALL equal the chunks produced when a new splitter is built for each document

#### Scenario: A different capacity builds a separate splitter

- **GIVEN** a splitter already built for one capacity
- **WHEN** the path needs the same tokenizer and overlap at a different capacity
- **THEN** it SHALL build a second splitter for that capacity
- **AND** it SHALL NOT reuse the first splitter for it
