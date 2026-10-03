import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


DEFAULT_DATASET = (
    Path("llm_apr_dataset")
    / "llm_apr_defects4j_candidates_v1_candidates_hard.jsonl"
)
DEFAULT_OUTPUT = Path("results") / "prioritization_baselines_test.json"
TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z_0-9]*|\d+|[^\sA-Za-z_0-9]")


def stable_hash_float(*parts):
    payload = "\x1f".join(str(part) for part in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return int(digest[:16], 16) / float(0xFFFFFFFFFFFFFFFF)


def stable_context_id(row):
    payload = "\x1f".join([row["bug_id"], row["anchor"], row["human_fix"]])
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"ctx_{digest[:16]}"


def code_tokens(source):
    return set(TOKEN_RE.findall(source or ""))


def jaccard(left, right):
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def source_order_score(row):
    indices = [
        source.get("candidate_index", 10**9)
        for source in row.get("sources", [])
        if source.get("candidate_index") is not None
    ]
    return -min(indices) if indices else -(10**9)


def load_candidate_pools(dataset_path, split, group_by):
    pools = defaultdict(list)
    with dataset_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if split != "all" and row.get("bug_split") != split:
                continue
            row["_anchor_tokens"] = code_tokens(row.get("anchor", ""))
            row["_patch_tokens"] = code_tokens(row.get("patch", ""))
            row["_context_id"] = stable_context_id(row)
            group_key = row["bug_id"] if group_by == "bug" else row["_context_id"]
            pools[group_key].append(row)
    return pools


def score_candidate(row, baseline, seed):
    if baseline == "random":
        return stable_hash_float(seed, row["candidate_id"])
    if baseline == "source_order":
        return source_order_score(row)
    if baseline == "occurrence_count":
        return float(row.get("occurrence_count", 0))
    if baseline == "anchor_token_similarity":
        return jaccard(row["_anchor_tokens"], row["_patch_tokens"])
    if baseline == "anchor_token_distance":
        return 1.0 - jaccard(row["_anchor_tokens"], row["_patch_tokens"])
    raise ValueError(f"Unknown baseline: {baseline}")


def rank_pool(candidates, baseline, seed, external_scores=None):
    scored = []
    for row in candidates:
        if external_scores is not None:
            score = external_scores.get(row["candidate_id"], float("-inf"))
        else:
            score = score_candidate(row, baseline, seed)
        scored.append(
            (
                score,
                stable_hash_float("tie-break", row["candidate_id"]),
                row,
            )
        )
    return [row for _, _, row in sorted(scored, key=lambda item: (item[0], item[1]), reverse=True)]


def evaluate_baseline(pools, baseline, k_values, seed, external_scores=None):
    positive_pool_count = 0
    no_positive_pool_count = 0
    candidate_count = 0
    correct_candidate_count = 0
    reciprocal_ranks = []
    first_correct_ranks = []
    validation_reductions = []
    recall_at_k = Counter()
    pool_sizes = []
    correct_counts = []

    for candidates in pools.values():
        candidate_count += len(candidates)
        correct_count = sum(1 for row in candidates if row.get("label") == "correct")
        correct_candidate_count += correct_count
        if correct_count == 0:
            no_positive_pool_count += 1
            continue

        positive_pool_count += 1
        pool_sizes.append(len(candidates))
        correct_counts.append(correct_count)
        ranked = rank_pool(candidates, baseline, seed, external_scores=external_scores)
        first_rank = next(
            index + 1 for index, row in enumerate(ranked) if row.get("label") == "correct"
        )
        first_correct_ranks.append(first_rank)
        reciprocal_ranks.append(1.0 / first_rank)
        validation_reductions.append((len(candidates) - first_rank) / len(candidates))

        for k in k_values:
            if first_rank <= k:
                recall_at_k[k] += 1

    denominator = max(positive_pool_count, 1)
    return {
        "baseline": baseline,
        "candidate_pools": len(pools),
        "positive_pools": positive_pool_count,
        "no_positive_pools": no_positive_pool_count,
        "candidate_count": candidate_count,
        "correct_candidate_count": correct_candidate_count,
        "mean_pool_size_positive": mean(pool_sizes),
        "mean_correct_candidates_per_positive_pool": mean(correct_counts),
        "mean_first_correct_rank": mean(first_correct_ranks),
        "mrr": mean(reciprocal_ranks),
        "mean_validation_reduction": mean(validation_reductions),
        **{f"recall@{k}": recall_at_k[k] / denominator for k in k_values},
    }


def mean(values):
    return sum(values) / len(values) if values else 0.0


def print_markdown_table(results, k_values):
    columns = [
        "baseline",
        "positive_pools",
        "mean_pool_size_positive",
        "mean_first_correct_rank",
        "mrr",
        "mean_validation_reduction",
        *[f"recall@{k}" for k in k_values],
    ]
    print("| " + " | ".join(columns) + " |")
    print("| " + " | ".join("---" for _ in columns) + " |")
    for result in results:
        values = []
        for column in columns:
            value = result[column]
            if isinstance(value, float):
                values.append(f"{value:.4f}")
            else:
                values.append(str(value))
        print("| " + " | ".join(values) + " |")


def write_outputs(output_path, results, metadata):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"metadata": metadata, "results": results}
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)

    csv_path = output_path.with_suffix(".csv")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)
    return csv_path


def load_external_scores(path):
    scores = {}
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                scores[row["candidate_id"]] = float(row["score"])
        return scores

    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            scores[row["candidate_id"]] = float(row["score"])
    return scores


def parse_args():
    parser = argparse.ArgumentParser(
        description="Evaluate no-training patch prioritization baselines."
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--split", choices=["train", "val", "test", "all"], default="test")
    parser.add_argument("--group-by", choices=["context", "bug"], default="context")
    parser.add_argument("--seed", default="llm-apr-prioritization-v1")
    parser.add_argument("--k", type=int, nargs="+", default=[1, 3, 5, 10])
    parser.add_argument(
        "--baselines",
        nargs="+",
        default=[
            "random",
            "source_order",
            "occurrence_count",
            "anchor_token_similarity",
            "anchor_token_distance",
        ],
    )
    parser.add_argument(
        "--score-file",
        type=Path,
        help="Optional JSONL or CSV file with candidate_id and score columns from a trained model.",
    )
    parser.add_argument("--score-name", default="model_score")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main():
    args = parse_args()
    pools = load_candidate_pools(args.dataset, args.split, args.group_by)
    results = [
        evaluate_baseline(pools, baseline, args.k, args.seed)
        for baseline in args.baselines
    ]
    if args.score_file:
        external_scores = load_external_scores(args.score_file)
        results.append(
            evaluate_baseline(
                pools,
                args.score_name,
                args.k,
                args.seed,
                external_scores=external_scores,
            )
        )
    results = sorted(results, key=lambda row: row["mrr"], reverse=True)
    metadata = {
        "dataset": str(args.dataset),
        "split": args.split,
        "group_by": args.group_by,
        "seed": args.seed,
        "k_values": args.k,
        "baseline_note": "Scores use only pre-validation candidate signals; human fixes are used only for grouping and labels.",
        "score_file": str(args.score_file) if args.score_file else None,
    }

    print(json.dumps(metadata, indent=2))
    print_markdown_table(results, args.k)
    csv_path = write_outputs(args.output, results, metadata)
    print(f"\nWrote {args.output}")
    print(f"Wrote {csv_path}")


if __name__ == "__main__":
    main()
