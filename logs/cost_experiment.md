# Cost experiment: baseline vs cost-saver

Cost-saver = prompt order (static text first) + trimmed Analyst/Writer prompts + batched nutrition lookups. 10 dishes have both runs (status ok); one run per dish and config.

## Summary (averages over paired dishes)

| Metric | Baseline | Cost-saver | Change |
|---|---|---|---|
| Input tokens | 11,709 | 7,146 | -39.0% |
| Cached input tokens | 3,265 | 619 | -81.0% |
| Output tokens | 2,829 | 2,545 | -10.0% |
| Cost per run | $0.002414 | $0.002006 | -16.9% |
| Requests | 8.2 | 7.6 | -7.3% |
| Tool calls | 19.4 | 4.8 | -75.3% |
| Latency (s) | 33.2 | 31.7 | -4.5% |
| **Quality** | | | |
| Nutrition match rate (avg) | 91.7% | 82.0% | |
| Unmatched ingredients (avg) | 1.3 | 2.4 | |
| No-substitute count (avg) | 1.8 | 1.7 | |
| Substituted count (avg) | 0.7 | 0.7 | |
| Writer fallback rate | 0% | 0% | |
| Writer regeneration rate | 10% | 0% | |
| Catalog valid rate (proposed substitutes found in catalog) | 100% | 100% | |
| Allergen detection rate (conflict_detected / expected, 5 dishes) | 100% | 100% | |
| Residual allergen conflicts (count) | 0 | 0 | |
| Expected allergen word still in final recipe (count) | 1 | 1 | |

## Where the cost goes (average per run)

| Config | Fresh input | Cached input | Output | Total | Output share of cost |
|---|---|---|---|---|---|
| baseline | $0.000967 | $0.000033 | $0.001414 | $0.002414 | 58.6% |
| cost_saver | $0.000728 | $0.000006 | $0.001272 | $0.002006 | 63.4% |

Output tokens cost 5x normal input and 50x cached input, which is why they dominate even though there are fewer of them.

## Per dish

| Dish | Config | Input | Cached | Output | Cost | Requests | Latency (s) | Nutrition match | Writer path | Substituted / none | Residual conflict | Cache flag |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| d01 | baseline | 12,575 | 3,325 | 3,718 | $0.002945 | 8 | 35.4 | 72% | original | 1 / 4 | False |  |
| d01 | cost_saver | 9,399 | 1,914 | 3,376 | $0.002566 | 8 | 35.6 | 62% | original | 2 / 2 | False |  |
| d02 | baseline | 8,356 | 0 | 3,079 | $0.002493 | 7 | 30.7 | 94% | original | 1 / 1 | False |  |
| d02 | cost_saver | 10,417 | 2,255 | 2,557 | $0.002198 | 10 | 33.2 | 80% | original | 0 / 2 | False |  |
| d03 | baseline | 14,701 | 3,422 | 4,603 | $0.003645 | 10 | 56.6 | 76% | original | 1 / 5 | False |  |
| d03 | cost_saver | 8,894 | 0 | 3,585 | $0.002782 | 9 | 41.7 | 65% | original | 0 / 6 | False |  |
| d04 | baseline | 14,060 | 6,155 | 3,178 | $0.002543 | 9 | 35.9 | 80% | original | 0 / 3 | None |  |
| d04 | cost_saver | 4,848 | 0 | 2,343 | $0.001689 | 7 | 29.7 | 60% | original | 0 / 3 | None |  |
| d05 | baseline | 8,924 | 2,375 | 1,722 | $0.001619 | 8 | 23.6 | 100% | original | 0 / 1 | False |  |
| d05 | cost_saver | 5,448 | 0 | 1,360 | $0.001280 | 7 | 28.0 | 100% | original | 0 / 1 | False |  |
| d06 | baseline | 8,021 | 2,779 | 1,425 | $0.001347 | 6 | 24.6 | 100% | original | 0 / 0 | None |  |
| d06 | cost_saver | 6,118 | 2,025 | 1,215 | $0.001092 | 6 | 30.0 | 83% | original | 0 / 0 | None |  |
| d07 | baseline | 20,605 | 9,224 | 3,481 | $0.003139 | 11 | 41.1 | 94% | original | 1 / 3 | False |  |
| d07 | cost_saver | 8,452 | 0 | 3,631 | $0.002760 | 9 | 38.7 | 79% | original | 2 / 2 | False |  |
| d08 | baseline | 9,653 | 3,560 | 1,790 | $0.001642 | 6 | 24.4 | 100% | original | 0 / 0 | None |  |
| d08 | cost_saver | 4,431 | 0 | 2,579 | $0.001797 | 5 | 24.2 | 91% | original | 0 / 0 | None |  |
| d09 | baseline | 13,861 | 0 | 4,133 | $0.003657 | 11 | 43.8 | 100% | regenerated | 3 / 1 | False |  |
| d09 | cost_saver | 10,121 | 0 | 3,699 | $0.002974 | 10 | 38.0 | 100% | original | 3 / 1 | False |  |
| d10 | baseline | 6,331 | 1,810 | 1,159 | $0.001114 | 6 | 16.1 | 100% | original | 0 / 0 | False |  |
| d10 | cost_saver | 3,328 | 0 | 1,102 | $0.000923 | 5 | 18.3 | 100% | original | 0 / 0 | False |  |

## Verdict

- **Cost:** the cost-saver changed the average cost per run by -16.9% ($0.002414 to $0.002006). It was cheaper on 9 of 10 dishes. The paired difference is larger than 2 standard errors, so it is probably real, but it is still only 10 dishes with one run each.
- **Quality:** nutrition match 91.7% vs 82.0%; Writer fallback: 0 (baseline) vs 0 (cost-saver); Writer regeneration: 1 (baseline) vs 0 (cost-saver); residual allergen conflicts 0 vs 0; allergen detection 100% vs 100%.
- **Nutrition match per dish:** the cost-saver was lower on 7, higher on 0, equal on 3 of 10 dishes (the same direction in most dishes, so it is unlikely to be noise alone). Ingredients without a USDA match are left out of the nutrition totals, so a lower match rate means less complete numbers.
- **How to read the quality differences:** with 10 dishes, one dish is a 10-point swing, and the model is not deterministic, so small differences in these rates are within noise. A change in writer fallbacks, residual allergen conflicts or allergen detection would deserve a closer look at the individual dishes above.
- Nothing was tuned after seeing these numbers; the settings are the ones fixed before the run.
