# Decidability table

Bounds are challenger minus baseline, equal-bug percentage points; * = decided (interval excludes 0).

## Defects4J (488 bugs)

| Baseline | E0 archived | E1 +census | +F2 census top-up | +F3 generated tests | +F4 human review | Final (+R fix re-run) | Final, rename-aware | Flips to reopen |
|---|---|---|---|---|---|---|---|---|
| mra | [+2.84, +11.51]* | [+5.57, +11.51]* | [+5.57, +11.51]* | [+5.67, +11.51]* | [+7.02, +10.62]* | [+9.27, +10.33]* | [+9.42, +10.51]* | 51 |
| best_config_top1 | [-1.23, +2.25] | [-1.23, +2.25] | [-1.23, +2.25] | [-1.23, +2.25] | [-0.41, +1.64] | [+1.23, +1.64]* | [+1.23, +1.64]* | 6 |
| first_global | [+1.23, +7.58]* | [+1.23, +7.58]* | [+1.23, +7.58]* | [+1.64, +7.58]* | [+3.69, +6.35]* | [+5.94, +6.35]* | [+5.94, +6.35]* | 29 |
| borda | [+4.51, +10.45]* | [+5.74, +10.45]* | [+5.94, +10.45]* | [+6.15, +10.45]* | [+7.17, +10.04]* | [+7.99, +9.22]* | [+7.58, +8.81]* | 39 |
| rrf | [+4.71, +10.45]* | [+5.74, +10.45]* | [+5.94, +10.45]* | [+5.94, +10.45]* | [+6.97, +10.04]* | [+7.79, +9.22]* | [+7.79, +9.22]* | 38 |
| mean_norm_position | [+8.65, +14.26]* | [+8.86, +14.26]* | [+8.86, +14.26]* | [+8.95, +14.26]* | [+10.38, +13.48]* | [+13.00, +13.43]* | [+13.19, +13.62]* | 64 |
| occurrence | [+5.03, +10.66]* | [+6.00, +10.66]* | [+6.25, +10.66]* | [+6.25, +10.66]* | [+7.28, +10.25]* | [+8.09, +9.43]* | [+7.99, +9.32]* | 40 |
| mra_then_occurrence | [+4.41, +10.35]* | [+5.77, +10.35]* | [+5.77, +10.35]* | [+5.77, +10.35]* | [+6.80, +9.94]* | [+7.41, +9.12]* | [+7.38, +9.02]* | 37 |
| testability | [+0.00, +1.43] | [+0.00, +1.43] | [+0.00, +1.43] | [+0.00, +1.43] | [+0.41, +1.43]* | [+0.41, +0.61]* | [+0.41, +0.61]* | 2 |
| one_stage | [+0.00, +2.25] | [+0.00, +2.25] | [+0.00, +2.25] | [+0.20, +2.25]* | [+0.20, +1.64]* | [+0.41, +0.82]* | [+0.41, +1.02]* | 2 |
| source_agnostic | [-1.57, +4.34] | [+0.31, +4.34]* | [+0.72, +4.34]* | [+0.72, +4.34]* | [+1.64, +4.17]* | [+1.84, +3.28]* | [+2.05, +3.48]* | 9 |
| token_similarity | [+7.13, +14.04]* | [+7.41, +14.04]* | [+7.57, +14.04]* | [+7.83, +14.04]* | [+8.90, +13.31]* | [+11.41, +13.27]* | [+11.41, +13.28]* | 56 |
| codet5_similarity | [+8.10, +13.81]* | [+8.31, +13.81]* | [+8.51, +13.81]* | [+8.57, +13.81]* | [+9.60, +13.21]* | [+12.26, +13.21]* | [+12.26, +13.21]* | 60 |
| naturalness | [+6.97, +13.73]* | [+6.97, +13.73]* | [+7.38, +13.73]* | [+7.38, +13.73]* | [+8.40, +13.12]* | [+10.86, +12.91]* | [+10.86, +12.91]* | 53 |
| entropy_delta | [+6.35, +13.93]* | [+7.38, +13.93]* | [+7.79, +13.93]* | [+7.99, +13.93]* | [+9.02, +13.12]* | [+11.27, +12.71]* | [+11.27, +12.71]* | 55 |
| uniform | [+8.15, +15.42]* | [+8.47, +15.42]* | [+8.74, +15.42]* | [+8.80, +15.42]* | [+9.86, +14.77]* | [+12.47, +14.71]* | [+12.53, +14.73]* | 62 |

Decided per step: E0 archived: 12/16, E1 +census: 13/16, +F2 census top-up: 13/16, +F3 generated tests: 14/16, +F4 human review: 15/16, Final (+R fix re-run): 16/16

Flips to reopen that only the labels set by one layer could cause (per decided comparison):

- mra: E1 +census: not possible, +F2 census top-up: not possible, +F3 generated tests: not possible, +F4 human review: not possible, Final (+R fix re-run): not possible
- best_config_top1: E1 +census: not possible, +F2 census top-up: not possible, +F3 generated tests: not possible, +F4 human review: not possible, Final (+R fix re-run): 6
- first_global: E1 +census: not possible, +F2 census top-up: not possible, +F3 generated tests: not possible, +F4 human review: not possible, Final (+R fix re-run): not possible
- borda: E1 +census: not possible, +F2 census top-up: not possible, +F3 generated tests: not possible, +F4 human review: not possible, Final (+R fix re-run): not possible
- rrf: E1 +census: not possible, +F2 census top-up: not possible, +F3 generated tests: not possible, +F4 human review: not possible, Final (+R fix re-run): not possible
- mean_norm_position: E1 +census: not possible, +F2 census top-up: not possible, +F3 generated tests: not possible, +F4 human review: not possible, Final (+R fix re-run): not possible
- occurrence: E1 +census: not possible, +F2 census top-up: not possible, +F3 generated tests: not possible, +F4 human review: not possible, Final (+R fix re-run): not possible
- mra_then_occurrence: E1 +census: not possible, +F2 census top-up: not possible, +F3 generated tests: not possible, +F4 human review: not possible, Final (+R fix re-run): not possible
- testability: E1 +census: not possible, +F2 census top-up: not possible, +F3 generated tests: not possible, +F4 human review: 2, Final (+R fix re-run): not possible
- one_stage: E1 +census: not possible, +F2 census top-up: not possible, +F3 generated tests: not possible, +F4 human review: not possible, Final (+R fix re-run): not possible
- source_agnostic: E1 +census: 12, +F2 census top-up: not possible, +F3 generated tests: not possible, +F4 human review: not possible, Final (+R fix re-run): not possible
- token_similarity: E1 +census: not possible, +F2 census top-up: not possible, +F3 generated tests: not possible, +F4 human review: not possible, Final (+R fix re-run): not possible
- codet5_similarity: E1 +census: not possible, +F2 census top-up: not possible, +F3 generated tests: not possible, +F4 human review: not possible, Final (+R fix re-run): not possible
- naturalness: E1 +census: not possible, +F2 census top-up: not possible, +F3 generated tests: not possible, +F4 human review: not possible, Final (+R fix re-run): not possible
- entropy_delta: E1 +census: not possible, +F2 census top-up: not possible, +F3 generated tests: not possible, +F4 human review: not possible, Final (+R fix re-run): not possible
- uniform: E1 +census: not possible, +F2 census top-up: not possible, +F3 generated tests: not possible, +F4 human review: not possible, Final (+R fix re-run): not possible

## HumanEval-Java (E3)

| Baseline | A0 archived | HE-E1 primary | X4 post hoc |
|---|---|---|---|
| uniform_random | [-3.76, +41.20] | [+21.11, +37.82]* | [+15.61, +38.75]* |
| token_similarity | [+7.88, +49.43]* | [+36.01, +46.10]* | [+30.50, +46.84]* |
| occurrence_count | [-38.26, +38.91] | [-7.12, +3.13] | [-11.75, +16.32] |
| native_position | [-16.18, +29.22] | [+9.72, +21.23]* | [+4.67, +23.37]* |
| native_then_occurrence | [-33.48, +31.06] | [-7.21, +1.35] | [-10.40, +12.16] |
| testability_product | [-4.94, +3.09] | [-1.85, -1.23]* | [-2.47, -1.23]* |

## G1 fresh campaign (confirmatory)

|---|---|---|---|
| challenger_frozen vs occurrence | [-17.41, +25.27] | [-3.53, +3.23] | [-2.72, +2.82] |
| occurrence vs uniform | [-52.28, +28.78] | [-6.70, +4.69] | - |
| challenger_frozen vs uniform | [-53.43, +37.79] | [-7.19, +4.86] | - |
| codet5_similarity vs uniform | [-53.31, +25.50] | [-6.69, +3.80] | - |
| naturalness vs uniform | [-46.76, +51.41] | [-5.90, +7.88] | - |

## Other studies

- RepairBench: 1/9 pairs decided.
- D4C trigger passage: 1/4 decided.
- D2 plausible pools: 0/21 decided.
- PrevaRank input order: 0/51 permutation-vs-canonical comparisons decided.
- POD detector pairs: 0/10 decided.
