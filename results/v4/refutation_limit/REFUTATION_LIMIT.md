# Refutation limit: what one-sided evidence can decide

Post hoc, read-only analysis of evidence already collected (novelty panel C1). Script: `analysis_tools/v4/refutation_limit.py`; brute-force test: `analysis_tools/v4/test_refutation_limit.py`. Numbers are percentage points (challenger minus baseline for Defects4J), equal-bug weights, AST identity, known-wins, N-a.

## The proposition (an operational pre-flight check, not a new theorem)

Every comparison has a lower bound L and an upper bound H, taken over all ways the unknown patch labels could turn out. Two completions matter here. A0 is the value when every unknown class is incorrect. A1 is the value when every unknown class is correct. Both are taken after the N-a no-op rule.

**Claim.** Evidence that can only mark unknown patches incorrect (re-execution, the census, F2, generated tests, G1 execution) never changes A0. Each step moves [L, H] towards A0. So such evidence can decide a comparison only in the direction of sign(A0). It can never decide one with A0 = 0. Confirm-only evidence does the same thing with A1.

**Why.** A0 is computed only from classes whose label is known: it is the sum of d times y over those classes. Refuting an unknown class changes its label from unknown to 0, and it contributed 0 to A0 before as well, so A0 stays the same. If that class has d < 0, L goes up by |d|. If it has d > 0, H goes down by d. So L <= A0 <= H holds at every state, and refuting every refutable class gives the limit. Each refutation moves the bound by its own |d|, and the moves simply add up. So taking the largest |d| first gives the exact minimum number of refutations. This is the same argument as `breakdown.minimal_count`.

**Two conditions.** First, the refutation must not hit a class that is already known correct. Under known-wins, such a hit would make the class unknown and lower A0 (for a no-op class, the N-a rule would even turn it into 0). The script counts these cases in the hazard column below. Second, some classes are *conflict-locked*: their identical members carry both a 0 and a 1 in the archive. Adding more 0s to single candidates (census, F2, G1 execution) cannot resolve such a class. The candidate-level limit is therefore [A0 + sum over locked classes of min(0, d), A0 + sum over locked classes of max(0, d)]. Only a class-level rule can resolve a locked class: the frozen F3 rule and F4 may overwrite one, and R removes archived 0s. The *execution ceiling* also locks the classes whose members all passed their tests in the archive. Re-running the same tests cannot refute them; only new tests can.

**Positioning.** This is the closed-world, worst-case completion. A0 is the base score of rank-biased precision, where unjudged items count as non-relevant, and A1 is base plus residual (Moffat & Zobel, TOIS 2008). A0 and A1 are also Manski's worst-case and best-case completions (2003). Carterette, Allan & Sitaraman's minimal test collections (SIGIR 2006) pick the judgments that decide a pairwise difference, but with two-sided judgments. What we add is an operational use. We tag each evidence source by polarity (refute, confirm, retract), apply the label-conflict rule, and compute before any container time is spent which open comparisons a planned campaign can decide at all, and with how many refutations at least. Everything here is post hoc: the check was not run before the campaigns.

## Defects4J: A0 at every evidence step (16 comparisons)

Layers: **E0** = archived labels (start); **E1** = refute-only, candidate-level (census re-execution); **F2** = refute-only, candidate-level (F2 re-execution); **F3** = refute-only, class-level (generated tests; may overwrite conflict classes); **F4** = two-sided, class-level (human review verdicts); **R** = retraction + confirmation (re-run archived failures; C1-fix).

| Baseline | A0 E0 | A0 E1 | A0 F2 | A0 F3 | A0 F4 | A0 R | A0 constant E0..F3 | [L, H] at E0 | [L, H] at R |
|---|---|---|---|---|---|---|---|---|---|
| mra | +7.59 | +7.59 | +7.59 | +7.59 | +8.16 | +10.15 | yes | [+2.84, +11.51]* | [+9.27, +10.33]* |
| best_config_top1 | +0.00 | +0.00 | +0.00 | +0.00 | -0.20 | +1.43 | yes | [-1.23, +2.25] | [+1.23, +1.64]* |
| first_global | +3.69 | +3.69 | +3.69 | +3.69 | +3.89 | +6.15 | yes | [+1.23, +7.58]* | [+5.94, +6.35]* |
| borda | +8.20 | +8.20 | +8.20 | +8.20 | +9.22 | +9.22 | yes | [+4.51, +10.45]* | [+7.99, +9.22]* |
| rrf | +8.20 | +8.20 | +8.20 | +8.20 | +9.22 | +9.22 | yes | [+4.71, +10.45]* | [+7.79, +9.22]* |
| mean_norm_position | +9.88 | +9.88 | +9.88 | +9.88 | +10.61 | +13.22 | yes | [+8.65, +14.26]* | [+13.00, +13.43]* |
| occurrence | +8.40 | +8.40 | +8.40 | +8.40 | +9.43 | +9.43 | yes | [+5.03, +10.66]* | [+8.09, +9.43]* |
| mra_then_occurrence | +8.30 | +8.30 | +8.30 | +8.30 | +9.32 | +9.12 | yes | [+4.41, +10.35]* | [+7.41, +9.12]* |
| testability | +1.02 | +1.02 | +1.02 | +1.02 | +1.43 | +0.61 | yes | [+0.00, +1.43] | [+0.41, +0.61]* |
| one_stage | +1.84 | +1.84 | +1.84 | +1.84 | +1.23 | +0.61 | yes | [+0.00, +2.25] | [+0.41, +0.82]* |
| source_agnostic | +3.11 | +3.11 | +3.11 | +3.11 | +3.55 | +3.07 | yes | [-1.57, +4.34] | [+1.84, +3.28]* |
| token_similarity | +9.68 | +9.68 | +9.68 | +9.68 | +10.59 | +13.07 | yes | [+7.13, +14.04]* | [+11.41, +13.27]* |
| codet5_similarity | +9.31 | +9.31 | +9.31 | +9.31 | +10.34 | +13.00 | yes | [+8.10, +13.81]* | [+12.26, +13.21]* |
| naturalness | +9.43 | +9.43 | +9.43 | +9.43 | +10.45 | +12.70 | yes | [+6.97, +13.73]* | [+10.86, +12.91]* |
| entropy_delta | +9.63 | +9.63 | +9.63 | +9.63 | +10.45 | +12.50 | yes | [+6.35, +13.93]* | [+11.27, +12.70]* |
| uniform | +10.98 | +10.98 | +10.98 | +10.98 | +11.94 | +14.50 | yes | [+8.15, +15.42]* | [+12.47, +14.71]* |

A0 is constant from E0 to F3 for 16/16 comparisons. Steps at which A0 moved (number of comparisons): {'F4': 16, 'R': 13}. * = decided.

### Class-level transitions per layer (all AST classes in the pool, raw known-wins labels)

| Step | Polarity | Transitions | Known-correct classes lost (hazard) |
|---|---|---|---|
| E1 | refute-only, candidate-level (census re-execution) | unknown -> 0: 122 | 0 |
| F2 | refute-only, candidate-level (F2 re-execution) | unknown -> 0: 109 | 0 |
| F3 | refute-only, class-level (generated tests; may overwrite conflict classes) | unknown -> 0: 23 | 0 |
| F4 | two-sided, class-level (human review verdicts) | conflict -> 0: 1, conflict -> 1: 1, unknown -> 0: 20, unknown -> 1: 18 | 0 |
| R | retraction + confirmation (re-run archived failures; C1-fix) | 0 -> 1: 5, conflict -> 1: 30 | 0 |

Overwrites of conflict classes recorded by final_evidence: {'F4': 2}. F3 overwrote 0 conflict classes, so the strict and permissive readings of F3 coincide in what F3 actually did.

Where each comparison's A0 change at F4 and R came from, by class transition (pp, number of classes in brackets; 'conflict' = the class was conflict-locked at the previous step):

| Baseline | F4 | R |
|---|---|---|
| mra | conflict -> 1: -0.021 (1); unknown -> 1: +0.587 (18) | 0 -> 1: -0.039 (2); conflict -> 1: +2.036 (24) |
| best_config_top1 | unknown -> 1: -0.205 (5) | conflict -> 1: +1.639 (8) |
| first_global | unknown -> 1: +0.205 (9) | conflict -> 1: +2.254 (11) |
| borda | unknown -> 1: +1.025 (5) | 0 |
| rrf | unknown -> 1: +1.025 (5) | 0 |
| mean_norm_position | unknown -> 1: +0.734 (6) | 0 -> 1: -0.051 (1); conflict -> 1: +2.664 (13) |
| occurrence | unknown -> 1: +1.025 (5) | 0 |
| mra_then_occurrence | unknown -> 1: +1.025 (5) | conflict -> 1: -0.205 (7) |
| testability | unknown -> 1: +0.410 (2) | conflict -> 1: -0.820 (4) |
| one_stage | conflict -> 1: -0.205 (1); unknown -> 1: -0.410 (2) | conflict -> 1: -0.615 (5) |
| source_agnostic | conflict -> 1: -0.102 (1); unknown -> 1: +0.546 (4) | 0 -> 1: -0.205 (1); conflict -> 1: -0.273 (6) |
| token_similarity | unknown -> 1: +0.915 (9) | conflict -> 1: +2.475 (16) |
| codet5_similarity | unknown -> 1: +1.025 (5) | conflict -> 1: +2.664 (13) |
| naturalness | unknown -> 1: +1.025 (5) | conflict -> 1: +2.254 (13) |
| entropy_delta | unknown -> 1: +0.820 (6) | 0 -> 1: -0.205 (1); conflict -> 1: +2.254 (13) |
| uniform | conflict -> 1: -0.003 (1); unknown -> 1: +0.970 (18) | 0 -> 1: -0.015 (5); conflict -> 1: +2.576 (30) |

## Defects4J: refute-only and confirm-only limits

k = minimum refutations (or confirmations) / helpful classes available. 'strict' = candidate-level (conflict-locked); 'permissive' = class-level; 'exec ceiling' = candidate-level and only classes with a member not archived as test-passing; 'exec obs.' also locks classes whose triggers passed when the census/F2 re-ran them.

### Open at E0 (4)

| Baseline | [L, H] | A0 | A1 | locked conflict classes | strict limit | refute strict | refute permissive | exec ceiling | exec obs. | confirm strict |
|---|---|---|---|---|---|---|---|---|---|---|
| best_config_top1 | [-1.23, +2.25] | +0.00 | +1.02 | 9 | [+0.00, +1.84] | no (A0=0) | no (A0=0) | no (A0=0) | no (A0=0) | no (locked) |
| testability | [+0.00, +1.43] | +1.02 | +0.41 | 5 | [+0.00, +1.02] | no (locked) | yes (+), k=1/5 | no (locked) | no (locked) | yes (+), k=1/2 |
| one_stage | [+0.00, +2.25] | +1.84 | +0.41 | 8 | [+0.61, +2.25] | yes (+), k=1/3 | yes (+), k=1/9 | no (locked) | no (locked) | no (locked) |
| source_agnostic | [-1.57, +4.34] | +3.11 | -0.34 | 9 | [+2.12, +3.72] | yes (+), k=8/22 | yes (+), k=8/28 | yes (+), k=8/19 | yes (+), k=8/19 | no (locked) |

### Open at E1 (3)

| Baseline | [L, H] | A0 | A1 | locked conflict classes | strict limit | refute strict | refute permissive | exec ceiling | exec obs. | confirm strict |
|---|---|---|---|---|---|---|---|---|---|---|
| best_config_top1 | [-1.23, +2.25] | +0.00 | +1.02 | 9 | [+0.00, +1.84] | no (A0=0) | no (A0=0) | no (A0=0) | no (A0=0) | no (locked) |
| testability | [+0.00, +1.43] | +1.02 | +0.41 | 5 | [+0.00, +1.02] | no (locked) | yes (+), k=1/5 | no (locked) | no (locked) | yes (+), k=1/2 |
| one_stage | [+0.00, +2.25] | +1.84 | +0.41 | 8 | [+0.61, +2.25] | yes (+), k=1/3 | yes (+), k=1/9 | no (locked) | no (locked) | no (locked) |

### Open at F2 (3)

| Baseline | [L, H] | A0 | A1 | locked conflict classes | strict limit | refute strict | refute permissive | exec ceiling | exec obs. | confirm strict |
|---|---|---|---|---|---|---|---|---|---|---|
| best_config_top1 | [-1.23, +2.25] | +0.00 | +1.02 | 9 | [+0.00, +1.84] | no (A0=0) | no (A0=0) | no (A0=0) | no (A0=0) | no (locked) |
| testability | [+0.00, +1.43] | +1.02 | +0.41 | 5 | [+0.00, +1.02] | no (locked) | yes (+), k=1/5 | no (locked) | no (locked) | yes (+), k=1/2 |
| one_stage | [+0.00, +2.25] | +1.84 | +0.41 | 8 | [+0.61, +2.25] | yes (+), k=1/3 | yes (+), k=1/9 | no (locked) | no (locked) | no (locked) |

### Open at F3 (2)

| Baseline | [L, H] | A0 | A1 | locked conflict classes | strict limit | refute strict | refute permissive | exec ceiling | exec obs. | confirm strict |
|---|---|---|---|---|---|---|---|---|---|---|
| best_config_top1 | [-1.23, +2.25] | +0.00 | +1.02 | 9 | [+0.00, +1.84] | no (A0=0) | no (A0=0) | no (A0=0) | no (A0=0) | no (locked) |
| testability | [+0.00, +1.43] | +1.02 | +0.41 | 5 | [+0.00, +1.02] | no (locked) | yes (+), k=1/5 | no (locked) | no (locked) | yes (+), k=1/2 |

### Open at F4 (1)

| Baseline | [L, H] | A0 | A1 | locked conflict classes | strict limit | refute strict | refute permissive | exec ceiling | exec obs. | confirm strict |
|---|---|---|---|---|---|---|---|---|---|---|
| best_config_top1 | [-0.41, +1.64] | -0.20 | +1.43 | 9 | [-0.20, +1.64] | no (locked) | yes (-), k=9/9 | no (locked) | no (locked) | no (locked) |

## G1 fresh campaign


| Comparison | View | [L, H] | A0 | A1 | refute limit (strict) | refute: reachable? k | share of helpful mass needed | exec ceiling | confirm: k |
|---|---|---|---|---|---|---|---|---|---|
| challenger_frozen vs occurrence | G-E0 | [-17.41, +25.27] | +0.0512 | +7.81 | [+0.0512, +0.0512] | yes (+), k=157/159 | 99.7% | yes (+), k=157/159 | yes (+), k=85/140 |
| challenger_frozen vs occurrence | G-E1 | [-3.53, +3.23] | +0.0512 | -0.36 | [+0.0512, +0.0512] | yes (+), k=26/26 | 98.6% | no (locked) | yes (-), k=21/26 |
| occurrence vs uniform | G-E0 | [-52.28, +28.78] | +0.0297 | -23.53 | [+0.0297, +0.0297] | yes (+), k=1218/1219 | 99.9% | yes (+), k=1218/1219 | yes (-), k=450/1219 |
| occurrence vs uniform | G-E1 | [-6.70, +4.69] | +0.0297 | -2.04 | [+0.0297, +0.0297] | yes (+), k=166/167 | 99.6% | no (locked) | yes (-), k=89/167 |
| challenger_frozen vs uniform | G-E0 | [-53.43, +37.79] | +0.0809 | -15.72 | [+0.0809, +0.0809] | yes (+), k=1275/1278 | 99.8% | yes (+), k=1275/1278 | yes (-), k=697/1278 |
| challenger_frozen vs uniform | G-E1 | [-7.19, +4.86] | +0.0809 | -2.40 | [+0.0809, +0.0809] | yes (+), k=176/179 | 98.9% | no (locked) | yes (-), k=89/179 |
| codet5_similarity vs uniform | G-E0 | [-53.31, +25.50] | +0.6957 | -28.51 | [+0.6957, +0.6957] | yes (+), k=1259/1292 | 98.7% | yes (+), k=1259/1292 | yes (-), k=378/1292 |
| codet5_similarity vs uniform | G-E1 | [-6.69, +3.80] | +0.6957 | -3.58 | [+0.6957, +0.6957] | yes (+), k=154/183 | 90.6% | no (locked) | yes (-), k=61/183 |
| naturalness vs uniform | G-E0 | [-46.76, +51.41] | +0.0809 | +4.57 | [+0.0809, +0.0809] | yes (+), k=1176/1179 | 99.8% | yes (+), k=1176/1179 | yes (+), k=295/339 |
| naturalness vs uniform | G-E1 | [-5.90, +7.88] | +0.0809 | +1.90 | [+0.0809, +0.0809] | yes (+), k=155/158 | 98.6% | no (locked) | yes (+), k=36/51 |

P1 negative unknown mass by execution status at G-E1: admissible_triggers_pass_semantics_unknown: 18 classes, 2.36 pp, unresolved_no_admissible_trigger: 1 classes, 0.20 pp, unresolved_placement_or_repetition: 4 classes, 0.61 pp, unresolved_setup_or_controls: 3 classes, 0.41 pp.


## HumanEval-Java (E3)

candidate-level labels (no identity classes, no known-wins lock; the rules leave fix-equivalent but failing candidates unknown, and X1 refutes regardless of the archived-unknown reason).

| Baseline | View | [L, H] | A0 | A1 | refute: reachable? k | exec ceiling | confirm: reachable? k |
|---|---|---|---|---|---|---|---|
| uniform_random | archived | [-3.76, +41.20] | +10.37 | +27.07 | yes (+), k=497/2179 | yes (+), k=581/590 | yes (+), k=7/51 |
| uniform_random | X1 | [-2.09, +39.98] | +10.37 | +27.52 | yes (+), k=265/1917 | yes (+), k=319/328 | yes (+), k=4/49 |
| uniform_random | X2 | [+13.94, +39.97] | +26.84 | +27.07 | decided | decided | decided |
| uniform_random | HE-E1 | [+21.11, +37.82] | +31.41 | +27.52 | decided | decided | decided |
| uniform_random | X4-posthoc | [+15.61, +38.75] | +26.84 | +27.52 | decided | decided | decided |
| token_similarity | archived | [+7.88, +49.43] | +18.53 | +38.78 | decided | decided | decided |
| token_similarity | X1 | [+12.82, +48.20] | +18.53 | +42.49 | decided | decided | decided |
| token_similarity | X2 | [+25.56, +48.07] | +34.85 | +38.78 | decided | decided | decided |
| token_similarity | HE-E1 | [+36.01, +46.10] | +39.62 | +42.49 | decided | decided | decided |
| token_similarity | X4-posthoc | [+30.50, +46.84] | +34.85 | +42.49 | decided | decided | decided |
| occurrence_count | archived | [-38.26, +38.91] | +18.86 | -18.21 | yes (+), k=62/172 | yes (+), k=62/148 | yes (-), k=64/172 |
| occurrence_count | X1 | [-20.13, +38.29] | +18.86 | -0.71 | yes (+), k=33/110 | yes (+), k=33/86 | yes (-), k=86/110 |
| occurrence_count | X2 | [-29.87, +16.94] | +5.28 | -18.21 | yes (+), k=57/121 | yes (+), k=62/97 | yes (-), k=28/121 |
| occurrence_count | HE-E1 | [-7.12, +3.13] | -3.28 | -0.71 | yes (-), k=6/11 | no (locked) | yes (-), k=7/29 |
| occurrence_count | X4-posthoc | [-11.75, +16.32] | +5.28 | -0.71 | yes (+), k=20/59 | yes (+), k=21/35 | yes (-), k=37/59 |
| native_position | archived | [-16.18, +29.22] | +0.81 | +12.24 | yes (+), k=269/286 | no (locked) | yes (+), k=29/51 |
| native_position | X1 | [-11.69, +28.05] | +0.81 | +15.55 | yes (+), k=195/211 | no (locked) | yes (+), k=21/49 |
| native_position | X2 | [+0.18, +24.55] | +12.50 | +12.24 | decided | decided | decided |
| native_position | HE-E1 | [+9.72, +21.23] | +15.41 | +15.55 | decided | decided | decided |
| native_position | X4-posthoc | [+4.67, +23.37] | +12.50 | +15.55 | decided | decided | decided |
| native_then_occurrence | archived | [-33.48, +31.06] | +13.06 | -15.47 | yes (+), k=55/110 | yes (+), k=55/99 | yes (-), k=51/110 |
| native_then_occurrence | X1 | [-18.02, +29.83] | +13.06 | -1.25 | yes (+), k=30/69 | yes (+), k=30/58 | yes (-), k=60/69 |
| native_then_occurrence | X2 | [-25.87, +13.40] | +3.01 | -15.47 | yes (+), k=54/75 | yes (+), k=60/64 | yes (-), k=22/75 |
| native_then_occurrence | HE-E1 | [-7.21, +1.35] | -4.61 | -1.25 | yes (-), k=3/11 | no (locked) | yes (-), k=4/11 |
| native_then_occurrence | X4-posthoc | [-10.40, +12.16] | +3.01 | -1.25 | yes (+), k=18/34 | yes (+), k=20/23 | yes (-), k=26/34 |
| testability_product | archived | [-4.94, +3.09] | -0.62 | -1.23 | yes (-), k=6/6 | no (locked) | yes (-), k=6/7 |
| testability_product | X1 | [-4.32, +2.47] | -0.62 | -1.23 | yes (-), k=5/5 | no (locked) | yes (-), k=5/6 |
| testability_product | X2 | [-3.09, -0.62] | -2.47 | -1.23 | decided | decided | decided |
| testability_product | HE-E1 | [-1.85, -1.23] | -1.85 | -1.23 | decided | decided | decided |
| testability_product | X4-posthoc | [-2.47, -1.23] | -2.47 | -1.23 | decided | decided | decided |

A0 unchanged archived -> X1 (refute-only) for every baseline: True. A1 unchanged archived -> X2 (confirm-only): True.

## RepairBench (from repairbench_v4.json; conflict classes not recomputed)

| Pair | bounds | A0 | A1 | decided | decision sign = sign(A0) |
|---|---|---|---|---|---|
| mra vs uniform | [-10.46, +10.90] | +0.36 | +0.08 | False | None |
| occurrence vs mra | [-3.81, +17.32] | +8.46 | +5.05 | False | None |
| occurrence vs uniform | [-4.28, +18.24] | +8.82 | +5.14 | False | None |
| codet5_similarity vs mra | [-12.08, +6.67] | -0.31 | -5.10 | False | None |
| codet5_similarity vs uniform | [-12.15, +7.18] | +0.04 | -5.01 | False | None |
| challenger_frozen vs mra | [-9.15, +11.99] | +2.85 | -0.00 | False | None |
| challenger_frozen vs uniform | [-9.75, +13.03] | +3.20 | +0.08 | False | None |
| challenger_frozen vs occurrence | [-8.43, -2.25] | -5.62 | -5.06 | True | True |
| challenger_frozen vs codet5_similarity | [-5.02, +13.27] | +3.16 | +5.09 | False | None |

## Pre-flight table: could each refute-only campaign decide what was open at its start?

Formal reach from the start state, under the campaign's semantics. 'k' = minimum refutations / helpful classes. 'Capable hours' = container-hours of jobs that touch at least one class able to move a comparison that the campaign could decide. This is relative to the decision objective only: the campaigns also tightened comparisons that were already decided, so the rest is not waste.

'Bug-level join' counts every job in a bug that holds such a class, even if the job targeted other classes.

| Campaign | Semantics | Open at start: reach (k) | Newly decided | Jobs | Hours | Capable jobs / hours (class join) | Bug-level join |
|---|---|---|---|---|---|---|---|
| census (E0 -> E1) | execution (archived test-pass) | best_config_top1: no, A0=0; testability: no, locked; one_stage: no, locked; source_agnostic: yes + k=8/19 | source_agnostic | - | 16.00 | not joined | not joined |
| F2 (E1 -> F2) | execution (archived test-pass) | best_config_top1: no, A0=0; testability: no, locked; one_stage: no, locked | none | 137 | 5.70 | 0 / 0.00 h | 0 / 0.00 h |
| F3 strict (F2 -> F3) | candidate (conflict classes locked) | best_config_top1: no, A0=0; testability: no, locked; one_stage: yes + k=1/3 | one_stage | 76 | 13.01 | 3 / 0.50 h | 3 / 0.50 h |
| F3 permissive (F2 -> F3) | class (frozen F3 rule may overwrite conflict classes) | best_config_top1: no, A0=0; testability: yes + k=1/5; one_stage: yes + k=1/9 | one_stage | 76 | 13.01 | 4 / 0.63 h | 8 / 1.33 h |
| R (F4 -> R) | retraction + confirmation (not refute-only) | n/a (not refute-only) | best_config_top1 | 38 | 0.80 | n/a | n/a |
| G1 tier P execution (G-E0 -> G-E1), P1 | candidate (no test-pass information before execution) | challenger_frozen vs occurrence: yes + k=157/159 | none | 157 | 4.63 | 104 / 2.16 h | 104 / 2.16 h |
| G1 tier S execution (G-E0 -> G-E1), secondaries | candidate (no test-pass information before execution) | occurrence vs uniform: yes + k=1218/1219; challenger_frozen vs uniform: yes + k=1275/1278; codet5_similarity vs uniform: yes + k=1259/1292; naturalness vs uniform: yes + k=1176/1179 | none | 388 | 15.40 | 387 / 15.37 h | 387 / 15.37 h |

HumanEval-Java, comparisons open at the archived labels (E3 tier A/B hours are not in the cost ledger used here):

| Baseline | A0 | refute-only (k) | exec ceiling (k) | decided by X1 (refute-only part of E3) | decided by X2 (confirm-only part) | decided by HE-E1 |
|---|---|---|---|---|---|---|
| uniform_random | +10.37 | yes (+), k=497/2179 | yes (+), k=581/590 | open | identified + | identified + |
| occurrence_count | +18.86 | yes (+), k=62/172 | yes (+), k=62/148 | open | open | open |
| native_position | +0.81 | yes (+), k=269/286 | no (locked) | open | identified + | identified + |
| native_then_occurrence | +13.06 | yes (+), k=55/110 | yes (+), k=55/99 | open | open | open |
| testability_product | -0.62 | yes (-), k=6/6 | no (locked) | open | identified - | identified - |

## Choices and caveats

- Archived test-pass (execution ceiling, Defects4J): a candidate counts as test-passing when every archived record of it compiled and passed its tests (`run_evidence_pilot_step2.load_inputs`, compile = 1 and test_given_compile = 1). A class is refutable by re-execution if at least one member is not test-passing in that sense; that includes members with no or conflicting archived outcomes. 'exec obs.' also treats candidates whose triggers passed in the census or F2 as unrefutable by re-execution.
- G1: before execution there is no test-pass information (G-E0 execution ceiling = strict limit). From G-E1 on, a class is unrefutable by re-execution when its executed representative passed its triggers (admissible_triggers_pass_semantics_unknown). HumanEval: a candidate is test-passing when all its legacy records compiled and passed and none is flagged as a compile/test conflict.
- F3 semantics: the frozen F3 rule sets whole classes and may overwrite conflict classes, so the 'permissive' (class) reading is what F3 actually did. The 'strict' reading respects accepted-correct labels. R is tagged retraction + confirmation, not as refute-only or plain positive evidence.
- Hours: F2, F3, R and G1 from terminal.json 'seconds' joined to package jobs.json; census 16.0 h from the cost ledger (not joined per job). Capable hours count whole bug jobs.
- Several 'predictions' are guaranteed by the arithmetic. The check flags futility in advance; it is not a forecast with a hit rate. Everything is post hoc and computed by Claude; not yet checked by a human.
