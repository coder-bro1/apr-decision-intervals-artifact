# Addendum to Protocol v4: C1 equivalence constraints on Defects4J

Frozen 2026-10-01, before the analysis below is run on Defects4J. The hash is
recorded in `results/v4/protocol_freeze.json`.

**Why.** R1 M2 notes that exact identity turns rename-only variants into
independent unknowns. This splits both the unknown mass and the occurrence
"votes". REVISION_PLAN C1 lists this as the "equivalence constraints" family.
The specification grid (B1/B4) already ran a rename-aware identity, but only for
challenger vs MRA, only on E0/E1, and without equivalence to the developer fix.

**Equivalence relation.** Two methods are equivalent if either of these holds:

- **(a) Same javac AST fingerprint.** This is the contract identity,
  `BatchMethodFingerprint`.
- **(b) Same normalised javac AST.** `BatchMethodNormalize` output
  `h_noann_alpha`: annotations removed, and parameters and local variables
  renamed `v0, v1, …` in declaration order.

The relation is closed transitively (union-find) within a bug. It is therefore
never finer than the AST identity.

**Rename-aware identity (C1-id).** Candidates of a bug that are equivalent form
one class. Classes follow the known-wins rule. Merged members whose known labels
contradict leave the class unknown. The number of such new contradictions is
reported.

**Fix equivalence (C1-fix).** A candidate equivalent to the developer fix of its
context (the `human_fix` of the curated v2 record) under (a) or (b) makes its
C1-id class correct. This applies only when that class has no known label. A
class with a known incorrect label that is fix-equivalent is reported, never
changed.

**Evidence views.** Everything is computed on each of these views, all built by
`analysis_tools/v4/final_evidence.py`:

- E1;
- E1+F2;
- E1+F2+F3 (relevance-reviewed witnesses);
- E1+F2+F3+F4 (annotator class verdicts);
- E1+F2+F3+F4c (only the "correct" verdicts).

**Comparisons.** Challenger vs every baseline in `select_f2_topup.BASELINES`,
with bug unit, equal-bug weighting, N-a, uniform ties and exact bounds. Each is
reported under three settings:

1. AST identity (the contract);
2. C1-id;
3. C1-id + C1-fix.

**Consistency check with E3.** The same normaliser is run on the HumanEval-Java
E3 records. We report how its fix equivalences compare with the frozen E3 rule
(AST fingerprint, or token-level renaming of declared names).
