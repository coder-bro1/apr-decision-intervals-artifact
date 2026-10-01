# Addendum to Protocol v4: prospective test of the pre-flight check (P1)

Frozen 2026-10-02, before any execution of this campaign. The predictions below were computed and published
(pushed to a public repository) before the first container started.

## Why

The target-aware pre-flight check and its pilot-yield planner were designed after the earlier campaigns and evaluated
retrospectively. P1 tests them prospectively: predictions for every open comparison are fixed first, then the campaign
runs, then predictions are compared with outcomes.

## Start state and comparisons

- Evidence: the final Defects4J evidence (E1+F2+F3+F4+R, all labels as in the paper).
- Comparisons: the 21 comparisons at the second decision point (plausible-only eligibility, `analysis_tools/v4/d2.py`).
  With the final evidence, 13 are decided and 8 are open.

## Selection (no outcome read)

- Targets: every helpful class of an open comparison with A0 != 0 that the earlier generated-test campaign (F3 tier 1)
  did not test; one representative per class (lowest candidate id among archived test-passing members).
- Built by `analysis_tools/v4/select_p1_prospective.py`: 99 classes, 99 candidates, 70 bugs.
- results/v4/p1_prospective/candidates.json SHA-256: a82e7da12bc38cc2a22de7ec57cddb39097aebfbc7066bda02862f4d8df35924

## Predictions (frozen)

- Planner: each targeted helpful class is refuted independently with probability 0.142 (F3's realised yield per
  targeted class); 20,000 draws, seed 20261002. Prediction "decided" if P(decide) >= 0.5, else "open".
- results/v4/p1_prospective/predictions.json SHA-256: 90508e712d9fb7fd8e7fccd31ecd803171cd49a43b223c373749083b545e271d
- Summary: selector vs PrevaRank decided (P = 0.9986); selector vs correctness stage cannot be decided (A0 = 0); the
  other six open (P between 0 and 0.098).

## Execution

Unchanged F3 protocol (`ADDENDUM_V4_F3_DIFFTEST.md`): EvoSuite (two suites, 180 s each) and Randoop (180 s) on the
fixed version, in the Defects4J 2.0 / Java 8 image
sha256:335001efa26b313093968f26dee062e31ae69a8b24f0e9ecb124ae97b73b9323; tests failing on the fix removed; a
counterexample must pass on the fix and fail on the candidate in both of two runs. `execution_tools/run_difftest.py`.

## Screening and analysis (fixed now)

- Counterexamples are screened against the four pre-specified exclusions of the F3 relevance rule, with the same review
  view (`f3_review_view.py`) and recording (`f3_record_verdicts.py`). Screening is done by the same AI assistant as
  for F3 and is disclosed in the AI-use statement.
- A reference-behaviour witness sets its whole class incorrect (F3 class rule). The 21 comparisons are recomputed from
  the start state plus the P1 witnesses.
- Reported: realised decided/open for each of the eight open comparisons against its prediction; the Brier score of
  P(decide); the realised yield. All eight are reported whatever the outcome.
