"""Refit the September policy and run a separately charged label-query simulation."""

import argparse
import hashlib
import json
import math
import platform
import sys
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path

import numpy as np
import sklearn
from threadpoolctl import threadpool_limits

from build_validation_contract_step1 import audit_frozen, json_rows, sha256, write_json, write_rows
from evaluate_stage_aware_policy_v2 import fit_logistic, safe_log_loss
from evaluate_shift_aware_safe_scheduler_v2 import RobustSupportModel
from evidence_budget_bounds import comparison_bounds, difference_coefficients, exact_distribution, resolved, risk_upper, select_query
from validation_policy_contract import CandidateView, SourcePosition, decision_from_scores, native_scores


ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "results/contract_step1"
OUT = ROOT / "results/pilot_step2"
METHODS = ("random_all", "random_disagreement", "uncertainty", "disagreement_first", "decision_focused")
BUDGETS = (0, 1, 2, 4, 8, 16, 32)
MASKS = ("hide_all", "hide_half")
C_GRID = (.01, .1, 1., 10.)
STAGES = ("compile", "test_given_compile", "correct_given_test")


def verify_inputs():
    old = audit_frozen()
    manifest = json.loads((INPUT / "manifest.json").read_text(encoding="utf-8"))
    for path, digest in manifest["files"].items():
        if sha256(ROOT / path) != digest:
            raise ValueError(f"Step 1 input changed: {path}")
    return {"july": old, "step1_manifest_sha256": sha256(INPUT / "manifest.json"),
            "step1_files_verified": len(manifest["files"])}


def execution_sources():
    paths = {Path(m.__file__).resolve() for m in list(sys.modules.values())
             if getattr(m, "__file__", None) and str(m.__file__).endswith(".py")}
    return {str(p.relative_to(ROOT)): sha256(p) for p in sorted(paths)
            if p.is_relative_to(ROOT) and ".venv" not in p.parts}


def load_inputs():
    contexts = list(json_rows(INPUT / "contexts.jsonl"))
    context_map = {r["context_id"]: r for r in contexts}
    raw = list(json_rows(INPUT / "decision_candidates.jsonl"))
    views = [CandidateView(r["candidate_id"], r["context_id"], r["anchor"], r["patch"],
                           tuple(SourcePosition(**s) for s in r["sources"])) for r in raw]
    evidence = {r["candidate_id"]: r for r in json_rows(INPUT / "evaluation_evidence.jsonl")}
    if set(evidence) != {v.candidate_id for v in views}:
        raise ValueError("Evidence and full pool differ.")
    legacy = {}
    for kind in ("all", "excluded"):
        for row in json_rows(ROOT / f"llm_apr_dataset/llm_apr_defects4j_candidates_v2_candidates_{kind}.jsonl"):
            legacy[row["candidate_id"]] = {k: row.get(k) for k in
                ("compile_values", "test_values", "compile_conflict", "test_conflict")}
    training = []
    for view in views:
        e = evidence[view.candidate_id]
        records = [legacy[k] for k in e["legacy_candidate_ids"]]

        def outcome(stage):
            values = {key for row in records for key, count in (row[stage + "_values"] or {}).items()
                      if count and key in {"true", "false"}}
            if any(row[stage + "_conflict"] for row in records) or len(values) != 1:
                return None
            return next(iter(values)) == "true"

        compile_y, test_y = outcome("compile"), outcome("test")
        semantic_y = {"correct": 1, "incorrect": 0, "unknown": None}[e["label"]]
        if semantic_y == 1 and (compile_y is not True or test_y is not True):
            raise ValueError("Correct label contradicts stage-factorization requirements.")
        training.append({"candidate_id": view.candidate_id,
                         "fold": context_map[view.context_id]["fold"],
                         "bug_id": context_map[view.context_id]["bug_id"],
                         "compile": int(compile_y) if compile_y is not None else None,
                         "test_given_compile": int(test_y) if compile_y is True and test_y is not None else None,
                         "correct_given_test": semantic_y if compile_y is True and test_y is True else None})
    # The scorer/support model receive only this allowlisted projection, never training labels.
    support_rows = [{**asdict(view), "_context_id": view.context_id} for view in views]
    return views, contexts, evidence, training, support_rows


class ProvenanceFeatures:
    def __init__(self, training_views):
        self.sources = sorted({s.source_config for v in training_views for s in v.sources})
        self.max_index = max(s.candidate_index for v in training_views for s in v.sources)

    def transform(self, views):
        matrix = []
        scale = max(self.max_index, 1)
        for view in views:
            positions = [s.candidate_index for s in view.sources]
            by_source = defaultdict(list)
            for source in view.sources:
                by_source[source.source_config].append(source.candidate_index)
            lo = min(positions)
            values = [lo / scale, float(np.mean(positions)) / scale, max(positions) / scale,
                      float(np.std(positions)) / scale, math.log1p(len(positions)),
                      len(by_source) / len(self.sources), float(lo == 0)]
            values += [float(lo == i) for i in range(self.max_index + 1)] + [float(lo > self.max_index)]
            values += [float(s in by_source) for s in self.sources]
            values += [1 - min(by_source[s]) / scale if s in by_source else 0. for s in self.sources]
            matrix.append(values)
        result = np.asarray(matrix, dtype=np.float64)
        if not np.isfinite(result).all():
            raise ValueError("Nonfinite features.")
        return result


def role_folds(j):
    roles = {"test": {f"fold_{j}"}, "calibration": {f"fold_{(j + 1) % 5}"},
             "tuning": {f"fold_{(j + 2) % 5}"}}
    roles["training"] = {f"fold_{i}" for i in range(5)} - set.union(*roles.values())
    return roles


def fit_scores(views, training, support_rows):
    results, audits, predictions = {}, [], []
    for j in range(5):
        roles = role_folds(j)
        refit_folds = roles["training"] | roles["tuning"]
        subsets = {role: [i for i, row in enumerate(training) if row["fold"] in folds]
                   for role, folds in {**roles, "refit": refit_folds}.items()}
        bug_sets = {role: {training[i]["bug_id"] for i in indices}
                    for role, indices in subsets.items() if role != "refit"}
        if any(bug_sets[a] & bug_sets[b] for a in bug_sets for b in bug_sets if a != b):
            raise ValueError("Bug leakage across roles.")
        design = ProvenanceFeatures([views[i] for i in subsets["training"]])
        refit = ProvenanceFeatures([views[i] for i in subsets["refit"]])
        x_design, x_refit = design.transform(views), refit.transform(views)
        stage_scores = []
        stage_audit = []
        for stage in STAGES:
            eligible = {role: [i for i in indices if training[i][stage] is not None]
                        for role, indices in subsets.items()}
            y = {role: np.array([training[i][stage] for i in indices], dtype=np.int8)
                 for role, indices in eligible.items()}
            if not len(y["training"]) or not len(y["tuning"]):
                raise ValueError("Stage lacks training or tuning evidence.")
            trials = []
            for c in C_GRID:
                model = fit_logistic(x_design[eligible["training"]], y["training"], c)
                prob = model.predict_proba(x_design[eligible["tuning"]])[:, 1]
                trials.append({"C": c, "tuning_log_loss": safe_log_loss(y["tuning"], prob)})
            best = min(trials, key=lambda t: (t["tuning_log_loss"], t["C"]))["C"]
            model = fit_logistic(x_refit[eligible["refit"]], y["refit"], best)
            probabilities = model.predict_proba(x_refit)[:, 1]
            stage_scores.append(probabilities)
            if hasattr(model, "named_steps"):
                scaler, logistic = model.named_steps["standardscaler"], model.named_steps["logisticregression"]
                state = {"mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist(),
                         "coef": logistic.coef_.tolist(), "intercept": logistic.intercept_.tolist()}
            else:
                state = {"constant_probability": model.probability}
            stage_audit.append({"stage": stage, "C": best, "trials": trials, "state": state,
                                "eligible_counts": {role: len(v) for role, v in eligible.items()},
                                "positive_counts": {role: int(v.sum()) for role, v in y.items()}})
        joint = np.prod(stage_scores, axis=0)
        support = RobustSupportModel.fit([support_rows[i] for i in subsets["refit"]])
        relevant = subsets["test"] + subsets["calibration"]
        distances = support.context_distances([support_rows[i] for i in relevant])
        scores = {views[i].candidate_id: float(joint[i]) for i in relevant}
        results[j] = {"scores": scores, "distances": distances, "support_threshold": support.threshold(.95),
                      "seen_sources": set(refit.sources)}
        for role in ("test", "calibration"):
            for i in subsets[role]:
                predictions.append({"rotation": j, "role": role, "candidate_id": views[i].candidate_id,
                                    "score": float(joint[i]), **{s: float(p[i]) for s, p in zip(STAGES, stage_scores)}})
        audits.append({"rotation": j, "roles": {k: sorted(v) for k, v in roles.items()},
                       "role_bugs": {k: sorted(v) for k, v in bug_sets.items()}, "disjoint": True,
                       "training_feature_map": {"sources": design.sources, "max_index": design.max_index},
                       "refit_feature_map": {"sources": refit.sources, "max_index": refit.max_index},
                       "support": {**support.metadata(), "q95_threshold": support.threshold(.95)},
                       "stages": stage_audit})
        print(f"Fitted rotation {j + 1}/5: full-pool stage scores and independent support", flush=True)
    return results, audits, predictions


def build_records(views, contexts, evidence, fitted):
    pools = defaultdict(list)
    for view in views:
        pools[view.context_id].append(view)
    truth = {k: {"correct": 1, "incorrect": 0, "unknown": None}[r["label"]] for k, r in evidence.items()}
    rotations = {}
    for j, fit in fitted.items():
        records = []
        roles = role_folds(j)
        for ctx in contexts:
            if ctx["fold"] not in roles["test"] | roles["calibration"]:
                continue
            pool = tuple(pools[ctx["context_id"]])
            scores = {v.candidate_id: fit["scores"][v.candidate_id] for v in pool}
            b = decision_from_scores(pool, native_scores(pool))
            p = decision_from_scores(pool, scores)
            d = difference_coefficients(p, b)
            lower, upper = comparison_bounds(d, truth)
            candidate_sources = {s.source_config for v in pool for s in v.sources}
            supported = bool(pool) and candidate_sources <= fit["seen_sources"] and fit["distances"][ctx["context_id"]] <= fit["support_threshold"]
            margin = math.fsum(float(v) * scores[k] for k, v in d.items())
            old_margin = max(scores.values()) - max(scores[k] for k, prob in b.probabilities if prob) if pool else 0.
            records.append({"context_id": ctx["context_id"], "bug_id": ctx["bug_id"], "fold": ctx["fold"],
                            "role": "test" if ctx["fold"] in roles["test"] else "calibration",
                            "scores": scores, "baseline": b, "challenger": p, "coefficients": d,
                            "supported": supported, "margin": margin, "old_margin": old_margin,
                            "lower": lower, "upper": upper, "harm_upper": max(0., -float(lower)),
                            "harm_lower": max(0., -float(upper))})
        rotations[j] = records
    return rotations, truth


def selected_bug_harms(records, threshold, field="harm_upper"):
    harms = {}
    for r in records:
        if r["supported"] and r["coefficients"] and r["margin"] >= threshold:
            harms[r["bug_id"]] = max(harms.get(r["bug_id"], 0.), r[field])
    return harms


def utility(records, truth, selector):
    baseline, proposed, differences = [], [], []
    bug_bounds = defaultdict(list)
    for r in records:
        b = r["baseline"]
        p = r["challenger"] if selector(r) else b
        baseline.append(comparison_bounds(exact_distribution(b), truth))
        proposed.append(comparison_bounds(exact_distribution(p), truth))
        delta = comparison_bounds(difference_coefficients(p, b), truth)
        differences.append(delta)
        bug_bounds[r["bug_id"]].append(delta)
    def mean_bounds(values):
        return [math.fsum(float(v[i]) for v in values) / len(values) for i in (0, 1)]
    return {"contexts": len(records), "bugs": len(bug_bounds), "native_success_bounds": mean_bounds(baseline),
            "proposed_success_bounds": mean_bounds(proposed), "paired_delta_bounds": mean_bounds(differences),
            "equal_bug_paired_delta_bounds": mean_bounds([mean_bounds(v) for v in bug_bounds.values()])}


def calibrate(rotations, truth):
    tables, choices = [], []
    for j, records in rotations.items():
        calibration = [r for r in records if r["role"] == "calibration"]
        test = [r for r in records if r["role"] == "test"]
        grid = []
        for index in range(21):
            threshold = index / 20
            harms = selected_bug_harms(calibration, threshold)
            optimistic_harms = selected_bug_harms(calibration, threshold, "harm_lower")
            row = {"rotation": j, "threshold": threshold, "selected_calibration_bugs": len(harms),
                   "mean_upper_harm": float(np.mean(list(harms.values()))) if harms else None,
                   "posthoc_optimistic_mean_harm": float(np.mean(list(optimistic_harms.values()))) if harms else None,
                   "posthoc_optimistic_kl_not_a_certificate": risk_upper(list(optimistic_harms.values())),
                   **{method + "_upper": risk_upper(list(harms.values()), method) for method in ("kl", "hoeffding")}}
            grid.append(row)
        tables.extend(grid)
        for method in ("kl", "hoeffding"):
            for target in (.05, .10, .20):
                eligible = [r for r in grid if r["selected_calibration_bugs"] >= 20 and r[method + "_upper"] <= target]
                chosen = min(eligible, key=lambda r: (-r["selected_calibration_bugs"], r["threshold"])) if eligible else None
                threshold = chosen["threshold"] if chosen else None
                harms = selected_bug_harms(test, threshold) if chosen else {}
                choices.append({"rotation": j, "bound": method, "target": target, "threshold": threshold,
                                "calibration_certificate": chosen, "selected_test_bugs": len(harms),
                                "test_mean_upper_harm": float(np.mean(list(harms.values()))) if harms else None})
    oof = [r for records in rotations.values() for r in records if r["role"] == "test"]
    reports = {"challenger": utility(oof, truth, lambda r: True),
               "support_only": utility(oof, truth, lambda r: r["supported"])}
    for method in ("kl", "hoeffding"):
        for target in (.05, .10, .20):
            thresholds = {f"fold_{c['rotation']}": c["threshold"] for c in choices if c["bound"] == method and c["target"] == target}
            reports[f"{method}_risk_{target:.2f}"] = utility(oof, truth, lambda r: thresholds[r["fold"]] is not None and
                r["supported"] and r["margin"] >= thresholds[r["fold"]])
    return oof, tables, choices, reports


def stable_number(*parts):
    return int.from_bytes(hashlib.sha256(json.dumps(parts).encode()).digest()[:8], "big")


def simulate(record, truth, method, mask, seed):
    scores, d = record["scores"], record["coefficients"]
    observed = {k: truth[k] if mask == "hide_half" and stable_number("mask", seed, k) % 2 == 0 else None for k in scores}
    priorities = {k: (stable_number("priority", seed, k), k) for k in scores}
    attempted = set()
    states = []
    false_resolutions = 0
    for budget in range(max(BUDGETS) + 1):
        lower, upper = comparison_bounds(d, observed)
        is_resolved = resolved(lower, upper)
        # Accepted observations must restrict, never contradict, the full available evidence.
        full_lower, full_upper = record["lower"], record["upper"]
        if lower > full_lower or upper < full_upper:
            raise AssertionError("Revealing labels widened or contradicted the admissible full world set.")
        if is_resolved and not (full_lower >= 0 if lower >= 0 else full_upper < 0):
            false_resolutions += 1
        if budget in BUDGETS:
            states.append([float(is_resolved), float(upper - lower), len(attempted)])
        if is_resolved:
            states.extend([[1., float(upper - lower), len(attempted)] for b in BUDGETS if b > budget])
            break
        if not is_resolved and budget < max(BUDGETS):
            key = select_query(method, d, observed, scores, priorities, attempted)
            if key is not None:
                attempted.add(key)
                observed[key] = truth[key]
            else:
                states.extend([[0., float(upper - lower), len(attempted)] for b in BUDGETS if b > budget])
                break
    return np.array(states, dtype=float), false_resolutions


def paired_bug_bootstrap(values, records, replicates=2000):
    bugs = sorted({r["bug_id"] for r in records})
    sums = np.array([sum(values[i] for i, r in enumerate(records) if r["bug_id"] == bug) for bug in bugs])
    counts = np.array([sum(r["bug_id"] == bug for r in records) for bug in bugs])
    rng = np.random.default_rng(20260913)
    draws = rng.integers(0, len(bugs), size=(replicates, len(bugs)))
    bootstrap = sums[draws].sum(axis=1) / counts[draws].sum(axis=1)
    return {"point_estimate": float(np.mean(values)), "sampling_ci95": np.quantile(bootstrap, [.025, .975]).tolist(),
            "replicates": replicates, "unit": "paired bug clusters; context-weighted; seeds averaged first"}


def acquisition(oof, truth):
    values = np.zeros((len(MASKS), len(METHODS), len(oof), len(BUDGETS), 3))
    false_resolutions = 0
    for mi, mask in enumerate(MASKS):
        for ci, record in enumerate(oof):
            for method_index, method in enumerate(METHODS):
                for seed in range(10):
                    result, false_count = simulate(record, truth, method, mask, seed)
                    values[mi, method_index, ci] += result
                    false_resolutions += false_count
            if ci % 100 == 0:
                print(f"Acquisition {mask}: {ci}/{len(oof)} contexts", flush=True)
    values /= 10
    curves, per_context = [], []
    for mi, mask in enumerate(MASKS):
        initially_unresolved = values[mi, 0, :, 0, 0] < 1
        for ai, method in enumerate(METHODS):
            for bi, budget in enumerate(BUDGETS):
                row = {"mask": mask, "method": method, "budget": budget}
                metrics = values[mi, ai, :, bi].mean(axis=0)
                curves.append({**row, "resolved_fraction": float(metrics[0]), "mean_interval_width": float(metrics[1]),
                               "mean_requests": float(metrics[2]),
                               "initially_unresolved_contexts": int(initially_unresolved.sum()),
                               "resolved_fraction_initially_unresolved": float(values[mi, ai, initially_unresolved, bi, 0].mean())})
                for ci, r in enumerate(oof):
                    per_context.append({**row, "context_id": r["context_id"], "bug_id": r["bug_id"],
                                        "resolved_fraction_over_seeds": float(values[mi, ai, ci, bi, 0]),
                                        "mean_width": float(values[mi, ai, ci, bi, 1]),
                                        "mean_requests": float(values[mi, ai, ci, bi, 2])})
    primary = values[0, METHODS.index("decision_focused"), :, BUDGETS.index(4), 0] - values[0, METHODS.index("disagreement_first"), :, BUDGETS.index(4), 0]
    comparison = paired_bug_bootstrap(primary, oof)
    comparison["go"] = comparison["point_estimate"] >= .02 and comparison["sampling_ci95"][0] > 0 and false_resolutions == 0
    comparison["false_resolutions"] = false_resolutions
    return curves, per_context, comparison


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUT)
    args = parser.parse_args()
    out = args.output_dir.resolve()
    if out == ROOT or not out.is_relative_to(ROOT / "results") or out.is_relative_to(INPUT) or out.is_relative_to(ROOT / "results/v2"):
        raise ValueError("Use a new results namespace, never a frozen output directory.")
    inputs_before = verify_inputs()
    sources_before = execution_sources()
    protocol_hash = sha256(ROOT / "EVIDENCE_ACQUISITION_PILOT_STEP2.md")
    out.mkdir(parents=True, exist_ok=True)
    views, contexts, evidence, training, support_rows = load_inputs()
    print(f"Loaded {len(views)} candidates / {len(contexts)} contexts", flush=True)
    with threadpool_limits(limits=1):
        fitted, audits, predictions = fit_scores(views, training, support_rows)
    write_rows(out / "predictions.jsonl", predictions)
    write_json(out / "fold_audit.json", audits)
    write_rows(out / "stage_training_evidence.jsonl", training)
    rotations, truth = build_records(views, contexts, evidence, fitted)
    oof, risk_table, choices, utilities = calibrate(rotations, truth)
    write_json(out / "risk_calibration.json", {"threshold_table": risk_table, "choices": choices})
    write_rows(out / "context_comparisons.jsonl", [{"context_id": r["context_id"], "bug_id": r["bug_id"],
        "fold": r["fold"], "supported": r["supported"], "margin": r["margin"], "old_margin": r["old_margin"],
        "lower": float(r["lower"]), "upper": float(r["upper"]),
        "baseline": dict(r["baseline"].probabilities), "challenger": dict(r["challenger"].probabilities)} for r in oof])
    curves, per_context, comparison = acquisition(oof, truth)
    write_rows(out / "acquisition_by_context.jsonl", per_context)
    summary = {"protocol_sha256": protocol_hash, "inputs": inputs_before,
               "environment": {"python": platform.python_version(), "numpy": np.__version__, "sklearn": sklearn.__version__},
               "inventory": {"candidates": len(views), "contexts": len(contexts), "bugs": len({c['bug_id'] for c in contexts}),
                             "labels": dict(Counter(r["label"] for r in evidence.values()))},
               "margin_diagnostics": {"disagreements": sum(bool(r["coefficients"]) for r in oof),
                                      "old_zero_new_positive": sum(r["old_margin"] == 0 and r["margin"] > 1e-12 for r in oof),
                                      "supported_contexts": sum(r["supported"] for r in oof)},
               "utilities": utilities, "acquisition_curves": curves, "primary_acquisition_comparison": comparison,
               "frozen_inputs_unchanged": verify_inputs() == inputs_before}
    if sha256(ROOT / "EVIDENCE_ACQUISITION_PILOT_STEP2.md") != protocol_hash:
        raise ValueError("Protocol changed during run.")
    if execution_sources() != sources_before:
        raise ValueError("Executable sources changed during run.")
    summary["executable_sources"] = sources_before
    summary["diagnostic_amendment_sha256"] = sha256(ROOT / "STEP2_DIAGNOSTIC_AMENDMENT.md")
    write_json(out / "summary.json", summary)
    print(json.dumps({"utilities": utilities, "primary_acquisition_comparison": comparison}, indent=2), flush=True)


if __name__ == "__main__":
    main()
