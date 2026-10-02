# Addendum to Protocol v4: G2, a frozen, pre-specified transfer to D4C

Frozen 2026-10-01, before the G2 script reads any D4C outcome. The hash is
recorded in `results/v4/protocol_freeze.json`.

**Status, stated up front.** D4C's aggregate execution outcomes were inspected
in September (`results/d4c_external/combined_v1`, and `ranker_v1`, whose
feature encoding was chosen after that look). This analysis is therefore
**pre-specified on already-inspected data, not confirmatory**. Only G1 is
confirmatory.

What G2 adds: every policy, feature mapping and rule below is taken unchanged
from the Defects4J work, E4 or D1, and none of it is chosen on D4C. It answers
reviewers R2 B4/Q5/S4, R3 E3/T2 and R1 T1.

## Data

- D4C (ICSE'25) GPT patches for 276 Defects4J bugs, 10 samples per bug:
  `external_artifacts/d4c/archive/defects4j/pred_d4c_gpt_full_archived.csv`.
- Imported by `prepare_d4c_external_campaign.py` into
  `results/d4c_external/preparation_v2`: 2,594 unique candidates, each with its
  sample positions (`source_indices`, 0–9).
- Every candidate was executed with fixed and buggy controls, twice
  (`combined_v1/candidate_findings.jsonl`).

## Feature mapping (fixed now)

- D4C is **one source**, named `d4c`. A candidate's positions are its sample
  indices, 0–9; the Defects4J position scale is also 0–9. Duplicate samples are
  extra occurrences of that one source.
- There is no D4C-specific feature.
- **Challenger** (`challenger_frozen`): the three-stage Defects4J challenger,
  refit once on all 488 Defects4J bugs with C chosen by the rotation-0 tuning
  rule, exactly as in E4 (`repairbench_v4.frozen_challenger`). Its
  source-identity columns are zero for `d4c`.
- **Source-agnostic learner** (`source_agnostic_frozen`): the same procedure
  with the D1 `AgnosticFeatures`, fit on all 488 Defects4J bugs.
- **Overlap.** 246 of the 276 bugs also appear in the Defects4J pool, so their
  Defects4J labels are in the training data. This is disclosed. The features
  are provenance-only (position and occurrence), never code or labels, so no
  D4C outcome can leak into them.

## Contract

The contract is Protocol v4 unchanged:

- bug unit (276 bugs);
- javac AST identity (BatchMethodFingerprint, with a text fallback);
- known-wins class labels;
- the N-a no-op rule;
- uniform ties;
- exact shared-label bounds;
- equal-bug weighting;
- top-k with k = 3 and 5.

## Endpoints

1. **Primary: trigger passage.**
   - admissible triggers pass counts as 1;
   - a controlled trigger failure counts as 0;
   - "compile command failed twice" counts as 0, because a patch that does not
     compile cannot pass;
   - every other status is unknown.
2. **Secondary: semantic correctness, negatives only.**
   - Witnesses and compile failures count as 0.
   - Everything else is unknown, because D4C releases no per-candidate
     correctness label. The lower bound is therefore 0 by construction, and
     only upper bounds are informative.
   - `correct_id.txt` (bug-level only) is not used.

## Pre-registered comparisons

- `challenger_frozen` vs `mra` (the sample order);
- `challenger_frozen` vs `occurrence`;
- `challenger_frozen` vs `uniform`;
- `source_agnostic_frozen` vs `mra`.

**Expected limitation, stated before running.** D4C samples at temperature 1.0,
so sample order carries no rank information, and most candidates occur only
once. The comparisons may therefore collapse or stay open. Whatever the result,
it is reported.
