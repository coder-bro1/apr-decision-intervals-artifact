import sys as _sys  # release layout: shared helper modules live in lib/
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / "lib").is_dir()) / "lib"))
import argparse
import csv
import hashlib
import json
import math
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import beta
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from analyze_validation_funnel_signal_v2 import (
    exact_or_ast_evidence,
    known_aggregate_outcome,
)
from evaluate_prioritization import stable_context_id


DEFAULT_CANDIDATES = (
    Path("llm_apr_dataset")
    / "llm_apr_defects4j_candidates_v2_candidates_all.jsonl"
)
DEFAULT_REFERENCES = (
    Path("llm_apr_dataset")
    / "llm_apr_defects4j_candidates_v2_reference_fixes.jsonl"
)
DEFAULT_SPLITS = (
    Path("llm_apr_dataset")
    / "llm_apr_defects4j_candidates_v2_bug_kfold_splits.json"
)
DEFAULT_CODET5_SCORES = (
    Path("results")
    / "v2"
    / "zero_shot_all"
    / "Salesforce_codet5p-110m-embedding_all.jsonl"
)
DEFAULT_OUTPUT = Path("results") / "v2" / "stage_aware_policy.json"

TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z_0-9]*|\d+|[^\sA-Za-z_0-9]")
METHODS = ("provenance", "codet5", "content", "fusion")
STAGES = (
    "compile",
    "test_given_compile",
    "correct_given_test",
    "semantic_correct_nonreference",
)
DEFAULT_C_GRID = (0.01, 0.1, 1.0, 10.0)
DEFAULT_RISK_TARGETS = (0.05, 0.10, 0.20, 0.30, 0.40, 0.50)
DEFAULT_COVERAGE_GRID = tuple(index / 20 for index in range(1, 21))


def iter_jsonl(path):
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(f"Invalid JSON at {path}:{line_number}") from error


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def stable_fold(seed, bug_id, folds):
    digest = hashlib.sha256(f"{seed}\x1f{bug_id}".encode("utf-8")).hexdigest()
    return folds[int(digest[:16], 16) % len(folds)]


def load_codet5_scores(path):
    result = {}
    for row in iter_jsonl(path):
        candidate_id = row["candidate_id"]
        if candidate_id in result:
            raise ValueError(f"Duplicate CodeT5+ score for {candidate_id}.")
        result[candidate_id] = float(row["anchor_patch_cosine"])
    return result


def token_features(anchor, patch):
    anchor_tokens = set(TOKEN_RE.findall(anchor or ""))
    patch_tokens = set(TOKEN_RE.findall(patch or ""))
    union = anchor_tokens | patch_tokens
    jaccard = len(anchor_tokens & patch_tokens) / len(union) if union else 1.0
    added = len(patch_tokens - anchor_tokens) / max(len(patch_tokens), 1)
    removed = len(anchor_tokens - patch_tokens) / max(len(anchor_tokens), 1)
    anchor_chars = len(anchor or "")
    patch_chars = len(patch or "")
    anchor_lines = (anchor or "").count("\n") + 1
    patch_lines = (patch or "").count("\n") + 1
    delimiter_imbalance = sum(
        abs((patch or "").count(left) - (patch or "").count(right))
        for left, right in (("(", ")"), ("[", "]"), ("{", "}"))
    ) / max(patch_chars, 1)
    return [
        jaccard,
        added,
        removed,
        math.log1p(len(anchor_tokens)),
        math.log1p(len(patch_tokens)),
        math.log((patch_chars + 1) / (anchor_chars + 1)),
        math.log((patch_lines + 1) / (anchor_lines + 1)),
        delimiter_imbalance,
    ]


CONTENT_FEATURE_NAMES = [
    "codet5_anchor_patch_cosine",
    "token_set_jaccard",
    "token_added_fraction",
    "token_removed_fraction",
    "log_anchor_unique_tokens",
    "log_patch_unique_tokens",
    "log_patch_anchor_char_ratio",
    "log_patch_anchor_line_ratio",
    "patch_delimiter_imbalance_per_char",
]


def load_rows(candidate_path, codet5_path):
    codet5_scores = load_codet5_scores(codet5_path)
    rows = []
    seen = set()
    source_vocab = set()
    prompt_vocab = set()
    max_index = 0
    for raw in iter_jsonl(candidate_path):
        candidate_id = raw["candidate_id"]
        if candidate_id in seen:
            raise ValueError(f"Duplicate candidate ID: {candidate_id}")
        seen.add(candidate_id)
        if candidate_id not in codet5_scores:
            raise ValueError(f"Missing CodeT5+ score for {candidate_id}.")
        sources = [
            {
                "source_config": source["source_config"],
                "candidate_index": int(source["candidate_index"]),
            }
            for source in raw.get("sources") or []
            if source.get("candidate_index") is not None
        ]
        if not sources:
            raise ValueError(f"Candidate {candidate_id} has no generation position.")
        source_vocab.update(item["source_config"] for item in sources)
        prompt_vocab.update(raw.get("prompt_strategies") or [])
        max_index = max(max_index, max(item["candidate_index"] for item in sources))
        content = [codet5_scores[candidate_id]]
        content.extend(token_features(raw["anchor"], raw["patch"]))
        rows.append(
            {
                "candidate_id": candidate_id,
                "bug_id": raw["bug_id"],
                "context_id": stable_context_id(raw),
                "label": raw["label"],
                "compile_outcome": known_aggregate_outcome(raw.get("compile_values")),
                "test_outcome": known_aggregate_outcome(raw.get("test_values")),
                "compile_conflict": bool(raw.get("compile_conflict")),
                "test_conflict": bool(raw.get("test_conflict")),
                "label_evidence_conflict": bool(
                    raw.get("label_evidence_conflict")
                ),
                "reference_equivalent_evaluation_only": exact_or_ast_evidence(raw),
                "sources": sources,
                "prompt_count": len(set(raw.get("prompt_strategies") or [])),
                "content_features": content,
            }
        )
    if seen != set(codet5_scores):
        extras = set(codet5_scores) - seen
        raise ValueError(f"CodeT5+ score artifact has {len(extras)} extra candidates.")
    return rows, sorted(source_vocab), sorted(prompt_vocab), max_index


def provenance_feature_names(source_vocab, max_index):
    names = [
        "min_candidate_index_scaled",
        "mean_candidate_index_scaled",
        "max_candidate_index_scaled",
        "std_candidate_index_scaled",
        "log_occurrence_count",
        "unique_source_config_count_scaled",
        "prompt_strategy_count_scaled",
        "any_index_zero",
    ]
    names.extend(f"min_index_is_{index}" for index in range(max_index + 1))
    names.append("min_index_overflow")
    names.extend(f"source_present::{source}" for source in source_vocab)
    names.extend(f"source_early_position::{source}" for source in source_vocab)
    return names


def provenance_features(row, source_vocab, max_index, max_prompt_count):
    positions = [source["candidate_index"] for source in row["sources"]]
    scale = max(max_index, 1)
    min_position = min(positions)
    source_positions = defaultdict(list)
    for source in row["sources"]:
        source_positions[source["source_config"]].append(source["candidate_index"])
    values = [
        min_position / scale,
        sum(positions) / len(positions) / scale,
        max(positions) / scale,
        float(np.std(positions)) / scale,
        math.log1p(len(positions)),
        len(source_positions) / max(len(source_vocab), 1),
        row["prompt_count"] / max(max_prompt_count, 1),
        float(min_position == 0),
    ]
    values.extend(float(min_position == index) for index in range(max_index + 1))
    values.append(float(min_position > max_index))
    values.extend(float(source in source_positions) for source in source_vocab)
    values.extend(
        (
            1.0 - min(source_positions[source]) / scale
            if source in source_positions
            else 0.0
        )
        for source in source_vocab
    )
    return values


def build_feature_matrices(rows, source_vocab, max_index):
    max_prompt_count = max(row["prompt_count"] for row in rows)
    provenance = np.asarray(
        [
            provenance_features(
                row, source_vocab, max_index, max_prompt_count=max_prompt_count
            )
            for row in rows
        ],
        dtype=np.float64,
    )
    content = np.asarray(
        [row["content_features"] for row in rows], dtype=np.float64
    )
    fusion = np.concatenate([provenance, content], axis=1)
    matrices = {
        "provenance": provenance,
        "codet5": content[:, :1],
        "content": content,
        "fusion": fusion,
    }
    if not all(np.isfinite(matrix).all() for matrix in matrices.values()):
        raise ValueError("Non-finite model feature detected.")
    names = {
        "provenance": provenance_feature_names(source_vocab, max_index),
        "codet5": [CONTENT_FEATURE_NAMES[0]],
        "content": list(CONTENT_FEATURE_NAMES),
    }
    names["fusion"] = names["provenance"] + names["content"]
    for method, matrix in matrices.items():
        if matrix.shape[1] != len(names[method]):
            raise AssertionError(f"Feature-name mismatch for {method}.")
    return matrices, names


def stage_eligible_label(row, stage):
    if stage == "compile":
        if row["compile_conflict"] or row["compile_outcome"] is None:
            return None
        return int(row["compile_outcome"])
    if stage == "test_given_compile":
        if (
            row["compile_conflict"]
            or row["test_conflict"]
            or row["compile_outcome"] is not True
            or row["test_outcome"] is None
        ):
            return None
        return int(row["test_outcome"])
    if stage == "correct_given_test":
        if (
            row["compile_conflict"]
            or row["test_conflict"]
            or row["label_evidence_conflict"]
            or row["compile_outcome"] is not True
            or row["test_outcome"] is not True
            or row["label"] not in {"correct", "incorrect"}
        ):
            return None
        return int(row["label"] == "correct")
    if stage == "semantic_correct_nonreference":
        if (
            row["compile_conflict"]
            or row["test_conflict"]
            or row["label_evidence_conflict"]
            or row["compile_outcome"] is not True
            or row["test_outcome"] is not True
            or row["reference_equivalent_evaluation_only"]
            or row["label"] not in {"correct", "incorrect"}
        ):
            return None
        return int(row["label"] == "correct")
    raise ValueError(f"Unknown stage: {stage}")


def stage_indices_labels(rows, stage, allowed_folds=None):
    indices = []
    labels = []
    for index, row in enumerate(rows):
        if allowed_folds is not None and row["fold"] not in allowed_folds:
            continue
        label = stage_eligible_label(row, stage)
        if label is not None:
            indices.append(index)
            labels.append(label)
    return np.asarray(indices, dtype=np.int64), np.asarray(labels, dtype=np.int8)


class ConstantProbabilityModel:
    def __init__(self, probability):
        self.probability = float(probability)

    def predict_proba(self, matrix):
        positive = np.full(len(matrix), self.probability, dtype=np.float64)
        return np.column_stack([1.0 - positive, positive])


def fit_logistic(matrix, labels, regularization):
    if not len(labels):
        raise ValueError("Cannot fit a stage model without labels.")
    if len(set(labels.tolist())) == 1:
        return ConstantProbabilityModel(float(labels[0]))
    model = make_pipeline(
        StandardScaler(),
        LogisticRegression(
            C=regularization,
            solver="lbfgs",
            max_iter=3000,
            random_state=17,
        ),
    )
    model.fit(matrix, labels)
    return model


def safe_log_loss(labels, probabilities):
    return float(log_loss(labels, probabilities, labels=[0, 1]))


def tune_regularization(matrix, train_indices, train_labels, tune_indices, tune_labels, c_grid):
    trials = []
    best = None
    for regularization in c_grid:
        model = fit_logistic(matrix[train_indices], train_labels, regularization)
        probabilities = model.predict_proba(matrix[tune_indices])[:, 1]
        trial = {
            "C": regularization,
            "tuning_log_loss": safe_log_loss(tune_labels, probabilities),
            "tuning_roc_auc": (
                float(roc_auc_score(tune_labels, probabilities))
                if len(set(tune_labels.tolist())) == 2
                else None
            ),
        }
        trials.append(trial)
        key = (trial["tuning_log_loss"], regularization)
        if best is None or key < best[0]:
            best = (key, regularization)
    return best[1], trials


def nested_stage_scores(rows, matrices, folds, c_grid):
    row_count = len(rows)
    oof = {
        method: {
            stage: np.full(row_count, np.nan, dtype=np.float64)
            for stage in STAGES
        }
        for method in METHODS
    }
    calibration = defaultdict(lambda: defaultdict(dict))
    audits = []

    for test_index, test_fold in enumerate(folds):
        calibration_fold = folds[(test_index + 1) % len(folds)]
        tuning_fold = folds[(test_index + 2) % len(folds)]
        training_folds = set(folds) - {
            test_fold,
            calibration_fold,
            tuning_fold,
        }
        test_all = np.asarray(
            [index for index, row in enumerate(rows) if row["fold"] == test_fold],
            dtype=np.int64,
        )
        calibration_all = np.asarray(
            [
                index
                for index, row in enumerate(rows)
                if row["fold"] == calibration_fold
            ],
            dtype=np.int64,
        )

        for stage in STAGES:
            train_indices, train_labels = stage_indices_labels(
                rows, stage, training_folds
            )
            tune_indices, tune_labels = stage_indices_labels(
                rows, stage, {tuning_fold}
            )
            refit_indices, refit_labels = stage_indices_labels(
                rows, stage, training_folds | {tuning_fold}
            )
            calibration_eligible, calibration_labels = stage_indices_labels(
                rows, stage, {calibration_fold}
            )
            test_eligible, test_labels = stage_indices_labels(
                rows, stage, {test_fold}
            )
            bug_sets = {
                "training": {rows[index]["bug_id"] for index in train_indices},
                "tuning": {rows[index]["bug_id"] for index in tune_indices},
                "calibration": {
                    rows[index]["bug_id"] for index in calibration_eligible
                },
                "test": {rows[index]["bug_id"] for index in test_eligible},
            }
            disjoint = all(
                bug_sets[left].isdisjoint(bug_sets[right])
                for left_index, left in enumerate(bug_sets)
                for right in list(bug_sets)[left_index + 1 :]
            )
            if not disjoint:
                raise AssertionError(f"Nested bug leakage for {stage}/{test_fold}.")

            for method in METHODS:
                matrix = matrices[method]
                selected_c, trials = tune_regularization(
                    matrix,
                    train_indices,
                    train_labels,
                    tune_indices,
                    tune_labels,
                    c_grid,
                )
                model = fit_logistic(
                    matrix[refit_indices], refit_labels, selected_c
                )
                oof[method][stage][test_all] = model.predict_proba(
                    matrix[test_all]
                )[:, 1]
                calibration[test_fold][method][stage] = {
                    "indices": calibration_all,
                    "scores": model.predict_proba(matrix[calibration_all])[:, 1],
                }
                audits.append(
                    {
                        "test_fold": test_fold,
                        "calibration_fold": calibration_fold,
                        "tuning_fold": tuning_fold,
                        "training_folds": sorted(training_folds),
                        "stage": stage,
                        "method": method,
                        "selected_C": selected_c,
                        "regularization_trials": trials,
                        "training_count_before_refit": len(train_indices),
                        "refit_count": len(refit_indices),
                        "tuning_count": len(tune_indices),
                        "calibration_eligible_count": len(calibration_eligible),
                        "test_eligible_count": len(test_eligible),
                        "training_positive_count": int(
                            np.sum(train_labels, dtype=np.int64)
                        ),
                        "refit_positive_count": int(
                            np.sum(refit_labels, dtype=np.int64)
                        ),
                        "tuning_positive_count": int(
                            np.sum(tune_labels, dtype=np.int64)
                        ),
                        "calibration_positive_count": int(
                            np.sum(calibration_labels, dtype=np.int64)
                        ),
                        "test_positive_count": int(
                            np.sum(test_labels, dtype=np.int64)
                        ),
                        "all_role_bug_sets_disjoint": disjoint,
                    }
                )

    for method in METHODS:
        for stage in STAGES:
            if np.isnan(oof[method][stage]).any():
                raise AssertionError(f"Incomplete OOF scores for {method}/{stage}.")
    return oof, calibration, audits


def add_stage_selected_scores(rows, oof, calibration, audits, folds):
    row_count = len(rows)
    selected = {
        stage: np.full(row_count, np.nan, dtype=np.float64)
        for stage in STAGES
    }
    tuning_losses = {}
    for audit in audits:
        selected_trial = next(
            trial
            for trial in audit["regularization_trials"]
            if trial["C"] == audit["selected_C"]
        )
        tuning_losses[
            (audit["test_fold"], audit["stage"], audit["method"])
        ] = selected_trial["tuning_log_loss"]

    selection_audit = []
    for test_fold in folds:
        test_indices = np.asarray(
            [
                index
                for index, row in enumerate(rows)
                if row["fold"] == test_fold
            ],
            dtype=np.int64,
        )
        for stage in STAGES:
            candidates = [
                {
                    "method": method,
                    "tuning_log_loss": tuning_losses[
                        (test_fold, stage, method)
                    ],
                }
                for method in METHODS
            ]
            chosen = min(
                candidates,
                key=lambda row: (row["tuning_log_loss"], row["method"]),
            )
            method = chosen["method"]
            selected[stage][test_indices] = oof[method][stage][test_indices]
            calibration[test_fold]["stage_selected"][stage] = calibration[
                test_fold
            ][method][stage]
            selection_audit.append(
                {
                    "test_fold": test_fold,
                    "stage": stage,
                    "selected_feature_family": method,
                    "tuning_log_loss": chosen["tuning_log_loss"],
                    "feature_family_trials": candidates,
                }
            )
    if any(np.isnan(selected[stage]).any() for stage in STAGES):
        raise AssertionError("Stage-selected OOF scores are incomplete.")
    oof["stage_selected"] = selected
    return selection_audit


def binary_metrics(labels, scores, probabilistic=True):
    labels = np.asarray(labels, dtype=np.int8)
    scores = np.asarray(scores, dtype=np.float64)
    result = {
        "count": len(labels),
        "positive_count": int(np.sum(labels, dtype=np.int64)),
        "positive_rate": float(np.mean(labels)),
        "roc_auc": (
            float(roc_auc_score(labels, scores))
            if len(set(labels.tolist())) == 2
            else None
        ),
        "average_precision": float(average_precision_score(labels, scores)),
    }
    result["brier_score"] = (
        float(brier_score_loss(labels, scores)) if probabilistic else None
    )
    result["log_loss"] = (
        safe_log_loss(labels, scores) if probabilistic else None
    )
    return result


def evaluate_stage_models(rows, oof):
    results = {}
    native_scores = np.asarray(
        [-min(item["candidate_index"] for item in row["sources"]) for row in rows],
        dtype=np.float64,
    )
    codet5_scores = np.asarray(
        [row["content_features"][0] for row in rows], dtype=np.float64
    )
    for stage in STAGES:
        indices, labels = stage_indices_labels(rows, stage)
        stage_result = {
            method: binary_metrics(labels, oof[method][stage][indices])
            for method in oof
        }
        stage_result["native_order"] = binary_metrics(
            labels, native_scores[indices], probabilistic=False
        )
        stage_result["codet5_similarity"] = binary_metrics(
            labels, codet5_scores[indices], probabilistic=False
        )
        results[stage] = stage_result
    return results


def percentile(values, quantile):
    if not values:
        return None
    return float(np.quantile(np.asarray(values, dtype=np.float64), quantile))


def paired_bug_bootstrap_auc(rows, stage, left_scores, right_scores, iterations, seed):
    indices, labels = stage_indices_labels(rows, stage)
    by_bug = defaultdict(list)
    for local_index, row_index in enumerate(indices):
        by_bug[rows[row_index]["bug_id"]].append(local_index)
    bugs = sorted(by_bug)
    rng = random.Random(seed)
    differences = []
    for _ in range(iterations):
        sampled = rng.choices(bugs, k=len(bugs))
        selected = [
            local_index for bug_id in sampled for local_index in by_bug[bug_id]
        ]
        sampled_labels = labels[selected]
        if len(set(sampled_labels.tolist())) < 2:
            continue
        left_auc = roc_auc_score(sampled_labels, left_scores[indices][selected])
        right_auc = roc_auc_score(sampled_labels, right_scores[indices][selected])
        differences.append(float(left_auc - right_auc))
    point = float(
        roc_auc_score(labels, left_scores[indices])
        - roc_auc_score(labels, right_scores[indices])
    )
    return {
        "difference": point,
        "low": percentile(differences, 0.025),
        "high": percentile(differences, 0.975),
        "replicates": len(differences),
        "two_sided_bootstrap_p": min(
            1.0,
            2
            * min(
                sum(value <= 0 for value in differences) / len(differences),
                sum(value >= 0 for value in differences) / len(differences),
            ),
        ),
    }


def score_group_expectation(candidates, scores):
    if not candidates:
        return {
            "verified_success_lower": 0.0,
            "possible_success_upper": 0.0,
            "top_tie_size": 0,
        }
    if len(candidates) != len(scores):
        raise ValueError("Candidate and score counts differ.")
    top_score = max(scores)
    tied = [index for index, score in enumerate(scores) if score == top_score]
    correct = sum(candidates[index]["label"] == "correct" for index in tied)
    unknown = sum(candidates[index]["label"] == "unknown" for index in tied)
    return {
        "verified_success_lower": correct / len(tied),
        "possible_success_upper": (correct + unknown) / len(tied),
        "top_tie_size": len(tied),
    }


def build_context_universe(references, rows, bug_to_fold):
    universe = {}
    for reference in references:
        context_id = stable_context_id(reference)
        if context_id in universe:
            raise ValueError(f"Duplicate reference context: {context_id}")
        universe[context_id] = {
            "context_id": context_id,
            "bug_id": reference["bug_id"],
            "fold": bug_to_fold[reference["bug_id"]],
            "candidate_indices": [],
        }
    for index, row in enumerate(rows):
        if row["context_id"] not in universe:
            raise ValueError(f"Candidate outside reference universe: {row['context_id']}")
        universe[row["context_id"]]["candidate_indices"].append(index)
    return universe


def evaluate_budget_one(universe, rows, score_maps, iterations, seed):
    observations = {method: [] for method in score_maps}
    for context in universe.values():
        candidates = [rows[index] for index in context["candidate_indices"]]
        for method, scores in score_maps.items():
            expectation = score_group_expectation(
                candidates,
                [scores[row_index] for row_index in context["candidate_indices"]],
            )
            observations[method].append(
                {
                    "context_id": context["context_id"],
                    "bug_id": context["bug_id"],
                    **expectation,
                }
            )

    summaries = {}
    for method, method_rows in observations.items():
        summaries[method] = {
            "reference_context_count": len(method_rows),
            "contexts_with_candidates": sum(
                row["top_tie_size"] > 0 for row in method_rows
            ),
            "verified_budget1_success": float(
                np.mean([row["verified_success_lower"] for row in method_rows])
            ),
            "possible_budget1_success_upper": float(
                np.mean([row["possible_success_upper"] for row in method_rows])
            ),
            "top_tie_context_count": sum(
                row["top_tie_size"] > 1 for row in method_rows
            ),
        }

    native = {
        row["context_id"]: row
        for row in observations["native_order"]
    }
    paired = {}
    rng = random.Random(seed)
    bugs = sorted({row["bug_id"] for row in observations["native_order"]})
    for method in score_maps:
        if method == "native_order":
            continue
        current = {row["context_id"]: row for row in observations[method]}
        differences_by_bug = defaultdict(list)
        for context_id, native_row in native.items():
            differences_by_bug[native_row["bug_id"]].append(
                current[context_id]["verified_success_lower"]
                - native_row["verified_success_lower"]
            )
        point = sum(
            value
            for values in differences_by_bug.values()
            for value in values
        ) / len(native)
        samples = []
        for _ in range(iterations):
            sampled = rng.choices(bugs, k=len(bugs))
            values = [
                value
                for bug_id in sampled
                for value in differences_by_bug[bug_id]
            ]
            samples.append(sum(values) / len(values))
        paired[method] = {
            "verified_success_difference_vs_native_order": point,
            "low": percentile(samples, 0.025),
            "high": percentile(samples, 0.975),
            "replicates": len(samples),
        }
    return {"summaries": summaries, "paired_vs_native_order": paired}


def clopper_pearson_upper(errors, total, confidence):
    if total <= 0:
        return None
    if errors >= total:
        return 1.0
    return float(beta.ppf(confidence, errors + 1, total - errors))


def top_test_passing_by_context(indices, rows, scores):
    grouped = defaultdict(list)
    for index in indices:
        row = rows[index]
        if (
            row["compile_outcome"] is True
            and row["test_outcome"] is True
            and not row["compile_conflict"]
            and not row["test_conflict"]
            and not row["label_evidence_conflict"]
        ):
            grouped[row["context_id"]].append(index)
    result = []
    for context_id, candidates in grouped.items():
        best = sorted(
            candidates,
            key=lambda index: (-scores[index], rows[index]["candidate_id"]),
        )[0]
        result.append(
            {
                "context_id": context_id,
                "bug_id": rows[best]["bug_id"],
                "candidate_id": rows[best]["candidate_id"],
                "score": float(scores[best]),
                "label": rows[best]["label"],
            }
        )
    return sorted(result, key=lambda row: (-row["score"], row["context_id"]))


def selection_summary(selected, total_contexts):
    labels = Counter(row["label"] for row in selected)
    selected_count = len(selected)
    known_wrong = labels["incorrect"]
    unknown = labels["unknown"]
    correct = labels["correct"]
    return {
        "selected_context_count": selected_count,
        "total_reference_context_count": total_contexts,
        "coverage": selected_count / total_contexts if total_contexts else 0.0,
        "verified_correct_count": correct,
        "known_wrong_count": known_wrong,
        "unknown_count": unknown,
        "wrong_acceptance_lower": (
            known_wrong / selected_count if selected_count else None
        ),
        "wrong_acceptance_upper": (
            (known_wrong + unknown) / selected_count if selected_count else None
        ),
        "verified_success_lower": (
            correct / selected_count if selected_count else None
        ),
        "possible_success_upper": (
            (correct + unknown) / selected_count if selected_count else None
        ),
    }


def calibration_frontier(
    top_rows,
    total_contexts,
    coverage_grid,
    delta,
    min_support,
    unknown_policy,
):
    if not top_rows:
        return []
    thresholds = []
    for coverage in coverage_grid:
        target_count = max(1, math.ceil(coverage * len(top_rows)))
        threshold = top_rows[min(target_count, len(top_rows)) - 1]["score"]
        if threshold not in thresholds:
            thresholds.append(threshold)
    simultaneous_confidence = 1.0 - delta / max(len(thresholds), 1)
    frontier = []
    for threshold in thresholds:
        selected = [row for row in top_rows if row["score"] >= threshold]
        summary = selection_summary(selected, total_contexts)
        labels = Counter(row["label"] for row in selected)
        if unknown_policy == "pessimistic":
            risk_total = len(selected)
            risk_errors = labels["incorrect"] + labels["unknown"]
        elif unknown_policy == "complete_case":
            risk_total = labels["correct"] + labels["incorrect"]
            risk_errors = labels["incorrect"]
        else:
            raise ValueError(f"Unknown label policy: {unknown_policy}")
        frontier.append(
            {
                "threshold": threshold,
                "unknown_policy": unknown_policy,
                "risk_denominator": risk_total,
                "risk_error_count": risk_errors,
                "simultaneous_cp_upper": clopper_pearson_upper(
                    risk_errors, risk_total, simultaneous_confidence
                ),
                "meets_minimum_support": risk_total >= min_support,
                **summary,
            }
        )
    return frontier


def choose_frontier_point(frontier, risk_target):
    feasible = [
        row
        for row in frontier
        if row["meets_minimum_support"]
        and row["simultaneous_cp_upper"] is not None
        and row["simultaneous_cp_upper"] <= risk_target
    ]
    if not feasible:
        return None
    return max(
        feasible,
        key=lambda row: (row["selected_context_count"], -row["threshold"]),
    )


def evaluate_risk_control(
    rows,
    universe,
    folds,
    oof,
    calibration,
    risk_targets,
    coverage_grid,
    delta,
    min_support,
):
    fold_results = []
    aggregate = defaultdict(list)
    native_order_scores = np.asarray(
        [
            -min(source["candidate_index"] for source in row["sources"])
            for row in rows
        ],
        dtype=np.float64,
    )
    codet5_similarity_scores = np.asarray(
        [row["content_features"][0] for row in rows], dtype=np.float64
    )
    fixed_scores = {
        "native_order": native_order_scores,
        "codet5_similarity": codet5_similarity_scores,
    }
    learned_methods = tuple(oof)
    for test_fold in folds:
        test_indices = np.asarray(
            [index for index, row in enumerate(rows) if row["fold"] == test_fold],
            dtype=np.int64,
        )
        calibration_indices = calibration[test_fold]["fusion"][
            "correct_given_test"
        ]["indices"]
        test_total_contexts = sum(
            context["fold"] == test_fold for context in universe.values()
        )
        calibration_fold = (
            rows[int(calibration_indices[0])]["fold"]
            if len(calibration_indices)
            else None
        )
        calibration_total_contexts = sum(
            context["fold"] == calibration_fold for context in universe.values()
        )

        for method in learned_methods + tuple(fixed_scores):
            if method in learned_methods:
                calibration_scores = np.full(
                    len(rows), np.nan, dtype=np.float64
                )
                calibration_record = calibration[test_fold][method][
                    "correct_given_test"
                ]
                calibration_scores[
                    calibration_record["indices"]
                ] = calibration_record["scores"]
                test_scores = oof[method]["correct_given_test"]
            else:
                calibration_record = {"indices": calibration_indices}
                calibration_scores = fixed_scores[method]
                test_scores = fixed_scores[method]
            calibration_top = top_test_passing_by_context(
                calibration_record["indices"], rows, calibration_scores
            )
            test_top = top_test_passing_by_context(
                test_indices, rows, test_scores
            )
            for unknown_policy in ("pessimistic", "complete_case"):
                frontier = calibration_frontier(
                    calibration_top,
                    calibration_total_contexts,
                    coverage_grid,
                    delta,
                    min_support,
                    unknown_policy,
                )
                for risk_target in risk_targets:
                    chosen = choose_frontier_point(frontier, risk_target)
                    selected = (
                        [
                            row
                            for row in test_top
                            if row["score"] >= chosen["threshold"]
                        ]
                        if chosen
                        else []
                    )
                    test_summary = selection_summary(
                        selected, test_total_contexts
                    )
                    record = {
                        "test_fold": test_fold,
                        "method": method,
                        "unknown_policy": unknown_policy,
                        "risk_target": risk_target,
                        "calibration_feasible": chosen is not None,
                        "calibration_selected_point": chosen,
                        "calibration_frontier": frontier,
                        "test": test_summary,
                    }
                    fold_results.append(record)
                    aggregate[(method, unknown_policy, risk_target)].append(record)

    summaries = []
    for (method, unknown_policy, risk_target), records in sorted(
        aggregate.items()
    ):
        selected = sum(
            row["test"]["selected_context_count"] for row in records
        )
        total = sum(
            row["test"]["total_reference_context_count"] for row in records
        )
        correct = sum(row["test"]["verified_correct_count"] for row in records)
        wrong = sum(row["test"]["known_wrong_count"] for row in records)
        unknown = sum(row["test"]["unknown_count"] for row in records)
        summaries.append(
            {
                "method": method,
                "unknown_policy": unknown_policy,
                "risk_target": risk_target,
                "feasible_fold_count": sum(
                    row["calibration_feasible"] for row in records
                ),
                "fold_count": len(records),
                "selected_context_count": selected,
                "total_reference_context_count": total,
                "coverage": selected / total if total else 0.0,
                "verified_correct_count": correct,
                "known_wrong_count": wrong,
                "unknown_count": unknown,
                "heldout_wrong_acceptance_lower": (
                    wrong / selected if selected else None
                ),
                "heldout_wrong_acceptance_upper": (
                    (wrong + unknown) / selected if selected else None
                ),
                "heldout_verified_success_lower": (
                    correct / selected if selected else None
                ),
                "heldout_possible_success_upper": (
                    (correct + unknown) / selected if selected else None
                ),
            }
        )
    return {"summaries": summaries, "fold_details": fold_results}


def write_scores(path, rows, oof):
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "candidate_id",
        "bug_id",
        "context_id",
        "fold",
        "label",
        "compile_outcome",
        "test_outcome",
        "has_conflict",
        "codet5_anchor_patch_cosine",
    ]
    for method in oof:
        fieldnames.extend(
            [
                f"{method}_p_compile",
                f"{method}_p_test_given_compile",
                f"{method}_p_correct_given_test",
                f"{method}_p_end_to_end_correct",
                f"{method}_p_semantic_correct_nonreference",
                f"{method}_p_end_to_end_semantic",
            ]
        )
    output_rows = []
    for index, row in enumerate(rows):
        record = {
            "candidate_id": row["candidate_id"],
            "bug_id": row["bug_id"],
            "context_id": row["context_id"],
            "fold": row["fold"],
            "label": row["label"],
            "compile_outcome": row["compile_outcome"],
            "test_outcome": row["test_outcome"],
            "has_conflict": (
                row["compile_conflict"]
                or row["test_conflict"]
                or row["label_evidence_conflict"]
            ),
            "codet5_anchor_patch_cosine": row["content_features"][0],
        }
        for method in oof:
            p_compile = float(oof[method]["compile"][index])
            p_test = float(oof[method]["test_given_compile"][index])
            p_correct = float(oof[method]["correct_given_test"][index])
            p_semantic = float(
                oof[method]["semantic_correct_nonreference"][index]
            )
            record.update(
                {
                    f"{method}_p_compile": p_compile,
                    f"{method}_p_test_given_compile": p_test,
                    f"{method}_p_correct_given_test": p_correct,
                    f"{method}_p_end_to_end_correct": (
                        p_compile * p_test * p_correct
                    ),
                    f"{method}_p_semantic_correct_nonreference": p_semantic,
                    f"{method}_p_end_to_end_semantic": (
                        p_compile * p_test * p_semantic
                    ),
                }
            )
        output_rows.append(record)
    with path.open("w", encoding="utf-8") as handle:
        for row in output_rows:
            handle.write(json.dumps(row) + "\n")
    csv_path = path.with_suffix(".csv")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)
    return csv_path


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Fit leakage-separated conditional validation models and evaluate "
            "partial-identification accept/defer policies."
        )
    )
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--references", type=Path, default=DEFAULT_REFERENCES)
    parser.add_argument("--splits", type=Path, default=DEFAULT_SPLITS)
    parser.add_argument("--codet5-scores", type=Path, default=DEFAULT_CODET5_SCORES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--iterations", type=int, default=2000)
    parser.add_argument("--seed", default="llm-apr-v2-stage-aware-policy")
    parser.add_argument("--risk-delta", type=float, default=0.05)
    parser.add_argument("--risk-min-support", type=int, default=20)
    return parser.parse_args()


def main():
    args = parse_args()
    rows, source_vocab, prompt_vocab, max_index = load_rows(
        args.candidates, args.codet5_scores
    )
    references = list(iter_jsonl(args.references))
    split_manifest = json.loads(args.splits.read_text(encoding="utf-8"))
    folds = list(split_manifest["metadata"]["fold_names"])
    bug_to_fold = dict(split_manifest["bug_to_fold"])
    all_bugs = {row["bug_id"] for row in rows} | {
        row["bug_id"] for row in references
    }
    added_bug_folds = {}
    for bug_id in sorted(all_bugs - set(bug_to_fold)):
        fold = stable_fold(args.seed, bug_id, folds)
        bug_to_fold[bug_id] = fold
        added_bug_folds[bug_id] = fold
    for row in rows:
        row["fold"] = bug_to_fold[row["bug_id"]]

    matrices, feature_names = build_feature_matrices(
        rows, source_vocab, max_index
    )
    oof, calibration, fold_audit = nested_stage_scores(
        rows, matrices, folds, DEFAULT_C_GRID
    )
    stage_selection_audit = add_stage_selected_scores(
        rows, oof, calibration, fold_audit, folds
    )
    stage_metrics = evaluate_stage_models(rows, oof)
    final_comparisons = {
        "fusion_vs_provenance": paired_bug_bootstrap_auc(
            rows,
            "correct_given_test",
            oof["fusion"]["correct_given_test"],
            oof["provenance"]["correct_given_test"],
            args.iterations,
            f"{args.seed}:final:fusion-v-provenance",
        ),
        "fusion_vs_content": paired_bug_bootstrap_auc(
            rows,
            "correct_given_test",
            oof["fusion"]["correct_given_test"],
            oof["content"]["correct_given_test"],
            args.iterations,
            f"{args.seed}:final:fusion-v-content",
        ),
        "fusion_vs_codet5": paired_bug_bootstrap_auc(
            rows,
            "correct_given_test",
            oof["fusion"]["correct_given_test"],
            oof["codet5"]["correct_given_test"],
            args.iterations,
            f"{args.seed}:final:fusion-v-codet5",
        ),
        "fusion_vs_raw_codet5_similarity": paired_bug_bootstrap_auc(
            rows,
            "correct_given_test",
            oof["fusion"]["correct_given_test"],
            np.asarray(
                [row["content_features"][0] for row in rows],
                dtype=np.float64,
            ),
            args.iterations,
            f"{args.seed}:final:fusion-v-raw-codet5",
        ),
        "semantic_nonreference_fusion_vs_provenance": paired_bug_bootstrap_auc(
            rows,
            "semantic_correct_nonreference",
            oof["fusion"]["semantic_correct_nonreference"],
            oof["provenance"]["semantic_correct_nonreference"],
            args.iterations,
            f"{args.seed}:semantic-nonreference:fusion-v-provenance",
        ),
        "semantic_nonreference_fusion_vs_raw_codet5_similarity": (
            paired_bug_bootstrap_auc(
                rows,
                "semantic_correct_nonreference",
                oof["fusion"]["semantic_correct_nonreference"],
                np.asarray(
                    [row["content_features"][0] for row in rows],
                    dtype=np.float64,
                ),
                args.iterations,
                f"{args.seed}:semantic-nonreference:fusion-v-raw-codet5",
            )
        ),
        "semantic_nonreference_stage_selected_vs_raw_codet5_similarity": (
            paired_bug_bootstrap_auc(
                rows,
                "semantic_correct_nonreference",
                oof["stage_selected"]["semantic_correct_nonreference"],
                np.asarray(
                    [row["content_features"][0] for row in rows],
                    dtype=np.float64,
                ),
                args.iterations,
                (
                    f"{args.seed}:semantic-nonreference:"
                    "stage-selected-v-raw-codet5"
                ),
            )
        ),
    }

    universe = build_context_universe(references, rows, bug_to_fold)
    native_order = np.asarray(
        [-min(source["candidate_index"] for source in row["sources"]) for row in rows],
        dtype=np.float64,
    )
    score_maps = {"native_order": native_order}
    score_maps["codet5_similarity"] = np.asarray(
        [row["content_features"][0] for row in rows], dtype=np.float64
    )
    for method in oof:
        score_maps[f"{method}_factorized"] = (
            oof[method]["compile"]
            * oof[method]["test_given_compile"]
            * oof[method]["correct_given_test"]
        )
    for method in ("provenance", "fusion", "stage_selected"):
        score_maps[f"{method}_reference_excluded_factorized"] = (
            oof[method]["compile"]
            * oof[method]["test_given_compile"]
            * oof[method]["semantic_correct_nonreference"]
        )
    for early_method in ("provenance", "fusion"):
        score_maps[
            f"{early_method}_codet5_semantic_factorized"
        ] = (
            oof[early_method]["compile"]
            * oof[early_method]["test_given_compile"]
            * oof["codet5"]["semantic_correct_nonreference"]
        )
    budget_one = evaluate_budget_one(
        universe,
        rows,
        score_maps,
        args.iterations,
        f"{args.seed}:budget-one",
    )
    risk_control = evaluate_risk_control(
        rows,
        universe,
        folds,
        oof,
        calibration,
        DEFAULT_RISK_TARGETS,
        DEFAULT_COVERAGE_GRID,
        args.risk_delta,
        args.risk_min_support,
    )

    scores_path = args.output.with_name("stage_aware_nested_scores.jsonl")
    scores_csv = write_scores(scores_path, rows, oof)
    endpoint_counts = {
        stage: {
            "eligible_count": len(stage_indices_labels(rows, stage)[0]),
            "positive_count": int(
                np.sum(stage_indices_labels(rows, stage)[1], dtype=np.int64)
            ),
        }
        for stage in STAGES
    }
    expected_counts = {
        "compile": {"eligible_count": 54475, "positive_count": 31267},
        "test_given_compile": {"eligible_count": 31228, "positive_count": 4085},
        "correct_given_test": {"eligible_count": 2846, "positive_count": 1544},
        "semantic_correct_nonreference": {
            "eligible_count": 1541,
            "positive_count": 239,
        },
    }
    checks = {
        "codet5_score_coverage_exact": len(rows) == 55325,
        "reference_universe_count": len(universe) == 863,
        "all_candidate_context_count": sum(
            bool(context["candidate_indices"]) for context in universe.values()
        )
        == 863,
        "endpoint_counts_match_frozen_funnel": endpoint_counts == expected_counts,
        "all_nested_role_bug_sets_disjoint": all(
            row["all_role_bug_sets_disjoint"] for row in fold_audit
        ),
        "reference_fields_absent_from_deployable_features": all(
            "reference" not in name and "human_fix" not in name
            for names in feature_names.values()
            for name in names
        ),
        "all_oof_scores_finite": all(
            np.isfinite(oof[method][stage]).all()
            for method in oof
            for stage in STAGES
        ),
    }
    if not all(checks.values()):
        failures = [name for name, passed in checks.items() if not passed]
        raise AssertionError(f"Stage-aware policy checks failed: {failures}")

    payload = {
        "analysis": "stage_aware_policy_v2",
        "inputs": {
            "candidates": str(args.candidates),
            "candidates_sha256": sha256(args.candidates),
            "references": str(args.references),
            "references_sha256": sha256(args.references),
            "splits": str(args.splits),
            "splits_sha256": sha256(args.splits),
            "codet5_scores": str(args.codet5_scores),
            "codet5_scores_sha256": sha256(args.codet5_scores),
        },
        "counts": {
            "candidate_count": len(rows),
            "reference_context_count": len(universe),
            "source_config_count": len(source_vocab),
            "prompt_strategy_count": len(prompt_vocab),
            "max_candidate_index": max_index,
            "endpoint_counts": endpoint_counts,
        },
        "split_protocol": {
            "folds": folds,
            "roles": (
                "For each outer test fold: one separate calibration fold, one "
                "tuning fold, and two training folds. C is selected on tuning "
                "log loss; the model is refit on training+tuning; risk thresholds "
                "use only calibration; final metrics use only test."
            ),
            "added_bug_fold_assignments": added_bug_folds,
        },
        "feature_manifest": {
            "source_configs": source_vocab,
            "prompt_strategies_observed": prompt_vocab,
            "features": feature_names,
            "forbidden_inputs": [
                "human_fix text",
                "exact_match",
                "ast_match",
                "reference-equivalence status",
                "semantic label",
                "compile/test outcome before its action",
            ],
            "codet5_model_commit": "d9f3a534af4252f04b10cd9f78e05037542d10f6",
        },
        "model": {
            "family": "L2-regularized logistic regression with standardized features",
            "regularization_grid": list(DEFAULT_C_GRID),
            "selection_metric": "nested tuning-fold log loss",
            "factorization": (
                "p(compile) * p(test | compile) * p(correct | test)"
            ),
            "stage_selected_method": (
                "For each outer fold and validation stage, the feature family "
                "with minimum tuning-fold log loss is selected before scoring "
                "the calibration and test folds."
            ),
        },
        "stage_metrics": stage_metrics,
        "final_correctness_paired_bug_bootstrap": final_comparisons,
        "all_context_budget_one": budget_one,
        "risk_control": {
            "definition": (
                "Top scored test-passing candidate per context. Unknown labels are "
                "either pessimistically counted as errors (primary) or dropped "
                "complete-case (bias diagnostic). Candidate thresholds are selected "
                "from a fixed coverage grid with Bonferroni-simultaneous one-sided "
                "Clopper-Pearson upper bounds on a separate calibration fold."
            ),
            "delta": args.risk_delta,
            "minimum_support": args.risk_min_support,
            "risk_targets": list(DEFAULT_RISK_TARGETS),
            "coverage_grid": list(DEFAULT_COVERAGE_GRID),
            **risk_control,
        },
        "fold_audit": fold_audit,
        "stage_feature_selection_audit": stage_selection_audit,
        "integrity_checks": checks,
        "outputs": {
            "nested_scores_jsonl": str(scores_path),
            "nested_scores_jsonl_sha256": sha256(scores_path),
            "nested_scores_csv": str(scores_csv),
            "nested_scores_csv_sha256": sha256(scores_csv),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    summary_csv = args.output.with_suffix(".csv")
    rows_csv = []
    for stage, methods in stage_metrics.items():
        for method, metrics in methods.items():
            rows_csv.append(
                {
                    "section": "stage_metric",
                    "stage_or_target": stage,
                    "method": method,
                    "unknown_policy": "",
                    "count_or_selected": metrics["count"],
                    "positive_or_correct": metrics["positive_count"],
                    "roc_auc_or_coverage": metrics["roc_auc"],
                    "lower": "",
                    "upper": "",
                }
            )
    for row in risk_control["summaries"]:
        rows_csv.append(
            {
                "section": "risk_control",
                "stage_or_target": row["risk_target"],
                "method": row["method"],
                "unknown_policy": row["unknown_policy"],
                "count_or_selected": row["selected_context_count"],
                "positive_or_correct": row["verified_correct_count"],
                "roc_auc_or_coverage": row["coverage"],
                "lower": row["heldout_wrong_acceptance_lower"],
                "upper": row["heldout_wrong_acceptance_upper"],
            }
        )
    with summary_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows_csv[0]))
        writer.writeheader()
        writer.writerows(rows_csv)

    print(
        json.dumps(
            {
                "output": str(args.output),
                "summary_csv": str(summary_csv),
                "scores": str(scores_path),
                "integrity_checks": checks,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
