# Addendum to Protocol v4: E2 PrevaRank input-order permutations

Frozen 2026-09-29, before any permutation run.
Parent protocol: `PROTOCOL_V4_BUG_LEVEL.md`, Section 9 ("E2: PrevaRank
permutations (50)").

## Question

Does the order in which patches are supplied to PrevaRank change its measured
usefulness, not just its ranking? This answers R1 E5 and PC C4.

## Tie-breaking documentation (part a)

Neither the artifact README nor the Figshare release documents a tie-breaking
rule. The JAR ships without sources. Disassembling it with `javap` shows:

- The ranking step `BugTypeAndRankingService.rankPatchesAccordingToValues`
  uses a stable sort by historical value, so ties keep input order.
- `RankPatches.handleTiesBasedOnComplexity` first sorts ties by GumTree AST
  size. It then re-sorts everything by (value, previous rank). Since the
  previous rank is the input-order rank, this appears to undo the AST-size
  order.
- `refineRanking` then promotes the first patch of each category.

These readings are hypotheses. They are tested empirically below (check T),
not assumed.

## Runs (part b)

- **50 permutations**, k = 1..50. Each uses
  `prepare_prevarank_llm_v2.py --pool-types mixed --input-order stable_hash
  --input-order-seed e2-perm-<k>` with the frozen runtime-probe report, giving
  465 mixed pools and 4,180 candidates.
- Each permutation then goes through `run_prevarank_llm_v2.py`,
  `verify_prevarank_llm_run_v2.py` and `evaluate_prevarank_llm_v2.py`,
  unchanged. The ordering depends only on hashes of identifiers, never on
  labels.
- The driver is `analysis_tools/v4/run_e2_prevarank.py`. It is resumable, and
  each run gets its own directory, `results/v4/prevarank/perm_<k>`.
- Docker images are pinned by digest:
  - `eclipse-temurin@sha256:92a2a4d7…`
  - `mysql@sha256:f61944ff…`
- The canonical_v4 (native order) and stable_hash_v1 runs are kept as
  same-input references.

## Analysis

The analysis script is `analysis_tools/v4/e2_analysis.py`.

- **Labels.** The v4 evidence views E0 and E1 are joined through each
  candidate's legacy ids. A pool's top patch counts as correct, incorrect or
  unknown under the known-wins rule.
- **Per permutation:**
  - success@1 as a shared-label interval [lower, upper] over the pools with at
    least one known-correct or unknown candidate;
  - the rank of the first known-correct patch;
  - both with equal-bug weighting.
- **Distribution across permutations.** Report the minimum, median and
  maximum of each endpoint, and the share of permutations whose interval lies
  entirely above or below the canonical run's interval.
- **Paired difference.** For each permutation against canonical, bound the
  success@1 difference with shared labels. Report how many of the 50 are
  identified and in which direction.
- **Check T (tie-breaking).** Within groups of patches with equal historical
  value and equal category, compute the share of output orders that equal the
  input order. A share of 1.0 in every run confirms that input order breaks
  ties.

## Framing (part c)

The supplied order is a hidden experimental treatment. Evaluations of tools
like this must fix the order and report it. All results are reported,
whatever they show.
