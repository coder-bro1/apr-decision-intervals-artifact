# Replication package: Testing Can Only Refute

Anonymised replication package for the FSE 2027 submission *Testing Can Only Refute: Deciding Automated Program Repair Comparisons under Incomplete Evidence*.

## Quick check (about a minute, standard library only)

```
python reproduce.py
```

This verifies every file against `SHA256SUMS.json`, regenerates all generated tables and figures of the paper from
the stored results (compared byte for byte with `paper/`), and checks the principal numbers listed in `claims.json`.

## Layout

| Path | Contents |
|---|---|
| `analysis_tools/v4/` | Every analysis behind the paper: decision intervals (`v4core.py`), evidence layers (`final_evidence.py`, `c1_fixrerun_analysis.py`), decision basis and flips (`decision_basis.py`, `decidability_table.py`), refutation limit and pre-flight check (`refutation_limit.py`, `target_aware_preflight.py`), positive controls (`positive_controls.py`), top-k bounds (`topk.py`, brute-force tests in `test_topk.py`), rubric and stress analyses (`f4_rubric_sensitivity.py`, `r1_review_checks.py`), transfer settings and audits. |
| `execution_tools/` | The controlled re-execution protocol (census runner, evidence rules, Defects4J and HumanEval-Java runners). |
| `manuscript/tools/make_v4_figures.py` | Generates every table and figure of the paper from the result files. |
| `protocols/` | The frozen protocol, the pre-registration of the fresh campaign, and every addendum, each frozen before its campaign ran. |
| `results/v4/` | Result files of every analysis and campaign. Execution campaigns keep each job's `terminal.json` (findings and the SHA-256 of every raw log) and `analysis.json`, plus the package manifests and job lists. |
| `results/g1/` | The fresh campaign: generations, policy scores, execution records and results. |
| `paper/` | The tables and figures exactly as included in the paper. |
| `claims.json` | Principal numbers of the paper with the file and key that hold them. |
| `UPSTREAM_SOURCES.md` | Upstream artifacts that are not redistributed, with revisions and hashes. |
| `BUILD_REPORT.json` | What the package builder included, excluded and why. |

## Where each result comes from

| Paper | Result file | Script |
|---|---|---|
| Table 4, Fig. 1(a,b), RQ1 | `results/v4/decidability/`, `results/v4/decision_basis/` | `decidability_table.py`, `decision_basis.py` |
| Robustness, grid, top-k | `results/v4/decidability/SENSITIVITY.md`, `results/v4/grid/`, `results/v4/topk/` | `decidability_table.py`, `run_grid.py`, `topk.py` |
| Table 5, Fig. 1(c) | `results/v4/humaneval/`, `results/g1/g1_final.json`, `results/v4/repairbench/`, `results/v4/d4c_frozen/`, `results/v4/prevarank/`, `results/v4/pod/` | per-setting scripts in `analysis_tools/v4/` |
| Table 6, RQ2 | `results/v4/target_aware_preflight_v1/`, `results/v4/refutation_limit/` | `target_aware_preflight.py`, `refutation_limit.py` |
| Fig. 2, RQ3 positive controls | `results/v4/positive_controls/`, `results/v4/positive_controls_bootstrap_v1/` | `positive_controls.py`, `check_controls.py` |
| RQ3 witnesses, panel, fix re-run | `results/v4/f1_concordance_run_v1/`, `results/v4/f6_panel/`, `results/v4/c1_fixrerun_run_v1/` | `execution_tools/`, `c1_fixrerun_analysis.py` |
| RQ3 human judgments | `results/v4/annotation_results/`, `results/v4/annotation_simple/ANSWERS_*.csv`, `results/v4/f4_rubric_sensitivity_v1/` | `f4_rubric_sensitivity.py` |
| Stress views, error budget, planner, no-op-ineligible intervals | `results/v4/r1_review_v1/` | `r1_review_checks.py` |
| Failure audit (RQ3) | `results/v4/r1_failure_audit/`, `results/v4/r1_failure_audit_run_v1/` | `select_r1_failure_audit.py`, `r1_failure_audit_analysis.py` |
| Prospective campaign (RQ2), second decision point (RQ4) | `results/v4/p1_prospective/`, `results/v4/p1_prospective_run_v1/` | `select_p1_prospective.py`, `p1_record_verdicts.py`, `p1_analysis.py` |
| Conclusion validity | `results/v4/inference/` | inference scripts in `analysis_tools/v4/` |

## Pre-registration of the prospective campaign

The first commit of this repository contains only `protocols/ADDENDUM_V4_P1_PROSPECTIVE.md` and
`results/v4/p1_prospective/{predictions.json, PREDICTIONS.md, candidates.json}`, pushed before the campaign's first
container started. The files are unchanged since; `PREREGISTRATION_SHA256.txt` lists their hashes.

## Reproduction levels

1. **From stored results** (this package alone): `python reproduce.py`.
2. **Analyses from the evidence ledger**: the scripts in `analysis_tools/v4/` recompute every result file. They need
   the candidate texts of the upstream archives, which are not redistributed (`UPSTREAM_SOURCES.md` gives the
   pinned revisions; the SHA-256 of every derived input is recorded in the protocols and manifests, and the
   scripts check them before running). Python 3.12 with `requirements.txt`.
3. **Re-execution**: `execution_tools/run_census.py` re-runs any campaign from its package manifest in the pinned
   Defects4J containers (Docker; image digests in each `manifest.json`). Defects4J 3.0.1 (commit `8c16da82`,
   Java 11) and 2.0.0 (commit `01f13c69`, Java 8); HumanEval-Java with JUnit 4.12 on Temurin 8.

## What is not included, and why

- Candidate and project source text from upstream archives (RepairLLaMA, the detector benchmark): no
  redistribution licence. Defects4J project sources: retrieved by the official Defects4J CLI.
- Raw container logs: their SHA-256 is recorded in each job's `terminal.json`.
- The annotation key of the human review and the annotation packets (they contain candidate code).
- The optional follow-up stage of the fresh campaign, which was not completed.

## Licence

Code: MIT. Data produced by this study: CC BY 4.0. See `LICENSE`.
