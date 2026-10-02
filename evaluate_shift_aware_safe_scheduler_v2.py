import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from evaluate_nested_stream_calibration_v2 import (
    aggregate_occurrences,
    calibration_rows,
    evaluate_methods,
    group_pools,
    known_generator_scores,
    load_data,
    make_calibrator,
    paired_bug_cluster,
    pool_observation,
)
from evaluate_prioritization import stable_context_id
from evaluate_stage_aware_policy_v2 import token_features


DEFAULT_CANDIDATES = (
    Path("llm_apr_dataset")
    / "llm_apr_defects4j_candidates_v2_candidates_hard.jsonl"
)
DEFAULT_OCCURRENCES = (
    Path("llm_apr_dataset")
    / "llm_apr_defects4j_candidates_v2_candidate_occurrences_all.jsonl"
)
DEFAULT_REFERENCES = (
    Path("llm_apr_dataset")
    / "llm_apr_defects4j_candidates_v2_reference_fixes.jsonl"
)
DEFAULT_SPLITS = (
    Path("llm_apr_dataset")
    / "llm_apr_defects4j_candidates_v2_bug_kfold_splits.json"
)
DEFAULT_KNOWN_SCORES = (
    Path("results")
    / "v2"
    / "nested_stream_calibration_eb_scores"
    / "known_generator_bug_oof.jsonl"
)
DEFAULT_EXTERNAL_SCORE_ROOT = Path("results/v2/external_transfer_eb_scores")
DEFAULT_EXTERNAL_DATA_ROOT = Path("llm_apr_dataset/external")
DEFAULT_OUTPUT = Path("results/v2/shift_aware_safe_scheduler.json")

RISK_TARGETS = (0.05, 0.10, 0.20, 0.30)
SUPPORT_QUANTILES = (0.90, 0.95, 0.99)
PRIMARY_RISK_TARGET = 0.20
PRIMARY_SUPPORT_QUANTILE = 0.95
MARGIN_QUANTILES = tuple(index / 10 for index in range(10))
DELTA = 0.05
MIN_SELECTED_BUGS = 20

EXTERNAL_SETTINGS = {
    "humanevaljava": {
        "candidate_path": DEFAULT_EXTERNAL_DATA_ROOT
        / "llm_apr_humanevaljava_candidates_v2_candidates_labeled.jsonl",
        "score_path": DEFAULT_EXTERNAL_SCORE_ROOT
        / "retain_conflicts"
        / "humanevaljava"
        / "labeled_full.jsonl",
        "audit_path": DEFAULT_EXTERNAL_DATA_ROOT
        / "llm_apr_humanevaljava_candidates_v2_audit_summary.json",
        "source_index_lt": None,
    },
    "gitbugjava": {
        "candidate_path": DEFAULT_EXTERNAL_DATA_ROOT
        / "llm_apr_gitbugjava_candidates_v2_candidates_labeled.jsonl",
        "score_path": DEFAULT_EXTERNAL_SCORE_ROOT
        / "retain_conflicts"
        / "gitbugjava"
        / "labeled_full.jsonl",
        "audit_path": DEFAULT_EXTERNAL_DATA_ROOT
        / "llm_apr_gitbugjava_candidates_v2_audit_summary.json",
        "source_index_lt": None,
    },
    "gitbugjava_top10": {
        "candidate_path": DEFAULT_EXTERNAL_DATA_ROOT
        / "llm_apr_gitbugjava_candidates_v2_candidates_labeled.jsonl",
        "score_path": DEFAULT_EXTERNAL_SCORE_ROOT
        / "retain_conflicts"
        / "gitbugjava"
        / "top10_per_generator.jsonl",
        "audit_path": DEFAULT_EXTERNAL_DATA_ROOT
        / "llm_apr_gitbugjava_candidates_v2_audit_summary.json",
        "source_index_lt": 10,
    },
}


def iter_jsonl(path):
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"Invalid JSON at {path}:{line_number}") from error


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def numeric_seed(seed):
    return int.from_bytes(
        hashlib.sha256(str(seed).encode("utf-8")).digest()[:8], "big"
    )


def pool_rows(rows):
    pools = defaultdict(list)
    for row in rows:
        pools[row["_context_id"]].append(row)
    return dict(pools)


def source_occurrences(row):
    if row.get("_stream_occurrences"):
        return row["_stream_occurrences"]
    return [
        {
            "source_config": source["source_config"],
            "candidate_index": int(source["candidate_index"]),
        }
        for source in row.get("sources") or []
        if source.get("candidate_index") is not None
    ]


def candidate_support_features(row, max_training_index, source_count):
    occurrences = source_occurrences(row)
    if not occurrences:
        raise ValueError(f"Candidate {row['candidate_id']} has no source occurrence.")
    positions = np.asarray(
        [int(item["candidate_index"]) for item in occurrences],
        dtype=np.float64,
    )
    position_scale = max(int(max_training_index), 1)
    source_scale = max(int(source_count), 1)
    generation = [
        float(np.min(positions)) / position_scale,
        float(np.mean(positions)) / position_scale,
        float(np.max(positions)) / position_scale,
        float(np.std(positions)) / position_scale,
        math.log1p(len(positions)),
        len({item["source_config"] for item in occurrences}) / source_scale,
    ]
    return np.asarray(
        generation + token_features(row.get("anchor"), row.get("patch")),
        dtype=np.float64,
    )


class RobustSupportModel:
    def __init__(
        self,
        center,
        scale,
        max_training_index,
        source_count,
        training_context_distances,
    ):
        self.center = np.asarray(center, dtype=np.float64)
        self.scale = np.asarray(scale, dtype=np.float64)
        self.max_training_index = int(max_training_index)
        self.source_count = int(source_count)
        self.training_context_distances = np.asarray(
            training_context_distances, dtype=np.float64
        )

    @classmethod
    def fit(cls, rows):
        if not rows:
            raise ValueError("Cannot fit support model without candidates.")
        occurrences = [
            occurrence
            for row in rows
            for occurrence in source_occurrences(row)
        ]
        max_index = max(int(item["candidate_index"]) for item in occurrences)
        source_count = len({item["source_config"] for item in occurrences})
        matrix = np.asarray(
            [
                candidate_support_features(row, max_index, source_count)
                for row in rows
            ],
            dtype=np.float64,
        )
        center = np.median(matrix, axis=0)
        q25 = np.quantile(matrix, 0.25, axis=0)
        q75 = np.quantile(matrix, 0.75, axis=0)
        scale = (q75 - q25) / 1.349
        standard = np.std(matrix, axis=0)
        scale = np.where(scale > 1e-8, scale, standard)
        scale = np.where(scale > 1e-8, scale, 1.0)
        model = cls(center, scale, max_index, source_count, [])
        distances = model.candidate_distances(rows)
        by_context = defaultdict(list)
        for row, distance in zip(rows, distances):
            by_context[row["_context_id"]].append(float(distance))
        model.training_context_distances = np.asarray(
            [
                float(np.quantile(values, 0.90))
                for _, values in sorted(by_context.items())
            ],
            dtype=np.float64,
        )
        return model

    def candidate_distances(self, rows):
        matrix = np.asarray(
            [
                candidate_support_features(
                    row, self.max_training_index, self.source_count
                )
                for row in rows
            ],
            dtype=np.float64,
        )
        standardized = (matrix - self.center) / self.scale
        return np.sqrt(np.mean(np.square(standardized), axis=1))

    def context_distances(self, rows):
        distances = self.candidate_distances(rows)
        by_context = defaultdict(list)
        for row, distance in zip(rows, distances):
            by_context[row["_context_id"]].append(float(distance))
        return {
            context_id: float(np.quantile(values, 0.90))
            for context_id, values in by_context.items()
        }

    def threshold(self, quantile):
        return float(np.quantile(self.training_context_distances, quantile))

    def metadata(self):
        return {
            "feature_count": len(self.center),
            "max_training_candidate_index": self.max_training_index,
            "training_source_config_count": self.source_count,
            "training_context_count": len(self.training_context_distances),
            "center": self.center.tolist(),
            "scale": self.scale.tolist(),
        }


def top_tie(candidates, score_map):
    scores = [float(score_map[row["_evaluation_id"]]) for row in candidates]
    best = max(scores)
    return [
        row
        for row, score in zip(candidates, scores)
        if float(score) == best
    ]


def tie_success(candidates):
    return sum(row["label"] == "correct" for row in candidates) / len(candidates)


def build_context_records(
    rows,
    score_maps,
    support_model,
    seen_sources,
    support_quantile,
):
    context_distances = support_model.context_distances(rows)
    support_threshold = support_model.threshold(support_quantile)
    records = []
    for context_id, candidates in sorted(pool_rows(rows).items()):
        native_top = top_tie(candidates, score_maps["source_order_tie_aware"])
        stream_top = top_tie(candidates, score_maps["stream_index_max"])
        native_ids = {row["_evaluation_id"] for row in native_top}
        stream_ids = {row["_evaluation_id"] for row in stream_top}
        native_success = tie_success(native_top)
        stream_success = tie_success(stream_top)
        stream_best = max(
            float(score_maps["stream_index_max"][row["_evaluation_id"]])
            for row in candidates
        )
        stream_at_native = max(
            float(score_maps["stream_index_max"][row["_evaluation_id"]])
            for row in native_top
        )
        candidate_sources = {
            occurrence["source_config"]
            for row in candidates
            for occurrence in source_occurrences(row)
        }
        unseen_sources = sorted(candidate_sources - set(seen_sources))
        distance = context_distances[context_id]
        records.append(
            {
                "context_id": context_id,
                "bug_id": candidates[0]["bug_id"],
                "candidate_count": len(candidates),
                "native_top_size": len(native_top),
                "stream_top_size": len(stream_top),
                "top_sets_identical": native_ids == stream_ids,
                "override_margin": max(0.0, stream_best - stream_at_native),
                "native_budget1_success": native_success,
                "stream_budget1_success": stream_success,
                "harm": max(native_success - stream_success, 0.0),
                "gain": max(stream_success - native_success, 0.0),
                "strict_harm": int(
                    native_success > 0.0 and stream_success == 0.0
                ),
                "strict_gain": int(
                    stream_success > 0.0 and native_success == 0.0
                ),
                "support_distance": distance,
                "support_threshold": support_threshold,
                "out_of_support": (
                    distance > support_threshold or bool(unseen_sources)
                ),
                "source_configs": sorted(candidate_sources),
                "unseen_sources": unseen_sources,
            }
        )
    return records


def unique_margin_thresholds(records):
    margins = [
        row["override_margin"]
        for row in records
        if not row["out_of_support"] and not row["top_sets_identical"]
    ]
    if not margins:
        return []
    return sorted(
        {
            float(np.quantile(np.asarray(margins, dtype=np.float64), quantile))
            for quantile in MARGIN_QUANTILES
        }
    )


def selected_records(records, threshold):
    if threshold is None:
        return []
    return [
        row
        for row in records
        if not row["out_of_support"]
        and not row["top_sets_identical"]
        and row["override_margin"] >= threshold
    ]


def bug_harm_values(records):
    harms = defaultdict(list)
    for row in records:
        harms[row["bug_id"]].append(float(row["harm"]))
    return [max(values) for _, values in sorted(harms.items())]


def simultaneous_hoeffding_upper(harms, threshold_count, delta=DELTA):
    if not harms:
        return 1.0
    mean_harm = float(np.mean(np.asarray(harms, dtype=np.float64)))
    margin = math.sqrt(
        math.log(max(threshold_count, 1) / delta) / (2 * len(harms))
    )
    return min(1.0, mean_harm + margin)


def select_override_threshold(
    records,
    risk_target,
    min_selected_bugs=MIN_SELECTED_BUGS,
    delta=DELTA,
):
    thresholds = unique_margin_thresholds(records)
    trials = []
    for threshold in thresholds:
        selected = selected_records(records, threshold)
        harms = bug_harm_values(selected)
        upper = simultaneous_hoeffding_upper(
            harms, len(thresholds), delta=delta
        )
        trials.append(
            {
                "threshold": threshold,
                "selected_context_count": len(selected),
                "selected_bug_count": len(harms),
                "mean_bug_harm": (
                    float(np.mean(harms)) if harms else None
                ),
                "simultaneous_harm_upper": upper,
                "strict_harm_context_count": sum(
                    row["strict_harm"] for row in selected
                ),
                "strict_gain_context_count": sum(
                    row["strict_gain"] for row in selected
                ),
                "feasible": (
                    len(harms) >= min_selected_bugs and upper <= risk_target
                ),
            }
        )
    feasible = [row for row in trials if row["feasible"]]
    chosen = (
        max(
            feasible,
            key=lambda row: (
                row["selected_context_count"],
                -row["simultaneous_harm_upper"],
                row["threshold"],
            ),
        )
        if feasible
        else None
    )
    return {
        "risk_target": risk_target,
        "delta": delta,
        "minimum_selected_bugs": min_selected_bugs,
        "threshold_grid_size": len(thresholds),
        "selected_threshold": chosen["threshold"] if chosen else None,
        "selected_calibration_contexts": (
            chosen["selected_context_count"] if chosen else 0
        ),
        "selected_calibration_bugs": (
            chosen["selected_bug_count"] if chosen else 0
        ),
        "selected_calibration_harm_upper": (
            chosen["simultaneous_harm_upper"] if chosen else None
        ),
        "feasible": chosen is not None,
        "trials": trials,
    }


def assign_actions(records, threshold):
    actions = {}
    for row in records:
        if row["out_of_support"]:
            action = "defer"
        elif row["top_sets_identical"]:
            action = "agreement"
        elif threshold is not None and row["override_margin"] >= threshold:
            action = "override"
        else:
            action = "fallback"
        actions[row["context_id"]] = action
    return actions


def gated_score_map(rows, score_maps, actions):
    result = {}
    for row in rows:
        method = (
            "stream_index_max"
            if actions[row["_context_id"]] == "override"
            else "source_order_tie_aware"
        )
        result[row["_evaluation_id"]] = score_maps[method][
            row["_evaluation_id"]
        ]
    return result


def action_summary(records, actions):
    counts = Counter(actions.values())
    source_counts = defaultdict(Counter)
    for row in records:
        for source_config in row.get("source_configs", []):
            source_counts[source_config][actions[row["context_id"]]] += 1
    override = [
        row for row in records if actions[row["context_id"]] == "override"
    ]
    harms = bug_harm_values(override)
    return {
        "context_count": len(records),
        "action_counts": dict(sorted(counts.items())),
        "source_config_action_counts": {
            source_config: dict(sorted(action_counts.items()))
            for source_config, action_counts in sorted(source_counts.items())
        },
        "override_context_rate": (
            counts["override"] / len(records) if records else 0.0
        ),
        "override_bug_count": len(harms),
        "mean_override_bug_harm": (
            float(np.mean(harms)) if harms else None
        ),
        "strict_harm_context_count": sum(
            row["strict_harm"] for row in override
        ),
        "strict_gain_context_count": sum(
            row["strict_gain"] for row in override
        ),
        "expected_harm_sum": sum(row["harm"] for row in override),
        "expected_gain_sum": sum(row["gain"] for row in override),
    }


def score_maps_from_ledger(path, field_names):
    score_maps = {name: {} for name in field_names}
    rows = []
    for record in iter_jsonl(path):
        key = record.get("evaluation_id") or record["candidate_id"]
        rows.append(record)
        for name in field_names:
            score_maps[name][key] = float(record[name])
    return rows, score_maps


def append_unique(target, source):
    for method, scores in source.items():
        overlap = set(target[method]) & set(scores)
        if overlap:
            raise ValueError(
                f"Duplicate score keys for {method}: {len(overlap)}"
            )
        target[method].update(scores)


def universe_from_references(path):
    universe = {}
    for row in iter_jsonl(path):
        context_id = stable_context_id(row)
        if context_id in universe:
            raise ValueError(f"Duplicate reference context: {context_id}")
        universe[context_id] = row["bug_id"]
    return universe


def top_success_for_pool(candidates, score_map):
    return tie_success(top_tie(candidates, score_map))


def all_context_budget_one(
    rows,
    score_maps,
    universe,
    iterations,
    seed,
):
    pools = pool_rows(rows)
    unknown_contexts = set(pools) - set(universe)
    if unknown_contexts:
        raise ValueError(
            f"Candidate pools absent from reference universe: {len(unknown_contexts)}"
        )
    per_method = {}
    context_values = {}
    for method, score_map in score_maps.items():
        values = {
            context_id: (
                top_success_for_pool(pools[context_id], score_map)
                if context_id in pools
                else 0.0
            )
            for context_id in universe
        }
        context_values[method] = values
        per_method[method] = {
            "universe_contexts": len(universe),
            "candidate_contexts": len(pools),
            "expected_verified_budget1_successes": sum(values.values()),
            "verified_budget1_success": sum(values.values()) / len(universe),
        }

    bug_ids = sorted(set(universe.values()))
    bug_index = {bug_id: index for index, bug_id in enumerate(bug_ids)}
    context_count_by_bug = np.zeros(len(bug_ids), dtype=np.float64)
    for context_id, bug_id in universe.items():
        context_count_by_bug[bug_index[bug_id]] += 1
    rng = np.random.default_rng(numeric_seed(seed))
    weights = rng.multinomial(
        len(bug_ids),
        np.full(len(bug_ids), 1.0 / len(bug_ids)),
        size=iterations,
    )
    denominator = weights @ context_count_by_bug
    def compare_against(reference_method):
        reference = context_values[reference_method]
        comparisons = {}
        for method, values in context_values.items():
            if method == reference_method:
                continue
            sums = np.zeros(len(bug_ids), dtype=np.float64)
            for context_id, bug_id in universe.items():
                sums[bug_index[bug_id]] += (
                    values[context_id] - reference[context_id]
                )
            distribution = (weights @ sums) / denominator
            observed = float(sums.sum() / len(universe))
            comparisons[method] = {
                "observed_difference": observed,
                "ci_low": float(np.quantile(distribution, 0.025)),
                "ci_high": float(np.quantile(distribution, 0.975)),
                "cluster_unit": "bug_id",
            }
        return comparisons

    return {
        "summaries": per_method,
        "paired_vs_native": compare_against("source_order_tie_aware"),
        "paired_vs_always_stream": compare_against(
            "always_stream_index_max"
        ),
    }


def paired_ranking_comparison(
    rows,
    score_maps,
    left_method,
    right_method,
    iterations,
    seed,
):
    pools = group_pools(rows, "context")
    observations = {}
    for method in (left_method, right_method):
        observations[method] = [
            observation
            for pool_id, candidates in sorted(pools.items())
            if (
                observation := pool_observation(
                    pool_id, candidates, score_maps[method]
                )
            )
            is not None
        ]
    left = observations[left_method]
    right = observations[right_method]
    return {
        "mrr": paired_bug_cluster(
            left,
            right,
            "expected_mrr",
            iterations,
            f"{seed}:mrr",
        ),
        "recall_at_1": paired_bug_cluster(
            left,
            right,
            "expected_recall@1",
            iterations,
            f"{seed}:recall-at-1",
        ),
    }


def add_gate_vs_stream_comparisons(
    ranking,
    rows,
    score_maps,
    iterations,
    seed,
):
    ranking["paired_safe_gates_vs_always_stream"] = {
        method: paired_ranking_comparison(
            rows,
            score_maps,
            method,
            "always_stream_index_max",
            iterations,
            f"{seed}:{method}",
        )
        for method in score_maps
        if method.startswith("safe_gate_")
    }


def make_gate_method_name(support_quantile, risk_target):
    return (
        f"safe_gate_q{int(round(100 * support_quantile)):02d}_"
        f"r{int(round(100 * risk_target)):02d}"
    )


def nested_internal_evaluation(
    candidates,
    occurrences,
    split_manifest,
    references,
    iterations,
    seed,
):
    folds = list(split_manifest["metadata"]["fold_names"])
    combined_rows = []
    base_scores = defaultdict(dict)
    gate_scores = defaultdict(dict)
    fold_audits = []
    action_records = defaultdict(list)

    for test_index, test_fold in enumerate(folds):
        calibration_fold = folds[(test_index + 1) % len(folds)]
        training_folds = set(folds) - {test_fold, calibration_fold}
        train_occurrences = [
            row for row in occurrences if row["_fold"] in training_folds
        ]
        calibration_occurrences = [
            row for row in occurrences if row["_fold"] == calibration_fold
        ]
        test_occurrences = [
            row for row in occurrences if row["_fold"] == test_fold
        ]
        train_rows = aggregate_occurrences(train_occurrences, candidates)
        calibration_eval_rows = aggregate_occurrences(
            calibration_occurrences, candidates
        )
        test_rows = aggregate_occurrences(test_occurrences, candidates)
        calibrator = make_calibrator("empirical_bayes", {}).fit(
            calibration_rows(train_occurrences)
        )
        calibration_scores = known_generator_scores(
            calibration_eval_rows, calibrator
        )
        test_scores = known_generator_scores(test_rows, calibrator)
        support_model = RobustSupportModel.fit(train_rows)
        seen_sources = {
            row["source_config"] for row in train_occurrences
        }

        for method in (
            "source_order_tie_aware",
            "stream_index_max",
            "global_index_only",
        ):
            append_unique(
                base_scores,
                {method: test_scores[method]},
            )

        selections = {}
        action_audit = {}
        for support_quantile in SUPPORT_QUANTILES:
            calibration_records = build_context_records(
                calibration_eval_rows,
                calibration_scores,
                support_model,
                seen_sources,
                support_quantile,
            )
            test_records = build_context_records(
                test_rows,
                test_scores,
                support_model,
                seen_sources,
                support_quantile,
            )
            for risk_target in RISK_TARGETS:
                method = make_gate_method_name(
                    support_quantile, risk_target
                )
                selection = select_override_threshold(
                    calibration_records, risk_target
                )
                actions = assign_actions(
                    test_records, selection["selected_threshold"]
                )
                gate_scores[method].update(
                    gated_score_map(test_rows, test_scores, actions)
                )
                selections[method] = selection
                summary = action_summary(test_records, actions)
                summary["selected_threshold"] = selection[
                    "selected_threshold"
                ]
                summary["calibration_harm_upper"] = selection[
                    "selected_calibration_harm_upper"
                ]
                summary["realized_harm_within_calibration_upper"] = (
                    selection["feasible"]
                    and summary["mean_override_bug_harm"] is not None
                    and summary["mean_override_bug_harm"]
                    <= selection["selected_calibration_harm_upper"]
                )
                action_audit[method] = summary
                for record in test_records:
                    action_records[method].append(
                        {
                            **record,
                            "outer_test_fold": test_fold,
                            "action": actions[record["context_id"]],
                        }
                    )

        train_bugs = {
            row["bug_id"]
            for row in train_rows
        }
        calibration_bugs = {
            row["bug_id"]
            for row in calibration_eval_rows
        }
        test_bugs = {row["bug_id"] for row in test_rows}
        disjoint = (
            train_bugs.isdisjoint(calibration_bugs)
            and train_bugs.isdisjoint(test_bugs)
            and calibration_bugs.isdisjoint(test_bugs)
        )
        fold_audits.append(
            {
                "test_fold": test_fold,
                "calibration_fold": calibration_fold,
                "training_folds": sorted(training_folds),
                "training_occurrences": len(train_occurrences),
                "calibration_occurrences": len(calibration_occurrences),
                "test_occurrences": len(test_occurrences),
                "training_candidates": len(train_rows),
                "calibration_candidates": len(calibration_eval_rows),
                "test_candidates": len(test_rows),
                "training_bugs": len(train_bugs),
                "calibration_bugs": len(calibration_bugs),
                "test_bugs": len(test_bugs),
                "all_role_bug_sets_disjoint": disjoint,
                "seen_source_config_count": len(seen_sources),
                "support_model": support_model.metadata(),
                "selections": selections,
                "test_actions": action_audit,
                "calibrator": calibrator.metadata(),
            }
        )
        combined_rows.extend(test_rows)

    expected_candidates = len(candidates)
    if len(combined_rows) != expected_candidates:
        raise AssertionError(
            f"Nested test rows {len(combined_rows)} != {expected_candidates}."
        )
    if len({row["_evaluation_id"] for row in combined_rows}) != len(
        combined_rows
    ):
        raise AssertionError("A candidate was scored in multiple test folds.")

    score_maps = {
        "source_order_tie_aware": base_scores["source_order_tie_aware"],
        "always_stream_index_max": base_scores["stream_index_max"],
        "always_global_index": base_scores["global_index_only"],
        **gate_scores,
    }
    ranking = evaluate_methods(
        combined_rows,
        score_maps,
        "context",
        iterations,
        f"{seed}:internal-ranking",
    )
    add_gate_vs_stream_comparisons(
        ranking,
        combined_rows,
        score_maps,
        iterations,
        f"{seed}:internal-gate-v-stream",
    )
    budget = all_context_budget_one(
        combined_rows,
        score_maps,
        references,
        iterations,
        f"{seed}:internal-budget",
    )
    return {
        "rows": combined_rows,
        "score_maps": score_maps,
        "ranking": ranking,
        "all_context_budget_one": budget,
        "fold_audit": fold_audits,
        "action_records": dict(action_records),
    }


def rows_from_candidate_and_score_files(
    candidate_path,
    score_path,
    namespace,
    source_index_lt=None,
):
    score_rows, score_maps = score_maps_from_ledger(
        score_path,
        (
            "source_order_tie_aware",
            "stream_index_max",
            "global_index_only",
        ),
    )
    score_by_candidate = {
        row["candidate_id"]: row for row in score_rows
    }
    candidates = {}
    universe = {}
    for row in iter_jsonl(candidate_path):
        universe[stable_context_id(row)] = row["bug_id"]
        if row["candidate_id"] in score_by_candidate:
            candidates[row["candidate_id"]] = row
    if set(candidates) != set(score_by_candidate):
        missing = set(score_by_candidate) - set(candidates)
        raise ValueError(
            f"External score candidates missing from data: {len(missing)}"
        )
    rows = []
    for candidate_id in sorted(candidates):
        raw = dict(candidates[candidate_id])
        score_row = score_by_candidate[candidate_id]
        if raw["label"] != score_row["label"]:
            raise ValueError(f"External label mismatch for {candidate_id}.")
        occurrences = [
            {
                "source_config": source["source_config"],
                "candidate_index": int(source["candidate_index"]),
            }
            for source in raw.get("sources") or []
            if source.get("candidate_index") is not None
            and (
                source_index_lt is None
                or int(source["candidate_index"]) < source_index_lt
            )
        ]
        if not occurrences:
            raise ValueError(
                f"External candidate {candidate_id} has no selected occurrence."
            )
        raw["_stream_occurrences"] = occurrences
        raw["_context_id"] = score_row["context_id"]
        if raw["_context_id"] != stable_context_id(raw):
            raise ValueError(
                f"External context identity mismatch for {candidate_id}."
            )
        raw["_outer_fold"] = namespace
        raw["_namespace"] = None
        raw["_evaluation_id"] = candidate_id
        source_configs = sorted(
            {item["source_config"] for item in occurrences}
        )
        raw["_single_source_config"] = (
            source_configs[0] if len(source_configs) == 1 else None
        )
        rows.append(raw)
    return rows, score_maps, universe


def validate_external_universe(universe, expected_context_count):
    if len(universe) != expected_context_count:
        raise ValueError(
            "External labeled contexts do not match the frozen reference "
            f"denominator: {len(universe)} != {expected_context_count}."
        )
    return universe


def final_defects4j_gate(
    all_rows,
    known_score_path,
    support_model,
    seen_sources,
):
    _, score_maps = score_maps_from_ledger(
        known_score_path,
        (
            "source_order_tie_aware",
            "stream_index_max",
            "global_index_only",
        ),
    )
    candidate_ids = {row["_evaluation_id"] for row in all_rows}
    if any(set(scores) != candidate_ids for scores in score_maps.values()):
        raise ValueError("Known-generator OOF score coverage mismatch.")
    selections = {}
    for support_quantile in SUPPORT_QUANTILES:
        records = build_context_records(
            all_rows,
            score_maps,
            support_model,
            seen_sources,
            support_quantile,
        )
        for risk_target in RISK_TARGETS:
            method = make_gate_method_name(support_quantile, risk_target)
            selections[method] = select_override_threshold(
                records, risk_target
            )
    return selections


def external_evaluation(
    benchmark,
    setting,
    support_model,
    seen_sources,
    final_selections,
    iterations,
    seed,
):
    rows, base_scores, universe = rows_from_candidate_and_score_files(
        setting["candidate_path"],
        setting["score_path"],
        benchmark,
        source_index_lt=setting.get("source_index_lt"),
    )
    audit = json.loads(
        setting["audit_path"].read_text(encoding="utf-8")
    )
    score_maps = {
        "source_order_tie_aware": base_scores["source_order_tie_aware"],
        "always_stream_index_max": base_scores["stream_index_max"],
        "always_global_index": base_scores["global_index_only"],
    }
    action_summaries = {}
    action_records = {}
    for support_quantile in SUPPORT_QUANTILES:
        records = build_context_records(
            rows,
            base_scores,
            support_model,
            seen_sources,
            support_quantile,
        )
        for risk_target in RISK_TARGETS:
            method = make_gate_method_name(support_quantile, risk_target)
            threshold = final_selections[method]["selected_threshold"]
            actions = assign_actions(records, threshold)
            score_maps[method] = gated_score_map(rows, base_scores, actions)
            action_summaries[method] = action_summary(records, actions)
            action_records[method] = [
                {**record, "action": actions[record["context_id"]]}
                for record in records
            ]
    ranking = evaluate_methods(
        rows,
        score_maps,
        "context",
        iterations,
        f"{seed}:{benchmark}:ranking",
    )
    add_gate_vs_stream_comparisons(
        ranking,
        rows,
        score_maps,
        iterations,
        f"{seed}:{benchmark}:gate-v-stream",
    )
    universe = validate_external_universe(
        universe, int(audit["reference_context_count"])
    )
    budget = all_context_budget_one(
        rows,
        score_maps,
        universe,
        iterations,
        f"{seed}:{benchmark}:budget",
    )
    return {
        "benchmark": benchmark,
        "candidate_count": len(rows),
        "context_count": len(universe),
        "positive_context_count": int(
            sum(
                any(row["label"] == "correct" for row in candidates)
                for candidates in pool_rows(rows).values()
            )
        ),
        "ranking": ranking,
        "all_context_budget_one": budget,
        "action_summaries": action_summaries,
        "action_records": action_records,
    }


def primary_summary(result):
    method = make_gate_method_name(
        PRIMARY_SUPPORT_QUANTILE, PRIMARY_RISK_TARGET
    )
    ranking_by_method = {
        row["method"]: row["summary"]
        for row in result["ranking"]["results"]
    }
    budget = result["all_context_budget_one"]
    return {
        "method": method,
        "native": ranking_by_method["source_order_tie_aware"],
        "always_stream": ranking_by_method["always_stream_index_max"],
        "safe_gate": ranking_by_method[method],
        "safe_gate_mrr_vs_native": result["ranking"][
            "paired_comparisons"
        ][method]["mrr_vs_source_order"],
        "safe_gate_mrr_vs_always_stream": result["ranking"][
            "paired_safe_gates_vs_always_stream"
        ][method]["mrr"],
        "safe_gate_budget1": budget["summaries"][method],
        "native_budget1": budget["summaries"][
            "source_order_tie_aware"
        ],
        "safe_gate_budget1_vs_native": budget["paired_vs_native"][method],
        "safe_gate_budget1_vs_always_stream": budget[
            "paired_vs_always_stream"
        ][method],
    }


def write_action_ledger(path, internal_actions, external_results):
    path = Path(path)
    rows = []
    for method, records in internal_actions.items():
        for record in records:
            rows.append(
                {
                    "benchmark": "defects4j",
                    "method": method,
                    **record,
                }
            )
    for benchmark, result in external_results.items():
        for method, records in result["action_records"].items():
            for record in records:
                rows.append(
                    {
                        "benchmark": benchmark,
                        "method": method,
                        **record,
                    }
                )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    return path, len(rows)


def write_summary_csv(path, payload):
    rows = []
    for benchmark, result in (
        ("defects4j", payload["internal"]),
        *payload["external"].items(),
    ):
        summary = result["primary_summary"]
        actions = (
            result["primary_actions"]
            if benchmark == "defects4j"
            else result["action_summaries"][summary["method"]]
        )
        rows.append(
            {
                "benchmark": benchmark,
                "method": summary["method"],
                "native_mrr": summary["native"]["mrr"],
                "always_stream_mrr": summary["always_stream"]["mrr"],
                "safe_gate_mrr": summary["safe_gate"]["mrr"],
                "safe_gate_mrr_minus_native": summary[
                    "safe_gate_mrr_vs_native"
                ]["observed_difference"],
                "mrr_ci_low": summary["safe_gate_mrr_vs_native"]["ci_low"],
                "mrr_ci_high": summary["safe_gate_mrr_vs_native"]["ci_high"],
                "safe_gate_mrr_minus_always_stream": summary[
                    "safe_gate_mrr_vs_always_stream"
                ]["observed_difference"],
                "stream_mrr_ci_low": summary[
                    "safe_gate_mrr_vs_always_stream"
                ]["ci_low"],
                "stream_mrr_ci_high": summary[
                    "safe_gate_mrr_vs_always_stream"
                ]["ci_high"],
                "native_all_context_budget1": summary["native_budget1"][
                    "verified_budget1_success"
                ],
                "safe_gate_all_context_budget1": summary[
                    "safe_gate_budget1"
                ]["verified_budget1_success"],
                "budget1_difference": summary[
                    "safe_gate_budget1_vs_native"
                ]["observed_difference"],
                "budget1_ci_low": summary[
                    "safe_gate_budget1_vs_native"
                ]["ci_low"],
                "budget1_ci_high": summary[
                    "safe_gate_budget1_vs_native"
                ]["ci_high"],
                "safe_gate_budget1_minus_always_stream": summary[
                    "safe_gate_budget1_vs_always_stream"
                ]["observed_difference"],
                "stream_budget1_ci_low": summary[
                    "safe_gate_budget1_vs_always_stream"
                ]["ci_low"],
                "stream_budget1_ci_high": summary[
                    "safe_gate_budget1_vs_always_stream"
                ]["ci_high"],
                "override_context_rate": actions["override_context_rate"],
                "defer_context_count": actions["action_counts"].get(
                    "defer", 0
                ),
                "fallback_context_count": actions["action_counts"].get(
                    "fallback", 0
                ),
            }
        )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate a nested, shift-aware safe scheduler that controls "
            "incremental harm relative to native LLM candidate order."
        )
    )
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--occurrences", type=Path, default=DEFAULT_OCCURRENCES)
    parser.add_argument("--references", type=Path, default=DEFAULT_REFERENCES)
    parser.add_argument("--splits", type=Path, default=DEFAULT_SPLITS)
    parser.add_argument(
        "--known-scores", type=Path, default=DEFAULT_KNOWN_SCORES
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--iterations", type=int, default=10000)
    parser.add_argument(
        "--seed", default="shift-aware-safe-scheduler-v2"
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    candidates, occurrences, configs, split_manifest, exclusions = load_data(
        args.candidates,
        args.occurrences,
        args.splits,
        exclude_conflicts=False,
    )
    references = universe_from_references(args.references)
    internal = nested_internal_evaluation(
        candidates,
        occurrences,
        split_manifest,
        references,
        args.iterations,
        args.seed,
    )

    all_rows = aggregate_occurrences(occurrences, candidates)
    support_model = RobustSupportModel.fit(all_rows)
    seen_sources = set(configs)
    final_selections = final_defects4j_gate(
        all_rows,
        args.known_scores,
        support_model,
        seen_sources,
    )
    external = {
        benchmark: external_evaluation(
            benchmark,
            setting,
            support_model,
            seen_sources,
            final_selections,
            args.iterations,
            args.seed,
        )
        for benchmark, setting in EXTERNAL_SETTINGS.items()
    }

    primary_method = make_gate_method_name(
        PRIMARY_SUPPORT_QUANTILE, PRIMARY_RISK_TARGET
    )
    internal_primary_actions = action_summary(
        internal["action_records"][primary_method],
        {
            row["context_id"]: row["action"]
            for row in internal["action_records"][primary_method]
        },
    )
    internal_payload = {
        "ranking": internal["ranking"],
        "all_context_budget_one": internal["all_context_budget_one"],
        "fold_audit": internal["fold_audit"],
        "primary_actions": internal_primary_actions,
    }
    internal_payload["primary_summary"] = primary_summary(internal_payload)
    for result in external.values():
        result["primary_summary"] = primary_summary(result)

    action_ledger = args.output.with_name(
        "shift_aware_safe_scheduler_actions.jsonl"
    )
    action_ledger, action_row_count = write_action_ledger(
        action_ledger, internal["action_records"], external
    )
    payload = {
        "analysis": "shift_aware_safe_scheduler_v2",
        "status": "frozen_protocol_full_result",
        "method_spec": "SHIFT_AWARE_SAFE_SCHEDULER_SPEC.md",
        "inputs": {
            "candidates": str(args.candidates),
            "candidates_sha256": sha256(args.candidates),
            "occurrences": str(args.occurrences),
            "occurrences_sha256": sha256(args.occurrences),
            "references": str(args.references),
            "references_sha256": sha256(args.references),
            "splits": str(args.splits),
            "splits_sha256": sha256(args.splits),
            "known_scores": str(args.known_scores),
            "known_scores_sha256": sha256(args.known_scores),
            "external": {
                benchmark: {
                    "candidate_path": str(setting["candidate_path"]),
                    "candidate_sha256": sha256(
                        setting["candidate_path"]
                    ),
                    "score_path": str(setting["score_path"]),
                    "score_sha256": sha256(setting["score_path"]),
                    "audit_path": str(setting["audit_path"]),
                    "audit_sha256": sha256(setting["audit_path"]),
                    "source_index_lt": setting["source_index_lt"],
                }
                for benchmark, setting in EXTERNAL_SETTINGS.items()
            },
        },
        "protocol": {
            "risk_targets": list(RISK_TARGETS),
            "support_quantiles": list(SUPPORT_QUANTILES),
            "primary_risk_target": PRIMARY_RISK_TARGET,
            "primary_support_quantile": PRIMARY_SUPPORT_QUANTILE,
            "margin_quantiles": list(MARGIN_QUANTILES),
            "delta": DELTA,
            "minimum_selected_bugs": MIN_SELECTED_BUGS,
            "harm_estimand": (
                "expected worst-context budget-1 loss relative to exact-tie "
                "native order, aggregated at selected bug"
            ),
            "bound": (
                "one-sided Hoeffding upper bound with union correction over "
                "the margin-threshold grid"
            ),
            "defer_behavior": (
                "mark out-of-support; retain native order for operational "
                "ranking without claiming learned-policy coverage"
            ),
        },
        "counts": {
            "defects4j_candidates": len(candidates),
            "defects4j_occurrences": len(occurrences),
            "defects4j_reference_contexts": len(references),
            "source_configs": len(configs),
            "excluded": exclusions,
        },
        "support_model_full_defects4j": support_model.metadata(),
        "final_defects4j_gate_selections_for_external": final_selections,
        "internal": internal_payload,
        "external": external,
        "risk_diagnostics": {
            "all_feasible_primary_fold_harm_within_calibration_upper": all(
                (
                    not row["selections"][primary_method]["feasible"]
                    or row["test_actions"][primary_method][
                        "realized_harm_within_calibration_upper"
                    ]
                )
                for row in internal["fold_audit"]
            ),
            "primary_fold_results": [
                {
                    "test_fold": row["test_fold"],
                    "calibration_harm_upper": row["selections"][
                        primary_method
                    ]["selected_calibration_harm_upper"],
                    "test_mean_override_bug_harm": row["test_actions"][
                        primary_method
                    ]["mean_override_bug_harm"],
                    "within_upper": row["test_actions"][primary_method][
                        "realized_harm_within_calibration_upper"
                    ],
                }
                for row in internal["fold_audit"]
            ],
        },
        "integrity_checks": {
            "all_internal_role_bug_sets_disjoint": all(
                row["all_role_bug_sets_disjoint"]
                for row in internal["fold_audit"]
            ),
            "all_internal_candidates_scored_once": (
                len(internal["rows"]) == len(candidates)
                and len(
                    {
                        row["_evaluation_id"]
                        for row in internal["rows"]
                    }
                )
                == len(candidates)
            ),
            "all_14_source_configs_seen_for_external": len(configs) == 14,
            "primary_method_predeclared": (
                primary_method == "safe_gate_q95_r20"
            ),
            "external_actions_fixed_without_external_label_features": True,
            "no_human_fix_or_reference_features": True,
        },
        "outputs": {
            "action_ledger": str(action_ledger),
            "action_ledger_rows": action_row_count,
        },
    }
    if not all(payload["integrity_checks"].values()):
        failures = [
            name
            for name, passed in payload["integrity_checks"].items()
            if not passed
        ]
        raise AssertionError(f"Shift-aware integrity checks failed: {failures}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    csv_path = write_summary_csv(args.output.with_suffix(".csv"), payload)
    payload["outputs"]["summary_csv"] = str(csv_path)
    payload["outputs"]["action_ledger_sha256"] = sha256(action_ledger)
    payload["outputs"]["summary_csv_sha256"] = sha256(csv_path)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "output": str(args.output),
                "summary_csv": str(csv_path),
                "action_ledger": str(action_ledger),
                "primary_method": primary_method,
                "internal_primary": payload["internal"]["primary_summary"],
                "external_primary": {
                    benchmark: result["primary_summary"]
                    for benchmark, result in external.items()
                },
            },
            indent=2,
        )
    )
    return payload


if __name__ == "__main__":
    main()
