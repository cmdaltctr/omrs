# Statistics levels: basic, medium, expert

Set the level in `plan.json` as `"stats": "basic" | "medium" | "expert"`. The size sets the default. The user can change it. Choose the level before the run.

All functions are in `stats.py`. Copy it into `experiments/_lib/`. In OMRS a different `_lib/stats.py` exists, so read "Statistics module" in SKILL.md first. It uses only the Python standard library. Do not write new statistics code in an experiment folder.

## Pick the test from the data

| Your data per item | Example | Test (medium and up) | Interval |
| --- | --- | --- | --- |
| Yes/no, same items in both arms | Hit@1, page flagged, answer correct | `mcnemar_exact` | `wilson` per arm, `paired_bootstrap` on the difference |
| A score, same items in both arms | nDCG@10, MRR, coverage, latency | `paired_permutation` | `paired_bootstrap` |
| Items grouped (pages in documents, questions per passage) | pages from 40 PDFs | as above, with `groups=` | `paired_bootstrap(..., groups=)` |

Paired means each item is measured under both arms. Always use a paired design when you can. It removes the item-to-item noise.

## The three levels

### Basic

For Quick experiments and smoke tests. No p-values.

- Counts, rates and means for each arm.
- The difference from the baseline.
- Wins, losses and ties per item (`win_loss`).
- Pass or fail for each gate.

Plain sentence: "The candidate got 49 of 76 right, 7 more than the baseline. It won on 12 items, lost on 5 and tied on 59."

### Medium (default)

For Standard experiments. Basic, plus:

- A 95% range for each rate (`wilson`) or mean.
- A 95% range for the difference (`paired_bootstrap`, 10,000 resamples, seed fixed).
- One paired test for each primary hypothesis (`mcnemar_exact` or `paired_permutation`).
- Grouped resampling when items share a document (`groups=`).

Plain sentences:
- Range: "The gain is 9 points. The 95% range is 2 to 16 points, so the true gain is very likely positive."
- Test: "A gain this large would happen by chance about 1 time in 50 (p = 0.02)."
- Range that crosses zero: "The 95% range runs from -3 to +11 points, so this data cannot tell us whether the change helps."

### Expert

For Confirmatory experiments. Medium, plus:

- **Smallest detectable gain** before the run (`min_detectable_effect`). If it is larger than the gain you care about, enlarge the data or downgrade to exploratory.
- **Correction for many tests** (`holm`) when there is more than one primary test.
- **Repeat runs** for model randomness. Run each item 3 or more times and use the mean per item.
- **Sensitivity check**: re-score at the threshold ×0.9 and ×1.1. Report whether the gate result changes.

Plain sentences:
- Detectable gain: "With 76 items we can only detect gains of 12 points or more. A smaller gain may be real but unproven."
- Correction: "After the correction for running 3 tests, only H1 stays below the 0.05 cut-off."
- Sensitivity: "The gate fails at all three thresholds, so the result does not hinge on the exact cut."

## Rules

1. Choose the test and the level in the plan. Do not change them after you see results.
2. Report the difference and its range first. The p-value comes second.
3. "Not significant" means "not shown". It does not mean "no effect". Say which one the range supports.
4. Do not use the bootstrap for p-values with fewer than 50 items. It gives p-values that are too small. Use the permutation test or the exact McNemar test.
5. Write one plain sentence under every number in the report.

## Sources

- Miller, E. (2024). Adding Error Bars to Evals: A Statistical Approach to Language Model Evaluations. arXiv:2411.00640. Recommends standard errors, clustering, paired differences and power analysis.
- Smucker, M. D., Allan, J. and Carterette, B. (2007). A comparison of statistical significance tests for information retrieval evaluation. CIKM. Finds that the randomisation, t-test and bootstrap tests mostly agree, and that the Wilcoxon and sign tests do not.
- Smucker, M. D., Allan, J. and Carterette, B. (2009). Agreement among statistical significance tests for information retrieval evaluation at varying sample sizes. SIGIR. Finds that the bootstrap gives smaller p-values as the number of topics falls.
- Parapar, J. et al. (2021). Simulation of rankings to compare statistical significance tests in information retrieval evaluation. ACM SAC.
