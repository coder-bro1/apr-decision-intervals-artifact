import sys as _sys  # release layout: shared helper modules live in lib/
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / "lib").is_dir()) / "lib"))
import argparse
import csv
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from evaluate_prioritization import DEFAULT_DATASET, jaccard, stable_context_id


DEFAULT_SPLITS = (
    Path("llm_apr_dataset")
    / "llm_apr_defects4j_candidates_v1_bug_kfold_splits.json"
)
DEFAULT_OUTPUT_DIR = Path("results") / "stream_calibration"
TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z_0-9]*|\d+|[^\sA-Za-z_0-9]")


METHODS = [
    "global_index_calibrated",
    "source_prior_calibrated",
    "stream_index_max",
    "stream_index_mean",
    "stream_index_noisy_or",
    "stream_calibrated_fusion",
]


def read_jsonl(path):
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def load_manifest(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def code_tokens(source):
    return set(TOKEN_RE.findall(source or ""))


def token_count(source):
    return len(TOKEN_RE.findall(source or ""))


def mean_std(values):
    values = list(values)
    if not values:
        return 0.0, 1.0
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    std = math.sqrt(variance)
    return mean, std if std > 1e-12 else 1.0


def safe_logit(value):
    value = min(max(value, 1e-6), 1.0 - 1e-6)
    return math.log(value / (1.0 - value))


def smooth_rate(correct, total, prior, strength):
    if total <= 0:
        return prior
    return (correct + strength * prior) / (total + strength)


def index_bin(index, exact_until=8):
    if index is None:
        return "missing"
    index = int(index)
    return str(index) if index <= exact_until else f"{exact_until + 1}+"


def source_occurrences(row):
    for source in row.get("sources", []):
        source_config = source.get("source_config")
        candidate_index = source.get("candidate_index")
        if source_config is None or candidate_index is None:
            continue
        yield {
            "source_config": source_config,
            "prompt_strategy": source.get("prompt_strategy"),
            "candidate_index": int(candidate_index),
            "index_bin": index_bin(candidate_index),
        }


def load_rows(dataset_path, bug_to_fold):
    rows = []
    source_configs = set()
    prompt_strategies = set()
    for row in read_jsonl(dataset_path):
        fold = bug_to_fold.get(row["bug_id"])
        if fold is None:
            continue
        item = dict(row)
        item["_fold"] = fold
        item["_context_id"] = stable_context_id(row)
        item["_anchor_tokens"] = code_tokens(row.get("anchor", ""))
        item["_patch_tokens"] = code_tokens(row.get("patch", ""))
        item["_anchor_token_count"] = len(item["_anchor_tokens"])
        item["_patch_token_count"] = len(item["_patch_tokens"])
        item["_patch_lexical_tokens"] = token_count(row.get("patch", ""))
        occurrences = list(source_occurrences(row))
        item["_stream_occurrences"] = occurrences
        item["_source_configs"] = sorted({occ["source_config"] for occ in occurrences})
        item["_prompt_strategies"] = sorted(
            {occ["prompt_strategy"] for occ in occurrences if occ["prompt_strategy"]}
        )
        source_configs.update(item["_source_configs"])
        prompt_strategies.update(item["_prompt_strategies"])
        rows.append(item)
    return rows, sorted(source_configs), sorted(prompt_strategies)


class StreamCalibrator:
    def __init__(self, index_strength=50.0, source_strength=50.0, stream_strength=35.0):
        self.index_strength = index_strength
        self.source_strength = source_strength
        self.stream_strength = stream_strength
        self.global_prior = 0.0
        self.index_rates = {}
        self.source_rates = {}
        self.stream_rates = {}
        self.index_counts = {}
        self.source_counts = {}
        self.stream_counts = {}

    def fit(self, rows):
        global_total = 0
        global_correct = 0
        index_counts = defaultdict(lambda: [0, 0])
        source_counts = defaultdict(lambda: [0, 0])
        stream_counts = defaultdict(lambda: [0, 0])

        for row in rows:
            label = 1 if row.get("label") == "correct" else 0
            for occ in row["_stream_occurrences"]:
                global_total += 1
                global_correct += label
                index_counts[occ["index_bin"]][0] += 1
                index_counts[occ["index_bin"]][1] += label
                source_counts[occ["source_config"]][0] += 1
                source_counts[occ["source_config"]][1] += label
                stream_counts[(occ["source_config"], occ["index_bin"])][0] += 1
                stream_counts[(occ["source_config"], occ["index_bin"])][1] += label

        self.global_prior = (global_correct + 0.5) / (global_total + 1.0)
        self.index_counts = {
            key: {"total": total, "correct": correct}
            for key, (total, correct) in index_counts.items()
        }
        self.source_counts = {
            key: {"total": total, "correct": correct}
            for key, (total, correct) in source_counts.items()
        }
        self.stream_counts = {
            f"{source}|{bin_label}": {"total": total, "correct": correct}
            for (source, bin_label), (total, correct) in stream_counts.items()
        }

        self.index_rates = {
            key: smooth_rate(correct, total, self.global_prior, self.index_strength)
            for key, (total, correct) in index_counts.items()
        }
        self.source_rates = {
            key: smooth_rate(correct, total, self.global_prior, self.source_strength)
            for key, (total, correct) in source_counts.items()
        }
        for (source, bin_label), (total, correct) in stream_counts.items():
            source_prior = self.source_prob(source)
            index_prior = self.index_prob(bin_label)
            hierarchical_prior = 0.5 * source_prior + 0.5 * index_prior
            self.stream_rates[(source, bin_label)] = smooth_rate(
                correct,
                total,
                hierarchical_prior,
                self.stream_strength,
            )
        return self

    def index_prob(self, bin_label):
        return self.index_rates.get(bin_label, self.global_prior)

    def source_prob(self, source_config):
        return self.source_rates.get(source_config, self.global_prior)

    def stream_prob(self, source_config, bin_label):
        if (source_config, bin_label) in self.stream_rates:
            return self.stream_rates[(source_config, bin_label)]
        return 0.5 * self.source_prob(source_config) + 0.5 * self.index_prob(bin_label)

    def candidate_probabilities(self, row):
        occurrences = row["_stream_occurrences"]
        if not occurrences:
            return {
                "global_index_values": [self.global_prior],
                "source_prior_values": [self.global_prior],
                "stream_values": [self.global_prior],
            }
        return {
            "global_index_values": [
                self.index_prob(occ["index_bin"]) for occ in occurrences
            ],
            "source_prior_values": [
                self.source_prob(occ["source_config"]) for occ in occurrences
            ],
            "stream_values": [
                self.stream_prob(occ["source_config"], occ["index_bin"])
                for occ in occurrences
            ],
        }

    def metadata(self):
        return {
            "global_prior": self.global_prior,
            "index_rates": self.index_rates,
            "source_rates": self.source_rates,
            "stream_rates": {
                f"{source}|{bin_label}": value
                for (source, bin_label), value in self.stream_rates.items()
            },
            "index_counts": self.index_counts,
            "source_counts": self.source_counts,
            "stream_counts": self.stream_counts,
            "smoothing": {
                "index_strength": self.index_strength,
                "source_strength": self.source_strength,
                "stream_strength": self.stream_strength,
            },
        }


def noisy_or(values):
    product = 1.0
    for value in values:
        product *= 1.0 - min(max(value, 0.0), 1.0)
    return 1.0 - product


def raw_calibrated_features(row, calibrator):
    probs = calibrator.candidate_probabilities(row)
    global_values = probs["global_index_values"]
    source_values = probs["source_prior_values"]
    stream_values = probs["stream_values"]
    source_indices = [
        occ["candidate_index"] for occ in row["_stream_occurrences"]
    ] or [10**9]
    min_index = min(source_indices)
    anchor_count = row["_anchor_token_count"]
    patch_count = row["_patch_token_count"]
    lexical_similarity = jaccard(row["_anchor_tokens"], row["_patch_tokens"])
    occurrence_count = float(row.get("occurrence_count", 0))
    source_count = float(len(row["_source_configs"]))
    prompt_count = float(len(row["_prompt_strategies"]))

    raw = {
        "global_index_max": max(global_values),
        "global_index_mean": sum(global_values) / len(global_values),
        "source_prior_max": max(source_values),
        "source_prior_mean": sum(source_values) / len(source_values),
        "stream_index_max": max(stream_values),
        "stream_index_mean": sum(stream_values) / len(stream_values),
        "stream_index_noisy_or": noisy_or(stream_values),
        "stream_index_max_logit": safe_logit(max(stream_values)),
        "min_candidate_index": float(min_index if min_index < 10**9 else 99),
        "reciprocal_min_index": 1.0 / (1.0 + min_index) if min_index < 10**9 else 0.0,
        "occurrence_count": occurrence_count,
        "log_occurrence_count": math.log1p(occurrence_count),
        "source_config_count": source_count,
        "prompt_strategy_count": prompt_count,
        "anchor_patch_similarity": lexical_similarity,
        "anchor_patch_distance": 1.0 - lexical_similarity,
        "log_patch_token_count": math.log1p(patch_count),
        "log_abs_token_delta": math.log1p(abs(patch_count - anchor_count)),
        "patch_anchor_token_ratio": patch_count / max(anchor_count, 1),
    }
    return raw


def add_context_z_features(items):
    by_context = defaultdict(list)
    for item in items:
        by_context[item["row"]["_context_id"]].append(item)

    z_features = [
        "global_index_max",
        "source_prior_max",
        "stream_index_max",
        "stream_index_mean",
        "stream_index_noisy_or",
        "min_candidate_index",
        "reciprocal_min_index",
        "occurrence_count",
        "anchor_patch_similarity",
        "anchor_patch_distance",
        "log_patch_token_count",
        "log_abs_token_delta",
    ]

    for context_items in by_context.values():
        for feature in z_features:
            mean, std = mean_std(item["raw"][feature] for item in context_items)
            for item in context_items:
                item["raw"][f"context_z_{feature}"] = (
                    item["raw"][feature] - mean
                ) / std


def one_hot_features(row, source_configs, prompt_strategies):
    features = {}
    sources = set(row["_source_configs"])
    prompts = set(row["_prompt_strategies"])
    for source in source_configs:
        features[f"has_source_config={source}"] = 1.0 if source in sources else 0.0
    for prompt in prompt_strategies:
        features[f"has_prompt_strategy={prompt}"] = 1.0 if prompt in prompts else 0.0
    return features


def build_fold_features(rows, calibrator, source_configs, prompt_strategies):
    items = []
    for row in rows:
        raw = raw_calibrated_features(row, calibrator)
        raw.update(one_hot_features(row, source_configs, prompt_strategies))
        items.append({"row": row, "raw": raw})
    add_context_z_features(items)

    feature_names = [
        "global_index_max",
        "global_index_mean",
        "source_prior_max",
        "source_prior_mean",
        "stream_index_max",
        "stream_index_mean",
        "stream_index_noisy_or",
        "stream_index_max_logit",
        "min_candidate_index",
        "reciprocal_min_index",
        "occurrence_count",
        "log_occurrence_count",
        "source_config_count",
        "prompt_strategy_count",
        "anchor_patch_similarity",
        "anchor_patch_distance",
        "log_patch_token_count",
        "log_abs_token_delta",
        "patch_anchor_token_ratio",
        "context_z_global_index_max",
        "context_z_source_prior_max",
        "context_z_stream_index_max",
        "context_z_stream_index_mean",
        "context_z_stream_index_noisy_or",
        "context_z_min_candidate_index",
        "context_z_reciprocal_min_index",
        "context_z_occurrence_count",
        "context_z_anchor_patch_similarity",
        "context_z_anchor_patch_distance",
        "context_z_log_patch_token_count",
        "context_z_log_abs_token_delta",
        *[f"has_source_config={source}" for source in source_configs],
        *[f"has_prompt_strategy={prompt}" for prompt in prompt_strategies],
    ]

    for item in items:
        item["features"] = [float(item["raw"].get(name, 0.0)) for name in feature_names]
    return items, feature_names


def train_fusion(train_items, c, max_iter):
    x_train = np.asarray([item["features"] for item in train_items], dtype=np.float32)
    y_train = np.asarray(
        [1 if item["row"].get("label") == "correct" else 0 for item in train_items],
        dtype=np.int64,
    )
    pipeline = Pipeline(
        steps=[
            ("scale", StandardScaler()),
            (
                "logreg",
                LogisticRegression(
                    C=c,
                    class_weight="balanced",
                    max_iter=max_iter,
                    solver="lbfgs",
                ),
            ),
        ]
    )
    pipeline.fit(x_train, y_train)
    return pipeline, int(y_train.sum())


def score_fusion(model, score_items):
    x_score = np.asarray([item["features"] for item in score_items], dtype=np.float32)
    return model.predict_proba(x_score)[:, 1]


def fit_and_score(rows, fold_names, source_configs, prompt_strategies, c, max_iter):
    method_scores = {method: [] for method in METHODS}
    fold_metadata = {}
    feature_names = None

    for heldout_fold in fold_names:
        train_rows = [row for row in rows if row["_fold"] != heldout_fold]
        score_rows = [row for row in rows if row["_fold"] == heldout_fold]
        calibrator = StreamCalibrator().fit(train_rows)
        train_items, feature_names = build_fold_features(
            train_rows,
            calibrator,
            source_configs,
            prompt_strategies,
        )
        score_items, _ = build_fold_features(
            score_rows,
            calibrator,
            source_configs,
            prompt_strategies,
        )
        model, positive_train_rows = train_fusion(train_items, c, max_iter)
        fusion_scores = score_fusion(model, score_items)

        coefficients = model.named_steps["logreg"].coef_[0]
        ranked_coefficients = sorted(
            zip(feature_names, coefficients),
            key=lambda item: abs(item[1]),
            reverse=True,
        )

        for item, fusion_score in zip(score_items, fusion_scores):
            row = item["row"]
            raw = item["raw"]
            candidate_id = row["candidate_id"]
            base = {"candidate_id": candidate_id, "heldout_fold": heldout_fold}
            method_scores["global_index_calibrated"].append(
                {**base, "score": raw["global_index_max"]}
            )
            method_scores["source_prior_calibrated"].append(
                {**base, "score": raw["source_prior_max"]}
            )
            method_scores["stream_index_max"].append(
                {**base, "score": raw["stream_index_max"]}
            )
            method_scores["stream_index_mean"].append(
                {**base, "score": raw["stream_index_mean"]}
            )
            method_scores["stream_index_noisy_or"].append(
                {**base, "score": raw["stream_index_noisy_or"]}
            )
            method_scores["stream_calibrated_fusion"].append(
                {**base, "score": float(fusion_score)}
            )

        fold_metadata[heldout_fold] = {
            "train_rows": len(train_rows),
            "score_rows": len(score_rows),
            "positive_train_rows": positive_train_rows,
            "calibrator": calibrator.metadata(),
            "top_fusion_coefficients": [
                {"feature": name, "coefficient": float(coef)}
                for name, coef in ranked_coefficients[:30]
            ],
        }

    return method_scores, feature_names, fold_metadata


def write_method_scores(output_dir, method_scores):
    output_paths = {}
    output_dir.mkdir(parents=True, exist_ok=True)
    for method, rows in method_scores.items():
        jsonl_path = output_dir / f"{method}_bug_kfold_oof_scores.jsonl"
        csv_path = output_dir / f"{method}_bug_kfold_oof_scores.csv"
        with jsonl_path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(
                    json.dumps(
                        {"candidate_id": row["candidate_id"], "score": row["score"]}
                    )
                    + "\n"
                )
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["candidate_id", "score", "heldout_fold"],
            )
            writer.writeheader()
            writer.writerows(rows)
        output_paths[method] = {"jsonl": str(jsonl_path), "csv": str(csv_path)}
    return output_paths


def main():
    parser = argparse.ArgumentParser(
        description="Fit stream-calibrated source-order rankers with bug-level OOF scoring."
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--splits", type=Path, default=DEFAULT_SPLITS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--c", type=float, default=1.0)
    parser.add_argument("--max-iter", type=int, default=2000)
    args = parser.parse_args()

    manifest = load_manifest(args.splits)
    rows, source_configs, prompt_strategies = load_rows(
        args.dataset,
        manifest["bug_to_fold"],
    )
    fold_names = sorted(manifest["folds"])
    method_scores, feature_names, fold_metadata = fit_and_score(
        rows,
        fold_names,
        source_configs,
        prompt_strategies,
        c=args.c,
        max_iter=args.max_iter,
    )
    output_paths = write_method_scores(args.output_dir, method_scores)

    metadata = {
        "dataset": str(args.dataset),
        "splits": str(args.splits),
        "output_dir": str(args.output_dir),
        "row_count": len(rows),
        "methods": METHODS,
        "source_configs": source_configs,
        "prompt_strategies": prompt_strategies,
        "feature_names": feature_names,
        "score_files": output_paths,
        "fold_metadata": fold_metadata,
        "notes": [
            "All scores are generated out-of-fold by bug_id.",
            "Calibrated methods use only pre-validation provenance/order features plus static lexical features for the fusion row.",
            "No test_passed, patch_compiles, or manual labels are used at scoring time.",
        ],
    }
    metadata_path = args.output_dir / "stream_calibrated_rankers_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "row_count": len(rows),
                "folds": fold_names,
                "methods": METHODS,
                "score_files": output_paths,
                "metadata": str(metadata_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
