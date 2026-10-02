"""D1/B6: learned baselines on the identical pilot_step2 pipeline (same folds, features, C grid, logistic fit).

1. Gate: refit the frozen three-stage challenger and require its held-out scores to match predictions.jsonl.
2. one_stage: one logistic model predicting accepted correctness directly (rows with known labels).
3. source_agnostic: the three-stage challenger with all source-identity feature columns removed
   (per-source membership and per-source position columns), i.e. 'generator metadata removed' (R2 B6).
Writes results/v4/learners/{one_stage,source_agnostic}.jsonl with held-out (test-rotation) scores.
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import run_evidence_pilot_step2 as S  # noqa: E402
from evaluate_stage_aware_policy_v2 import fit_logistic, safe_log_loss  # noqa: E402

OUT = ROOT / "results/v4/learners"


class AgnosticFeatures(S.ProvenanceFeatures):
    """Same columns as ProvenanceFeatures minus the 2 x |sources| source-identity columns."""

    def transform(self, views):
        full = super().transform(views)
        return full[:, : full.shape[1] - 2 * len(self.sources)]


def fit_rotation(views, training, j, stages, feature_cls, targets):
    roles = S.role_folds(j)
    refit_folds = roles["training"] | roles["tuning"]
    subsets = {role: [i for i, row in enumerate(training) if row["fold"] in folds]
               for role, folds in {**roles, "refit": refit_folds}.items()}
    design = feature_cls([views[i] for i in subsets["training"]])
    refit = feature_cls([views[i] for i in subsets["refit"]])
    x_design, x_refit = design.transform(views), refit.transform(views)
    stage_scores, audit = [], []
    for stage in stages:
        eligible = {role: [i for i in idx if targets[i][stage] is not None] for role, idx in subsets.items()}
        y = {role: np.array([targets[i][stage] for i in idx], dtype=np.int8) for role, idx in eligible.items()}
        trials = []
        for c in S.C_GRID:
            model = fit_logistic(x_design[eligible["training"]], y["training"], c)
            prob = model.predict_proba(x_design[eligible["tuning"]])[:, 1]
            trials.append({"C": c, "tuning_log_loss": safe_log_loss(y["tuning"], prob)})
        best = min(trials, key=lambda t: (t["tuning_log_loss"], t["C"]))["C"]
        model = fit_logistic(x_refit[eligible["refit"]], y["refit"], best)
        stage_scores.append(model.predict_proba(x_refit)[:, 1])
        audit.append({"stage": stage, "C": best, "trials": trials})
    return np.prod(stage_scores, axis=0), stage_scores, subsets["test"], audit


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    views, contexts, evidence, training, _ = S.load_inputs()
    frozen = {}
    with open(ROOT / "results/pilot_step2/predictions.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r["role"] == "test":
                frozen[r["candidate_id"]] = r["score"]
    # 1. gate: refit the frozen challenger
    worst = 0.0
    for j in range(5):
        joint, _, test, _ = fit_rotation(views, training, j, S.STAGES, S.ProvenanceFeatures, training)
        for i in test:
            worst = max(worst, abs(float(joint[i]) - frozen[views[i].candidate_id]))
    gate = {"refit_matches_frozen_max_abs_error": worst, "passed": worst < 1e-9}
    print(json.dumps(gate), flush=True)
    if not gate["passed"]:
        raise SystemExit("Refit does not reproduce frozen challenger scores; pipeline not trusted")
    # 2. one-stage and 3. source-agnostic
    one_stage_targets = [{"correct": {"correct": 1, "incorrect": 0, "unknown": None}[evidence[v.candidate_id]["label"]]}
                         for v in views]
    outputs = {"one_stage": [], "source_agnostic": []}
    audits = {"one_stage": [], "source_agnostic": []}
    for j in range(5):
        joint, _, test, audit = fit_rotation(views, training, j, ("correct",), S.ProvenanceFeatures, one_stage_targets)
        outputs["one_stage"] += [{"candidate_id": views[i].candidate_id, "rotation": j, "score": float(joint[i])} for i in test]
        audits["one_stage"].append({"rotation": j, "stages": audit})
        joint, stages, test, audit = fit_rotation(views, training, j, S.STAGES, AgnosticFeatures, training)
        outputs["source_agnostic"] += [{"candidate_id": views[i].candidate_id, "rotation": j, "score": float(joint[i]),
                                        "compile": float(stages[0][i]), "test_given_compile": float(stages[1][i])}
                                       for i in test]
        audits["source_agnostic"].append({"rotation": j, "stages": audit})
        print(f"rotation {j} fitted", flush=True)
    for name, rows in outputs.items():
        assert len(rows) == len(views)
        with open(OUT / f"{name}.jsonl", "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
    (OUT / "audit.json").write_text(json.dumps({"gate": gate, "audits": audits}, indent=1))


if __name__ == "__main__":
    from threadpoolctl import threadpool_limits
    with threadpool_limits(limits=1):  # identical to run_evidence_pilot_step2.main
        main()
