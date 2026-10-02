import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from evaluate_prioritization import stable_context_id
from empirical_bayes_stream_calibrator import EmpiricalBayesStreamCalibrator
from fit_stream_calibrated_rankers import StreamCalibrator, index_bin, noisy_or


DEFAULT_CANDIDATES = (
    Path("llm_apr_dataset") / "llm_apr_defects4j_candidates_v2_candidates_hard.jsonl"
)
DEFAULT_OCCURRENCES = (
    Path("llm_apr_dataset")
    / "llm_apr_defects4j_candidates_v2_candidate_occurrences_all.jsonl"
)
DEFAULT_SPLITS = (
    Path("llm_apr_dataset") / "llm_apr_defects4j_candidates_v2_bug_kfold_splits.json"
)
DEFAULT_OUTPUT = Path("results") / "v2" / "nested_stream_calibration.json"
K_VALUES = [1, 3, 5, 10]


def read_jsonl(path):
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def load_data(candidate_path, occurrence_path, split_path, exclude_conflicts):
    split_manifest = json.loads(split_path.read_text(encoding="utf-8"))
    bug_to_fold = split_manifest["bug_to_fold"]
    candidates = {}
    exclusions = Counter()
    for row in read_jsonl(candidate_path):
        if exclude_conflicts and (
            row.get("compile_conflict")
            or row.get("test_conflict")
            or row.get("label_evidence_conflict")
        ):
            exclusions["conflicting_candidates"] += 1
            continue
        if row["bug_id"] not in bug_to_fold:
            raise ValueError(f"Candidate bug {row['bug_id']} is absent from the fold manifest.")
        candidates[row["candidate_id"]] = row

    occurrences = []
    for row in read_jsonl(occurrence_path):
        candidate = candidates.get(row["candidate_id"])
        if candidate is None:
            continue
        if row.get("label") != candidate.get("label"):
            raise ValueError(f"Occurrence label mismatch for {row['candidate_id']}.")
        item = dict(row)
        item["_fold"] = bug_to_fold[row["bug_id"]]
        occurrences.append(item)
    configs = sorted({row["source_config"] for row in occurrences})
    return candidates, occurrences, configs, split_manifest, dict(exclusions)


def calibration_rows(occurrences):
    return [
        {
            "label": row["label"],
            "_stream_occurrences": [
                {
                    "source_config": row["source_config"],
                    "candidate_index": int(row["candidate_index"]),
                    "index_bin": index_bin(row["candidate_index"]),
                }
            ],
        }
        for row in occurrences
    ]


def aggregate_occurrences(occurrences, candidates, namespace=None):
    grouped = defaultdict(list)
    for occurrence in occurrences:
        grouped[occurrence["candidate_id"]].append(occurrence)
    rows = []
    for candidate_id, selected in sorted(grouped.items()):
        row = dict(candidates[candidate_id])
        row["sources"] = [
            {
                "source_config": occurrence["source_config"],
                "prompt_strategy": occurrence.get("prompt_strategy"),
                "candidate_index": int(occurrence["candidate_index"]),
            }
            for occurrence in selected
        ]
        row["source_configs"] = sorted({item["source_config"] for item in row["sources"]})
        row["occurrence_count"] = len(selected)
        row["_stream_occurrences"] = [
            {
                "source_config": item["source_config"],
                "candidate_index": item["candidate_index"],
                "index_bin": index_bin(item["candidate_index"]),
            }
            for item in row["sources"]
        ]
        row["_context_id"] = stable_context_id(row)
        outer_folds = {item["_fold"] for item in selected}
        if len(outer_folds) != 1:
            raise ValueError(f"Candidate {candidate_id} spans multiple outer folds.")
        row["_outer_fold"] = next(iter(outer_folds))
        row["_single_source_config"] = (
            row["source_configs"][0] if len(row["source_configs"]) == 1 else None
        )
        row["_namespace"] = namespace
        row["_evaluation_id"] = f"{namespace}:{candidate_id}" if namespace else candidate_id
        rows.append(row)
    return rows


def source_order_score(row):
    indices = [item["candidate_index"] for item in row["_stream_occurrences"]]
    return -min(indices) if indices else float("-inf")


def positive_provenance(candidates):
    evidence = {
        key
        for row in candidates
        if row["label"] == "correct"
        for key in (row.get("annotation_evidence") or {})
    }
    if "correct_exact" in evidence or "correct_ast" in evidence:
        return "exact_or_ast_present"
    return "semantic_only"


def minimum_rank_distribution(group_size, correct_count):
    denominator = math.comb(group_size, correct_count)
    return [
        (rank, math.comb(group_size - rank, correct_count - 1) / denominator)
        for rank in range(1, group_size - correct_count + 2)
    ]


def pairwise_auc(candidates, score_map):
    correct_scores = [score_map[row["_evaluation_id"]] for row in candidates if row["label"] == "correct"]
    incorrect_scores = [
        score_map[row["_evaluation_id"]] for row in candidates if row["label"] == "incorrect"
    ]
    concordant = 0.0
    for correct_score in correct_scores:
        for incorrect_score in incorrect_scores:
            if correct_score > incorrect_score:
                concordant += 1.0
            elif correct_score == incorrect_score:
                concordant += 0.5
    pairs = len(correct_scores) * len(incorrect_scores)
    return (concordant / pairs if pairs else 0.0), pairs, concordant


def pool_observation(pool_id, candidates, score_map):
    correct_count = sum(row["label"] == "correct" for row in candidates)
    if not correct_count:
        return None
    groups = defaultdict(list)
    for row in candidates:
        groups[score_map[row["_evaluation_id"]]].append(row)
    before = 0
    rank_distribution = None
    tie_size = 0
    tie_correct = 0
    for score in sorted(groups, reverse=True):
        group = groups[score]
        group_correct = sum(row["label"] == "correct" for row in group)
        if group_correct:
            tie_size = len(group)
            tie_correct = group_correct
            rank_distribution = [
                (before + local_rank, probability)
                for local_rank, probability in minimum_rank_distribution(len(group), group_correct)
            ]
            break
        before += len(group)
    if rank_distribution is None:
        raise AssertionError("Positive pool has no positive rank distribution.")
    bug_ids = {row["bug_id"] for row in candidates}
    if len(bug_ids) != 1:
        raise ValueError(f"Pool {pool_id} spans multiple bugs.")
    auc, pairs, concordant = pairwise_auc(candidates, score_map)
    expected_rank = sum(rank * probability for rank, probability in rank_distribution)
    pool_sources = {row["_single_source_config"] for row in candidates}
    heldout_source_config = (
        next(iter(pool_sources)) if len(pool_sources) == 1 and None not in pool_sources else None
    )
    observation = {
        "bug_id": next(iter(bug_ids)),
        "pool_id": pool_id,
        "pool_size": len(candidates),
        "correct_count": correct_count,
        "positive_provenance": positive_provenance(candidates),
        "outer_fold": next(iter({row["_outer_fold"] for row in candidates})),
        "heldout_source_config": heldout_source_config,
        "expected_first_rank": expected_rank,
        "expected_mrr": sum(probability / rank for rank, probability in rank_distribution),
        "expected_validation_reduction": (len(candidates) - expected_rank) / len(candidates),
        "pairwise_auc": auc,
        "pairwise_pairs": pairs,
        "pairwise_concordant": concordant,
        "first_positive_score_group_size": tie_size,
        "correct_in_first_positive_score_group": tie_correct,
    }
    for k in K_VALUES:
        observation[f"expected_recall@{k}"] = sum(
            probability for rank, probability in rank_distribution if rank <= k
        )
    return observation


def group_pools(rows, group_by):
    pools = defaultdict(list)
    for row in rows:
        base = row["bug_id"] if group_by == "bug" else row["_context_id"]
        pool_id = f"{row['_namespace']}:{base}" if row.get("_namespace") else base
        pools[pool_id].append(row)
    return dict(pools)


def mean(values):
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def summarize(observations):
    if not observations:
        raise ValueError("No positive pools available for summarization.")
    pairs = sum(row["pairwise_pairs"] for row in observations)
    concordant = sum(row["pairwise_concordant"] for row in observations)
    tied = [row for row in observations if row["first_positive_score_group_size"] > 1]
    summary = {
        "positive_pools": len(observations),
        "positive_bugs": len({row["bug_id"] for row in observations}),
        "mean_pool_size_positive": mean(row["pool_size"] for row in observations),
        "mean_correct_candidates_per_positive_pool": mean(row["correct_count"] for row in observations),
        "mean_first_correct_rank": mean(row["expected_first_rank"] for row in observations),
        "mrr": mean(row["expected_mrr"] for row in observations),
        "mean_validation_reduction": mean(row["expected_validation_reduction"] for row in observations),
        "pairwise_auc_macro": mean(row["pairwise_auc"] for row in observations if row["pairwise_pairs"]),
        "pairwise_auc_micro": concordant / pairs if pairs else 0.0,
        "pairwise_pairs": pairs,
        "first_positive_tie_pool_count": len(tied),
        "first_positive_tie_pool_rate": len(tied) / len(observations),
    }
    for k in K_VALUES:
        summary[f"recall@{k}"] = mean(row[f"expected_recall@{k}"] for row in observations)
    return summary


def percentile(values, quantile):
    return float(np.quantile(np.asarray(values, dtype=np.float64), quantile))


def numeric_seed(seed):
    return int.from_bytes(hashlib.sha256(str(seed).encode("utf-8")).digest()[:8], "big")


def cluster_weights(observations, iterations, seed):
    bug_ids = sorted({row["bug_id"] for row in observations})
    rng = np.random.default_rng(numeric_seed(seed))
    weights = rng.multinomial(
        len(bug_ids), np.full(len(bug_ids), 1.0 / len(bug_ids)), size=iterations
    )
    return bug_ids, weights


def bug_cluster_bootstrap_ci(observations, iterations, seed):
    bug_ids, weights = cluster_weights(observations, iterations, seed)
    bug_index = {bug_id: index for index, bug_id in enumerate(bug_ids)}
    counts = np.zeros(len(bug_ids), dtype=np.float64)
    mean_metrics = {
        "mrr": "expected_mrr",
        "recall@1": "expected_recall@1",
        "recall@3": "expected_recall@3",
        "recall@5": "expected_recall@5",
        "recall@10": "expected_recall@10",
        "mean_first_correct_rank": "expected_first_rank",
        "mean_validation_reduction": "expected_validation_reduction",
        "pairwise_auc_macro": "pairwise_auc",
    }
    sums = {metric: np.zeros(len(bug_ids), dtype=np.float64) for metric in mean_metrics}
    pair_sums = np.zeros(len(bug_ids), dtype=np.float64)
    concordant_sums = np.zeros(len(bug_ids), dtype=np.float64)
    for row in observations:
        index = bug_index[row["bug_id"]]
        counts[index] += 1
        for metric, field in mean_metrics.items():
            sums[metric][index] += row[field]
        pair_sums[index] += row["pairwise_pairs"]
        concordant_sums[index] += row["pairwise_concordant"]
    denominator = weights @ counts
    intervals = {}
    for metric, bug_sums in sums.items():
        values = (weights @ bug_sums) / denominator
        intervals[metric] = {
            "ci_low": percentile(values, 0.025),
            "ci_high": percentile(values, 0.975),
        }
    micro_values = (weights @ concordant_sums) / np.maximum(weights @ pair_sums, 1.0)
    intervals["pairwise_auc_micro"] = {
        "ci_low": percentile(micro_values, 0.025),
        "ci_high": percentile(micro_values, 0.975),
    }
    return intervals


def paired_bug_cluster(left, right, field, iterations, seed):
    left_map = {row["pool_id"]: row for row in left}
    right_map = {row["pool_id"]: row for row in right}
    if set(left_map) != set(right_map):
        raise ValueError("Paired methods have different positive pools.")
    rows = [
        {
            "bug_id": left_map[pool_id]["bug_id"],
            "difference": left_map[pool_id][field] - right_map[pool_id][field],
        }
        for pool_id in sorted(left_map)
    ]
    bug_ids = sorted({row["bug_id"] for row in rows})
    bug_index = {bug_id: index for index, bug_id in enumerate(bug_ids)}
    sums = np.zeros(len(bug_ids), dtype=np.float64)
    counts = np.zeros(len(bug_ids), dtype=np.float64)
    for row in rows:
        index = bug_index[row["bug_id"]]
        sums[index] += row["difference"]
        counts[index] += 1
    rng = np.random.default_rng(numeric_seed(seed))
    weights = rng.multinomial(
        len(bug_ids), np.full(len(bug_ids), 1.0 / len(bug_ids)), size=iterations
    )
    distribution = (weights @ sums) / (weights @ counts)
    observed = float(sums.sum() / counts.sum())
    nonpositive = (np.count_nonzero(distribution <= 0) + 1) / (iterations + 1)
    nonnegative = (np.count_nonzero(distribution >= 0) + 1) / (iterations + 1)
    return {
        "observed_difference": observed,
        "ci_low": percentile(distribution, 0.025),
        "ci_high": percentile(distribution, 0.975),
        "two_sided_bootstrap_p": min(1.0, 2 * min(nonpositive, nonnegative)),
        "cluster_unit": "bug_id",
    }


def evaluate_methods(rows, score_maps, group_by, iterations, seed):
    pools = group_pools(rows, group_by)
    observations = {}
    results = []
    for method, score_map in score_maps.items():
        method_observations = [
            observation
            for pool_id, candidates in sorted(pools.items())
            if (observation := pool_observation(pool_id, candidates, score_map)) is not None
        ]
        observations[method] = method_observations
        strata = {}
        for stratum in ["exact_or_ast_present", "semantic_only"]:
            selected = [row for row in method_observations if row["positive_provenance"] == stratum]
            if selected:
                strata[stratum] = summarize(selected)
        fold_summaries = {
            fold: summarize([row for row in method_observations if row["outer_fold"] == fold])
            for fold in sorted({row["outer_fold"] for row in method_observations})
        }
        source_summaries = {
            source: summarize(
                [row for row in method_observations if row["heldout_source_config"] == source]
            )
            for source in sorted(
                {
                    row["heldout_source_config"]
                    for row in method_observations
                    if row["heldout_source_config"] is not None
                }
            )
        }
        results.append(
            {
                "method": method,
                "summary": summarize(method_observations),
                "bug_cluster_bootstrap_ci": bug_cluster_bootstrap_ci(
                    method_observations, iterations, f"{seed}:{group_by}:{method}"
                ),
                "positive_provenance_strata": strata,
                "outer_fold_summaries": fold_summaries,
                "heldout_source_config_summaries": source_summaries,
            }
        )
    reference = observations["source_order_tie_aware"]
    comparisons = {}
    for method, method_observations in observations.items():
        if method == "source_order_tie_aware":
            continue
        comparisons[method] = {
            "mrr_vs_source_order": paired_bug_cluster(
                method_observations,
                reference,
                "expected_mrr",
                iterations,
                f"{seed}:{group_by}:paired-mrr:{method}",
            ),
            "recall_at_1_vs_source_order": paired_bug_cluster(
                method_observations,
                reference,
                "expected_recall@1",
                iterations,
                f"{seed}:{group_by}:paired-r1:{method}",
            ),
            "mrr_vs_source_order_by_stratum": {},
            "mrr_vs_source_order_by_heldout_config": {},
        }
        for stratum in ["exact_or_ast_present", "semantic_only"]:
            left = [row for row in method_observations if row["positive_provenance"] == stratum]
            right = [row for row in reference if row["positive_provenance"] == stratum]
            if left:
                comparisons[method]["mrr_vs_source_order_by_stratum"][stratum] = paired_bug_cluster(
                    left,
                    right,
                    "expected_mrr",
                    iterations,
                    f"{seed}:{group_by}:paired-{stratum}:{method}",
                )
        for source in sorted(
            {
                row["heldout_source_config"]
                for row in method_observations
                if row["heldout_source_config"] is not None
            }
        ):
            left = [
                row for row in method_observations if row["heldout_source_config"] == source
            ]
            right = [row for row in reference if row["heldout_source_config"] == source]
            left_map = {row["pool_id"]: row for row in left}
            right_map = {row["pool_id"]: row for row in right}
            if set(left_map) != set(right_map):
                raise ValueError(f"Heldout-config pool mismatch for {source}.")
            differences = [
                left_map[pool_id]["expected_mrr"] - right_map[pool_id]["expected_mrr"]
                for pool_id in sorted(left_map)
            ]
            comparisons[method]["mrr_vs_source_order_by_heldout_config"][source] = {
                "positive_pools": len(differences),
                "observed_difference": mean(differences),
            }
    results.sort(key=lambda row: row["summary"]["mrr"], reverse=True)
    return {"results": results, "paired_comparisons": comparisons}


def known_generator_scores(rows, calibrator):
    score_maps = {name: {} for name in [
        "source_order_tie_aware",
        "stream_index_max",
        "stream_index_mean",
        "stream_index_noisy_or",
        "global_index_only",
        "source_prior_only",
        "random_expected",
    ]}
    for row in rows:
        values = calibrator.candidate_probabilities(row)
        key = row["_evaluation_id"]
        score_maps["source_order_tie_aware"][key] = source_order_score(row)
        score_maps["stream_index_max"][key] = max(values["stream_values"])
        score_maps["stream_index_mean"][key] = mean(values["stream_values"])
        score_maps["stream_index_noisy_or"][key] = noisy_or(values["stream_values"])
        score_maps["global_index_only"][key] = max(values["global_index_values"])
        score_maps["source_prior_only"][key] = max(values["source_prior_values"])
        score_maps["random_expected"][key] = 0.0
    return score_maps


def append_score_maps(target, source):
    for method, values in source.items():
        overlap = set(target[method]) & set(values)
        if overlap:
            raise ValueError(f"Duplicate evaluation IDs for {method}: {len(overlap)}")
        target[method].update(values)


def make_calibrator(calibrator_kind, strengths):
    if calibrator_kind == "fixed":
        return StreamCalibrator(**strengths)
    if calibrator_kind == "empirical_bayes":
        return EmpiricalBayesStreamCalibrator()
    raise ValueError(f"Unknown calibrator: {calibrator_kind}")


def compact_calibrator_metadata(calibrator):
    metadata = calibrator.metadata()
    return {
        "estimator": metadata.get("estimator", "fixed_strength_hierarchical_smoothing"),
        "global_prior": metadata["global_prior"],
        "learned_hyperparameters": metadata.get("learned_hyperparameters"),
        "fixed_smoothing": metadata.get("smoothing"),
        "optimization": metadata.get("optimization"),
    }


def build_protocols(candidates, occurrences, configs, folds, strengths, calibrator_kind):
    known_rows = []
    known_scores = defaultdict(dict)
    strict_rows = []
    strict_scores = defaultdict(dict)
    merged_rows = []
    merged_scores = defaultdict(dict)
    known_audit = []
    crossed_audit = []
    all_invariants = []

    for heldout_fold in folds:
        train_occurrences = [row for row in occurrences if row["_fold"] != heldout_fold]
        eval_occurrences = [row for row in occurrences if row["_fold"] == heldout_fold]
        calibrator = make_calibrator(calibrator_kind, strengths).fit(
            calibration_rows(train_occurrences)
        )
        fold_rows = aggregate_occurrences(eval_occurrences, candidates)
        append_score_maps(known_scores, known_generator_scores(fold_rows, calibrator))
        known_rows.extend(fold_rows)
        train_bugs = {row["bug_id"] for row in train_occurrences}
        eval_bugs = {row["bug_id"] for row in eval_occurrences}
        invariant = train_bugs.isdisjoint(eval_bugs)
        all_invariants.append(invariant)
        known_audit.append(
            {
                "heldout_fold": heldout_fold,
                "train_occurrences": len(train_occurrences),
                "eval_occurrences": len(eval_occurrences),
                "eval_candidates": len(fold_rows),
                "train_bug_count": len(train_bugs),
                "eval_bug_count": len(eval_bugs),
                "global_prior": calibrator.global_prior,
                "calibration": compact_calibrator_metadata(calibrator),
                "train_eval_bugs_disjoint": invariant,
            }
        )

        fold_merged_components = defaultdict(lambda: {"index": [], "prior": []})
        for heldout_config in configs:
            cell_train = [
                row
                for row in occurrences
                if row["_fold"] != heldout_fold and row["source_config"] != heldout_config
            ]
            cell_eval = [
                row
                for row in occurrences
                if row["_fold"] == heldout_fold and row["source_config"] == heldout_config
            ]
            cell_calibrator = make_calibrator(calibrator_kind, strengths).fit(
                calibration_rows(cell_train)
            )
            namespace = f"{heldout_fold}|{heldout_config}"
            cell_rows = aggregate_occurrences(cell_eval, candidates, namespace=namespace)
            cell_score_maps = {name: {} for name in [
                "source_order_tie_aware",
                "unseen_global_index",
                "unseen_stream_fallback",
                "unseen_population_prior",
                "random_expected",
            ]}
            max_fallback_difference = 0.0
            for row in cell_rows:
                key = row["_evaluation_id"]
                index_values = [
                    cell_calibrator.index_prob(item["index_bin"])
                    for item in row["_stream_occurrences"]
                ]
                stream_values = []
                for item in row["_stream_occurrences"]:
                    if item["source_config"] in cell_calibrator.source_rates:
                        raise AssertionError("Held-out generator leaked into stream table.")
                    stream_values.append(cell_calibrator.index_prob(item["index_bin"]))
                index_score = max(index_values)
                stream_score = max(stream_values)
                max_fallback_difference = max(max_fallback_difference, abs(index_score - stream_score))
                cell_score_maps["source_order_tie_aware"][key] = source_order_score(row)
                cell_score_maps["unseen_global_index"][key] = index_score
                cell_score_maps["unseen_stream_fallback"][key] = stream_score
                cell_score_maps["unseen_population_prior"][key] = cell_calibrator.global_prior
                cell_score_maps["random_expected"][key] = 0.0
            append_score_maps(strict_scores, cell_score_maps)
            strict_rows.extend(cell_rows)

            for occurrence in cell_eval:
                component = fold_merged_components[occurrence["candidate_id"]]
                component["index"].append(
                    cell_calibrator.index_prob(index_bin(occurrence["candidate_index"]))
                )
                component["prior"].append(cell_calibrator.global_prior)

            train_bugs = {row["bug_id"] for row in cell_train}
            eval_bugs = {row["bug_id"] for row in cell_eval}
            train_configs = {row["source_config"] for row in cell_train}
            eval_configs = {row["source_config"] for row in cell_eval}
            train_candidate_ids = {row["candidate_id"] for row in cell_train}
            eval_candidate_ids = {row["candidate_id"] for row in cell_eval}
            checks = {
                "train_eval_bugs_disjoint": train_bugs.isdisjoint(eval_bugs),
                "heldout_config_absent_from_training": heldout_config not in train_configs,
                "eval_contains_only_heldout_config": eval_configs <= {heldout_config},
                "train_eval_candidate_ids_disjoint": train_candidate_ids.isdisjoint(eval_candidate_ids),
                "fallback_equals_global_index": max_fallback_difference == 0.0,
            }
            all_invariants.extend(checks.values())
            crossed_audit.append(
                {
                    "heldout_fold": heldout_fold,
                    "heldout_config": heldout_config,
                    "train_occurrences": len(cell_train),
                    "eval_occurrences": len(cell_eval),
                    "eval_candidates": len(cell_rows),
                    "train_bug_count": len(train_bugs),
                    "eval_bug_count": len(eval_bugs),
                    "global_prior": cell_calibrator.global_prior,
                    "calibration": compact_calibrator_metadata(cell_calibrator),
                    "max_fallback_difference": max_fallback_difference,
                    **checks,
                }
            )

        fold_merged_rows = aggregate_occurrences(eval_occurrences, candidates)
        for row in fold_merged_rows:
            key = row["_evaluation_id"]
            components = fold_merged_components[row["candidate_id"]]
            if not components["index"]:
                raise AssertionError(f"No LOCO components for {row['candidate_id']}.")
            merged_scores["source_order_tie_aware"][key] = source_order_score(row)
            merged_scores["loco_index_max"][key] = max(components["index"])
            merged_scores["loco_index_mean"][key] = mean(components["index"])
            merged_scores["loco_index_noisy_or"][key] = noisy_or(components["index"])
            merged_scores["loco_population_prior_max"][key] = max(components["prior"])
            merged_scores["random_expected"][key] = 0.0
        merged_rows.extend(fold_merged_rows)

    if not all(all_invariants):
        raise AssertionError("At least one nested holdout leakage invariant failed.")
    return {
        "known_generator_bug_oof": (known_rows, dict(known_scores)),
        "unseen_generator_single_stream": (strict_rows, dict(strict_scores)),
        "unseen_generator_merged_loco": (merged_rows, dict(merged_scores)),
    }, {
        "known_generator_fold_audit": known_audit,
        "crossed_bug_generator_cell_audit": crossed_audit,
        "all_leakage_invariants_pass": True,
        "known_fold_count": len(known_audit),
        "crossed_cell_count": len(crossed_audit),
    }


def write_score_artifacts(output_path, protocols):
    score_dir = output_path.parent / (output_path.stem + "_scores")
    score_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for protocol, (rows, score_maps) in protocols.items():
        jsonl_path = score_dir / f"{protocol}.jsonl"
        csv_path = score_dir / f"{protocol}.csv"
        records = []
        for row in rows:
            key = row["_evaluation_id"]
            record = {
                "evaluation_id": key,
                "candidate_id": row["candidate_id"],
                "bug_id": row["bug_id"],
                "context_id": row["_context_id"],
                "namespace": row.get("_namespace"),
                **{method: values[key] for method, values in score_maps.items()},
            }
            records.append(record)
        with jsonl_path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record) + "\n")
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
        paths[protocol] = {"jsonl": str(jsonl_path), "csv": str(csv_path), "rows": len(records)}
    return paths


def flatten_results(group_results):
    rows = []
    for protocol, group_payload in group_results.items():
        for group_by, payload in group_payload.items():
            for result in payload["results"]:
                summary = result["summary"]
                for metric in ["mrr", "recall@1", "recall@3", "pairwise_auc_macro"]:
                    interval = result["bug_cluster_bootstrap_ci"][metric]
                    rows.append(
                        {
                            "protocol": protocol,
                            "group_by": group_by,
                            "method": result["method"],
                            "metric": metric,
                            "observed": summary[metric],
                            "ci_low": interval["ci_low"],
                            "ci_high": interval["ci_high"],
                            "positive_pools": summary["positive_pools"],
                            "positive_bugs": summary["positive_bugs"],
                        }
                    )
    return rows


def parse_args():
    parser = argparse.ArgumentParser(
        description="Evaluate stream calibration under crossed bug and generator holdouts on V2."
    )
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--occurrences", type=Path, default=DEFAULT_OCCURRENCES)
    parser.add_argument("--splits", type=Path, default=DEFAULT_SPLITS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--iterations", type=int, default=10000)
    parser.add_argument("--index-strength", type=float, default=50.0)
    parser.add_argument("--source-strength", type=float, default=50.0)
    parser.add_argument("--stream-strength", type=float, default=35.0)
    parser.add_argument(
        "--calibrator",
        choices=["fixed", "empirical_bayes"],
        default="fixed",
    )
    parser.add_argument("--exclude-conflicts", action="store_true")
    parser.add_argument("--bootstrap-seed", default="llm-apr-v2-nested-stream")
    return parser.parse_args()


def main():
    args = parse_args()
    candidates, occurrences, configs, manifest, exclusions = load_data(
        args.candidates, args.occurrences, args.splits, args.exclude_conflicts
    )
    folds = sorted(manifest["folds"])
    strengths = {
        "index_strength": args.index_strength,
        "source_strength": args.source_strength,
        "stream_strength": args.stream_strength,
    }
    protocols, holdout_audit = build_protocols(
        candidates, occurrences, configs, folds, strengths, args.calibrator
    )
    score_paths = write_score_artifacts(args.output, protocols)
    group_results = {}
    for protocol, (rows, score_maps) in protocols.items():
        group_results[protocol] = {}
        for group_by in ["context", "bug"]:
            group_results[protocol][group_by] = evaluate_methods(
                rows,
                score_maps,
                group_by,
                args.iterations,
                f"{args.bootstrap_seed}:{protocol}:{args.exclude_conflicts}",
            )

    payload = {
        "metadata": {
            "candidates": str(args.candidates),
            "occurrences": str(args.occurrences),
            "splits": str(args.splits),
            "candidate_count": len(candidates),
            "occurrence_count": len(occurrences),
            "source_configs": configs,
            "source_config_count": len(configs),
            "folds": folds,
            "exclude_conflicts": args.exclude_conflicts,
            "excluded": exclusions,
            "bootstrap_iterations": args.iterations,
            "bootstrap_cluster": "bug_id",
            "tie_policy": "exact expectation under uniform ordering inside equal-score groups",
            "calibrator": args.calibrator,
            "smoothing_strengths_fixed_before_evaluation": (
                strengths if args.calibrator == "fixed" else None
            ),
            "empirical_bayes_policy": (
                "All concentrations and the source/index mixing weight are estimated "
                "from each training fold by beta-binomial marginal likelihood."
                if args.calibrator == "empirical_bayes"
                else None
            ),
            "protocol_definitions": {
                "known_generator_bug_oof": "Fit on the other four bug folds using all generators; evaluate all generators on the held-out bug fold.",
                "unseen_generator_single_stream": "For every bug fold x generator cell, fit on the other bugs and other 13 generators; rank only that generator's held-out candidates.",
                "unseen_generator_merged_loco": "Merge all generators on held-out bugs; each occurrence receives an index fallback from a model fit without that bug fold or occurrence's generator.",
            },
            "score_files": score_paths,
            "holdout_audit": holdout_audit,
        },
        "protocols": group_results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    csv_path = args.output.with_suffix(".csv")
    flat_rows = flatten_results(group_results)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(flat_rows[0]))
        writer.writeheader()
        writer.writerows(flat_rows)

    print(
        json.dumps(
            {
                "candidate_count": len(candidates),
                "occurrence_count": len(occurrences),
                "configs": len(configs),
                "folds": len(folds),
                "crossed_cells": holdout_audit["crossed_cell_count"],
                "calibrator": args.calibrator,
                "all_leakage_invariants_pass": holdout_audit["all_leakage_invariants_pass"],
                "output": str(args.output),
                "csv": str(csv_path),
            },
            indent=2,
        )
    )
    for protocol, group_payload in group_results.items():
        print(protocol)
        for group_by, result_payload in group_payload.items():
            print(f"  {group_by}")
            for result in result_payload["results"]:
                summary = result["summary"]
                print(
                    f"    {result['method']}: MRR={summary['mrr']:.4f}, "
                    f"R@1={summary['recall@1']:.4f}, pools={summary['positive_pools']}"
                )


if __name__ == "__main__":
    main()
