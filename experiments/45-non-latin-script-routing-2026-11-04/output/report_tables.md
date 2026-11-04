### (a) Flagged pages, verdict on the text items before OCR

| Document | Page class | Flagged pages | Non-Latin | Latin | No verdict |
| --- | --- | --- | --- | --- | --- |
| io01 | non_latin | 48 | 0 | 48 | 0 |
| io01 | unclassified | 1 | 0 | 1 | 0 |
| io02 | non_latin | 16 | 0 | 0 | 16 |
| io03 | non_latin | 5 | 0 | 0 | 5 |
| io04 | latin | 52 | 0 | 0 | 52 |
| io05 | latin | 8 | 0 | 0 | 8 |
| io06 | latin | 78 | 0 | 0 | 78 |
| io07 | non_latin | 60 | 0 | 0 | 60 |
| io07 | unclassified | 6 | 0 | 0 | 6 |
| io08 | latin | 2 | 0 | 0 | 2 |
| mx08 | latin | 13 | 0 | 0 | 13 |
| rf01 | latin | 1 | 0 | 0 | 1 |
| rf02 | latin | 8 | 0 | 0 | 8 |
| rf03 | latin | 7 | 0 | 0 | 7 |
| rf04 | latin | 8 | 0 | 0 | 8 |
| rf05 | latin | 25 | 0 | 0 | 25 |
| rf06 | latin | 89 | 0 | 0 | 89 |
| rf07 | latin | 63 | 0 | 0 | 63 |
| rf08 | latin | 28 | 0 | 0 | 28 |
| tl01 | latin | 80 | 0 | 0 | 80 |
| tl02 | latin | 45 | 0 | 0 | 45 |
| tl03 | latin | 24 | 0 | 0 | 24 |
| tl04 | latin | 12 | 0 | 0 | 12 |
| tl05 | latin | 12 | 0 | 0 | 12 |
| tl06 | latin | 3 | 0 | 0 | 3 |
| tl07 | latin | 3 | 0 | 0 | 3 |
| tl08 | latin | 4 | 0 | 0 | 4 |

### (b) Stored local OCR text, verdict per document

| Document | Page class | Stored rows | Non-Latin | Latin | No verdict |
| --- | --- | --- | --- | --- | --- |
| bd02 | latin | 2 | 0 | 2 | 0 |
| bd04 | latin | 6 | 0 | 6 | 0 |
| bd07 | latin | 3 | 0 | 3 | 0 |
| io01 | non_latin | 48 | 9 | 21 | 18 |
| io02 | non_latin | 16 | 0 | 1 | 15 |
| io03 | non_latin | 5 | 0 | 5 | 0 |
| io04 | latin | 52 | 0 | 52 | 0 |
| io05 | latin | 7 | 0 | 7 | 0 |
| io06 | latin | 67 | 0 | 64 | 3 |
| io07 | non_latin | 60 | 52 | 1 | 7 |
| io08 | latin | 2 | 0 | 2 | 0 |
| mx01 | latin | 2 | 0 | 2 | 0 |
| mx02 | latin | 3 | 0 | 3 | 0 |
| mx03 | latin | 4 | 0 | 4 | 0 |
| mx04 | latin | 2 | 0 | 2 | 0 |
| mx05 | latin | 11 | 0 | 11 | 0 |
| mx06 | latin | 3 | 0 | 3 | 0 |
| mx07 | latin | 7 | 0 | 7 | 0 |
| mx08 | latin | 1 | 0 | 1 | 0 |
| rf06 | latin | 44 | 0 | 44 | 0 |
| rf07 | latin | 18 | 0 | 17 | 1 |
| rf08 | latin | 1 | 0 | 1 | 0 |
| tl01 | latin | 47 | 0 | 27 | 20 |
| tl02 | latin | 33 | 0 | 33 | 0 |
| tl03 | latin | 17 | 0 | 15 | 2 |
| tl06 | latin | 1 | 0 | 1 | 0 |
| tl07 | latin | 1 | 0 | 1 | 0 |
| tl08 | latin | 1 | 0 | 1 | 0 |

### (c) False positives on Latin pages

| Part | Latin pages | With a verdict | Non-Latin verdicts |
| --- | --- | --- | --- |
| c1 flagged pages, before OCR | 565 | 0 | 0 |
| c2 stored local text | 335 | 309 | 0 |
| c3 engine text (not gated) | 128 | 119 | 0 |

### (d) Local seconds on the 129 non-Latin pages (saved by `always`)

| Document | Seconds |
| --- | --- |
| io01 | 20.064 |
| io02 | 22.528 |
| io03 | 15.485 |
| io07 | 31.86 |
| Total (129 pages) | 89.937 |
| Total without timed-out documents | 89.937 |
| Latin-class stored rows (335 rows) | 641.432 |

### (e) The 129 non-Latin pages and the 0.9 cut

| Document | Pages | Kept by cut (e0) | Kept and non-Latin (e) | Low confidence | Hosted recommended | Confidence range |
| --- | --- | --- | --- | --- | --- | --- |
| io01 | 48 | 0 | 0 | 48 | 0 | 0.566 to 0.762 |
| io02 | 16 | 0 | 0 | 16 | 0 | 0.565 to 0.805 |
| io03 | 5 | 0 | 0 | 5 | 1 | 0.454 to 0.539 |
| io07 | 60 | 0 | 0 | 60 | 4 | 0.462 to 0.661 |
| All | 129 | 0 | 0 | 129 | 5 | 0.454 to 0.805 |

### Descriptive: letters per script in the engine text of the 129 pages

| Document | Top scripts (letters) |
| --- | --- |
| io01 | {"DEVANAGARI": 15067, "LATIN": 497} |
| io02 | {"ARABIC": 31417, "LATIN": 124, "CJK": 7, "THAI": 1, "CYRILLIC": 1} |
| io03 | {"ARABIC": 29545, "LATIN": 122} |
| io07 | {"BENGALI": 22253} |

