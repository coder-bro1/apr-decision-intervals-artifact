# Addendum to Protocol v4: audit of archived failures from high-failure configurations

Frozen 2026-10-02, before any re-execution. Prompted by Reviewer 1 (updated review), question Q1.

## Why

Positive controls show that five configurations (gpt35_gpt-zero-shot, gpt4_gpt-zero-shot, repairllama_ir1_or1,
repairllama_ir1_or3, repairllama_ir1_or4) have more than 10% of their copies of the developer fix recorded as failing.
If every archived failure label from these configurations were uninformative (stress view S2 in
results/v4/r1_review_v1), 7 of the 16 final Defects4J comparisons would reopen. Whether that view is realistic depends
on how often these configurations' archived failures of *other* candidates fail to reproduce.

## Selection (text only, no outcome read)

- Population: candidates with an archived execution-failure label (E0 = 0, basis exec, still 0 in the final view)
  whose failure records all come from the five configurations, that belong to a class relevant to at least one of the
  seven comparisons S2 reopens, excluding fix copies, fix re-run candidates and census witnesses (15,641 candidates).
- Sample: 32 per configuration, split between compile-only and test-failure labels in proportion to the population,
  seed 20261002, built by analysis_tools/v4/select_r1_failure_audit.py: 160 candidates in 132 bugs.
- candidates.json SHA-256: fb9cc3623f7c198738b2ec2f2fd97a35e86b0587aed342c329fc9a0218f527c0

## Execution

Unchanged census witness protocol (execution_tools/run_census.py, phase full, v3 image
sha256:9d43d93cc76845e19fb314247714f4015f0c5fd99277e6e90208069024e5d05e; fixed, buggy and candidate controls, two runs),
package built by prepare_v4_rerun_package.py.

## Analysis (fixed now)

- Reproduced: a rejection witness or a compile failure in both runs. Not reproduced: passes every admissible trigger in
  both runs. Unresolved: everything else (placement failure, voided evidence, inadmissible triggers).
- Non-reproduction rate = not reproduced / (reproduced + not reproduced), overall and per configuration, with
  Clopper-Pearson 95% intervals. Passing the triggers withdraws the archived failure; it does not make a patch correct.
- Propagation: in the final view, each of the 15,641 population labels is returned to unknown independently with the
  upper 95% limit of the non-reproduction rate of its configuration (Monte Carlo, 20,000 draws, seed 20261002); report
  P(decided) for all 16 comparisons. Also report the number of non-reproducing labels each comparison could absorb.
- No label of the paper's main views is changed by this audit; it is reported as a sensitivity.
