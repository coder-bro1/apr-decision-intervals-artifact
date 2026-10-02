# Protocol v4 Addendum F1: Source-Environment Concordance (Defects4J v2 / Java 8)

Frozen 2026-09-29, before any v2 execution. Parent: `PROTOCOL_V4_BUG_LEVEL.md`.

**Why.** Reviewers R1 (M4, Q2), R2 (A4, Q4) and R3 (E6, Q3, S5) note that the
185 rejection witnesses came from Defects4J v3.0.1 / Java 11, while the source
campaign used Defects4J v2.

## What runs

- **Candidates.** Every candidate of the v1 census package
  (`results/conflict_census/execution_v1`):
  - the 280 census candidates;
  - the 75 compatibility controls.
  
  Same case files, same anchors, same patches.
- **Harness.** The **unchanged** runner and evidence code: `census_runner.py`,
  `census_evidence.py`, `official_defects4j_runner.py`, `run_census.py`.
  Only the image changes. Jobs are grouped by bug, and every job is marked
  phase `full`, so run_census applies no smoke or control gate.
- **Environment.** Image `research-defects4j-v2-jdk8:d4c-v1`, id
  `sha256:335001efa26b313093968f26dee062e31ae69a8b24f0e9ecb124ae97b73b9323`:
  Defects4J v2.0.0 commit `01f13c69425fb8a0db290d12b1d48da1641bf6a9`, Java 8.
  One worker, the same resource limits as v1, and native triggers and
  exclusion lists of v2.

## What is reported (fixed now)

1. **A per-candidate concordance table,** v3 status × v2 status, for the
   185 witnesses, the 67 trigger-passers, the 10 compile-command failures,
   and the others.
2. **Witness reproduction rate:** the share of the 185 v3 witnesses that are
   also `controlled_trigger_failure` in v2, with an exact binomial interval.
3. **Headline bounds under E1-both.** A witness counts only if it reproduces
   in both environments; non-reproducing witnesses revert to unknown. This
   is shown next to E1 for every headline comparison.
4. **v2-only new witnesses** (v3 trigger-passers that fail in v2) are
   reported and used only in a clearly labelled sensitivity **E1-union**.
   They are never silently added to the primary evidence.
5. **False rejections among the 63 correct-labelled controls in v2,** with a
   rule-of-three bound. The 15 incorrect-labelled test-passing controls are
   reported separately and are never counted as false-rejection evidence.
6. **Compile-command failures that reproduce in both environments.** This is
   the input to the R1 M4 asymmetry sensitivity (B3 iii).

## Not done

- **No relabelling of archived labels.** Environment disagreements are
  diagnoses, not evidence.
- **Nothing in v1 census outputs is modified.**
