# Protocol v4 Addendum F6: Random False-Rejection Panel

Frozen 2026-09-29, before selection outcomes or execution. Parent:
`PROTOCOL_V4_BUG_LEVEL.md`.

**Why.** R3 (S5) and R1 (M4): the v1 compatibility panel was
coverage-oriented, not random, so it cannot estimate how often the witness
protocol rejects a correct patch.

## Frame and sample

- **Frame.** Occurrences in the RepairLLaMA/Defects4J pool that meet all of:
  - the E0 label is **correct**;
  - every archived record of the occurrence has test status **pass**
    (unanimous `test_values` true);
  - the occurrence is not already in the v1 census or control package;
  - the occurrence is not a no-op;
  - its bug is active in Defects4J v3.0.1. Deprecated bugs are checked
    inside the runner and reported as unresolved, never excluded after the
    fact.
- **Sample.** 100 occurrences drawn uniformly without replacement with
  `random.Random(20260929).sample` over the ID-sorted frame. **No
  replacement of difficult cases.** Stratum composition (reference match
  vs human judgment) is reported.
- **Execution.** The unchanged witness protocol (fixed, buggy and candidate
  controls, two repetitions, admissible triggers). Image v3.0.1 / Java 11,
  the environment that produced the 185 witnesses.

## Reported

- **False rejections:** candidates with `controlled_trigger_failure`, out of
  the evaluable ones. Report an exact Clopper-Pearson 95% upper bound, and
  the rule-of-three value if the count is zero.
- **Unresolved cases** are reported by status and are never counted as passes.
- **Every false rejection is inspected by hand and reported in full.**
