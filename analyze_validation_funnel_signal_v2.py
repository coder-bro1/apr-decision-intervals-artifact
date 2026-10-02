import argparse
import csv
import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path


DEFAULT_CANDIDATES = (
    Path("llm_apr_dataset")
    / "llm_apr_defects4j_candidates_v2_candidates_all.jsonl"
)
DEFAULT_OCCURRENCES = (
    Path("llm_apr_dataset")
    / "llm_apr_defects4j_candidates_v2_candidate_occurrences_all.jsonl"
)
DEFAULT_OUTPUT = Path("results") / "v2" / "validation_funnel_signal.json"

ENDPOINTS = (
    "compile",
    "test_given_compile",
    "reference_given_test",
    "adjudicated_given_test_nonreference",
    "semantic_correct_given_adjudicated_nonreference",
    "final_correct_given_test_adjudicated",
)

ENDPOINT_DEFINITIONS = {
    "compile": {
        "eligible": "Generated candidate or occurrence with a known compilation outcome.",
        "positive": "Compilation succeeds.",
    },
    "test_given_compile": {
        "eligible": "Compile-passing candidate or occurrence with a known test outcome.",
        "positive": "The available developer test suite passes.",
    },
    "reference_given_test": {
        "eligible": "Test-passing candidate or occurrence.",
        "positive": "Exact or AST equivalence to the developer reference is recorded.",
    },
    "adjudicated_given_test_nonreference": {
        "eligible": "Test-passing candidate without exact/AST reference evidence.",
        "positive": "A semantic correctness label is observed rather than unknown.",
    },
    "semantic_correct_given_adjudicated_nonreference": {
        "eligible": "Adjudicated, test-passing candidate without exact/AST reference evidence.",
        "positive": "The semantic judgment is correct.",
    },
    "final_correct_given_test_adjudicated": {
        "eligible": "Adjudicated test-passing candidate.",
        "positive": "The final candidate label is correct.",
    },
}


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


def evidence_types(row):
    evidence = row.get("annotation_evidence") or {}
    if isinstance(evidence, dict):
        return {key for key, count in evidence.items() if count}
    if isinstance(evidence, str):
        return {evidence}
    raise ValueError(f"Unexpected annotation_evidence type: {type(evidence)!r}")


def exact_or_ast_evidence(row):
    evidence = evidence_types(row)
    return bool({"correct_exact", "correct_ast"} & evidence)


def known_aggregate_outcome(values):
    values = values or {}
    known = {
        key
        for key, count in values.items()
        if count and key in {"true", "false"}
    }
    if known == {"true"}:
        return True
    if known == {"false"}:
        return False
    return None


def minimum_index(row):
    indices = [
        int(source["candidate_index"])
        for source in row.get("sources") or []
        if source.get("candidate_index") is not None
    ]
    return min(indices) if indices else None


def compact_candidate(row):
    return {
        "bug_id": row["bug_id"],
        "label": row["label"],
        "reference_equivalent": exact_or_ast_evidence(row),
        "compile_conflict": bool(row.get("compile_conflict")),
        "test_conflict": bool(row.get("test_conflict")),
        "label_evidence_conflict": bool(row.get("label_evidence_conflict")),
    }


def make_record(row, position, label, source_config=None):
    return {
        "bug_id": row["bug_id"],
        "source_config": source_config,
        "position": int(position),
        "score": -int(position),
        "label": int(bool(label)),
    }


def candidate_endpoint_records(row, retain_conflicts=False):
    position = minimum_index(row)
    if position is None:
        return []

    compile_outcome = (
        bool(row.get("patch_compiles"))
        if retain_conflicts
        else known_aggregate_outcome(row.get("compile_values"))
    )
    test_outcome = (
        bool(row.get("test_passed"))
        if retain_conflicts
        else known_aggregate_outcome(row.get("test_values"))
    )
    reference = exact_or_ast_evidence(row)
    label = row["label"]

    compile_conflict = bool(row.get("compile_conflict"))
    test_conflict = bool(row.get("test_conflict"))
    label_conflict = bool(row.get("label_evidence_conflict"))
    records = []

    if compile_outcome is not None and (retain_conflicts or not compile_conflict):
        records.append(("compile", make_record(row, position, compile_outcome)))

    valid_compile = compile_outcome is True and (retain_conflicts or not compile_conflict)
    if (
        valid_compile
        and test_outcome is not None
        and (retain_conflicts or not test_conflict)
    ):
        records.append(
            ("test_given_compile", make_record(row, position, test_outcome))
        )

    valid_test = (
        valid_compile
        and test_outcome is True
        and (retain_conflicts or not test_conflict)
    )
    valid_later_evidence = retain_conflicts or not label_conflict
    if valid_test and valid_later_evidence:
        records.append(
            ("reference_given_test", make_record(row, position, reference))
        )
        if not reference:
            records.append(
                (
                    "adjudicated_given_test_nonreference",
                    make_record(row, position, label in {"correct", "incorrect"}),
                )
            )
            if label in {"correct", "incorrect"}:
                records.append(
                    (
                        "semantic_correct_given_adjudicated_nonreference",
                        make_record(row, position, label == "correct"),
                    )
                )
        if label in {"correct", "incorrect"}:
            records.append(
                (
                    "final_correct_given_test_adjudicated",
                    make_record(row, position, label == "correct"),
                )
            )
    return records


def occurrence_endpoint_records(row, candidate):
    position = row.get("candidate_index")
    if position is None:
        return []
    source_config = row.get("source_config")
    records = []

    compile_outcome = row.get("patch_compiles")
    test_outcome = row.get("test_passed")
    if isinstance(compile_outcome, bool):
        records.append(
            (
                "compile",
                make_record(row, position, compile_outcome, source_config),
            )
        )

    if compile_outcome is True and isinstance(test_outcome, bool):
        records.append(
            (
                "test_given_compile",
                make_record(row, position, test_outcome, source_config),
            )
        )

    no_stage_conflict = not (
        candidate["compile_conflict"]
        or candidate["test_conflict"]
        or candidate["label_evidence_conflict"]
    )
    if compile_outcome is True and test_outcome is True and no_stage_conflict:
        reference = candidate["reference_equivalent"]
        label = candidate["label"]
        records.append(
            (
                "reference_given_test",
                make_record(row, position, reference, source_config),
            )
        )
        if not reference:
            records.append(
                (
                    "adjudicated_given_test_nonreference",
                    make_record(
                        row,
                        position,
                        label in {"correct", "incorrect"},
                        source_config,
                    ),
                )
            )
            if label in {"correct", "incorrect"}:
                records.append(
                    (
                        "semantic_correct_given_adjudicated_nonreference",
                        make_record(
                            row,
                            position,
                            label == "correct",
                            source_config,
                        ),
                    )
                )
        if label in {"correct", "incorrect"}:
            records.append(
                (
                    "final_correct_given_test_adjudicated",
                    make_record(
                        row,
                        position,
                        label == "correct",
                        source_config,
                    ),
                )
            )
    return records


def auc_from_counts(counts):
    positives = sum(values[1] for values in counts.values())
    negatives = sum(values[0] for values in counts.values())
    if not positives or not negatives:
        return None

    negatives_below = 0
    concordant = 0.0
    for score in sorted(counts):
        negative_count, positive_count = counts[score]
        concordant += positive_count * negatives_below
        concordant += 0.5 * positive_count * negative_count
        negatives_below += negative_count
    return concordant / (positives * negatives)


def auc(records):
    counts = defaultdict(lambda: [0, 0])
    for record in records:
        counts[record["score"]][record["label"]] += 1
    return auc_from_counts(counts)


def percentile(values, quantile):
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def records_by_bug_counts(records, include_source=False):
    grouped = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for record in records:
        key = (
            (record["source_config"], record["score"])
            if include_source
            else record["score"]
        )
        grouped[record["bug_id"]][key][record["label"]] += 1
    return grouped


def weighted_counts(grouped, bug_weights):
    combined = defaultdict(lambda: [0, 0])
    for bug_id, weight in bug_weights.items():
        for score, values in grouped[bug_id].items():
            combined[score][0] += weight * values[0]
            combined[score][1] += weight * values[1]
    return combined


def macro_source_auc_from_counts(counts):
    by_source = defaultdict(dict)
    for (source_config, score), values in counts.items():
        by_source[source_config][score] = values
    values = [
        source_auc
        for source_counts in by_source.values()
        if (source_auc := auc_from_counts(source_counts)) is not None
    ]
    return sum(values) / len(values) if values else None


def cluster_bootstrap(records, iterations, seed, include_macro_source=False):
    by_bug = records_by_bug_counts(records)
    by_bug_source = (
        records_by_bug_counts(records, include_source=True)
        if include_macro_source
        else None
    )
    bugs = sorted(by_bug)
    rng = random.Random(seed)
    auc_values = []
    macro_values = []
    for _ in range(iterations):
        weights = Counter(rng.choices(bugs, k=len(bugs)))
        sampled_auc = auc_from_counts(weighted_counts(by_bug, weights))
        if sampled_auc is not None:
            auc_values.append(sampled_auc)
        if include_macro_source:
            sampled_macro = macro_source_auc_from_counts(
                weighted_counts(by_bug_source, weights)
            )
            if sampled_macro is not None:
                macro_values.append(sampled_macro)
    result = {
        "source_order_auc": {
            "low": percentile(auc_values, 0.025),
            "high": percentile(auc_values, 0.975),
            "replicates": len(auc_values),
        }
    }
    if include_macro_source:
        result["source_config_macro_auc"] = {
            "low": percentile(macro_values, 0.025),
            "high": percentile(macro_values, 0.975),
            "replicates": len(macro_values),
        }
    return result


def rank_profile(records):
    counts = defaultdict(lambda: [0, 0])
    for record in records:
        counts[record["position"]][record["label"]] += 1
    return [
        {
            "candidate_index": position,
            "eligible_count": negative + positive,
            "positive_count": positive,
            "positive_rate": positive / (negative + positive),
        }
        for position, (negative, positive) in sorted(counts.items())
    ]


def per_source_metrics(records):
    grouped = defaultdict(list)
    for record in records:
        if record["source_config"] is not None:
            grouped[record["source_config"]].append(record)
    result = []
    for source_config, source_records in sorted(grouped.items()):
        positives = sum(record["label"] for record in source_records)
        result.append(
            {
                "source_config": source_config,
                "eligible_count": len(source_records),
                "positive_count": positives,
                "positive_rate": positives / len(source_records),
                "source_order_auc": auc(source_records),
            }
        )
    return result


def summarize_endpoint(records, iterations, seed, include_macro_source=False):
    positives = sum(record["label"] for record in records)
    source_auc = auc(records)
    summary = {
        "eligible_count": len(records),
        "positive_count": positives,
        "negative_count": len(records) - positives,
        "positive_rate": positives / len(records) if records else None,
        "source_order_auc": source_auc,
        "source_order_auc_minus_random": (
            source_auc - 0.5 if source_auc is not None else None
        ),
        "bug_count": len({record["bug_id"] for record in records}),
        "rank_profile": rank_profile(records),
    }
    if include_macro_source:
        source_rows = per_source_metrics(records)
        valid = [
            row["source_order_auc"]
            for row in source_rows
            if row["source_order_auc"] is not None
        ]
        summary["source_config_macro_auc"] = (
            sum(valid) / len(valid) if valid else None
        )
        summary["source_configs_with_defined_auc"] = len(valid)
        summary["per_source_config"] = source_rows
    if records and positives and positives < len(records):
        summary["bug_cluster_bootstrap_95ci"] = cluster_bootstrap(
            records,
            iterations,
            seed,
            include_macro_source=include_macro_source,
        )
    else:
        summary["bug_cluster_bootstrap_95ci"] = None
    return summary


def collect(candidate_path, occurrence_path):
    candidate_views = {
        "candidate_primary_no_conflicts": defaultdict(list),
        "candidate_conflict_retaining_ever_success": defaultdict(list),
    }
    candidate_map = {}
    candidate_count = 0
    duplicate_candidate_ids = 0

    for row in iter_jsonl(candidate_path):
        candidate_count += 1
        candidate_id = row["candidate_id"]
        if candidate_id in candidate_map:
            duplicate_candidate_ids += 1
        candidate_map[candidate_id] = compact_candidate(row)
        for endpoint, record in candidate_endpoint_records(row, retain_conflicts=False):
            candidate_views["candidate_primary_no_conflicts"][endpoint].append(record)
        for endpoint, record in candidate_endpoint_records(row, retain_conflicts=True):
            candidate_views["candidate_conflict_retaining_ever_success"][endpoint].append(
                record
            )

    occurrence_view = defaultdict(list)
    occurrence_count = 0
    missing_candidate_ids = Counter()
    for row in iter_jsonl(occurrence_path):
        occurrence_count += 1
        candidate = candidate_map.get(row["candidate_id"])
        if candidate is None:
            missing_candidate_ids[row["candidate_id"]] += 1
            continue
        for endpoint, record in occurrence_endpoint_records(row, candidate):
            occurrence_view[endpoint].append(record)

    return {
        "candidate_views": candidate_views,
        "occurrence_view": occurrence_view,
        "candidate_count": candidate_count,
        "occurrence_count": occurrence_count,
        "candidate_map_count": len(candidate_map),
        "duplicate_candidate_ids": duplicate_candidate_ids,
        "missing_occurrence_candidate_ids": dict(missing_candidate_ids),
    }


def validate_collected(collected):
    candidate_primary = collected["candidate_views"][
        "candidate_primary_no_conflicts"
    ]
    checks = {
        "candidate_ids_unique": collected["duplicate_candidate_ids"] == 0,
        "all_occurrences_reference_candidates": not collected[
            "missing_occurrence_candidate_ids"
        ],
        "candidate_map_complete": (
            collected["candidate_count"] == collected["candidate_map_count"]
        ),
        "candidate_endpoint_names_valid": all(
            endpoint in ENDPOINTS
            for view in collected["candidate_views"].values()
            for endpoint in view
        ),
        "occurrence_endpoint_names_valid": all(
            endpoint in ENDPOINTS for endpoint in collected["occurrence_view"]
        ),
        "candidate_test_pool_not_larger_than_compile_successes": (
            len(candidate_primary["test_given_compile"])
            <= sum(row["label"] for row in candidate_primary["compile"])
        ),
        "candidate_reference_pool_not_larger_than_test_successes": (
            len(candidate_primary["reference_given_test"])
            <= sum(row["label"] for row in candidate_primary["test_given_compile"])
        ),
        "semantic_endpoint_is_binary": all(
            row["label"] in {0, 1}
            for row in candidate_primary[
                "semantic_correct_given_adjudicated_nonreference"
            ]
        ),
    }
    if not all(checks.values()):
        failures = [name for name, passed in checks.items() if not passed]
        raise ValueError(f"Validation-funnel integrity checks failed: {failures}")
    return checks


def flatten_csv(payload):
    rows = []
    for view_name, endpoints in payload["views"].items():
        for endpoint, metrics in endpoints.items():
            interval = metrics.get("bug_cluster_bootstrap_95ci") or {}
            auc_interval = interval.get("source_order_auc") or {}
            macro_interval = interval.get("source_config_macro_auc") or {}
            rows.append(
                {
                    "view": view_name,
                    "endpoint": endpoint,
                    "eligible_count": metrics["eligible_count"],
                    "positive_count": metrics["positive_count"],
                    "positive_rate": metrics["positive_rate"],
                    "source_order_auc": metrics["source_order_auc"],
                    "source_order_auc_ci_low": auc_interval.get("low"),
                    "source_order_auc_ci_high": auc_interval.get("high"),
                    "source_config_macro_auc": metrics.get(
                        "source_config_macro_auc"
                    ),
                    "source_config_macro_auc_ci_low": macro_interval.get("low"),
                    "source_config_macro_auc_ci_high": macro_interval.get("high"),
                }
            )
    return rows


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Decompose native generation-order signal across the APR validation "
            "funnel without converting unknown semantic labels to negatives."
        )
    )
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--occurrences", type=Path, default=DEFAULT_OCCURRENCES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--iterations", type=int, default=2000)
    parser.add_argument(
        "--bootstrap-seed", default="llm-apr-v2-validation-funnel-signal"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    collected = collect(args.candidates, args.occurrences)
    checks = validate_collected(collected)

    views = {}
    for view_name, endpoints in collected["candidate_views"].items():
        views[view_name] = {
            endpoint: summarize_endpoint(
                endpoints.get(endpoint, []),
                args.iterations,
                f"{args.bootstrap_seed}:{view_name}:{endpoint}",
            )
            for endpoint in ENDPOINTS
        }
    views["occurrence_operational_no_candidate_conflicts"] = {
        endpoint: summarize_endpoint(
            collected["occurrence_view"].get(endpoint, []),
            args.iterations,
            f"{args.bootstrap_seed}:occurrence:{endpoint}",
            include_macro_source=True,
        )
        for endpoint in ENDPOINTS
    }

    payload = {
        "analysis": "validation_funnel_signal_v2",
        "inputs": {
            "candidates": str(args.candidates),
            "candidates_sha256": sha256(args.candidates),
            "occurrences": str(args.occurrences),
            "occurrences_sha256": sha256(args.occurrences),
        },
        "counts": {
            "deduplicated_candidates": collected["candidate_count"],
            "generation_occurrences": collected["occurrence_count"],
        },
        "methodology": {
            "source_order_score": (
                "Negative zero-based candidate_index; earlier generations receive "
                "larger scores. Candidate views use the minimum index across sources."
            ),
            "auc": (
                "Exact pairwise AUC with 0.5 credit for equal generation positions."
            ),
            "uncertainty": (
                f"{args.iterations} nonparametric bootstrap replicates clustered "
                "by Defects4J bug."
            ),
            "source_config_macro_auc": (
                "Unweighted mean of within-source-config AUCs having both classes; "
                "this blocks generator-mixture prevalence from creating the result."
            ),
            "candidate_primary": (
                "Excludes the conflict flag relevant to each stage. Later semantic "
                "stages exclude compile, test, and label-evidence conflicts."
            ),
            "candidate_sensitivity": (
                "Retains conflicts and uses the dataset's any-success aggregation. "
                "This is a sensitivity view, not the primary operational estimand."
            ),
            "unknown_policy": (
                "Unknown test-passing semantic labels enter the adjudication endpoint "
                "as unobserved; they are excluded from supervised semantic/final "
                "correctness endpoints and never relabeled incorrect."
            ),
        },
        "endpoint_definitions": ENDPOINT_DEFINITIONS,
        "integrity_checks": checks,
        "views": views,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    csv_path = args.output.with_suffix(".csv")
    csv_rows = flatten_csv(payload)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(csv_rows[0]))
        writer.writeheader()
        writer.writerows(csv_rows)

    print(
        json.dumps(
            {
                "output": str(args.output),
                "csv": str(csv_path),
                "candidate_count": collected["candidate_count"],
                "occurrence_count": collected["occurrence_count"],
                "integrity_checks": checks,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
