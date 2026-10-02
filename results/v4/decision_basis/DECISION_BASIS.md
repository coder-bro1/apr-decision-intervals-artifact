# Decision basis of the Defects4J decisions

exploratory, post hoc (designed after the final results were known). View: final Defects4J evidence E1+F2+F3+F4+R; bug unit, AST identity, known-wins, N-a, equal-bug.

A decision basis is a set of known labels whose correctness alone keeps the decision, with every other label treated as unknown. Minimal bases are not unique; this is *a* basis, built by one deterministic rule: use as few labels as possible from the least trustworthy tier, then the next, and so on (no-op rule, F3, human, R, execution failure, reference identity), highest gain first within a tier.

Tiers: T1 reference identity (archived exact/AST match to the developer fix); T2 execution failure (archived harness failure, census witness, F2 witness); R labels set by the fix-identical re-run or C1-fix; T3 human judgment (archived reviewers, F4); T4 F3 generated-test witness; T5 no-op rule.

Bounds are challenger minus baseline, equal-bug percentage points over 488 bugs. Flips to reopen = the smallest number of known labels whose flip makes the interval contain 0 (equal to the robustness column of results/v4/decidability). eps* = L / sum of all label gains (break-even random error rate).

| Comparison | Decided interval (pp) | Basis size by tier (T1 / T2 / R / T3 / T4 / T5) | Human judgments needed | F3 / no-op needed? | Flips to reopen | eps* |
|---|---|---|---|---|---|---|
| mra | [+9.27, +10.33] | 57 / 3572 / 0 / 0 / 0 / 0 | 0 | no/no | 51 | 9.49% |
| best_config_top1 | [+1.23, +1.64] | 22 / 224 / 8 / 12 / 0 / 0 | 12 (9 archived, 3 F4): Chart-10(i), Cli-35(c), Cli-9(i), Closure-31*(i), Codec-7*(c), Gson-16(c), Gson-5(i), JacksonDatabind-16(i), JacksonDatabind-67*(i), JacksonDatabind-70(i), Jsoup-40(i), Jsoup-6(i) | no/no | 6 | 2.21% |
| first_global | [+5.94, +6.35] | 47 / 381 / 11 / 6 / 0 / 0 | 6 (4 archived, 2 F4): Chart-4(i), Cli-17*(i), Cli-32(i), Cli-40(i), Closure-129*(i), Closure-31(i) | no/no | 29 | 6.13% |
| borda | [+7.99, +9.22] | 45 / 324 / 0 / 0 / 0 / 0 | 0 | no/no | 39 | 9.57% |
| rrf | [+7.79, +9.22] | 45 / 334 / 0 / 0 / 0 / 0 | 0 | no/no | 38 | 9.12% |
| mean_norm_position | [+13.00, +13.43] | 57 / 1558 / 0 / 0 / 0 / 0 | 0 | no/no | 64 | 12.02% |
| occurrence | [+8.09, +9.43] | 46 / 342 / 0 / 0 / 0 / 0 | 0 | no/no | 40 | 9.39% |
| mra_then_occurrence | [+7.41, +9.12] | 46 / 336 / 0 / 0 / 0 / 0 | 0 | no/no | 37 | 8.76% |
| testability | [+0.41, +0.61] | 9 / 85 / 0 / 6 / 0 / 0 | 6 (4 archived, 2 F4): Cli-35(c), Closure-61*(c), Csv-14(i), Jsoup-34(i), Lang-18(i), Lang-33*(c) | no/no | 2 | 1.98% |
| one_stage | [+0.41, +0.82] | 12 / 59 / 1 / 4 / 0 / 0 | 4 (4 archived, 0 F4): JacksonDatabind-101(i), JacksonDatabind-16(i), Jsoup-41(i), Time-7(i) | no/no | 2 | 2.60% |
| source_agnostic | [+1.84, +3.28] | 26 / 322 / 2 / 9 / 0 / 0 | 9 (7 archived, 2 F4): Chart-4(i), Cli-17(i), Cli-35(c), Closure-31*(i), Closure-58(i), Closure-61*(c), Csv-14(i), Csv-15(i), Jsoup-34(i) | no/no | 9 | 3.47% |
| token_similarity | [+11.41, +13.27] | 56 / 3013 / 0 / 0 / 0 / 0 | 0 | no/no | 56 | 10.83% |
| codet5_similarity | [+12.26, +13.21] | 52 / 1331 / 0 / 0 / 0 / 0 | 0 | no/no | 60 | 11.75% |
| naturalness | [+10.86, +12.91] | 51 / 412 / 0 / 0 / 0 / 0 | 0 | no/no | 53 | 10.29% |
| entropy_delta | [+11.27, +12.70] | 53 / 417 / 0 / 0 / 0 / 0 | 0 | no/no | 55 | 10.50% |
| uniform | [+12.47, +14.71] | 57 / 33367 / 0 / 0 / 0 / 0 | 0 | no/no | 62 | 11.30% |

Human judgments: * = F4 (second annotation layer), otherwise archived reviewers; (c) correct, (i) incorrect.

## Totals

- Decided: 16/16.
- Rest only on reference-identity and execution-failure labels (T1+T2 suffice): 11/16 (mra, borda, rrf, mean_norm_position, occurrence, mra_then_occurrence, token_similarity, codet5_similarity, naturalness, entropy_delta, uniform).
- Need human judgments: best_config_top1 12, first_global 6, testability 6, one_stage 4, source_agnostic 9; 31 distinct classes in 27 bugs (23 archived, 8 F4).
- Archived load-bearing judgments by label: {'incorrect': 21, 'correct': 2}; by review: {'agreement': 20, 'tiebreak': 3} (agreement = first-round two-reviewer agreement).
- F5 strata of the archived load-bearing judgments: {'accepted-incorrect': 21, 'accepted-correct': 2} (F5 found accepted-correct the most disputed stratum, 13/30, vs accepted-incorrect 3/30). F4 labels: {'incorrect': 5, 'correct': 3}.
- Load-bearing for more than one decision: Cli-35#57 (archived, correct): best_config_top1, testability, source_agnostic; Closure-61#74 (F4, correct): testability, source_agnostic; Csv-14#1 (archived, incorrect): testability, source_agnostic; JacksonDatabind-16#9 (archived, incorrect): best_config_top1, one_stage; Jsoup-34#11 (archived, incorrect): testability, source_agnostic.
- Load-bearing classes that are themselves F5 audit items: 2.
- Need an F3 label: none. Need the no-op rule: none.
- Bases that use R labels (R placed before human in trust): ['best_config_top1', 'first_global', 'one_stage', 'source_agnostic']; decisions that fail without any R label: ['best_config_top1']; decisions that fail without any human label: ['best_config_top1', 'first_global', 'testability', 'one_stage', 'source_agnostic'].
- Flipping all 16 F5-disputed labels changes the lower bounds by: mra +0.012, best_config_top1 +0.205, first_global +0.000, borda +0.000, rrf +0.000, mean_norm_position +0.102, occurrence +0.000, mra_then_occurrence +0.000, testability +0.000, one_stage +0.000, source_agnostic +0.000, token_similarity +0.012, codet5_similarity +0.000, naturalness +0.000, entropy_delta +0.000, uniform +0.028 pp.

