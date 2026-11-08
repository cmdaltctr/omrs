# Proposal: catch junk text layers on old printed books (issue #161)

**Status: PARKED.** Written 2026-11-08 on the operator's request, to be taken up when needed. It does not block Experiment 35 or 35a: their datasets (FinanceBench filings, FreshStack docs, BioASQ abstracts) hold no old printed books.

## Why

Issue #161 (severity high, likelihood 3 x impact 8 = 24). Some scanned old printed books (1588 to 1765: German Fraktur, Polish, Dutch blackletter, Latin italic) carry a garbled OCR text layer from the digitiser. The page scan accepts that layer as healthy, so OMRS indexes junk text with no warning and search cannot find the real content.

- Handwritten scans (`rf06`, `rf07`) are already fixed by default (page routing, the local OCR tier, dots-mocr on llama.cpp).
- Experiment 47 (32 unseen documents) showed the page scan sent none of 9 garbled old prints to OCR. The optional document router (Clef-Flash Q8_0, threshold 0.172 from Experiment 43) caught 28 of 54 junk pages (recall 0.52, gate 0.70): FAIL. Most missed old-print pages scored just above the threshold (for example J6 0.13 to 0.28, J15 0.16 to 0.37). Hosted Jev caught 18 of 54.
- Two other misses are not old print: G7 (born-digital Arabic, reversed letter order) and G8 page 11 (born-digital table page). They scored high (0.72 to 0.87), so a threshold change will not catch them.

## What Changes

- One new pre-registered experiment (Confirmatory, next free number when it starts) that asks: can OMRS send garbled old-print text layers to OCR without sending healthy pages there? It compares two candidate signals against the shipped default (no router):
  1. **Refit router threshold**: the existing Clef-Flash router with a threshold fitted on a set of old prints, confirmed on a separate held-out set.
  2. **Cheap text signal**: a deterministic old-print text score (for example the share of tokens found in a word list for the page's language, or character n-gram plausibility) with no model call.
- Production change only if a signal passes the gates on the held-out set. That follow-up (a default change, a new page rule through the reading-parts registry, Settings exposure) is written as its own change after the result.
- G7 (reversed Arabic, issue #196) and table-loss pages (issue #197) are recorded as known limits, out of scope here.

## Capabilities

### New Capabilities

- `old-print-junk-text-evaluation`: how OMRS evaluates a junk-text signal for old printed books before any default changes.

### Modified Capabilities

None. No production behaviour changes in this change.

## Impact

- `experiments/<next>-old-print-junk-text-gate-<date>/` only. No `src/` change.
- Data: new public-domain old prints (archive.org, Google Books, national libraries), with licences recorded. Reuse Experiment 47's old-print documents (J6, J11 to J18) as the fit set only, never as the held-out set.
- Cost: local runs on the Mac (Clef-Flash at 8-bit, root gotcha 16). Hosted Jev only as a named reference arm, only on open-licence pages, with the operator's word on spend.
- Issue #161 stays open until the follow-up production change merges.
