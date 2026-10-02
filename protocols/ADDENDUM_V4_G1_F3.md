# Addendum to Protocol v4: generated tests for G1's open primary comparison

Frozen 2026-10-01, before any G1 generated test exists. The hashes of this file
and of the selection are recorded in `results/v4/protocol_freeze.json`.

## Status

- The pre-registered primary result of G1 is P1 (challenger_frozen vs
  occurrence) under the evidence view **G-E1**, as specified in
  `PROTOCOL_G1_FRESH_CAMPAIGN.md`. It is open at [−3.53, +3.23], and it stays
  the primary result.
- This addendum adds one more evidence-acquisition step, **G-E2**, designed
  after that result was known. It is reported as a secondary, pre-specified
  step, not as confirmation.
- The targets are chosen mechanically, and the generated tests do not depend
  on any label.

## Targets

- **What:** every class relevant to P1 that is unknown under G-E1 and whose
  executed representative has status
  `admissible_triggers_pass_semantics_unknown`.
- **Result:** 25 of the 43 relevant unknown classes, in 17 bugs.
- **Excluded:** the other 18 have unresolved execution statuses (placement or
  repetition 9, setup or controls 5, no admissible trigger 3, test
  disagreement 1). They stay unknown.
- **Built by:** `analysis_tools/v4/select_g1_f3_targets.py`. The selection uses
  only tier P, which finished before this addendum.

## Method

The F3 procedure (`ADDENDUM_V4_F3_DIFFTEST.md`) is used unchanged:

- EvoSuite (two seeds) and Randoop generate tests on the fixed version, in the
  v2/Java 8 image;
- runner: `execution_tools/run_difftest.py` with `difftest_runner.py`;
- a counterexample is a test that passes on the fixed version in both
  repetitions and fails on the candidate in both;
- the same relevance rule applies (exclusions (a)–(d)), and every
  counterexample is read by hand.

The package copies the representatives' cases from
`results/g1/exec_tierP_package_v1`.

## Evidence view and report

- **G-E2 = G-E1 plus every class whose representative has at least one
  witness, labelled incorrect.**
- Report P1 under G-E2, with its bounds, the relevant unknowns left, and a
  break-down count if P1 is decided.
- Report all counterexamples and their verdicts.
