# Tasks

Parked 2026-11-08. Start only on the operator's word.

## 1. Plan

- [ ] 1.1 Reserve the next free experiment number and scaffold the folder (`omrs experiments new`). Verify: folder and `experiment.json` (Confirmatory, PLANNED).
- [ ] 1.2 Collect the fit set (Experiment 47 old prints plus new) and the held-out set (D1), with licences and SHA-256. Verify: `inputs.json` with hashes; held-out documents absent from Experiments 43 and 47.
- [ ] 1.3 Label every page from its image (D3) before any arm runs. Verify: `labels.json` committed before scores.
- [ ] 1.4 Write `protocol.md` and `plan.json` with arms, gates and stop rule (D2, D4). Operator approves the freeze and any hosted spend. Verify: plan committed before the first held-out run.

## 2. Fit

- [ ] 2.1 Fit the Clef-Flash threshold and the text-score cut on the fit set only. Verify: values written into `plan.json` as an amendment before the held-out run.

## 3. Confirm

- [ ] 3.1 Run all arms on the held-out set. Verify: per-arm score files and `summary.json`.
- [ ] 3.2 Write the report with gates, Wilson intervals and the decision. Verify: report and `experiment.json` status set.

## 4. Follow-up

- [ ] 4.1 If an arm passes, propose the production change (D5). If none passes, comment the documented limit on #161. Verify: new change id or issue comment.
