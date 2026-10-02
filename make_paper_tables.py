import argparse
import csv
import hashlib
import io
import json
import math
from collections import Counter
from pathlib import Path


VERSION = "v3.2"
DEFAULT_TABLES = Path("results/v2/paper_tables.md")
DEFAULT_CSV = Path("results/v2/paper_tables.csv")
DEFAULT_CLAIMS_JSON = Path("results/v2/paper_claims_and_threats.json")
DEFAULT_CLAIMS_MD = Path("PAPER_CLAIMS_AND_THREATS.md")
DEFAULT_PACKET = Path("docs/reviews/COAUTHOR_REVIEW_PACKET.md")
DEFAULT_MANIFEST = Path("results/v2/paper_artifact_manifest.json")

INPUTS = {
    "dataset_audit": Path(
        "llm_apr_dataset/llm_apr_defects4j_candidates_v2_audit_summary.json"
    ),
    "plausible_audit": Path(
        "llm_apr_dataset/llm_apr_defects4j_candidates_v2_plausible_apca_audit_summary.json"
    ),
    "baselines_context": Path("results/v2/tie_aware_baselines_context.json"),
    "stream_primary": Path("results/v2/nested_stream_calibration_eb.json"),
    "stream_no_conflicts": Path(
        "results/v2/nested_stream_calibration_eb_no_conflicts.json"
    ),
    "source_order_ablation": Path(
        "results/v2/source_order_position_ablation.json"
    ),
    "memorization_lineage_gate": Path(
        "results/v2/memorization_lineage_gate.json"
    ),
    "validation_funnel_signal": Path(
        "results/v2/validation_funnel_signal.json"
    ),
    "stage_aware_policy": Path(
        "results/v2/stage_aware_policy.json"
    ),
    "adaptive_validation_scheduler": Path(
        "results/v2/adaptive_validation_scheduler.json"
    ),
    "outcome_conditioned_stream_health": Path(
        "results/v2/outcome_conditioned_stream_health.json"
    ),
    "practical_pod_common_split": Path(
        "results/v2/practical_pod_common_split.json"
    ),
    "prevarank_llm": Path(
        "results/v2/prevarank_llm_evaluation.json"
    ),
    "prevarank_domain_shift": Path(
        "results/v2/prevarank_domain_shift_mixed.json"
    ),
    "prevarank_input_order": Path(
        "results/v2/prevarank_input_order_sensitivity.json"
    ),
    "prevarank_reproduction": Path(
        "external_artifacts/prevarank/reproduction/output/"
        "full_java21_20260718/reproduction_audit.json"
    ),
    "shift_aware_safe_scheduler": Path(
        "results/v2/shift_aware_safe_scheduler.json"
    ),
    "repairbench_import_audit": Path(
        "llm_apr_dataset/external/repairbench_gitbugjava_2025_v1/"
        "repairbench_gitbugjava_v1_audit_summary.json"
    ),
    "repairbench_campaign_integrity": Path(
        "results/v2/repairbench_campaign_integrity.json"
    ),
    "repairbench_external_campaign": Path(
        "results/v2/repairbench_external_campaign.json"
    ),
    "repairbench_semantic_review_audit": Path(
        "results/v2/repairbench_semantic_review/"
        "semantic_review_packet_audit.json"
    ),
    "external_transfer": Path("results/v2/external_transfer_eb.json"),
    "budget_success": Path("results/v2/budget_success_v2.json"),
    "plausible_apca": Path("results/v2/plausible_apca_evaluation.json"),
    "plausible_apca_no_conflicts": Path(
        "results/v2/plausible_apca_evaluation_no_conflicts.json"
    ),
    "unixcoder_audit": Path(
        "results/v2/plausible_apca_unixcoder_nested_scores.metadata.json"
    ),
}

AUXILIARY_INPUTS = {
    "plausible_labeled_candidates": Path(
        "llm_apr_dataset/llm_apr_defects4j_candidates_v2_candidates_plausible_labeled.jsonl"
    ),
    "plausible_unknown_candidates": Path(
        "llm_apr_dataset/llm_apr_defects4j_candidates_v2_candidates_plausible_unknown.jsonl"
    ),
    "prevarank_evaluation_ledger": Path(
        "results/v2/prevarank_llm_evaluation_ledger.jsonl"
    ),
    "prevarank_mixed_evaluation_ledger": Path(
        "results/v2/prevarank_llm_mixed_evaluation_ledger.jsonl"
    ),
    "prevarank_preparation_manifest": Path(
        "results/v2/prevarank_llm/canonical_v4/preparation_manifest.json"
    ),
    "prevarank_mixed_verification": Path(
        "results/v2/prevarank_llm/canonical_v4/"
        "mixed_verified_run_summary.json"
    ),
    "prevarank_stream_verification": Path(
        "results/v2/prevarank_llm/canonical_v4/"
        "stream_verified_run_summary.json"
    ),
    "prevarank_stable_hash_evaluation": Path(
        "results/v2/prevarank_llm_stable_hash_evaluation.json"
    ),
    "prevarank_stable_hash_ledger": Path(
        "results/v2/prevarank_llm_stable_hash_evaluation_ledger.jsonl"
    ),
    "prevarank_stable_hash_manifest": Path(
        "results/v2/prevarank_llm/stable_hash_v1/preparation_manifest.json"
    ),
    "prevarank_stable_hash_verification": Path(
        "results/v2/prevarank_llm/stable_hash_v1/"
        "mixed_verified_run_summary.json"
    ),
    "shift_aware_action_ledger": Path(
        "results/v2/shift_aware_safe_scheduler_actions.jsonl"
    ),
    "shift_aware_summary_csv": Path(
        "results/v2/shift_aware_safe_scheduler.csv"
    ),
    "repairbench_candidates": Path(
        "llm_apr_dataset/external/repairbench_gitbugjava_2025_v1/"
        "repairbench_gitbugjava_v1_candidates_all.jsonl"
    ),
    "repairbench_codet5_scores": Path(
        "results/v2/repairbench_zero_shot_scores/"
        "Salesforce_codet5p-110m-embedding_all.jsonl"
    ),
    "repairbench_codet5_metadata": Path(
        "results/v2/repairbench_zero_shot_scores/"
        "Salesforce_codet5p-110m-embedding_all.metadata.json"
    ),
    "repairbench_score_ledger": Path(
        "results/v2/repairbench_external_campaign_scores.jsonl"
    ),
    "repairbench_score_csv": Path(
        "results/v2/repairbench_external_campaign_scores.csv"
    ),
    "repairbench_safe_actions": Path(
        "results/v2/repairbench_safe_gate_actions.jsonl"
    ),
    "repairbench_blinded_review_items": Path(
        "results/v2/repairbench_semantic_review/blinded_review_items.jsonl"
    ),
    "repairbench_private_review_ledger": Path(
        "results/v2/repairbench_semantic_review/"
        "private_selection_ledger.jsonl"
    ),
}

SUPPORTING_ARTIFACTS = {
    "source_config_provenance": Path("SOURCE_CONFIG_PROVENANCE.md"),
    "validation_funnel_method_spec": Path("VALIDATION_FUNNEL_METHOD_SPEC.md"),
    "stream_health_method_spec": Path(
        "OUTCOME_CONDITIONED_STREAM_HEALTH_SPEC.md"
    ),
    "practical_pod_method_spec": Path(
        "PRACTICAL_POD_COMMON_SPLIT_SPEC.md"
    ),
    "prevarank_method_spec": Path("PREVARANK_BASELINE_PROTOCOL.md"),
    "shift_aware_scheduler_spec": Path(
        "SHIFT_AWARE_SAFE_SCHEDULER_SPEC.md"
    ),
    "repairbench_external_protocol": Path(
        "REPAIRBENCH_EXTERNAL_PROTOCOL.md"
    ),
    "validation_cost_protocol": Path(
        "VALIDATION_COST_MEASUREMENT_PROTOCOL.md"
    ),
    "final_analysis_hierarchy": Path(
        "FINAL_ANALYSIS_HIERARCHY.md"
    ),
    "paper_artifact_builder": Path(
        "build_paper_artifacts.py"
    ),
}


def load_json(path):
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def iter_jsonl(path):
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def number(value, digits=3):
    return f"{float(value):.{digits}f}"


def percent(value, digits=1):
    return f"{100 * float(value):.{digits}f}%"


def points(value, digits=1):
    return f"{100 * float(value):+.{digits}f}"


def points_interval(values, digits=1):
    return f"[{points(values['ci_low'], digits)}, {points(values['ci_high'], digits)}]"


def signed(value, digits=3):
    return f"{float(value):+.{digits}f}"


def interval(values, digits=3):
    return f"[{signed(values['ci_low'], digits)}, {signed(values['ci_high'], digits)}]"


def markdown_table(headers, rows):
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(header, "")) for header in headers) + " |")
    return "\n".join(lines)


def by_name(rows, key):
    return {row[key]: row for row in rows}


def stable_context_id(row):
    payload = "\x1f".join([row["bug_id"], row["anchor"], row["human_fix"]])
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"ctx_{digest[:16]}"


def pearson_correlation(left, right, weights=None):
    if len(left) != len(right) or len(left) < 2:
        raise ValueError("Correlation requires equal-length vectors with at least two values.")
    if weights is None:
        weights = [1.0] * len(left)
    if len(weights) != len(left) or any(weight <= 0 for weight in weights):
        raise ValueError("Correlation weights must be positive and match the vectors.")
    weight_sum = sum(weights)
    left_mean = sum(weight * value for weight, value in zip(weights, left)) / weight_sum
    right_mean = sum(weight * value for weight, value in zip(weights, right)) / weight_sum
    covariance = sum(
        weight * (x - left_mean) * (y - right_mean)
        for weight, x, y in zip(weights, left, right)
    )
    left_variance = sum(
        weight * (value - left_mean) ** 2 for weight, value in zip(weights, left)
    )
    right_variance = sum(
        weight * (value - right_mean) ** 2 for weight, value in zip(weights, right)
    )
    denominator = math.sqrt(left_variance * right_variance)
    if denominator == 0:
        raise ValueError("Correlation is undefined for a constant vector.")
    return covariance / denominator


def fisher_correlation_interval(correlation, sample_size, z_critical=1.959963984540054):
    if sample_size <= 3:
        raise ValueError("A Fisher correlation interval requires more than three units.")
    clipped = max(-1 + 1e-15, min(1 - 1e-15, float(correlation)))
    transformed = math.atanh(clipped)
    margin = z_critical / math.sqrt(sample_size - 3)
    return {
        "ci_low": math.tanh(transformed - margin),
        "ci_high": math.tanh(transformed + margin),
    }


def human_transfer_diagnostics(data):
    diagnostics = data["external_transfer"]["modes"]["retain_conflicts"][
        "humanevaljava"
    ]["labeled_full"]["calibration_diagnostics"]
    by_source = diagnostics["by_source_config"]
    rows = [by_source[name] for name in sorted(by_source)]
    defects_priors = [row["defects4j_source_prior"] for row in rows]
    external_rates = [row["empirical_correct_rate"] for row in rows]
    occurrence_weights = [row["occurrences"] for row in rows]
    correlation = pearson_correlation(defects_priors, external_rates)
    leave_one_out = [
        pearson_correlation(
            defects_priors[:index] + defects_priors[index + 1 :],
            external_rates[:index] + external_rates[index + 1 :],
        )
        for index in range(len(rows))
    ]
    return {
        "config_count": len(rows),
        "pearson_correlation": correlation,
        "pearson_fisher_95_ci": fisher_correlation_interval(correlation, len(rows)),
        "spearman_rank_correlation": diagnostics["source_quality_transfer"][
            "spearman_rank_correlation"
        ],
        "occurrence_weighted_pearson": pearson_correlation(
            defects_priors, external_rates, occurrence_weights
        ),
        "leave_one_config_pearson_low": min(leave_one_out),
        "leave_one_config_pearson_high": max(leave_one_out),
        "empirical_correct_rate": diagnostics["empirical_correct_rate"],
        "mean_transferred_probability": diagnostics["mean_transferred_probability"],
        "expected_calibration_error_10_bins": diagnostics[
            "expected_calibration_error_10_bins"
        ],
    }


def weak_oracle_context_profile():
    labels_by_context = {}
    candidate_paths = (
        AUXILIARY_INPUTS["plausible_labeled_candidates"],
        AUXILIARY_INPUTS["plausible_unknown_candidates"],
    )
    for path in candidate_paths:
        for row in iter_jsonl(path):
            labels = labels_by_context.setdefault(
                stable_context_id(row), {"correct": 0, "incorrect": 0, "unknown": 0}
            )
            labels[row["label"]] += 1
    no_verified_correct = [
        labels for labels in labels_by_context.values() if not labels["correct"]
    ]
    return {
        "test_positive_contexts": len(labels_by_context),
        "verified_correct_contexts": sum(
            bool(labels["correct"]) for labels in labels_by_context.values()
        ),
        "no_verified_correct_contexts": len(no_verified_correct),
        "no_verified_correct_with_unknown": sum(
            bool(labels["unknown"]) for labels in no_verified_correct
        ),
        "no_verified_correct_with_known_incorrect": sum(
            bool(labels["incorrect"]) for labels in no_verified_correct
        ),
        "unknown_contexts": sum(
            bool(labels["unknown"]) for labels in labels_by_context.values()
        ),
    }


def weak_oracle_statistics(data):
    plausible = data["plausible_audit"]
    passing = plausible["all_test_passing"]
    labeled = plausible["labeled"]
    context_profile = weak_oracle_context_profile()
    incorrect = labeled["labels"]["incorrect"]
    unknown = passing["labels"]["unknown"]
    total = passing["candidate_count"]
    verified_contexts = context_profile["verified_correct_contexts"]
    false_solved_contexts = context_profile["no_verified_correct_contexts"]
    return {
        "candidate_total": total,
        "candidate_correct": passing["labels"]["correct"],
        "candidate_incorrect": incorrect,
        "candidate_unknown": unknown,
        "candidate_labeled": labeled["candidate_count"],
        "candidate_incorrect_lower": incorrect / total,
        "candidate_incorrect_upper": (incorrect + unknown) / total,
        "candidate_incorrect_adjudicated": incorrect / labeled["candidate_count"],
        "test_positive_contexts": context_profile["test_positive_contexts"],
        "verified_correct_contexts": verified_contexts,
        "false_solved_contexts": false_solved_contexts,
        "false_solved_relative_inflation": false_solved_contexts / verified_contexts,
        "false_solved_with_unknown": context_profile[
            "no_verified_correct_with_unknown"
        ],
    }


def validate_inputs(data):
    all_inputs = {**INPUTS, **AUXILIARY_INPUTS, **SUPPORTING_ARTIFACTS}
    missing = [str(path) for path in all_inputs.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing paper inputs: {missing}")
    legacy_defects4j_inputs = [
        str(path)
        for path in all_inputs.values()
        if "llm_apr_defects4j_candidates_v1" in str(path).lower()
        or "results/v1" in str(path).lower().replace("\\", "/")
    ]
    if legacy_defects4j_inputs:
        raise ValueError(
            "The paper generator must not consume legacy Defects4J V1 "
            f"artifacts: {legacy_defects4j_inputs}"
        )

    dataset = data["dataset_audit"]
    plausible = data["plausible_audit"]
    stream = data["stream_primary"]
    source_order_ablation = data["source_order_ablation"]
    memorization_gate = data["memorization_lineage_gate"]
    validation_signal = data["validation_funnel_signal"]
    stage_policy = data["stage_aware_policy"]
    scheduler = data["adaptive_validation_scheduler"]
    stream_health = data["outcome_conditioned_stream_health"]
    practical_pod = data["practical_pod_common_split"]
    prevarank = data["prevarank_llm"]
    prevarank_shift = data["prevarank_domain_shift"]
    prevarank_order = data["prevarank_input_order"]
    prevarank_reproduction = data["prevarank_reproduction"]
    prevarank_manifest = load_json(
        AUXILIARY_INPUTS["prevarank_preparation_manifest"]
    )
    prevarank_mixed_verification = load_json(
        AUXILIARY_INPUTS["prevarank_mixed_verification"]
    )
    prevarank_stream_verification = load_json(
        AUXILIARY_INPUTS["prevarank_stream_verification"]
    )
    prevarank_stable_evaluation = load_json(
        AUXILIARY_INPUTS["prevarank_stable_hash_evaluation"]
    )
    prevarank_stable_manifest = load_json(
        AUXILIARY_INPUTS["prevarank_stable_hash_manifest"]
    )
    prevarank_stable_verification = load_json(
        AUXILIARY_INPUTS["prevarank_stable_hash_verification"]
    )
    canonical_mixed_pools = {
        pool["input_file"]: {
            (item["candidate_id"], item["native_index"])
            for item in pool["candidates"]
        }
        for pool in prevarank_manifest["pools"]
        if pool["pool_type"] == "mixed"
    }
    stable_mixed_pools = {
        pool["input_file"]: {
            (item["candidate_id"], item["native_index"])
            for item in pool["candidates"]
        }
        for pool in prevarank_stable_manifest["pools"]
        if pool["pool_type"] == "mixed"
    }
    shift_aware = data["shift_aware_safe_scheduler"]
    repairbench_audit = data["repairbench_import_audit"]
    repairbench_integrity = data["repairbench_campaign_integrity"]
    repairbench = data["repairbench_external_campaign"]
    repairbench_review = data["repairbench_semantic_review_audit"]
    external = data["external_transfer"]
    budget = data["budget_success"]
    apca = data["plausible_apca"]
    unixcoder = data["unixcoder_audit"]

    checks = {
        "dataset_v2": dataset["dataset"].endswith("_v2"),
        "dataset_checks": all(dataset["validation_checks"].values()),
        "plausible_checks": all(plausible["validation_checks"].values()),
        "stream_leakage_checks": stream["metadata"]["holdout_audit"][
            "all_leakage_invariants_pass"
        ],
        "source_order_ablation_checks": all(
            all(setting["validation_checks"].values())
            for setting in source_order_ablation["settings"].values()
        ),
        "memorization_gate_checks": all(
            memorization_gate["validation_checks"].values()
        ),
        "validation_funnel_checks": all(
            validation_signal["integrity_checks"].values()
        ),
        "stage_policy_checks": all(stage_policy["integrity_checks"].values()),
        "scheduler_checks": all(scheduler["integrity_checks"].values()),
        "stream_health_checks": all(
            stream_health["integrity_checks"].values()
        ),
        "practical_pod_expected_counts": all(
            practical_pod["integrity_audit"]["expected_count_checks"].values()
        ),
        "practical_pod_identity_checks": (
            practical_pod["integrity_audit"]["common_candidate_ids_unique"]
            and practical_pod["integrity_audit"][
                "all_verified_labels_match_the_released_labels"
            ]
            and practical_pod["integrity_audit"][
                "all_occurrence_labels_match_nested_score_labels"
            ]
            and practical_pod["integrity_audit"][
                "all_external_candidates_compile_and_pass_tests"
            ]
            and practical_pod["integrity_audit"][
                "all_nested_score_folds_match_bug_manifest"
            ]
        ),
        "prevarank_reproduction_complete": (
            prevarank_reproduction["summary"]["all_runs_exit_zero"]
            and prevarank_reproduction["summary"]["all_workbook_sets_match"]
            and prevarank_reproduction["summary"][
                "suspicious_runtime_line_count"
            ]
            == 0
            and prevarank_reproduction["summary"]["workbook_count"] == 348
        ),
        "prevarank_pinned_artifact_reconciles": (
            prevarank_reproduction["artifact"]["archive_sha256"]
            == prevarank["metadata"]["run_summaries"]["mixed"]["artifact"][
                "archive_sha256"
            ]
            == prevarank["metadata"]["run_summaries"]["stream"]["artifact"][
                "archive_sha256"
            ]
            and prevarank_reproduction["artifact"]["jar_sha256"]
            == prevarank["metadata"]["run_summaries"]["mixed"]["artifact"][
                "jar_sha256"
            ]
            == prevarank["metadata"]["run_summaries"]["stream"]["artifact"][
                "jar_sha256"
            ]
        ),
        "prevarank_runs_independently_verified": (
            prevarank_mixed_verification["complete"]
            and prevarank_stream_verification["complete"]
            and prevarank_mixed_verification["output_file_count"]
            == prevarank_manifest["counts"]["pool_counts"]["mixed"]
            and prevarank_stream_verification["output_file_count"]
            == prevarank_manifest["counts"]["pool_counts"]["stream"]
            and prevarank_mixed_verification["missing_output_files"] == []
            and prevarank_stream_verification["missing_output_files"] == []
            and prevarank_mixed_verification["extra_output_files"] == []
            and prevarank_stream_verification["extra_output_files"] == []
        ),
        "prevarank_evaluation_reconciles": (
            prevarank["reconciliation"]["all_output_counts_match"]
            and prevarank["reconciliation"]["pool_count"]
            == prevarank_manifest["counts"]["input_file_count"]
            and prevarank["reconciliation"]["candidate_instance_count"]
            == sum(
                prevarank_manifest["counts"][
                    "pool_candidate_instances"
                ].values()
            )
            and len(prevarank["protocols"]) == 6
        ),
        "prevarank_common_support_reconciles": (
            prevarank_manifest["counts"]["candidate_count"] == 4200
            and prevarank_manifest["counts"]["supported_candidate_count"]
            == prevarank_shift["llm_apr"]["candidate_instance_count"]
            == 4180
            and prevarank_manifest["counts"]["unsupported_candidate_count"]
            == 20
        ),
        "prevarank_domain_shift_ledger_pinned": (
            prevarank_shift["metadata"]["llm_ledger_sha256"]
            == sha256(AUXILIARY_INPUTS["prevarank_mixed_evaluation_ledger"])
        ),
        "prevarank_stable_hash_intervention_frozen": (
            prevarank_stable_manifest["adapter_contract"]["input_order"]
            == "stable_hash"
            and prevarank_stable_manifest["adapter_contract"][
                "input_order_seed"
            ]
            == "prevarank-mixed-order-sensitivity-v1"
            and prevarank_stable_manifest["candidates"]
            == prevarank_manifest["candidates"]
            and canonical_mixed_pools == stable_mixed_pools
            and prevarank_stable_manifest["counts"]["pool_counts"]["mixed"]
            == 465
            and prevarank_stable_manifest["counts"][
                "pool_candidate_instances"
            ]["mixed"]
            == 4180
        ),
        "prevarank_stable_hash_run_verified": (
            prevarank_stable_verification["complete"]
            and prevarank_stable_verification["manifest_sha256"]
            == sha256(AUXILIARY_INPUTS["prevarank_stable_hash_manifest"])
            and prevarank_stable_verification["output_file_count"] == 465
            and prevarank_stable_verification["missing_output_files"] == []
            and prevarank_stable_verification["extra_output_files"] == []
            and prevarank_stable_verification["log"][
                "suspicious_runtime_line_count"
            ]
            == 0
        ),
        "prevarank_stable_hash_evaluation_reconciles": (
            prevarank_stable_evaluation["metadata"]["manifest_sha256"]
            == sha256(AUXILIARY_INPUTS["prevarank_stable_hash_manifest"])
            and prevarank_stable_evaluation["metadata"]["run_summaries"][
                "mixed"
            ]
            == prevarank_stable_verification
            and prevarank_stable_evaluation["reconciliation"][
                "all_output_counts_match"
            ]
            and prevarank_stable_evaluation["reconciliation"]["pool_count"]
            == 465
            and prevarank_stable_evaluation["reconciliation"][
                "candidate_instance_count"
            ]
            == 4180
            and len(prevarank_stable_evaluation["protocols"]) == 3
        ),
        "prevarank_input_order_comparison_reconciles": (
            prevarank_order["metadata"]["canonical_ledger_sha256"]
            == sha256(AUXILIARY_INPUTS["prevarank_mixed_evaluation_ledger"])
            and prevarank_order["metadata"]["shuffled_ledger_sha256"]
            == sha256(AUXILIARY_INPUTS["prevarank_stable_hash_ledger"])
            and prevarank_order["metadata"]["bootstrap_iterations"] == 10000
            and prevarank_order["metadata"]["bootstrap_cluster"] == "bug_id"
            and prevarank_order["reconciliation"][
                "candidate_instance_count"
            ]
            == 4180
            and prevarank_order["reconciliation"]["pool_count"] == 465
            and prevarank_order["reconciliation"]["category_change_count"]
            == 0
            and prevarank_order["reconciliation"]["bug_type_change_count"]
            == 0
            and prevarank_order["reconciliation"][
                "historical_value_change_count"
            ]
            == 0
            and {
                world["label_world"]
                for world in prevarank_order["label_worlds"]
            }
            == {
                "adjudicated_only",
                "pessimistic_unknown",
                "optimistic_unknown",
            }
        ),
        "shift_aware_integrity_checks": all(
            shift_aware["integrity_checks"].values()
        ),
        "shift_aware_population_reconciles": (
            shift_aware["counts"]["defects4j_candidates"]
            == dataset["candidate_counts"]["hard"]
            and shift_aware["counts"]["defects4j_reference_contexts"] == 863
            and shift_aware["counts"]["source_configs"] == 14
            and shift_aware["internal"]["all_context_budget_one"][
                "summaries"
            ]["source_order_tie_aware"]["universe_contexts"]
            == 863
        ),
        "shift_aware_external_denominators_reconcile": (
            shift_aware["external"]["humanevaljava"]["context_count"] == 164
            and shift_aware["external"]["gitbugjava"]["context_count"] == 89
            and shift_aware["external"]["gitbugjava_top10"][
                "context_count"
            ]
            == 89
        ),
        "shift_aware_outputs_pinned": (
            shift_aware["outputs"]["action_ledger_sha256"]
            == sha256(AUXILIARY_INPUTS["shift_aware_action_ledger"])
            and shift_aware["outputs"]["summary_csv_sha256"]
            == sha256(AUXILIARY_INPUTS["shift_aware_summary_csv"])
        ),
        "repairbench_import_integrity": (
            repairbench_audit["upstream"]["commit_matches_pin"]
            and repairbench_audit["upstream"]["registered_model_count"] == 35
            and repairbench_audit["candidate_counts"]["included"] == 21144
            and repairbench_audit["contexts"]["all"] == 89
            and all(repairbench_audit["validation_checks"].values())
            and repairbench_audit["candidate_conflicts"]["any_conflict"] == 0
        ),
        "repairbench_campaign_shift_reconciles": (
            all(repairbench_integrity["validation_checks"].values())
            and repairbench_integrity["campaign_sizes"][
                "shared_exact_source_configs"
            ]
            == 0
            and repairbench_integrity["campaign_sizes"]["shared_contexts"]
            == 89
            and repairbench_integrity["candidate_overlap"][
                "candidate_identity_overlap"
            ]
            == 34
            and repairbench_integrity["metadata"]["input_files"][
                "new_candidates_sha256"
            ]
            == sha256(AUXILIARY_INPUTS["repairbench_candidates"])
            and repairbench_integrity["metadata"]["input_files"][
                "new_audit_sha256"
            ]
            == sha256(INPUTS["repairbench_import_audit"])
        ),
        "repairbench_external_integrity": (
            all(repairbench["integrity_checks"].values())
            and repairbench["campaign_counts"]["candidates"] == 21144
            and repairbench["campaign_counts"]["contexts"] == 89
            and repairbench["campaign_counts"]["new_source_configs"] == 35
            and repairbench["worlds"]["test_plausibility"]["merged"][
                "ranking"
            ]["methods"]["returned_index"]["summary"]["positive_pools"]
            == 76
            and repairbench["worlds"]["reference_complete_case"]["merged"][
                "ranking"
            ]["methods"]["returned_index"]["summary"]["positive_pools"]
            == 26
        ),
        "repairbench_protocol_chain_pinned": (
            repairbench["metadata"]["protocol_sha256"]
            == repairbench_review["protocol_sha256"]
            == sha256(SUPPORTING_ARTIFACTS["repairbench_external_protocol"])
            and repairbench["metadata"]["inputs"]["candidates_sha256"]
            == sha256(AUXILIARY_INPUTS["repairbench_candidates"])
            and repairbench["metadata"]["inputs"]["codet5_scores_sha256"]
            == sha256(AUXILIARY_INPUTS["repairbench_codet5_scores"])
            and repairbench["metadata"]["inputs"]["codet5_metadata_sha256"]
            == sha256(AUXILIARY_INPUTS["repairbench_codet5_metadata"])
            and repairbench["metadata"]["inputs"]["calibration_sha256"]
            == sha256(INPUTS["external_transfer"])
        ),
        "repairbench_outputs_pinned": (
            repairbench["outputs"]["score_ledger_sha256"]
            == sha256(AUXILIARY_INPUTS["repairbench_score_ledger"])
            and repairbench["outputs"]["score_csv_sha256"]
            == sha256(AUXILIARY_INPUTS["repairbench_score_csv"])
            and repairbench["outputs"]["safe_gate_actions_sha256"]
            == sha256(AUXILIARY_INPUTS["repairbench_safe_actions"])
        ),
        "repairbench_review_packet_pinned": (
            all(repairbench_review["validation_checks"].values())
            and repairbench_review["counts"]["eligible_contexts"] == 50
            and repairbench_review["counts"]["selected_unique_candidates"]
            == 325
            and repairbench_review["inputs"]["candidates_sha256"]
            == sha256(AUXILIARY_INPUTS["repairbench_candidates"])
            and repairbench_review["inputs"]["scores_sha256"]
            == sha256(AUXILIARY_INPUTS["repairbench_score_ledger"])
            and repairbench_review["outputs"]["blinded_items_sha256"]
            == sha256(
                AUXILIARY_INPUTS["repairbench_blinded_review_items"]
            )
            and repairbench_review["outputs"][
                "private_selection_ledger_sha256"
            ]
            == sha256(
                AUXILIARY_INPUTS["repairbench_private_review_ledger"]
            )
        ),
        "new_method_candidate_universe_reconciles": (
            validation_signal["counts"]["deduplicated_candidates"]
            == stage_policy["counts"]["candidate_count"]
            == dataset["candidate_counts"]["all_included"]
        ),
        "new_method_reference_universe_reconciles": (
            stage_policy["counts"]["reference_context_count"]
            == scheduler["counts"]["reference_contexts"]
            == stream_health["counts"]["reference_contexts"]
            == dataset["reference_context_count"]
        ),
        "stream_health_baseline_hash_reconciles": (
            stream_health["inputs"]["baseline_scheduler_sha256"]
            == sha256(INPUTS["adaptive_validation_scheduler"])
        ),
        "new_method_stage_counts_reconcile": (
            stage_policy["counts"]["endpoint_counts"]["compile"]["eligible_count"]
            == validation_signal["views"]["candidate_primary_no_conflicts"][
                "compile"
            ]["eligible_count"]
            and stage_policy["counts"]["endpoint_counts"]["test_given_compile"][
                "eligible_count"
            ]
            == validation_signal["views"]["candidate_primary_no_conflicts"][
                "test_given_compile"
            ]["eligible_count"]
            and stage_policy["counts"]["endpoint_counts"][
                "semantic_correct_nonreference"
            ]["positive_count"]
            == validation_signal["views"]["candidate_primary_no_conflicts"][
                "semantic_correct_given_adjudicated_nonreference"
            ]["positive_count"]
        ),
        "named_lineage_holdout_has_all_crossed_cells": (
            memorization_gate["lineage_holdout"]["named_model"]["metadata"][
                "crossed_cell_count"
            ]
            == 20
        ),
        "provider_lineage_holdout_has_all_crossed_cells": (
            memorization_gate["lineage_holdout"]["provider"]["metadata"][
                "crossed_cell_count"
            ]
            == 15
        ),
        "rotating_loco_has_all_crossed_cells": stream["metadata"]["holdout_audit"][
            "crossed_cell_count"
        ]
        == stream["metadata"]["source_config_count"] * len(stream["metadata"]["folds"]),
        "apca_excludes_test_failures": not apca["metadata"][
            "test_failure_negatives_included"
        ],
        "apca_excludes_unknowns": not apca["metadata"][
            "unknown_plausible_candidates_included"
        ],
        "unixcoder_leakage_checks": unixcoder["all_leakage_invariants_pass"],
        "apca_population_matches_labeled_corpus": (
            apca["metadata"]["candidate_count"]
            == plausible["labeled"]["candidate_count"]
            and apca["metadata"]["correct_count"]
            == plausible["labeled"]["labels"]["correct"]
            and apca["metadata"]["incorrect_count"]
            == plausible["labeled"]["labels"]["incorrect"]
        ),
        "apca_no_conflict_population_matches_corpus": (
            data["plausible_apca_no_conflicts"]["metadata"]["candidate_count"]
            == plausible["labeled_no_conflicts"]["candidate_count"]
            and data["plausible_apca_no_conflicts"]["metadata"]["correct_count"]
            == plausible["labeled_no_conflicts"]["labels"]["correct"]
            and data["plausible_apca_no_conflicts"]["metadata"]["incorrect_count"]
            == plausible["labeled_no_conflicts"]["labels"]["incorrect"]
        ),
        "unixcoder_population_matches_labeled_corpus": (
            unixcoder["candidate_count"] == plausible["labeled"]["candidate_count"]
        ),
        "manual_review_skips_remain_unknown": (
            dataset["occurrence_count_by_reviewer_provenance_status"][
                "manual_review_not_performed"
            ]
            > 0
            and plausible["unknown"]["annotation_evidence"][
                "unknown_review_skipped_exact_or_ast_present"
            ]
            > 0
            and plausible["validation_checks"][
                "all_incorrect_have_manual_semantic_negative"
            ]
        ),
        "weak_oracle_candidate_identity": plausible["all_test_passing"][
            "candidate_count"
        ]
        == plausible["labeled"]["candidate_count"]
        + plausible["unknown"]["candidate_count"],
        "weak_oracle_context_identity": plausible["all_test_passing"][
            "context_count"
        ]
        >= plausible["all_test_passing"]["positive_context_count"],
    }
    weak_contexts = weak_oracle_context_profile()
    source_strata = by_name(
        stream["protocols"]["known_generator_bug_oof"]["context"]["results"],
        "method",
    )["source_order_tie_aware"]["positive_provenance_strata"]
    checks["correctness_evidence_strata_reconcile"] = (
        sum(row["positive_pools"] for row in source_strata.values())
        == data["baselines_context"]["metadata"]["split_metadata"]["totals"][
            "positive_context_count"
        ]
        and all(row["positive_pools"] > 0 for row in source_strata.values())
    )
    gate_strata = memorization_gate["defects4j"]["all_configurations"][
        "correctness_evidence_strata"
    ]
    checks["memorization_gate_strata_reconcile"] = (
        sum(
            row["minimum_native_rank"]["summary"]["positive_pools"]
            for row in gate_strata.values()
        )
        == 338
        and memorization_gate["gitbugjava"]["all_configurations"][
            "positive_context_count"
        ]
        == 26
    )
    checks["singleton_gate_reconciles"] = (
        memorization_gate["singleton_existing_evidence"][
            "minimum_rank_minus_random"
        ]["observed_difference"]
        == source_order_ablation["settings"]["singleton_candidates"][
            "paired_comparisons"
        ]["source_order_minus_random"]["mrr"]["observed_difference"]
    )
    checks["weak_oracle_contexts_reconcile"] = (
        weak_contexts["test_positive_contexts"]
        == plausible["all_test_passing"]["context_count"]
        and weak_contexts["verified_correct_contexts"]
        == plausible["all_test_passing"]["positive_context_count"]
    )
    checks["weak_oracle_false_solved_contexts_have_no_unknowns"] = (
        weak_contexts["no_verified_correct_with_unknown"] == 0
        and weak_contexts["no_verified_correct_with_known_incorrect"]
        == weak_contexts["no_verified_correct_contexts"]
    )
    checks["unknown_labels_are_confined_to_verified_correct_contexts"] = (
        weak_contexts["unknown_contexts"] > 0
        and weak_contexts["no_verified_correct_with_unknown"] == 0
    )
    hard_test_failures = (
        dataset["candidate_counts"]["hard"]
        - plausible["labeled"]["candidate_count"]
    )
    checks["pretest_outcome_funnel_reconciles"] = (
        hard_test_failures
        == dataset["candidate_labels_hard"]["incorrect"]
        - plausible["labeled"]["labels"]["incorrect"]
        and hard_test_failures > 0
    )
    for modes in external["modes"].values():
        for settings in modes.values():
            for payload in settings.values():
                checks.setdefault("external_transfer_checks", True)
                checks["external_transfer_checks"] &= all(
                    payload["transfer_invariants"].values()
                )
    for setting in budget["settings"]:
        for group in setting["groups"].values():
            checks.setdefault("budget_checks", True)
            checks["budget_checks"] &= all(group["validation_checks"].values())
    defects_budget = next(
        setting
        for setting in budget["settings"]
        if setting["metadata"]["benchmark"] == "defects4j"
        and setting["metadata"]["setting"] == "compile_hard"
        and setting["metadata"]["conflict_mode"] == "retain_conflicts"
    )
    split_contexts = data["baselines_context"]["metadata"]["split_metadata"][
        "totals"
    ]["context_count"]
    empty_contexts = defects_budget["groups"]["context"]["summaries"][
        "stream_index_max"
    ]["1"]["empty_pools"]
    checks["operational_universe_reconciles"] = (
        defects_budget["metadata"]["universe_size_context"]
        == split_contexts + empty_contexts
    )
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise ValueError(f"Paper artifact validation failed: {failed}")
    return checks


def ranking_row(label, result):
    summary = result["summary"]
    ci = result["bug_cluster_bootstrap_ci"]["mrr"]
    return {
        "Method": label,
        "Pools": f"{summary['positive_pools']:,}",
        "MRR": number(summary["mrr"]),
        "MRR 95% CI": f"[{number(ci['ci_low'])}, {number(ci['ci_high'])}]",
        "R@1": percent(summary["recall@1"]),
        "R@5": percent(summary["recall@5"]),
        "R@10": percent(summary["recall@10"]),
        "Macro AUC": number(summary["pairwise_auc_macro"]),
    }


def dataset_tables(data):
    audit = data["dataset_audit"]
    plausible = data["plausible_audit"]
    split = data["baselines_context"]["metadata"]["split_metadata"]["totals"]
    rows = [
        {"Quantity": "Source configurations", "Value": f"{audit['source_file_count']:,}"},
        {"Quantity": "Official Defects4J bugs", "Value": f"{audit['official_bug_count']:,}"},
        {"Quantity": "Raw official occurrences", "Value": f"{audit['raw_audit']['raw_official_occurrences']:,}"},
        {"Quantity": "Included deduplicated candidates", "Value": f"{audit['candidate_counts']['all_included']:,}"},
        {"Quantity": "Labeled candidates", "Value": f"{audit['candidate_counts']['labeled']:,}"},
        {"Quantity": "Unknown candidates", "Value": f"{audit['candidate_labels_all']['unknown']:,}"},
        {"Quantity": "Compile-filtered pre-test candidates", "Value": f"{audit['candidate_counts']['hard']:,}"},
        {"Quantity": "Pre-test correct / incorrect", "Value": f"{audit['candidate_labels_hard']['correct']:,} / {audit['candidate_labels_hard']['incorrect']:,}"},
        {"Quantity": "Reference repair contexts", "Value": f"{audit['reference_context_count']:,}"},
        {"Quantity": "Scored pre-test bugs / contexts", "Value": f"{split['bug_count']:,} / {split['context_count']:,}"},
        {"Quantity": "Positive pre-test bugs / contexts", "Value": f"{split['positive_bug_count']:,} / {split['positive_context_count']:,}"},
        {"Quantity": "Candidates with any evidence conflict", "Value": f"{audit['candidate_conflicts']['any_conflict']:,}"},
        {"Quantity": "Reviewer agreement / Cohen kappa", "Value": f"{audit['inter_rater_agreement']['deduplicated_bug_patch_pairs']['agreement']:.3f} / {audit['inter_rater_agreement']['deduplicated_bug_patch_pairs']['cohen_kappa']:.3f}"},
    ]
    plausible_rows = [
        {
            "View": "All test-passing",
            "Candidates": f"{plausible['all_test_passing']['candidate_count']:,}",
            "Correct": f"{plausible['all_test_passing']['labels']['correct']:,}",
            "Incorrect": f"{plausible['all_test_passing']['labels']['incorrect']:,}",
            "Unknown": f"{plausible['all_test_passing']['labels']['unknown']:,}",
        },
        {
            "View": "Labeled primary",
            "Candidates": f"{plausible['labeled']['candidate_count']:,}",
            "Correct": f"{plausible['labeled']['labels']['correct']:,}",
            "Incorrect": f"{plausible['labeled']['labels']['incorrect']:,}",
            "Unknown": "0",
        },
        {
            "View": "Labeled no-conflict",
            "Candidates": f"{plausible['labeled_no_conflicts']['candidate_count']:,}",
            "Correct": f"{plausible['labeled_no_conflicts']['labels']['correct']:,}",
            "Incorrect": f"{plausible['labeled_no_conflicts']['labels']['incorrect']:,}",
            "Unknown": "0",
        },
    ]
    return rows, plausible_rows


def validation_funnel_table(data):
    audit = data["dataset_audit"]
    plausible = data["plausible_audit"]
    hard = audit["candidate_counts"]["hard"]
    labeled_passing = plausible["labeled"]["candidate_count"]
    test_failing = hard - labeled_passing
    return [
        {
            "Outcome stage": "Compile-filtered pre-test universe",
            "Candidates": f"{hard:,}",
            "Share of pre-test universe": "100.0%",
            "Paper interpretation": "Primary ranking universe before test execution.",
        },
        {
            "Outcome stage": "Does not pass available tests",
            "Candidates": f"{test_failing:,}",
            "Share of pre-test universe": percent(test_failing / hard),
            "Paper interpretation": "Existing tests can reject these candidates.",
        },
        {
            "Outcome stage": "Test-passing and adjudicated",
            "Candidates": f"{labeled_passing:,}",
            "Share of pre-test universe": percent(labeled_passing / hard),
            "Paper interpretation": "Population used by plausible-only APCA.",
        },
        {
            "Outcome stage": "Verified correct",
            "Candidates": f"{plausible['labeled']['labels']['correct']:,}",
            "Share of pre-test universe": percent(
                plausible["labeled"]["labels"]["correct"] / hard
            ),
            "Paper interpretation": "Semantic/equivalence-positive endpoint.",
        },
        {
            "Outcome stage": "Known overfitting test-passing",
            "Candidates": f"{plausible['labeled']['labels']['incorrect']:,}",
            "Share of pre-test universe": percent(
                plausible["labeled"]["labels"]["incorrect"] / hard
            ),
            "Paper interpretation": "Post-test correctness-assessment target.",
        },
    ]


def weak_oracle_table(data):
    audit = data["dataset_audit"]
    weak = weak_oracle_statistics(data)
    return [
        {
            "Level": "Candidate",
            "Population": f"{weak['candidate_total']:,} test-passing",
            "Verified correct": f"{weak['candidate_correct']:,}",
            "Known incorrect / false-solved": f"{weak['candidate_incorrect']:,}",
            "Unresolved": f"{weak['candidate_unknown']:,}",
            "Key result": (
                f"{percent(weak['candidate_incorrect_lower'])}-"
                f"{percent(weak['candidate_incorrect_upper'])} "
                f"corpus-wide incorrect bound; "
                f"{percent(weak['candidate_incorrect_adjudicated'])} among adjudicated"
            ),
        },
        {
            "Level": "Context",
            "Population": (
                f"{weak['test_positive_contexts']:,} test-positive / "
                f"{audit['reference_context_count']:,} reference"
            ),
            "Verified correct": f"{weak['verified_correct_contexts']:,}",
            "Known incorrect / false-solved": f"{weak['false_solved_contexts']:,}",
            "Unresolved": "0 among false-solved contexts",
            "Key result": (
                f"{percent(weak['false_solved_relative_inflation'])} relative inflation "
                "in apparent solvability"
            ),
        },
    ]


def primary_ranking_tables(data):
    known = data["stream_primary"]["protocols"]["known_generator_bug_oof"]["context"]
    nested = by_name(known["results"], "method")
    baseline = by_name(data["baselines_context"]["results"], "scorer")
    selected = [
        ("EB stream-index max", nested["stream_index_max"]),
        ("EB stream-index mean", nested["stream_index_mean"]),
        ("Global index only", nested["global_index_only"]),
        ("Source prior only", nested["source_prior_only"]),
        ("Minimum native rank", nested["source_order_tie_aware"]),
        ("Occurrence count", baseline["occurrence_count_tie_aware"]),
        ("Token similarity", baseline["anchor_token_similarity_tie_aware"]),
        ("Random expectation", nested["random_expected"]),
    ]
    rows = [ranking_row(label, result) for label, result in selected]
    comparisons = []
    for method, label in [
        ("stream_index_max", "EB stream-index max"),
        ("stream_index_mean", "EB stream-index mean"),
        ("global_index_only", "Global index only"),
        ("source_prior_only", "Source prior only"),
    ]:
        paired = known["paired_comparisons"][method]
        mrr = paired["mrr_vs_source_order"]
        recall = paired["recall_at_1_vs_source_order"]
        comparisons.append(
            {
                "Method vs minimum native rank": label,
                "MRR difference": signed(mrr["observed_difference"]),
                "MRR 95% CI": interval(mrr),
                "R@1 difference (pp)": points(recall["observed_difference"]),
                "Bootstrap p (MRR)": number(mrr["two_sided_bootstrap_p"], 4),
            }
        )
    return rows, comparisons


def source_order_ablation_table(data):
    settings = data["source_order_ablation"]["settings"]
    specifications = [
        (
            "All candidates",
            settings["all_candidates"],
            "source_order_tie_aware",
            "index_zero_only_tie_aware",
            "source_order_minus_index_zero_only",
        ),
        (
            "Exclude every index-0 candidate",
            settings["tail_without_index_zero"],
            "source_order_tie_aware",
            "random_expected",
            "source_order_minus_random",
        ),
        (
            "Occurrence count = 1 only",
            settings["singleton_candidates"],
            "source_order_tie_aware",
            "random_expected",
            "source_order_minus_random",
        ),
    ]
    labels = {
        "source_order_tie_aware": "Minimum native rank",
        "index_zero_only_tie_aware": "Index-0 versus later only",
        "random_expected": "Random expectation",
    }
    rows = []
    for setting, payload, method, reference, comparison_name in specifications:
        method_summary = payload["methods"][method]["summary"]
        reference_summary = payload["methods"][reference]["summary"]
        comparison = payload["paired_comparisons"][comparison_name]
        mrr = comparison["mrr"]
        recall = comparison["recall_at_1"]
        rows.append(
            {
                "Ablation setting": setting,
                "Pools": f"{method_summary['positive_pools']:,}",
                "Method": labels[method],
                "Reference": labels[reference],
                "Method MRR": number(method_summary["mrr"]),
                "Reference MRR": number(reference_summary["mrr"]),
                "MRR difference": signed(mrr["observed_difference"]),
                "MRR 95% CI": interval(mrr),
                "R@1 difference (pp)": points(recall["observed_difference"]),
            }
        )
    return rows


def correctness_evidence_stratum_table(data):
    known = data["stream_primary"]["protocols"]["known_generator_bug_oof"]["context"]
    results = by_name(known["results"], "method")
    comparisons = known["paired_comparisons"]
    rows = []
    for stratum, label in [
        ("exact_or_ast_present", "Exact/AST correct present"),
        ("semantic_only", "Semantic-only correct"),
    ]:
        stream = results["stream_index_max"]["positive_provenance_strata"][stratum]
        source = results["source_order_tie_aware"]["positive_provenance_strata"][
            stratum
        ]
        random = results["random_expected"]["positive_provenance_strata"][stratum]
        stream_diff = comparisons["stream_index_max"][
            "mrr_vs_source_order_by_stratum"
        ][stratum]
        random_diff = comparisons["random_expected"][
            "mrr_vs_source_order_by_stratum"
        ][stratum]
        rows.append(
            {
                "Correct-patch evidence": label,
                "Pools": f"{source['positive_pools']:,}",
                "Min-rank MRR": number(source["mrr"]),
                "Random MRR": number(random["mrr"]),
                "Min-rank - random": signed(-random_diff["observed_difference"]),
                "Min-rank - random 95% CI": (
                    f"[{signed(-random_diff['ci_high'])}, "
                    f"{signed(-random_diff['ci_low'])}]"
                ),
                "EB MRR": number(stream["mrr"]),
                "EB - min-rank": signed(stream_diff["observed_difference"]),
                "EB - min-rank 95% CI": interval(stream_diff),
            }
        )
    return rows


def generalization_table(data):
    protocols = data["stream_primary"]["protocols"]
    known = protocols["known_generator_bug_oof"]["context"]
    merged = protocols["unseen_generator_merged_loco"]["context"]
    single = protocols["unseen_generator_single_stream"]["context"]
    external = data["external_transfer"]["modes"]["retain_conflicts"][
        "humanevaljava"
    ]["labeled_full"]["evaluation"]["context"]
    specifications = [
        ("Known configurations, merged pools", known, "stream_index_max", "source_order_tie_aware"),
        ("Unseen benchmark, same 14 configurations", external, "stream_index_max", "source_order_tie_aware"),
        ("Held-out configuration, rotating merged LOCO (5x14)", merged, "loco_index_noisy_or", "source_order_tie_aware"),
        ("Held-out configuration, rotating single stream (5x14)", single, "unseen_stream_fallback", "source_order_tie_aware"),
    ]
    rows = []
    for setting, payload, method, reference in specifications:
        results = by_name(payload["results"], "method")
        comparison = payload["paired_comparisons"][method]["mrr_vs_source_order"]
        rows.append(
            {
                "Setting": setting,
                "Method": method,
                "Pools": f"{results[method]['summary']['positive_pools']:,}",
                "Method MRR": number(results[method]["summary"]["mrr"]),
                "Minimum-rank MRR": number(results[reference]["summary"]["mrr"]),
                "Difference": signed(comparison["observed_difference"]),
                "95% CI": interval(comparison),
                "p": number(comparison["two_sided_bootstrap_p"], 4),
            }
        )
    return rows


def transfer_diagnostics_table(data):
    diagnostics = human_transfer_diagnostics(data)
    correlation_ci = diagnostics["pearson_fisher_95_ci"]
    return [
        {
            "Diagnostic": "Source configurations",
            "Value": f"{diagnostics['config_count']}",
            "Interpretation": "One Defects4J prior and one HumanEval correctness rate per configuration.",
        },
        {
            "Diagnostic": "Pearson correlation",
            "Value": number(diagnostics["pearson_correlation"]),
            "Interpretation": (
                f"Descriptive Fisher 95% CI "
                f"[{number(correlation_ci['ci_low'])}, {number(correlation_ci['ci_high'])}]."
            ),
        },
        {
            "Diagnostic": "Spearman rank correlation",
            "Value": number(diagnostics["spearman_rank_correlation"]),
            "Interpretation": "Configuration-quality ordering is broadly preserved.",
        },
        {
            "Diagnostic": "Occurrence-weighted Pearson",
            "Value": number(diagnostics["occurrence_weighted_pearson"]),
            "Interpretation": "The association is not driven only by small configuration streams.",
        },
        {
            "Diagnostic": "Leave-one-config Pearson range",
            "Value": (
                f"[{number(diagnostics['leave_one_config_pearson_low'])}, "
                f"{number(diagnostics['leave_one_config_pearson_high'])}]"
            ),
            "Interpretation": "No single configuration explains the association.",
        },
        {
            "Diagnostic": "Observed correctness / mean score",
            "Value": (
                f"{percent(diagnostics['empirical_correct_rate'])} / "
                f"{percent(diagnostics['mean_transferred_probability'])}"
            ),
            "Interpretation": "Relative ranking transfers, but absolute probabilities do not.",
        },
        {
            "Diagnostic": "10-bin ECE",
            "Value": number(diagnostics["expected_calibration_error_10_bins"]),
            "Interpretation": "Large base-rate shift prevents probability-calibration claims.",
        },
    ]


def find_budget_setting(data, benchmark, setting, conflict_mode="retain_conflicts"):
    for payload in data["budget_success"]["settings"]:
        metadata = payload["metadata"]
        if (
            metadata["benchmark"] == benchmark
            and metadata["setting"] == setting
            and metadata["conflict_mode"] == conflict_mode
        ):
            return payload
    raise KeyError((benchmark, setting, conflict_mode))


def budget_rows(data, benchmark, setting, budgets):
    payload = find_budget_setting(data, benchmark, setting)
    group = payload["groups"]["context"]
    paired = group["paired_comparisons"][
        "stream_index_max_minus_source_order_tie_aware"
    ]
    rows = []
    for budget in budgets:
        key = str(budget)
        stream = group["summaries"]["stream_index_max"][key]
        source = group["summaries"]["source_order_tie_aware"][key]
        difference = paired[key]["success_rate_all_difference"]
        rows.append(
            {
                "Benchmark / setting": f"{benchmark} / {setting}",
                "Budget": "exhaustion" if key == "all" else key,
                "Oracle ceiling": percent(stream["oracle_coverage"]),
                "Stream success": percent(stream["success_rate_all"]),
                "Min-rank success": percent(source["success_rate_all"]),
                "Difference (pp)": points(difference["observed_difference"]),
                "95% CI (pp)": points_interval(difference),
                "Stream reviews": number(stream["expected_validations_per_pool"], 2),
                "Min-rank reviews": number(source["expected_validations_per_pool"], 2),
            }
        )
    return rows


def apca_tables(data):
    payload = data["plausible_apca"]
    classification = payload["candidate_level_classification"]
    ranking = payload["mixed_pool_ranking"]
    class_results = classification["results"]
    class_labels = [
        ("EB stream-index max", "stream_index_max"),
        ("EB stream-index mean", "stream_index_mean"),
        ("Minimum native rank", "source_order_tie_aware"),
        ("Token similarity", "anchor_token_similarity"),
        ("CodeT5+ zero-shot", "codet5p_similarity"),
        ("UniXcoder supervised", "unixcoder_apca"),
        ("Training-fold majority", "training_fold_majority"),
    ]
    class_rows = []
    for label, method in class_labels:
        metrics = class_results[method]["metrics"]
        ci = class_results[method]["bug_cluster_bootstrap_ci"]["balanced_accuracy"]
        class_rows.append(
            {
                "Method": label,
                "Accuracy": number(metrics["accuracy"]),
                "Balanced accuracy": number(metrics["balanced_accuracy"]),
                "BA 95% CI": f"[{number(ci['ci_low'])}, {number(ci['ci_high'])}]",
                "F1": number(metrics["f1_correct"]),
                "MCC": number(metrics["mcc"]),
                "ROC-AUC": number(metrics["roc_auc"]),
            }
        )
    rank_results = ranking["results"]
    rank_rows = []
    for label, method in class_labels[:-1]:
        summary = rank_results[method]["summary"]
        rank_rows.append(
            {
                "Method": label,
                "Mixed contexts": f"{summary['positive_pools']:,}",
                "MRR": number(summary["mrr"]),
                "R@1": percent(summary["recall@1"]),
                "R@3": percent(summary["recall@3"]),
                "Macro AUC": number(summary["pairwise_auc_macro"]),
            }
        )
    return class_rows, rank_rows


def sensitivity_table(data):
    primary_rank = data["stream_primary"]["protocols"]["known_generator_bug_oof"]["context"]
    clean_rank = data["stream_no_conflicts"]["protocols"]["known_generator_bug_oof"]["context"]
    primary_apca = data["plausible_apca"]
    clean_apca = data["plausible_apca_no_conflicts"]
    rows = []
    for label, payload in [("Primary", primary_rank), ("No conflicts", clean_rank)]:
        results = by_name(payload["results"], "method")
        paired = payload["paired_comparisons"]["stream_index_max"]["mrr_vs_source_order"]
        rows.append(
            {
                "Analysis": "Known-configuration ranking",
                "View": label,
                "Primary metric": number(results["stream_index_max"]["summary"]["mrr"]),
                "Reference metric": number(results["source_order_tie_aware"]["summary"]["mrr"]),
                "Paired difference": signed(paired["observed_difference"]),
                "95% CI": interval(paired),
            }
        )
    for label, payload in [("Primary", primary_apca), ("No conflicts", clean_apca)]:
        classification = payload["candidate_level_classification"]
        results = classification["results"]
        paired = classification["paired_primary_comparisons"]["source_order_tie_aware"]["balanced_accuracy"]
        rows.append(
            {
                "Analysis": "Plausible-only APCA",
                "View": label,
                "Primary metric": number(results["stream_index_max"]["metrics"]["balanced_accuracy"]),
                "Reference metric": number(results["source_order_tie_aware"]["metrics"]["balanced_accuracy"]),
                "Paired difference": signed(paired["observed_difference"]),
                "95% CI": interval(paired),
            }
        )
    return rows


def lineage_stratum_table(data, benchmark, grouping="provider", include_all=False):
    gate = data["memorization_lineage_gate"][benchmark]
    slices = gate[f"{grouping}_lineage_slices"]
    entries = []
    if include_all:
        entries.append(("All configurations", gate["all_configurations"]))
    entries.extend((name, payload) for name, payload in slices.items())
    rows = []
    for lineage, payload in entries:
        strata = payload["correctness_evidence_strata"]
        exact = strata.get("exact_or_ast_present")
        semantic = strata.get("semantic_only")
        interaction = payload["exact_vs_semantic_rank_advantage"]

        def stratum_cells(result):
            if not result:
                return "0", "NA", "NA"
            difference = result["minimum_rank_minus_random"]["mrr"]
            return (
                f"{result['minimum_native_rank']['summary']['positive_pools']:,}",
                signed(difference["observed_difference"]),
                interval(difference),
            )

        exact_n, exact_difference, exact_interval = stratum_cells(exact)
        semantic_n, semantic_difference, semantic_interval = stratum_cells(semantic)
        rows.append(
            {
                "Lineage": lineage,
                "Exact/AST pools": exact_n,
                "Exact/AST min-rank - random": exact_difference,
                "Exact/AST 95% CI": exact_interval,
                "Semantic-only pools": semantic_n,
                "Semantic-only min-rank - random": semantic_difference,
                "Semantic-only 95% CI": semantic_interval,
                "Exact - semantic advantage": (
                    signed(interaction["observed_difference_in_differences"])
                    if interaction["status"] == "estimated"
                    else "NA"
                ),
                "Interaction 95% CI": (
                    interval(interaction)
                    if interaction["status"] == "estimated"
                    else "NA"
                ),
            }
        )
    return rows


def family_holdout_table(data):
    gate = data["memorization_lineage_gate"]["lineage_holdout"]
    rows = []
    for grouping_label, grouping in [
        ("Named-model", "named_model"),
        ("Provider", "provider"),
    ]:
        payload = gate[grouping]
        views = [("Overall lineage-contexts", payload["overall"])]
        views.extend(
            (lineage, result)
            for lineage, result in payload["by_heldout_lineage"].items()
        )
        for heldout, result in views:
            methods = by_name(result["results"], "method")
            comparison = result["paired_comparisons"][
                "unseen_stream_fallback"
            ]["mrr_vs_source_order"]
            rows.append(
                {
                    "Grouping": grouping_label,
                    "Held-out lineage": heldout,
                    "Positive lineage-contexts": f"{methods['source_order_tie_aware']['summary']['positive_pools']:,}",
                    "Fallback MRR": number(
                        methods["unseen_stream_fallback"]["summary"]["mrr"]
                    ),
                    "Min-rank MRR": number(
                        methods["source_order_tie_aware"]["summary"]["mrr"]
                    ),
                    "Difference": signed(comparison["observed_difference"]),
                    "95% CI": interval(comparison),
                }
            )
    return rows


def validation_stage_signal_table(data):
    view = data["validation_funnel_signal"]["views"][
        "candidate_primary_no_conflicts"
    ]
    stages = [
        (
            "compile",
            "Compiles",
            "Negative association; native rank is not a general code-quality score.",
        ),
        (
            "test_given_compile",
            "Passes tests | compiles",
            "Modest early-position signal.",
        ),
        (
            "reference_given_test",
            "Exact/AST reference match | passes tests",
            "Strongest native-rank endpoint.",
        ),
        (
            "adjudicated_given_test_nonreference",
            "Adjudicated | test-passing non-reference",
            "Review selection is only weakly associated with rank.",
        ),
        (
            "semantic_correct_given_adjudicated_nonreference",
            "Semantic correctness | adjudicated non-reference",
            "Weak and statistically unresolved at the 0.5 boundary.",
        ),
        (
            "final_correct_given_test_adjudicated",
            "Final correctness | adjudicated test-passing",
            "Mixes reference-equivalent and semantic-only positives.",
        ),
    ]
    rows = []
    for key, label, interpretation in stages:
        result = view[key]
        ci = result["bug_cluster_bootstrap_95ci"]["source_order_auc"]
        rows.append(
            {
                "Validation endpoint": label,
                "Eligible": f"{result['eligible_count']:,}",
                "Positive": f"{result['positive_count']:,}",
                "Positive rate": percent(result["positive_rate"]),
                "Native-rank AUC": number(result["source_order_auc"]),
                "95% CI": (
                    f"[{number(ci['low'])}, {number(ci['high'])}]"
                ),
                "Interpretation": interpretation,
            }
        )
    return rows


def stage_aware_auc_table(data):
    metrics = data["stage_aware_policy"]["stage_metrics"]
    stages = [
        ("compile", "Compile"),
        ("test_given_compile", "Test | compile"),
        ("correct_given_test", "Final correct | test"),
        ("semantic_correct_nonreference", "Semantic non-reference"),
    ]
    methods = [
        ("native_order", "Minimum native rank"),
        ("codet5_similarity", "Raw CodeT5+ cosine"),
        ("provenance", "Nested provenance"),
        ("fusion", "Nested provenance + content"),
        ("stage_selected", "Nested stage-selected"),
    ]
    rows = []
    for method, label in methods:
        row = {"Method": label}
        for stage, stage_label in stages:
            row[f"{stage_label} AUC"] = number(metrics[stage][method]["roc_auc"])
        rows.append(row)
    return rows


def stage_budget_one_table(data):
    budget = data["stage_aware_policy"]["all_context_budget_one"]
    summaries = budget["summaries"]
    paired = budget["paired_vs_native_order"]
    methods = [
        ("native_order", "Minimum native rank"),
        ("codet5_similarity", "Raw CodeT5+ cosine"),
        ("provenance_factorized", "Stage-factorized provenance"),
        ("fusion_factorized", "Stage-factorized fusion"),
        ("stage_selected_factorized", "Stage-selected factorization"),
        (
            "stage_selected_reference_excluded_factorized",
            "Stage-selected, reference-excluded final stage",
        ),
        (
            "provenance_codet5_semantic_factorized",
            "Provenance early stages + CodeT5+ semantic stage",
        ),
    ]
    rows = []
    for method, label in methods:
        summary = summaries[method]
        if method == "native_order":
            gain = "-"
            gain_ci = "-"
        else:
            comparison = paired[method]
            gain = points(
                comparison["verified_success_difference_vs_native_order"]
            )
            gain_ci = (
                f"[{points(comparison['low'])}, {points(comparison['high'])}]"
            )
        rows.append(
            {
                "Method": label,
                "Verified budget-1 success": percent(
                    summary["verified_budget1_success"]
                ),
                "Possible success upper": percent(
                    summary["possible_budget1_success_upper"]
                ),
                "Gain vs native (pp)": gain,
                "95% CI (pp)": gain_ci,
            }
        )
    return rows


def risk_control_table(data):
    summaries = data["stage_aware_policy"]["risk_control"]["summaries"]
    lookup = {
        (row["method"], row["unknown_policy"], row["risk_target"]): row
        for row in summaries
    }
    specifications = [
        ("provenance", "pessimistic", 0.30),
        ("fusion", "pessimistic", 0.30),
        ("provenance", "pessimistic", 0.40),
        ("fusion", "pessimistic", 0.40),
        ("provenance", "complete_case", 0.40),
        ("fusion", "complete_case", 0.40),
        ("provenance", "pessimistic", 0.50),
        ("fusion", "pessimistic", 0.50),
    ]
    labels = {
        "provenance": "Stage-factorized provenance",
        "fusion": "Stage-factorized fusion",
    }
    rows = []
    for method, unknown_policy, target in specifications:
        result = lookup[(method, unknown_policy, target)]
        rows.append(
            {
                "Method": labels[method],
                "Unknown handling": unknown_policy.replace("_", " "),
                "Target wrong-accept risk": percent(target, 0),
                "Feasible folds": (
                    f"{result['feasible_fold_count']}/{result['fold_count']}"
                ),
                "Selected contexts": f"{result['selected_context_count']:,}",
                "Coverage": percent(result["coverage"]),
                "Correct / wrong / unknown": (
                    f"{result['verified_correct_count']:,} / "
                    f"{result['known_wrong_count']:,} / "
                    f"{result['unknown_count']:,}"
                ),
            }
        )
    return rows


def scheduler_cost_table(data):
    scheduler = data["adaptive_validation_scheduler"]
    summaries = {
        (row["cost_scenario"], row["unknown_world"], row["policy"]): row
        for row in scheduler["summaries"]
    }
    paired = {
        (
            row["cost_scenario"],
            row["unknown_world"],
            row["left"],
            row["right"],
        ): row
        for row in scheduler["paired_bug_bootstrap"]
    }
    labels = {
        "equal_actions": "Equal",
        "test_expensive": "Test expensive",
        "review_expensive": "Review expensive",
        "test_and_review_expensive": "Test + review expensive",
    }
    rows = []
    for scenario, label in labels.items():
        costs = scheduler["cost_scenarios"][scenario]
        native = summaries[(scenario, "pessimistic", "native_serial")]
        provenance = summaries[(scenario, "pessimistic", "provenance_serial")]
        fusion = summaries[(scenario, "pessimistic", "fusion_serial")]
        prov_gain = paired[
            (scenario, "pessimistic", "provenance_serial", "native_serial")
        ]
        fusion_gain = paired[
            (scenario, "pessimistic", "fusion_serial", "native_serial")
        ]
        prov_adaptive = paired[
            (
                scenario,
                "pessimistic",
                "provenance_adaptive",
                "provenance_serial",
            )
        ]
        fusion_adaptive = paired[
            (
                scenario,
                "pessimistic",
                "fusion_adaptive",
                "fusion_serial",
            )
        ]
        rows.append(
            {
                "Cost scenario": label,
                "Compile:test:review": (
                    f"{costs['compile']:g}:{costs['test']:g}:{costs['review']:g}"
                ),
                "Native AUC": number(native["normalized_budget_auc"], 4),
                "Provenance serial AUC": number(
                    provenance["normalized_budget_auc"], 4
                ),
                "Provenance gain 95% CI": (
                    f"{signed(prov_gain['difference'], 4)} "
                    f"[{signed(prov_gain['low'], 4)}, "
                    f"{signed(prov_gain['high'], 4)}]"
                ),
                "Fusion serial AUC": number(
                    fusion["normalized_budget_auc"], 4
                ),
                "Fusion gain 95% CI": (
                    f"{signed(fusion_gain['difference'], 4)} "
                    f"[{signed(fusion_gain['low'], 4)}, "
                    f"{signed(fusion_gain['high'], 4)}]"
                ),
                "Adaptive - serial": (
                    f"prov {signed(prov_adaptive['difference'], 4)}; "
                    f"fusion {signed(fusion_adaptive['difference'], 4)}"
                ),
            }
        )
    return rows


def scheduler_stratum_table(data):
    scheduler = data["adaptive_validation_scheduler"]
    summaries = {
        (
            row["cost_scenario"],
            row["unknown_world"],
            row["policy"],
            row["correctness_stratum"],
        ): row
        for row in scheduler["stratified_summaries"]
    }
    paired = {
        (
            row["cost_scenario"],
            row["unknown_world"],
            row["left"],
            row["right"],
            row["correctness_stratum"],
        ): row
        for row in scheduler["stratified_paired_bug_bootstrap"]
    }
    rows = []
    for stratum, stratum_label in [
        ("exact_or_ast", "Exact/AST"),
        ("semantic_only", "Semantic-only"),
    ]:
        for policy, policy_label in [
            ("native_serial", "Minimum native rank"),
            ("provenance_serial", "Stage-factorized provenance"),
            ("fusion_serial", "Stage-factorized fusion"),
            (
                "fusion_codet5_semantic_serial",
                "Fusion early stages + CodeT5+ semantic stage",
            ),
        ]:
            summary = summaries[
                ("equal_actions", "pessimistic", policy, stratum)
            ]
            if policy == "native_serial":
                gain = "-"
                gain_ci = "-"
            else:
                comparison = paired[
                    (
                        "equal_actions",
                        "pessimistic",
                        policy,
                        "native_serial",
                        stratum,
                    )
                ]
                gain = signed(comparison["difference"], 4)
                gain_ci = (
                    f"[{signed(comparison['low'], 4)}, "
                    f"{signed(comparison['high'], 4)}]"
                )
            rows.append(
                {
                    "Correctness stratum": stratum_label,
                    "Policy": policy_label,
                    "Contexts": f"{summary['reference_context_count']:,}",
                    "Normalized budget AUC": number(
                        summary["normalized_budget_auc"], 4
                    ),
                    "Gain vs native": gain,
                    "95% CI": gain_ci,
                }
            )
    return rows


def stream_health_diagnostic_table(data):
    diagnostics = data["outcome_conditioned_stream_health"][
        "sibling_outcome_diagnostics"
    ]
    labels = {
        "compile": "Compile",
        "test_given_compile": "Test | compile",
        "correct_given_test": "Final correct | test",
        "semantic_correct_nonreference": "Semantic non-reference",
    }
    rows = []
    for endpoint, label in labels.items():
        result = diagnostics[endpoint]
        ci = result["bug_cluster_bootstrap_95ci"]
        rows.append(
            {
                "Sibling endpoint": label,
                "Candidates with observed sibling": (
                    f"{result['candidate_count_with_observed_sibling']:,}"
                ),
                "Positive": f"{result['positive_count']:,}",
                "Leave-one-candidate-out AUC": number(
                    result["leave_one_candidate_out_sibling_auc"], 4
                ),
                "95% CI": (
                    f"[{number(ci['low'], 4)}, {number(ci['high'], 4)}]"
                ),
            }
        )
    return rows


def stream_health_policy_table(data):
    result = data["outcome_conditioned_stream_health"]
    comparisons = {
        (
            row["cost_scenario"],
            row["method"],
            row["reference"],
        ): row
        for row in result["paired_bug_bootstrap"]
        if row["unknown_world"] == "pessimistic"
        and row["strength"] == 5.0
    }
    labels = {
        "equal_actions": "Equal",
        "test_expensive": "Test expensive",
        "review_expensive": "Review expensive",
        "test_and_review_expensive": "Test + review expensive",
    }
    rows = []
    for scenario, scenario_label in labels.items():
        for method in ("provenance", "fusion"):
            serial = comparisons[(scenario, method, "serial")]
            adaptive = comparisons[
                (scenario, method, "adaptive_static_beliefs")
            ]
            rows.append(
                {
                    "Cost scenario": scenario_label,
                    "Base probabilities": method.capitalize(),
                    "Stream health - serial": signed(
                        serial["difference"], 4
                    ),
                    "Serial 95% CI": (
                        f"[{signed(serial['low'], 4)}, "
                        f"{signed(serial['high'], 4)}]"
                    ),
                    "Stream health - static adaptive": signed(
                        adaptive["difference"], 4
                    ),
                    "Adaptive 95% CI": (
                        f"[{signed(adaptive['low'], 4)}, "
                        f"{signed(adaptive['high'], 4)}]"
                    ),
                }
            )
    return rows


def practical_pod_label_table(data):
    result = data["practical_pod_common_split"]
    audit = result["label_provenance_audit"]
    worlds = result["worlds"]
    released = worlds["released"]["dataset"]
    verified = worlds["verified_only"]["dataset"]
    optimistic = worlds["optimistic_unknown"]["dataset"]
    full_cross = audit["full_170_external_vs_provenance_label"]
    return [
        {
            "View": "Released package (all 170)",
            "Candidates": "170",
            "Assigned correct": f"{full_cross['correct::correct']:,}",
            "Assigned incorrect": (
                f"{full_cross['overfitting::incorrect'] + full_cross['overfitting::unknown']:,}"
            ),
            "Provenance-unresolved": f"{full_cross['overfitting::unknown']:,}",
            "Key result": "80 released negatives were not semantically reviewed",
        },
        {
            "View": "Five-detector common split",
            "Candidates": f"{released['patches']:,}",
            "Assigned correct": f"{released['correct_patches']:,}",
            "Assigned incorrect": f"{released['overfitting_patches']:,}",
            "Provenance-unresolved": (
                f"{audit['common_unreviewed_candidates']:,}"
            ),
            "Key result": (
                f"{percent(audit['common_unreviewed_fraction_of_all'])} of all; "
                f"{percent(audit['common_unreviewed_fraction_of_released_overfitting'])} "
                "of released negatives"
            ),
        },
        {
            "View": "Verified-only sensitivity",
            "Candidates": f"{verified['patches']:,}",
            "Assigned correct": f"{verified['correct_patches']:,}",
            "Assigned incorrect": f"{verified['overfitting_patches']:,}",
            "Provenance-unresolved": "0",
            "Key result": (
                f"Only {verified['mixed_label_bugs']} bugs retain mixed labels"
            ),
        },
        {
            "View": "Optimistic unknown bound",
            "Candidates": f"{optimistic['patches']:,}",
            "Assigned correct": f"{optimistic['correct_patches']:,}",
            "Assigned incorrect": f"{optimistic['overfitting_patches']:,}",
            "Provenance-unresolved": "0 (assumed correct)",
            "Key result": "Opposite extreme assignment, not ground truth",
        },
    ]


def practical_pod_ranking_table(data):
    result = data["practical_pod_common_split"]
    world_labels = {
        "released": "Released / pessimistic",
        "verified_only": "Verified only",
        "optimistic_unknown": "Optimistic unknown",
    }
    methods = [
        "source_order",
        "yang_entropy_delta",
        "invalidator",
        "fixcheck",
        "llm4patchcorrect",
        "tian_dl4patchcorrectness",
        "stage_selected",
        "random_expected",
    ]
    rows = []
    for world_name, world_label in world_labels.items():
        ranking = result["worlds"][world_name]["operational_ranking"]
        for method in methods:
            summary = ranking["summaries"][method]
            paired = ranking["paired_vs_native_order"].get(method)
            rows.append(
                {
                    "Label world": world_label,
                    "Method": summary["display_name"],
                    "Positive bugs": f"{summary['positive_bugs']:,}",
                    "MRR": number(summary["mrr"], 4),
                    "R@1": percent(summary["recall@1"]),
                    "R@3": percent(summary["recall@3"]),
                    "Mean first rank": number(
                        summary["mean_first_correct_rank"], 3
                    ),
                    "MRR vs native": (
                        signed(paired["observed"]["mrr_diff"], 4)
                        if paired
                        else "-"
                    ),
                    "95% CI": (
                        f"[{signed(paired['confidence_intervals']['mrr_diff']['low'], 4)}, "
                        f"{signed(paired['confidence_intervals']['mrr_diff']['high'], 4)}]"
                        if paired
                        else "-"
                    ),
                }
            )
    return rows


def practical_pod_classification_table(data):
    result = data["practical_pod_common_split"]
    world_labels = {
        "released": "Released / pessimistic",
        "verified_only": "Verified only",
        "optimistic_unknown": "Optimistic unknown",
    }
    methods = [
        "yang_entropy_delta",
        "invalidator",
        "fixcheck",
        "llm4patchcorrect",
        "tian_dl4patchcorrectness",
        "stage_selected",
    ]
    rows = []
    for world_name, world_label in world_labels.items():
        classification = result["worlds"][world_name]["classification"]
        for method in methods:
            item = classification[method]
            metrics = item["metrics"]
            ci = item["bug_clustered_95ci"]["balanced_accuracy"]
            rows.append(
                {
                    "Label world": world_label,
                    "Method": item["display_name"],
                    "Balanced accuracy": number(
                        metrics["balanced_accuracy"], 3
                    ),
                    "BA 95% CI": (
                        f"[{number(ci['low'], 3)}, {number(ci['high'], 3)}]"
                    ),
                    "MCC": (
                        number(metrics["mcc"], 3)
                        if metrics["mcc"] is not None
                        else "undefined"
                    ),
                    "Correct recall": percent(metrics["positive_recall"]),
                    "Overfit recall": percent(metrics["negative_recall"]),
                }
            )
    return rows


def find_prevarank_protocol(data, pool_type, label_world):
    return next(
        protocol
        for protocol in data["prevarank_llm"]["protocols"]
        if protocol["pool_type"] == pool_type
        and protocol["label_world"] == label_world
    )


def prevarank_reproduction_table(data):
    audit = data["prevarank_reproduction"]
    summary = audit["summary"]
    manifest = load_json(AUXILIARY_INPUTS["prevarank_preparation_manifest"])
    mixed = load_json(AUXILIARY_INPUTS["prevarank_mixed_verification"])
    stream = load_json(AUXILIARY_INPUTS["prevarank_stream_verification"])
    counts = manifest["counts"]
    exact_or_metadata = (
        summary["divergence_classes"]["exact"]
        + summary["divergence_classes"]["metadata_only"]
    )
    return [
        {
            "Audit item": "Released classical-APR workbooks",
            "Count": f"{summary['workbook_count']}/{summary['workbook_count']}",
            "Result": "All eight tool runs exit zero; output sets complete",
        },
        {
            "Audit item": "Logically exact reproduction",
            "Count": (
                f"{summary['divergence_classes']['exact']}/"
                f"{summary['workbook_count']}"
            ),
            "Result": percent(summary["exact_workbook_rate"], 2),
        },
        {
            "Audit item": "Patch-order reproduction",
            "Count": f"{exact_or_metadata}/{summary['workbook_count']}",
            "Result": percent(summary["patch_order_match_rate"], 2),
        },
        {
            "Audit item": "Different parsed patch multiset",
            "Count": (
                f"{summary['patch_multiset_mismatch_workbook_count']}/"
                f"{summary['workbook_count']}"
            ),
            "Result": "Reported, never silently discarded",
        },
        {
            "Audit item": "LLM candidates on released-parser support",
            "Count": (
                f"{counts['supported_candidate_count']}/"
                f"{counts['candidate_count']}"
            ),
            "Result": percent(
                counts["supported_candidate_count"]
                / counts["candidate_count"],
                2,
            ),
        },
        {
            "Audit item": "Mixed-generator outputs independently verified",
            "Count": (
                f"{mixed['output_file_count']}/"
                f"{counts['pool_counts']['mixed']}"
            ),
            "Result": "Complete; zero suspicious runtime failures",
        },
        {
            "Audit item": "Per-generator outputs independently verified",
            "Count": (
                f"{stream['output_file_count']}/"
                f"{counts['pool_counts']['stream']}"
            ),
            "Result": "Complete; zero suspicious runtime failures",
        },
    ]


def prevarank_world_table(data):
    world_labels = {
        "adjudicated_only": "Adjudicated only",
        "pessimistic_unknown": "Unknown = incorrect",
        "optimistic_unknown": "Unknown = correct",
    }
    rows = []
    for pool_type, pool_label in (
        ("mixed", "Mixed generators"),
        ("stream", "One generator stream"),
    ):
        for world_name, world_label in world_labels.items():
            protocol = find_prevarank_protocol(data, pool_type, world_name)
            methods = protocol["methods"]
            native = methods["native_order_tie_aware"]["summary"]
            prevarank = methods["prevarank_released_rank"]["summary"]
            random = methods["random_tie_aware"]["summary"]
            vs_native = protocol["paired_comparisons_vs_native"][
                "prevarank_released_rank"
            ]["mrr_vs_native"]
            vs_random = protocol[
                "paired_prevarank_comparisons_vs_random"
            ]["prevarank_released_rank"]["mrr_vs_random"]
            rows.append(
                {
                    "Pool": pool_label,
                    "Label world": world_label,
                    "Informative pools": f"{protocol['informative_pool_count']:,}",
                    "Native MRR": number(native["mrr"], 4),
                    "PrevaRank MRR": number(prevarank["mrr"], 4),
                    "Random MRR": number(random["mrr"], 4),
                    "PrevaRank - native": signed(
                        vs_native["observed_difference"], 4
                    ),
                    "Native 95% CI": (
                        f"[{signed(vs_native['ci_low'], 4)}, "
                        f"{signed(vs_native['ci_high'], 4)}]"
                    ),
                    "PrevaRank - random": signed(
                        vs_random["observed_difference"], 4
                    ),
                    "Random 95% CI": (
                        f"[{signed(vs_random['ci_low'], 4)}, "
                        f"{signed(vs_random['ci_high'], 4)}]"
                    ),
                }
            )
    return rows


def prevarank_adjudicated_metric_table(data):
    rows = []
    for pool_type, pool_label in (
        ("mixed", "Mixed generators"),
        ("stream", "One generator stream"),
    ):
        protocol = find_prevarank_protocol(
            data, pool_type, "adjudicated_only"
        )
        native = protocol["methods"]["native_order_tie_aware"]["summary"]
        prevarank = protocol["methods"]["prevarank_released_rank"]["summary"]
        comparisons = protocol["paired_comparisons_vs_native"][
            "prevarank_released_rank"
        ]
        rows.append(
            {
                "Pool": pool_label,
                "Metric": "MRR",
                "Native": number(native["mrr"], 4),
                "PrevaRank": number(prevarank["mrr"], 4),
                "Difference": signed(
                    comparisons["mrr_vs_native"]["observed_difference"], 4
                ),
                "95% CI": (
                    f"[{signed(comparisons['mrr_vs_native']['ci_low'], 4)}, "
                    f"{signed(comparisons['mrr_vs_native']['ci_high'], 4)}]"
                ),
            }
        )
        rows.append(
            {
                "Pool": pool_label,
                "Metric": "Recall@1",
                "Native": number(native["recall@1"], 4),
                "PrevaRank": number(prevarank["recall@1"], 4),
                "Difference": signed(
                    comparisons["recall_at_1_vs_native"][
                        "observed_difference"
                    ],
                    4,
                ),
                "95% CI": (
                    f"[{signed(comparisons['recall_at_1_vs_native']['ci_low'], 4)}, "
                    f"{signed(comparisons['recall_at_1_vs_native']['ci_high'], 4)}]"
                ),
            }
        )
        rows.append(
            {
                "Pool": pool_label,
                "Metric": "Pairwise AUC",
                "Native": number(native["pairwise_auc_macro"], 4),
                "PrevaRank": number(prevarank["pairwise_auc_macro"], 4),
                "Difference": signed(
                    comparisons["pairwise_auc_vs_native"][
                        "observed_difference"
                    ],
                    4,
                ),
                "95% CI": (
                    f"[{signed(comparisons['pairwise_auc_vs_native']['ci_low'], 4)}, "
                    f"{signed(comparisons['pairwise_auc_vs_native']['ci_high'], 4)}]"
                ),
            }
        )
    return rows


def prevarank_shift_table(data):
    shift = data["prevarank_domain_shift"]
    classical = shift["classical_apr"]
    llm = shift["llm_apr"]
    inheritance = shift["llm_released_rank_input_order_inheritance"]
    comparison = shift["comparison"]
    return [
        {
            "Diagnostic": "No-Category rate",
            "Classical APR": percent(classical["no_category_rate"], 2),
            "LLM APR": percent(llm["no_category_rate"], 2),
            "Comparison": (
                f"{points(comparison['no_category_rate_difference'], 2)} pp, "
                f"95% CI {points_interval(comparison['no_category_rate_difference_ci'], 2)}"
            ),
        },
        {
            "Diagnostic": "Candidates participating in historical-value ties",
            "Classical APR": percent(
                classical["historical_value_tied_candidate_rate"], 2
            ),
            "LLM APR": percent(
                llm["historical_value_tied_candidate_rate"], 2
            ),
            "Comparison": "Descriptive",
        },
        {
            "Diagnostic": "Pools with one historical value",
            "Classical APR": percent(
                classical["all_same_historical_value_pool_rate"], 2
            ),
            "LLM APR": percent(
                llm["all_same_historical_value_pool_rate"], 2
            ),
            "Comparison": "Descriptive",
        },
        {
            "Diagnostic": "Category-distribution divergence",
            "Classical APR": "-",
            "LLM APR": "-",
            "Comparison": (
                "Jensen-Shannon "
                f"{comparison['category_distribution_jensen_shannon_divergence']:.3f}"
            ),
        },
        {
            "Diagnostic": "Final rank agrees with input within value ties",
            "Classical APR": "-",
            "LLM APR": percent(
                inheritance[
                    "historical_value_tied_pair_input_order_agreement"
                ],
                2,
            ),
            "Comparison": (
                f"{inheritance['historical_value_tied_pair_count']:,} tied pairs"
            ),
        },
        {
            "Diagnostic": "Exact supplied position retained",
            "Classical APR": "-",
            "LLM APR": percent(
                inheritance["exact_input_position_retained_rate"], 2
            ),
            "Comparison": (
                f"{inheritance['exact_input_position_retained_count']:,}/"
                f"{inheritance['candidate_count']:,} candidates"
            ),
        },
    ]


def find_prevarank_order_world(data, label_world):
    return next(
        world
        for world in data["prevarank_input_order"]["label_worlds"]
        if world["label_world"] == label_world
    )


def prevarank_input_order_table(data):
    result = data["prevarank_input_order"]
    reconciliation = result["reconciliation"]
    sensitivity = reconciliation["released_rank_order_sensitivity"]
    alignments = reconciliation["input_order_alignment_matrix"][
        "alignments"
    ]
    rows = [
        {
            "Diagnostic": "Candidate positions changed",
            "Canonical/native input": "Reference order",
            "Stable-hash input": (
                f"{reconciliation['input_position_change_count']:,}/"
                f"{reconciliation['candidate_instance_count']:,}"
            ),
            "Paired result": percent(
                reconciliation["input_position_change_rate"], 2
            ),
        },
        {
            "Diagnostic": "Released candidate ranks changed",
            "Canonical/native input": "-",
            "Stable-hash input": (
                f"{reconciliation['released_rank_change_count']:,}/"
                f"{reconciliation['candidate_instance_count']:,}"
            ),
            "Paired result": percent(
                reconciliation["released_rank_change_rate"], 2
            ),
        },
        {
            "Diagnostic": "Pool top patch changed",
            "Canonical/native input": "-",
            "Stable-hash input": (
                f"{sensitivity['pool_top_patch_change_count']:,}/"
                f"{sensitivity['pool_count']:,}"
            ),
            "Paired result": percent(
                sensitivity["pool_top_patch_change_rate"], 2
            ),
        },
        {
            "Diagnostic": "Normalized-patch pair order reversed",
            "Canonical/native input": "-",
            "Stable-hash input": (
                f"{sensitivity['pairwise_order_discordance_count']:,}/"
                f"{sensitivity['pairwise_order_comparison_count']:,}"
            ),
            "Paired result": percent(
                sensitivity[
                    "pairwise_order_discordance_rate_micro"
                ],
                2,
            ),
        },
        {
            "Diagnostic": "Output agrees with own input within value ties",
            "Canonical/native input": percent(
                alignments["canonical_rank_vs_canonical_input"][
                    "historical_value_tied_pair_input_order_agreement"
                ],
                2,
            ),
            "Stable-hash input": percent(
                alignments["shuffled_rank_vs_shuffled_input"][
                    "historical_value_tied_pair_input_order_agreement"
                ],
                2,
            ),
            "Paired result": (
                "Cross-order "
                f"{percent(alignments['canonical_rank_vs_shuffled_input']['historical_value_tied_pair_input_order_agreement'], 2)} / "
                f"{percent(alignments['shuffled_rank_vs_canonical_input']['historical_value_tied_pair_input_order_agreement'], 2)}"
            ),
        },
        {
            "Diagnostic": "Category / bug type / historical value changes",
            "Canonical/native input": "Reference features",
            "Stable-hash input": "Same candidates",
            "Paired result": (
                f"{reconciliation['category_change_count']} / "
                f"{reconciliation['bug_type_change_count']} / "
                f"{reconciliation['historical_value_change_count']}"
            ),
        },
    ]
    labels = {
        "adjudicated_only": "Adjudicated MRR",
        "pessimistic_unknown": "Pessimistic-Unknown MRR",
        "optimistic_unknown": "Optimistic-Unknown MRR",
    }
    for world_name, label in labels.items():
        world = find_prevarank_order_world(data, world_name)
        canonical = world["methods"]["canonical_released_rank"]["summary"]
        shuffled = world["methods"]["shuffled_released_rank"]["summary"]
        comparison = world["paired_comparisons"][
            "shuffled_rank_minus_canonical_rank"
        ]["mrr"]
        rows.append(
            {
                "Diagnostic": label,
                "Canonical/native input": number(canonical["mrr"], 4),
                "Stable-hash input": number(shuffled["mrr"], 4),
                "Paired result": (
                    f"{signed(comparison['observed_difference'], 4)}, "
                    f"95% CI [{signed(comparison['ci_low'], 4)}, "
                    f"{signed(comparison['ci_high'], 4)}]"
                ),
            }
        )
    return rows


def shift_result(data, benchmark):
    result = data["shift_aware_safe_scheduler"]
    return (
        result["internal"]
        if benchmark == "defects4j"
        else result["external"][benchmark]
    )


def shift_action_summary(result, method):
    if "primary_actions" in result and method == "safe_gate_q95_r20":
        return result["primary_actions"]
    if "action_summaries" in result:
        return result["action_summaries"][method]
    counts = Counter()
    summaries = []
    for fold in result["fold_audit"]:
        summary = fold["test_actions"][method]
        counts.update(summary["action_counts"])
        summaries.append(summary)
    override_bugs = sum(row["override_bug_count"] for row in summaries)
    weighted_harm = sum(
        (row["mean_override_bug_harm"] or 0.0) * row["override_bug_count"]
        for row in summaries
    )
    return {
        "context_count": sum(row["context_count"] for row in summaries),
        "action_counts": dict(counts),
        "override_context_rate": (
            counts["override"]
            / sum(row["context_count"] for row in summaries)
        ),
        "override_bug_count": override_bugs,
        "mean_override_bug_harm": (
            weighted_harm / override_bugs if override_bugs else None
        ),
    }


def shift_safe_performance_table(data):
    labels = {
        "defects4j": "Defects4J nested",
        "humanevaljava": "HumanEval-Java",
        "gitbugjava": "GitBug-Java full",
        "gitbugjava_top10": "GitBug-Java top-10",
    }
    rows = []
    for benchmark, label in labels.items():
        result = shift_result(data, benchmark)
        summary = result["primary_summary"]
        mrr = summary["safe_gate_mrr_vs_native"]
        budget = summary["safe_gate_budget1_vs_native"]
        rows.append(
            {
                "Benchmark": label,
                "Contexts": (
                    f"{summary['native_budget1']['universe_contexts']:,}"
                ),
                "Solvable": f"{summary['native']['positive_pools']:,}",
                "Native MRR": number(summary["native"]["mrr"], 4),
                "Always-stream MRR": number(
                    summary["always_stream"]["mrr"], 4
                ),
                "Safe-gate MRR": number(summary["safe_gate"]["mrr"], 4),
                "MRR gain": signed(mrr["observed_difference"], 4),
                "MRR 95% CI": (
                    f"[{signed(mrr['ci_low'], 4)}, "
                    f"{signed(mrr['ci_high'], 4)}]"
                ),
                "Native budget-1": percent(
                    summary["native_budget1"][
                        "verified_budget1_success"
                    ],
                    2,
                ),
                "Safe budget-1": percent(
                    summary["safe_gate_budget1"][
                        "verified_budget1_success"
                    ],
                    2,
                ),
                "Budget-1 gain": points(
                    budget["observed_difference"], 2
                ),
                "Budget 95% CI": points_interval(budget, 2),
            }
        )
    return rows


def shift_safe_action_table(data):
    labels = {
        "defects4j": "Defects4J nested",
        "humanevaljava": "HumanEval-Java",
        "gitbugjava": "GitBug-Java full",
        "gitbugjava_top10": "GitBug-Java top-10",
    }
    method = "safe_gate_q95_r20"
    rows = []
    for benchmark, label in labels.items():
        result = shift_result(data, benchmark)
        summary = shift_action_summary(result, method)
        counts = summary["action_counts"]
        rows.append(
            {
                "Benchmark": label,
                "Agreement": f"{counts.get('agreement', 0):,}",
                "Override": f"{counts.get('override', 0):,}",
                "Fallback": f"{counts.get('fallback', 0):,}",
                "Defer": f"{counts.get('defer', 0):,}",
                "Override rate": percent(
                    summary["override_context_rate"], 1
                ),
                "Mean override bug harm": (
                    number(summary["mean_override_bug_harm"], 4)
                    if summary["mean_override_bug_harm"] is not None
                    else "-"
                ),
            }
        )
    return rows


def shift_safe_cost_table(data):
    labels = {
        "defects4j": "Defects4J nested",
        "humanevaljava": "HumanEval-Java",
        "gitbugjava": "GitBug-Java full",
        "gitbugjava_top10": "GitBug-Java top-10",
    }
    rows = []
    for benchmark, label in labels.items():
        summary = shift_result(data, benchmark)["primary_summary"]
        mrr = summary["safe_gate_mrr_vs_always_stream"]
        budget = summary["safe_gate_budget1_vs_always_stream"]
        rows.append(
            {
                "Benchmark": label,
                "Gate - stream MRR": signed(
                    mrr["observed_difference"], 4
                ),
                "MRR 95% CI": (
                    f"[{signed(mrr['ci_low'], 4)}, "
                    f"{signed(mrr['ci_high'], 4)}]"
                ),
                "Gate - stream budget-1": points(
                    budget["observed_difference"], 2
                ),
                "Budget 95% CI": points_interval(budget, 2),
            }
        )
    return rows


def shift_safe_risk_fold_table(data):
    result = data["shift_aware_safe_scheduler"]
    method = "safe_gate_q95_r20"
    rows = []
    for fold in result["internal"]["fold_audit"]:
        selection = fold["selections"][method]
        test = fold["test_actions"][method]
        rows.append(
            {
                "Test fold": fold["test_fold"],
                "Calibration contexts": (
                    f"{selection['selected_calibration_contexts']:,}"
                ),
                "Calibration bugs": (
                    f"{selection['selected_calibration_bugs']:,}"
                ),
                "Calibrated harm upper": number(
                    selection["selected_calibration_harm_upper"], 4
                ),
                "Test overrides": (
                    f"{test['action_counts'].get('override', 0):,}"
                ),
                "Test mean harm": number(
                    test["mean_override_bug_harm"], 4
                ),
                "Within bound": (
                    "yes"
                    if test["realized_harm_within_calibration_upper"]
                    else "no"
                ),
            }
        )
    return rows


def shift_safe_sensitivity_table(data):
    result = data["shift_aware_safe_scheduler"]["internal"]
    ranking = {
        row["method"]: row["summary"]
        for row in result["ranking"]["results"]
    }
    rows = []
    for risk_target in (0.05, 0.10, 0.20, 0.30):
        method = f"safe_gate_q95_r{int(100 * risk_target):02d}"
        summary = ranking[method]
        comparison = result["ranking"]["paired_comparisons"][method][
            "mrr_vs_source_order"
        ]
        budget = result["all_context_budget_one"]["paired_vs_native"][
            method
        ]
        actions = shift_action_summary(result, method)
        rows.append(
            {
                "Harm target": percent(risk_target, 0),
                "Overrides": (
                    f"{actions['action_counts'].get('override', 0):,}"
                ),
                "Fallbacks": (
                    f"{actions['action_counts'].get('fallback', 0):,}"
                ),
                "Defers": f"{actions['action_counts'].get('defer', 0):,}",
                "MRR": number(summary["mrr"], 4),
                "MRR gain": signed(
                    comparison["observed_difference"], 4
                ),
                "MRR 95% CI": (
                    f"[{signed(comparison['ci_low'], 4)}, "
                    f"{signed(comparison['ci_high'], 4)}]"
                ),
                "Budget-1 gain": points(
                    budget["observed_difference"], 2
                ),
                "Budget 95% CI": points_interval(budget, 2),
            }
        )
    return rows


def shift_safe_stratum_table(data):
    labels = {
        "defects4j": "Defects4J nested",
        "humanevaljava": "HumanEval-Java",
        "gitbugjava": "GitBug-Java full",
        "gitbugjava_top10": "GitBug-Java top-10",
    }
    stratum_labels = {
        "exact_or_ast_present": "Exact/AST present",
        "semantic_only": "Semantic only",
    }
    method = "safe_gate_q95_r20"
    rows = []
    for benchmark, benchmark_label in labels.items():
        result = shift_result(data, benchmark)
        summary = next(
            row
            for row in result["ranking"]["results"]
            if row["method"] == method
        )
        comparisons = result["ranking"]["paired_comparisons"][method][
            "mrr_vs_source_order_by_stratum"
        ]
        for stratum, stratum_label in stratum_labels.items():
            item = summary["positive_provenance_strata"].get(stratum)
            comparison = comparisons.get(stratum)
            if not item or not comparison:
                continue
            rows.append(
                {
                    "Benchmark": benchmark_label,
                    "Correctness stratum": stratum_label,
                    "Pools": f"{item['positive_pools']:,}",
                    "Safe-gate MRR": number(item["mrr"], 4),
                    "MRR gain": signed(
                        comparison["observed_difference"], 4
                    ),
                    "95% CI": (
                        f"[{signed(comparison['ci_low'], 4)}, "
                        f"{signed(comparison['ci_high'], 4)}]"
                    ),
                }
            )
    return rows


def shift_safe_source_config_table(data):
    counts = data["shift_aware_safe_scheduler"]["internal"][
        "primary_actions"
    ]["source_config_action_counts"]
    rows = []
    for source_config, actions in sorted(counts.items()):
        total = sum(actions.values())
        rows.append(
            {
                "Source configuration": source_config,
                "Context-source incidences": f"{total:,}",
                "Agreement": f"{actions.get('agreement', 0):,}",
                "Override": f"{actions.get('override', 0):,}",
                "Fallback": f"{actions.get('fallback', 0):,}",
                "Defer": f"{actions.get('defer', 0):,}",
                "Override incidence": percent(
                    actions.get("override", 0) / total if total else 0,
                    1,
                ),
            }
        )
    return rows


def repairbench_campaign_table(data):
    audit = data["repairbench_import_audit"]
    integrity = data["repairbench_campaign_integrity"]
    sizes = integrity["campaign_sizes"]
    overlap = integrity["candidate_overlap"]
    mechanics = integrity["generation_mechanics"]["model_counts"]
    reference = audit["candidate_reference_labels"]
    return [
        {
            "Quantity": "Unique candidates",
            "RepairLLaMA campaign": f"{sizes['old_candidates']:,}",
            "RepairBench campaign": f"{sizes['new_candidates']:,}",
            "Boundary": (
                f"{overlap['candidate_identity_overlap']:,} exact identities "
                f"shared ({percent(overlap['new_candidate_overlap_rate'], 2)} "
                "of RepairBench)"
            ),
        },
        {
            "Quantity": "Exact source configurations",
            "RepairLLaMA campaign": f"{sizes['old_source_configs']:,}",
            "RepairBench campaign": f"{sizes['new_source_configs']:,}",
            "Boundary": (
                f"{sizes['shared_exact_source_configs']:,} exact IDs shared"
            ),
        },
        {
            "Quantity": "GitBug-Java contexts",
            "RepairLLaMA campaign": f"{sizes['old_contexts']:,}",
            "RepairBench campaign": f"{sizes['new_contexts']:,}",
            "Boundary": (
                f"{sizes['shared_contexts']:,} shared; campaign shift, not "
                "benchmark independence"
            ),
        },
        {
            "Quantity": "Included occurrences",
            "RepairLLaMA campaign": "-",
            "RepairBench campaign": (
                f"{audit['deduplication']['included_occurrences']:,}"
            ),
            "Boundary": (
                f"{audit['deduplication']['occurrences_removed_by_exact_patch_deduplication']:,} "
                "duplicate occurrences collapsed"
            ),
        },
        {
            "Quantity": "Reference correct / incorrect / Unknown",
            "RepairLLaMA campaign": "-",
            "RepairBench campaign": (
                f"{reference['correct']:,} / {reference['incorrect']:,} / "
                f"{reference['unknown']:,}"
            ),
            "Boundary": "Test-passing nonmatches remain Unknown",
        },
        {
            "Quantity": "Generation mechanics",
            "RepairLLaMA campaign": "-",
            "RepairBench campaign": (
                f"{mechanics['repeated_responses']} repeated-response; "
                f"{mechanics['single_response_multiple_choices']} "
                "single-response multi-choice"
            ),
            "Boundary": "Index means returned-array position",
        },
    ]


def repairbench_merged_ranking_table(data):
    result = data["repairbench_external_campaign"]
    worlds = {
        "test_plausibility": "Test plausibility",
        "reference_complete_case": "Reference complete case",
        "reference_pessimistic": "Reference pessimistic",
    }
    rows = []
    for world, label in worlds.items():
        payload = result["worlds"][world]
        ranking = payload["merged"]["ranking"]
        methods = ranking["methods"]
        index_random = ranking["comparisons"]["returned_index_minus_random"][
            "mrr"
        ]
        similarity_index = ranking["comparisons"][
            "codet5_similarity_minus_returned_index"
        ]["mrr"]
        rows.append(
            {
                "Endpoint": label,
                "Candidates": f"{payload['candidate_count']:,}",
                "Positive contexts": (
                    f"{methods['returned_index']['summary']['positive_pools']:,}"
                ),
                "Random MRR": number(
                    methods["random_expected"]["summary"]["mrr"], 4
                ),
                "Returned MRR": number(
                    methods["returned_index"]["summary"]["mrr"], 4
                ),
                "CodeT5+ similarity MRR": number(
                    methods["codet5_similarity"]["summary"]["mrr"], 4
                ),
                "Returned - random": signed(
                    index_random["observed_difference"], 4
                ),
                "Returned 95% CI": (
                    f"[{signed(index_random['ci_low'], 4)}, "
                    f"{signed(index_random['ci_high'], 4)}]"
                ),
                "Similarity - returned": signed(
                    similarity_index["observed_difference"], 4
                ),
                "Similarity 95% CI": (
                    f"[{signed(similarity_index['ci_low'], 4)}, "
                    f"{signed(similarity_index['ci_high'], 4)}]"
                ),
            }
        )
    return rows


def repairbench_budget_one_table(data):
    budget = data["repairbench_external_campaign"]["worlds"][
        "test_plausibility"
    ]["merged"]["all_context_budget_one"]
    labels = {
        "random_expected": "Random expectation",
        "returned_index": "Returned-sample index",
        "global_index_fallback": "Defects4J global-index fallback",
        "codet5_distance": "CodeT5+ distance (original direction)",
        "codet5_similarity": "CodeT5+ similarity (Amendment A1)",
        "safe_gate_q95_r20": "Frozen safe gate q95/r20",
    }
    comparison_keys = {
        "random_expected": "random_expected_minus_returned_index",
        "global_index_fallback": (
            "global_index_fallback_minus_returned_index"
        ),
        "codet5_distance": "codet5_distance_minus_returned_index",
        "codet5_similarity": "codet5_similarity_minus_returned_index",
        "safe_gate_q95_r20": (
            "safe_gate_q95_r20_minus_returned_index"
        ),
    }
    rows = []
    for method, label in labels.items():
        summary = budget["methods"][method]
        comparison = (
            budget["comparisons"][comparison_keys[method]]
            if method in comparison_keys
            else None
        )
        rows.append(
            {
                "Method": label,
                "All-context budget-1": percent(summary["observed"], 2),
                "Difference vs returned": (
                    points(comparison["observed"], 2)
                    if comparison
                    else "-"
                ),
                "95% CI": (
                    points_interval(comparison, 2) if comparison else "-"
                ),
            }
        )
    return rows


def repairbench_pool_scale_table(data):
    result = data["repairbench_external_campaign"]
    worlds = {
        "test_plausibility": "Test plausibility",
        "reference_complete_case": "Reference complete case",
        "reference_pessimistic": "Reference pessimistic",
    }
    rows = []
    diagnostics = result["exploratory_pool_scale_diagnostics"]["worlds"]
    for world, label in worlds.items():
        payload = result["worlds"][world]
        merged = payload["merged"]["ranking"]
        streams = payload["per_generator"]["ranking"]
        merged_similarity = merged["methods"]["codet5_similarity"]["summary"]
        stream_similarity = streams["methods"]["codet5_similarity"]["summary"]
        merged_effect = merged["comparisons"][
            "codet5_similarity_minus_returned_index"
        ]["mrr"]["observed_difference"]
        stream_effect = streams["comparisons"][
            "codet5_similarity_minus_returned_index"
        ]["mrr"]["observed_difference"]
        interaction = diagnostics[world][
            "codet5_similarity_relative_to_returned_index"
        ]
        rows.append(
            {
                "Endpoint": label,
                "Merged AUC": number(
                    merged_similarity["pairwise_auc_macro"], 4
                ),
                "Merged MRR": number(merged_similarity["mrr"], 4),
                "Merged similarity - returned": signed(merged_effect, 4),
                "Per-generator AUC": number(
                    stream_similarity["pairwise_auc_macro"], 4
                ),
                "Per-generator MRR": number(stream_similarity["mrr"], 4),
                "Per-generator similarity - returned": signed(
                    stream_effect, 4
                ),
                "Pool-scale interaction": signed(
                    interaction["observed"], 4
                ),
                "Interaction 95% CI": (
                    f"[{signed(interaction['ci_low'], 4)}, "
                    f"{signed(interaction['ci_high'], 4)}]"
                ),
            }
        )
    return rows


def repairbench_readiness_table(data):
    result = data["repairbench_external_campaign"]
    review = data["repairbench_semantic_review_audit"]
    mechanics = result["worlds"]["test_plausibility"]["per_generator"][
        "returned_index_minus_random_by_generation_mechanics"
    ]
    return [
        {
            "Audit item": "Unseen exact source configurations",
            "Value": f"{result['campaign_counts']['new_source_configs']:,}",
            "Interpretation": "No configuration aliases to training IDs",
        },
        {
            "Audit item": "Safe-gate actions",
            "Value": (
                f"{result['safe_gate_transport']['action_counts']['defer']:,} "
                "defer"
            ),
            "Interpretation": "Returned ranking preserved in all contexts",
        },
        {
            "Audit item": "Generation-mechanics interaction",
            "Value": (
                f"{signed(mechanics['interaction']['observed'], 4)}, "
                f"95% CI [{signed(mechanics['interaction']['ci_low'], 4)}, "
                f"{signed(mechanics['interaction']['ci_high'], 4)}]"
            ),
            "Interpretation": "No resolved returned-index difference by mode",
        },
        {
            "Audit item": "Unknown-only review eligibility",
            "Value": (
                f"{review['counts']['eligible_candidates']:,} candidates / "
                f"{review['counts']['eligible_contexts']:,} contexts"
            ),
            "Interpretation": "All contexts lack an exact/AST positive",
        },
        {
            "Audit item": "Blinded union selected",
            "Value": (
                f"{review['counts']['selected_unique_candidates']:,} "
                "candidates"
            ),
            "Interpretation": "Returned, CodeT5+ similarity, and random top-3",
        },
        {
            "Audit item": "Confirmatory human requirement",
            "Value": (
                f"{review['blinding']['reviewers_required_for_confirmatory_use']} "
                "independent reviewers"
            ),
            "Interpretation": "Third reviewer adjudicates disagreement",
        },
    ]


def build_tables(data):
    dataset, plausible = dataset_tables(data)
    ranking, ranking_diffs = primary_ranking_tables(data)
    class_rows, mixed_rows = apca_tables(data)
    weak = weak_oracle_statistics(data)
    return [
        {
            "id": "T1",
            "title": "Adjudication-aware V2 dataset",
            "headers": ["Quantity", "Value"],
            "rows": dataset,
            "note": "All later experiments use V2. V1 counts are not comparable.",
        },
        {
            "id": "T1b",
            "title": "Plausible-patch APCA subset",
            "headers": ["View", "Candidates", "Correct", "Incorrect", "Unknown"],
            "rows": plausible,
            "note": "Test passing is an inclusion gate, never a correctness label.",
        },
        {
            "id": "T1c",
            "title": "Weak-oracle inflation under test-passing labels",
            "headers": [
                "Level",
                "Population",
                "Verified correct",
                "Known incorrect / false-solved",
                "Unresolved",
                "Key result",
            ],
            "rows": weak_oracle_table(data),
            "note": (
                f"The {percent(weak['candidate_incorrect_lower'])}-"
                f"{percent(weak['candidate_incorrect_upper'])} interval partially "
                "identifies the corpus-wide incorrect share by treating unresolved "
                "patches as all correct versus all incorrect. "
                f"The {percent(weak['candidate_incorrect_adjudicated'])} quantity is "
                "the incorrect share only among adjudicated test-passing candidates."
            ),
        },
        {
            "id": "T1d",
            "title": "Validation-outcome funnel for the primary ranking universe",
            "headers": [
                "Outcome stage",
                "Candidates",
                "Share of pre-test universe",
                "Paper interpretation",
            ],
            "rows": validation_funnel_table(data),
            "note": (
                "The schema name `hard` is retained for reproducibility, but this is "
                "a compile-filtered pre-test universe, not a plausible-patch-only "
                "overfitting benchmark. Most candidates still fail the available tests."
            ),
        },
        {
            "id": "T2",
            "title": "Known-configuration conditional prioritization",
            "headers": ["Method", "Pools", "MRR", "MRR 95% CI", "R@1", "R@5", "R@10", "Macro AUC"],
            "rows": ranking,
            "note": (
                "Metrics condition on 338 contexts containing a verified correct "
                "candidate; ties use exact expectation. Minimum native rank is the "
                "best observed within-stream candidate index across selected source "
                "configurations, not one global chronological order."
            ),
        },
        {
            "id": "T2b",
            "title": "Paired comparisons against minimum native rank",
            "headers": ["Method vs minimum native rank", "MRR difference", "MRR 95% CI", "R@1 difference (pp)", "Bootstrap p (MRR)"],
            "rows": ranking_diffs,
            "note": "All intervals use 10,000 bug-clustered bootstrap replicates.",
        },
        {
            "id": "T2c",
            "title": "Minimum-native-rank mechanism ablations",
            "headers": [
                "Ablation setting",
                "Pools",
                "Method",
                "Reference",
                "Method MRR",
                "Reference MRR",
                "MRR difference",
                "MRR 95% CI",
                "R@1 difference (pp)",
            ],
            "rows": source_order_ablation_table(data),
            "note": "The aggregate gain is largely captured by the index-0 spike, but later positions retain significant signal after every index-0 candidate is removed. Restricting to singleton candidates shows that minimum-index ranking is not merely an occurrence-count/deduplication artifact.",
        },
        {
            "id": "T2d",
            "title": "Correctness-evidence stratum sensitivity",
            "headers": [
                "Correct-patch evidence",
                "Pools",
                "Min-rank MRR",
                "Random MRR",
                "Min-rank - random",
                "Min-rank - random 95% CI",
                "EB MRR",
                "EB - min-rank",
                "EB - min-rank 95% CI",
            ],
            "rows": correctness_evidence_stratum_table(data),
            "note": "The headline minimum-rank and calibration gains are concentrated in contexts containing an exact/AST-equivalent correct patch. Only 40 semantic-only contexts are available, and neither minimum native rank nor empirical-Bayes calibration has a statistically resolved advantage there.",
        },
        {
            "id": "T2e",
            "title": "Reference-equivalence sensitivity by provider lineage",
            "headers": [
                "Lineage",
                "Exact/AST pools",
                "Exact/AST min-rank - random",
                "Exact/AST 95% CI",
                "Semantic-only pools",
                "Semantic-only min-rank - random",
                "Semantic-only 95% CI",
                "Exact - semantic advantage",
                "Interaction 95% CI",
            ],
            "rows": lineage_stratum_table(data, "defects4j"),
            "note": (
                "The exact/AST-versus-semantic rank-advantage gap is positive for "
                "CodeLlama/RepairLLaMA, DeepSeek, and OpenAI provider lineages. This "
                "is consistent with reference reproduction, task difficulty, or "
                "benchmark contamination, but does not identify which mechanism is causal."
            ),
        },
        {
            "id": "T3",
            "title": "Configuration-shift stress tests",
            "headers": ["Setting", "Method", "Pools", "Method MRR", "Minimum-rank MRR", "Difference", "95% CI", "p"],
            "rows": generalization_table(data),
            "note": (
                "HumanEval-Java is an unseen benchmark using the same 14 source "
                "configurations seen during Defects4J calibration. The two held-out "
                "configuration rows rotate every configuration through 5 bug folds, "
                "producing 70 crossed cells. This is not leave-one-model-family-out "
                "because several configurations share model and prompting lineage."
            ),
        },
        {
            "id": "T3b",
            "title": "HumanEval-Java score-transport diagnostics",
            "headers": ["Diagnostic", "Value", "Interpretation"],
            "rows": transfer_diagnostics_table(data),
            "note": "The Fisher interval treats 14 configurations as analysis units and is descriptive because several configurations share model families and prompting lineage. The result supports relative score/rank transport, not absolute probability calibration.",
        },
        {
            "id": "T3c",
            "title": "Crossed model-lineage and bug-fold holdouts",
            "headers": [
                "Grouping",
                "Held-out lineage",
                "Positive lineage-contexts",
                "Fallback MRR",
                "Min-rank MRR",
                "Difference",
                "95% CI",
            ],
            "rows": family_holdout_table(data),
            "note": (
                "Four named-model lineages x five bug folds produce 20 cells; three "
                "conservative provider lineages x five folds produce 15 cells. "
                "Overall rows count lineage-contexts, so one repair context may appear "
                "once per lineage that generated a correct candidate. Calibration "
                "falls back gracefully but does not beat minimum native rank."
            ),
        },
        {
            "id": "T4",
            "title": "Defects4J retrospective pre-test review budgets",
            "headers": ["Benchmark / setting", "Budget", "Oracle ceiling", "Stream success", "Min-rank success", "Difference (pp)", "95% CI (pp)", "Stream reviews", "Min-rank reviews"],
            "rows": budget_rows(data, "defects4j", "compile_hard", [1, 3, 5, 10, "all"]),
            "note": (
                "Retrospective top-k coverage assumes a perfect semantic adjudicator "
                "that recognizes the first correct patch. It is pre-test candidate "
                "scheduling under an oracle, not a policy that stops when the original "
                "tests pass. Unsolved and post-filter empty contexts remain in the "
                "denominator."
            ),
        },
        {
            "id": "T4b",
            "title": "External retrospective semantic-review transfer",
            "headers": ["Benchmark / setting", "Budget", "Oracle ceiling", "Stream success", "Min-rank success", "Difference (pp)", "95% CI (pp)", "Stream reviews", "Min-rank reviews"],
            "rows": budget_rows(data, "humanevaljava", "labeled_full", [1, 5, 10, "all"]) + budget_rows(data, "gitbugjava", "labeled_full", [1, 5, 10, "all"]),
            "note": "These are adjudication-assisted candidate-review curves, not test-stop simulations. HumanEval-Java transfer is strong; GitBug-Java has only 26 solvable contexts and remains inconclusive.",
        },
        {
            "id": "T4c",
            "title": "GitBug-Java reference-equivalence stress test",
            "headers": [
                "Lineage",
                "Exact/AST pools",
                "Exact/AST min-rank - random",
                "Exact/AST 95% CI",
                "Semantic-only pools",
                "Semantic-only min-rank - random",
                "Semantic-only 95% CI",
                "Exact - semantic advantage",
                "Interaction 95% CI",
            ],
            "rows": lineage_stratum_table(
                data, "gitbugjava", include_all=True
            ),
            "note": (
                "Minimum native rank beats random in 22 exact/AST-present GitBug-Java "
                "contexts, while only four semantic-only contexts exist. The direction "
                "matches Defects4J, but the semantic stratum is too small for a decisive "
                "contamination or general-semantic-confidence conclusion."
            ),
        },
        {
            "id": "T5",
            "title": "Plausible-only candidate-level APCA",
            "headers": ["Method", "Accuracy", "Balanced accuracy", "BA 95% CI", "F1", "MCC", "ROC-AUC"],
            "rows": class_rows,
            "note": "Nested 3/1/1 bug folds separate scorer fitting, threshold selection, and testing. The supervised UniXcoder result is negative evidence: task-specific fine-tuning did not outperform the zero-shot CodeT5+ embedding baseline.",
        },
        {
            "id": "T5b",
            "title": "Plausible-only ranking on nontrivial mixed contexts",
            "headers": ["Method", "Mixed contexts", "MRR", "R@1", "R@3", "Macro AUC"],
            "rows": mixed_rows,
            "note": "Correct-only and incorrect-only contexts are excluded from ranking. Minimum native rank and empirical-Bayes metadata are statistically tied here, so no within-plausible-pool superiority claim is made.",
        },
        {
            "id": "T6",
            "title": "Conflict-exclusion sensitivity",
            "headers": ["Analysis", "View", "Primary metric", "Reference metric", "Paired difference", "95% CI"],
            "rows": sensitivity_table(data),
            "note": "Primary metric is MRR for ranking and balanced accuracy for APCA; excluding every evidence-conflict flag leaves the qualitative conclusions unchanged.",
        },
        {
            "id": "T7",
            "title": "Minimum-native-rank signal across the validation funnel",
            "headers": [
                "Validation endpoint",
                "Eligible",
                "Positive",
                "Positive rate",
                "Native-rank AUC",
                "95% CI",
                "Interpretation",
            ],
            "rows": validation_stage_signal_table(data),
            "note": (
                "Candidate-level primary view excludes evidence conflicts and uses "
                "bug-clustered uncertainty. The score is not a generic correctness "
                "confidence: it is slightly anti-predictive for compilation, modest "
                "for test passage, strongest for exact/AST reference reproduction, "
                "and unresolved for semantic-only correctness."
            ),
        },
        {
            "id": "T8",
            "title": "Nested stage-aware outcome discrimination",
            "headers": [
                "Method",
                "Compile AUC",
                "Test | compile AUC",
                "Final correct | test AUC",
                "Semantic non-reference AUC",
            ],
            "rows": stage_aware_auc_table(data),
            "note": (
                "Each outer bug fold uses two training folds, one tuning fold, one "
                "risk-calibration fold, and one test fold. Human-fix text, reference "
                "matches, and validation outcomes unavailable before an action are "
                "forbidden features. Fusion improves point estimates at several "
                "stages but does not significantly beat raw CodeT5+ on final or "
                "semantic-only correctness."
            ),
        },
        {
            "id": "T9",
            "title": "All-context budget-1 stage-factorized prioritization",
            "headers": [
                "Method",
                "Verified budget-1 success",
                "Possible success upper",
                "Gain vs native (pp)",
                "95% CI (pp)",
            ],
            "rows": stage_budget_one_table(data),
            "note": (
                "All 863 reference contexts remain in the denominator. Factorized "
                "scores multiply separately fitted compile, test, and correctness "
                "probabilities. The result is prioritization under recorded outcomes, "
                "not an automatic correctness guarantee."
            ),
        },
        {
            "id": "T10",
            "title": "Risk-controlled automatic acceptance feasibility",
            "headers": [
                "Method",
                "Unknown handling",
                "Target wrong-accept risk",
                "Feasible folds",
                "Selected contexts",
                "Coverage",
                "Correct / wrong / unknown",
            ],
            "rows": risk_control_table(data),
            "note": (
                "Thresholds use a separate calibration fold, a fixed coverage grid, "
                "minimum support 20, and Bonferroni-simultaneous one-sided "
                "Clopper-Pearson bounds. No method certifies any fold at target risk "
                "30% or below. Complete-case analysis is optimistic because the "
                "unknown labels are selectively missing; the primary pessimistic "
                "analysis counts unknown acceptance as an error."
            ),
        },
        {
            "id": "T11",
            "title": "Cost-sensitive serial and adaptive validation scheduling",
            "headers": [
                "Cost scenario",
                "Compile:test:review",
                "Native AUC",
                "Provenance serial AUC",
                "Provenance gain 95% CI",
                "Fusion serial AUC",
                "Fusion gain 95% CI",
                "Adaptive - serial",
            ],
            "rows": scheduler_cost_table(data),
            "note": (
                "The normalized budget AUC integrates success across predeclared "
                "budget fractions and includes all 863 contexts. Serial factorized "
                "prioritization improves over native order in most cost scenarios. "
                "Myopic adaptive interleaving does not improve over the corresponding "
                "serial policy and is retained as a negative result."
            ),
        },
        {
            "id": "T11b",
            "title": "Scheduler utility by correctness-evidence stratum",
            "headers": [
                "Correctness stratum",
                "Policy",
                "Universe contexts",
                "Normalized budget AUC",
                "Gain vs native",
                "95% CI",
            ],
            "rows": scheduler_stratum_table(data),
            "note": (
                "Equal action costs and pessimistic unknown handling are shown. "
                "Factorized-policy gains are resolved for 298 exact/AST contexts but "
                "not for the 40 semantic-only contexts. Replacing the final stage "
                "with raw CodeT5+ similarity does not close this semantic-evidence gap."
            ),
        },
        {
            "id": "T12",
            "title": "Within-context generator-stream outcome correlation",
            "headers": [
                "Sibling endpoint",
                "Candidates with observed sibling",
                "Positive",
                "Leave-one-candidate-out AUC",
                "95% CI",
            ],
            "rows": stream_health_diagnostic_table(data),
            "note": (
                "For each candidate, the diagnostic excludes that candidate's own "
                "outcome and aggregates other candidates sharing its repair context "
                "and source configuration. It is a retrospective information-"
                "availability diagnostic, not a deployable score. Correctness rows "
                "remain vulnerable to selective semantic adjudication; compile and "
                "test outcomes are fully observed."
            ),
        },
        {
            "id": "T12b",
            "title": "Outcome-conditioned stream-health scheduling",
            "headers": [
                "Cost scenario",
                "Base probabilities",
                "Stream health - serial",
                "Serial 95% CI",
                "Stream health - static adaptive",
                "Adaptive 95% CI",
            ],
            "rows": stream_health_policy_table(data),
            "note": (
                "The predeclared k=5 residual updater uses only outcomes observed "
                "earlier in the same validation run. Despite strong sibling-outcome "
                "correlation, it does not reliably improve the static serial policy; "
                "only the test-expensive provenance comparison has an interval just "
                "above zero. Predictive information is therefore not equivalent to "
                "incremental decision value."
            ),
        },
        {
            "id": "T13",
            "title": "Practical POD RepairLLaMA label-provenance audit",
            "headers": [
                "View",
                "Candidates",
                "Assigned correct",
                "Assigned incorrect",
                "Provenance-unresolved",
                "Key result",
            ],
            "rows": practical_pod_label_table(data),
            "note": (
                "RepairLLaMA's final adjudication script skips the entire bug row "
                "once any candidate is exact-, AST-, or semantic-correct. The "
                "remaining default False values are not manual incorrectness "
                "judgments. Released labels are retained only as a compatibility "
                "world; verified-only and optimistic assignments expose sensitivity."
            ),
        },
        {
            "id": "T13b",
            "title": "Practical POD common-split operational ranking",
            "headers": [
                "Label world",
                "Method",
                "Positive bugs",
                "MRR",
                "R@1",
                "R@3",
                "Mean first rank",
                "MRR vs native",
                "95% CI",
            ],
            "rows": practical_pod_ranking_table(data),
            "note": (
                "All 169 common candidates are identity-reconciled to the original "
                "RepairLLaMA output and bug-out-of-fold nested scores. Binary POD "
                "predictions place predicted-correct patches first and use native "
                "index within tiers. Native order is already saturated: R@1 is "
                "81.0% and R@3 is 100% under released labels, rising to 97.6% R@1 "
                "in the verified-only view. No proposed-policy superiority claim "
                "is supported."
            ),
        },
        {
            "id": "T13c",
            "title": "Practical POD classification sensitivity to unresolved labels",
            "headers": [
                "Label world",
                "Method",
                "Balanced accuracy",
                "BA 95% CI",
                "MCC",
                "Correct recall",
                "Overfit recall",
            ],
            "rows": practical_pod_classification_table(data),
            "note": (
                "The released-label rows reproduce the source package's reported "
                "behavior, including LLM4PatchCorrect balanced accuracy near 0.57. "
                "Variation across provenance worlds demonstrates construct "
                "sensitivity; no world is claimed to reveal the unknown patches' "
                "true labels."
            ),
        },
        {
            "id": "T14",
            "title": "Pinned PrevaRank reproduction and LLM-patch support",
            "headers": ["Audit item", "Count", "Result"],
            "rows": prevarank_reproduction_table(data),
            "note": (
                "The final-paper Figshare archive, executable, and database are "
                "content-hashed. Reproduction uses the authors' released JAR rather "
                "than a reimplementation. Nineteen deletion-only candidates are "
                "unsupported by the released parser and one candidate triggers a "
                "deterministic uncaught analysis exception; all methods use the "
                "resulting 99.52% common support."
            ),
        },
        {
            "id": "T14b",
            "title": "Authentic PrevaRank ranking across pool and label protocols",
            "headers": [
                "Pool",
                "Label world",
                "Informative pools",
                "Native MRR",
                "PrevaRank MRR",
                "Random MRR",
                "PrevaRank - native",
                "Native 95% CI",
                "PrevaRank - random",
                "Random 95% CI",
            ],
            "rows": prevarank_world_table(data),
            "note": (
                "Intervals use 10,000 paired bug-cluster bootstrap replicates. "
                "Mixed pools combine all generator configurations and match this "
                "paper's scheduler; stream pools retain PrevaRank's original "
                "one-APR-tool-at-a-time structure. Adjudicated-only is primary. "
                "The opposite Unknown assignments are partial-identification "
                "sensitivity worlds, not alternative ground truths."
            ),
        },
        {
            "id": "T14c",
            "title": "Authentic PrevaRank adjudicated ranking by metric",
            "headers": [
                "Pool",
                "Metric",
                "Native",
                "PrevaRank",
                "Difference",
                "95% CI",
            ],
            "rows": prevarank_adjudicated_metric_table(data),
            "note": (
                "PrevaRank is below native order on all three mixed-pool metrics. "
                "Its per-generator point estimates are positive, but all intervals "
                "cross zero. Thus the evidence rejects a mixed-pool superiority "
                "claim and leaves superiority in the original stream setting "
                "unresolved."
            ),
        },
        {
            "id": "T14d",
            "title": "PrevaRank classical-to-LLM mechanism shift",
            "headers": [
                "Diagnostic",
                "Classical APR",
                "LLM APR",
                "Comparison",
            ],
            "rows": prevarank_shift_table(data),
            "note": (
                "Classical counts use the 348 reproduced released-tool workbooks; "
                "LLM counts use 465 mixed-generator contexts. The input-order "
                "agreement rows diagnose the canonical run. T14e supplies the "
                "controlled stable-hash intervention needed for a causal "
                "output-order-sensitivity claim."
            ),
        },
        {
            "id": "T14e",
            "title": "Controlled PrevaRank input-order sensitivity",
            "headers": [
                "Diagnostic",
                "Canonical/native input",
                "Stable-hash input",
                "Paired result",
            ],
            "rows": prevarank_input_order_table(data),
            "note": (
                "The stable-hash run uses the identical 4,180 supported candidates "
                "and 465 mixed pools, changing only candidate order with the frozen "
                "label-independent seed. Feature classifications remain invariant, "
                "but output rankings and top choices change substantially. The "
                "adjudicated utility difference is unresolved; the pessimistic "
                "Unknown result is negative and assumption-bound. Thus the "
                "intervention establishes structural ranking instability, not a "
                "label-robust average performance effect."
            ),
        },
        {
            "id": "T15",
            "title": "Shift-aware safe scheduler performance",
            "headers": [
                "Benchmark",
                "Contexts",
                "Solvable",
                "Native MRR",
                "Always-stream MRR",
                "Safe-gate MRR",
                "MRR gain",
                "MRR 95% CI",
                "Native budget-1",
                "Safe budget-1",
                "Budget-1 gain",
                "Budget 95% CI",
            ],
            "rows": shift_safe_performance_table(data),
            "note": (
                "The safe gate uses the predeclared 95th-percentile support "
                "cutoff and 20% expected incremental-harm target. Defects4J is "
                "fully nested with three fitting folds, one calibration fold, "
                "and one final fold. External actions are fixed from Defects4J "
                "without external labels. Full GitBug-Java is entirely deferred "
                "because its native generation budget extends to index 59; the "
                "top-10 control matches Defects4J's index support. Universe "
                "contexts include empty post-filter pools; T15b action counts "
                "cover only the 853 nonempty Defects4J pools."
            ),
        },
        {
            "id": "T15b",
            "title": "Shift-aware scheduler action and support audit",
            "headers": [
                "Benchmark",
                "Agreement",
                "Override",
                "Fallback",
                "Defer",
                "Override rate",
                "Mean override bug harm",
            ],
            "rows": shift_safe_action_table(data),
            "note": (
                "Agreement requires identical top tie sets. Override applies "
                "configuration-position calibration. Fallback and defer both "
                "retain native ranking, but defer marks a context outside the "
                "training support envelope. Harm is the worst context-level "
                "loss in exact tie-aware budget-1 success within an overridden "
                "bug."
            ),
        },
        {
            "id": "T15c",
            "title": "Utility cost relative to always-stream calibration",
            "headers": [
                "Benchmark",
                "Gate - stream MRR",
                "MRR 95% CI",
                "Gate - stream budget-1",
                "Budget 95% CI",
            ],
            "rows": shift_safe_cost_table(data),
            "note": (
                "This table quantifies the price of support-based deferral. "
                "The internal difference is unresolved; HumanEval-Java loses "
                "some always-stream utility because 24 contexts are deferred, "
                "while still outperforming native order in T15. The full "
                "GitBug row is a deliberate all-defer result, not a failed "
                "attempt to tune around shift."
            ),
        },
        {
            "id": "T15d",
            "title": "Fold-separated incremental-harm calibration",
            "headers": [
                "Test fold",
                "Calibration contexts",
                "Calibration bugs",
                "Calibrated harm upper",
                "Test overrides",
                "Test mean harm",
                "Within bound",
            ],
            "rows": shift_safe_risk_fold_table(data),
            "note": (
                "Each threshold is selected without its test fold. The upper "
                "bound is one-sided Hoeffding with union correction over the "
                "fixed margin grid. All five test-fold mean harms remain below "
                "their separately calibrated bounds; this does not guarantee "
                "transport under arbitrary campaign shift."
            ),
        },
        {
            "id": "T15e",
            "title": "Safe scheduler harm-target sensitivity",
            "headers": [
                "Harm target",
                "Overrides",
                "Fallbacks",
                "Defers",
                "MRR",
                "MRR gain",
                "MRR 95% CI",
                "Budget-1 gain",
                "Budget 95% CI",
            ],
            "rows": shift_safe_sensitivity_table(data),
            "note": (
                "The 95th-percentile support cutoff is fixed. At 5% and 10% "
                "expected incremental-harm targets, no outer fold certifies an "
                "override and the policy falls back to native order. The 20% "
                "target is primary and was frozen before the full result."
            ),
        },
        {
            "id": "T15f",
            "title": "Safe scheduler correctness-evidence boundary",
            "headers": [
                "Benchmark",
                "Correctness stratum",
                "Pools",
                "Safe-gate MRR",
                "MRR gain",
                "95% CI",
            ],
            "rows": shift_safe_stratum_table(data),
            "note": (
                "As in the earlier scheduler analyses, the resolved aggregate "
                "gain is concentrated in contexts containing exact/AST-"
                "equivalent repairs. Semantic-only intervals cross zero on "
                "Defects4J and HumanEval-Java; GitBug-Java has only four "
                "semantic-only positive contexts."
            ),
        },
        {
            "id": "T15g",
            "title": "Safe scheduler source-configuration coverage audit",
            "headers": [
                "Source configuration",
                "Context-source incidences",
                "Agreement",
                "Override",
                "Fallback",
                "Defer",
                "Override incidence",
            ],
            "rows": shift_safe_source_config_table(data),
            "note": (
                "Rows count source-configuration incidences inside candidate "
                "contexts, not independent contexts; one context can therefore "
                "contribute to multiple rows. Every configuration occurs in "
                "overridden contexts, which rules out a degenerate policy that "
                "only activates for one favored generator."
            ),
        },
        {
            "id": "T16",
            "title": "RepairBench campaign-shift and label audit",
            "headers": [
                "Quantity",
                "RepairLLaMA campaign",
                "RepairBench campaign",
                "Boundary",
            ],
            "rows": repairbench_campaign_table(data),
            "note": (
                "RepairBench contributes a newer generation campaign with 35 "
                "exactly unseen source-configuration IDs and negligible exact "
                "patch overlap. The 89 GitBug-Java contexts and research lineage "
                "are shared, so this is not independent-benchmark or independent-"
                "group replication. Test-passing nonmatches remain Unknown."
            ),
        },
        {
            "id": "T16b",
            "title": "RepairBench merged-pool confirmatory ranking",
            "headers": [
                "Endpoint",
                "Candidates",
                "Positive contexts",
                "Random MRR",
                "Returned MRR",
                "CodeT5+ similarity MRR",
                "Returned - random",
                "Returned 95% CI",
                "Similarity - returned",
                "Similarity 95% CI",
            ],
            "rows": repairbench_merged_ranking_table(data),
            "note": (
                "Test plausibility is the frozen primary endpoint. Reference "
                "complete-case and pessimistic-Unknown rows are sensitivity "
                "worlds. Returned-sample index does not beat exact-tie random "
                "expectation in any row, while zero-shot CodeT5+ similarity is "
                "resolved below returned index in the merged pools."
            ),
        },
        {
            "id": "T16c",
            "title": "RepairBench all-context budget-1 success",
            "headers": [
                "Method",
                "All-context budget-1",
                "Difference vs returned",
                "95% CI",
            ],
            "rows": repairbench_budget_one_table(data),
            "note": (
                "The denominator is all 89 contexts, including 13 without any "
                "test-plausible candidate. Both CodeT5+ directions are retained "
                "to disclose Protocol Amendment A1. Every source configuration "
                "is unseen, so the safe gate defers everywhere and exactly "
                "preserves returned-index utility."
            ),
        },
        {
            "id": "T16d",
            "title": "Exploratory merged-pool tail-risk diagnostic",
            "headers": [
                "Endpoint",
                "Merged AUC",
                "Merged MRR",
                "Merged similarity - returned",
                "Per-generator AUC",
                "Per-generator MRR",
                "Per-generator similarity - returned",
                "Pool-scale interaction",
                "Interaction 95% CI",
            ],
            "rows": repairbench_pool_scale_table(data),
            "note": (
                "This diagnostic was motivated after the confirmatory result "
                "exposed AUC/top-rank discordance and is therefore exploratory. "
                "Negative interactions show that CodeT5+ similarity loses "
                "relative first-correct utility when independently generated "
                "streams are merged, despite modest candidate-level AUC in the "
                "reference-label worlds."
            ),
        },
        {
            "id": "T16e",
            "title": "RepairBench shift and adjudication readiness",
            "headers": ["Audit item", "Value", "Interpretation"],
            "rows": repairbench_readiness_table(data),
            "note": (
                "The gate and semantic-review packet consume no revealed "
                "RepairBench semantic labels. The blinded packet is ready but "
                "remains off the critical path; without two independent human "
                "reviewers, Unknown-label bounds remain primary."
            ),
        },
    ]


def make_claims(data):
    known = data["stream_primary"]["protocols"]["known_generator_bug_oof"]["context"]
    known_results = by_name(known["results"], "method")
    known_diff = known["paired_comparisons"]["stream_index_max"]["mrr_vs_source_order"]
    random_vs_source = known["paired_comparisons"]["random_expected"][
        "mrr_vs_source_order"
    ]
    semantic_random_vs_source = known["paired_comparisons"]["random_expected"][
        "mrr_vs_source_order_by_stratum"
    ]["semantic_only"]
    semantic_stream_vs_source = known["paired_comparisons"]["stream_index_max"][
        "mrr_vs_source_order_by_stratum"
    ]["semantic_only"]
    source_ablation = data["source_order_ablation"]["settings"]
    all_vs_index0 = source_ablation["all_candidates"]["paired_comparisons"][
        "source_order_minus_index_zero_only"
    ]["mrr"]
    tail_vs_random = source_ablation["tail_without_index_zero"][
        "paired_comparisons"
    ]["source_order_minus_random"]["mrr"]
    singleton_vs_random = source_ablation["singleton_candidates"][
        "paired_comparisons"
    ]["source_order_minus_random"]["mrr"]
    merged = data["stream_primary"]["protocols"]["unseen_generator_merged_loco"]["context"]
    merged_diff = merged["paired_comparisons"]["loco_index_noisy_or"]["mrr_vs_source_order"]
    defects = find_budget_setting(data, "defects4j", "compile_hard")["groups"]["context"]
    defects_diff = defects["paired_comparisons"]["stream_index_max_minus_source_order_tie_aware"]["1"]["success_rate_all_difference"]
    human = find_budget_setting(data, "humanevaljava", "labeled_full")["groups"]["context"]
    human_diff = human["paired_comparisons"]["stream_index_max_minus_source_order_tie_aware"]["1"]["success_rate_all_difference"]
    gitbug = find_budget_setting(data, "gitbugjava", "labeled_full")["groups"]["context"]
    gitbug_diff = gitbug["paired_comparisons"]["stream_index_max_minus_source_order_tie_aware"]["1"]["success_rate_all_difference"]
    human_payload = data["external_transfer"]["modes"]["retain_conflicts"][
        "humanevaljava"
    ]["labeled_full"]
    source_transfer = human_payload["calibration_diagnostics"][
        "source_quality_transfer"
    ]
    transfer_diagnostics = human_transfer_diagnostics(data)
    transfer_ci = transfer_diagnostics["pearson_fisher_95_ci"]
    apca = data["plausible_apca"]["candidate_level_classification"]
    apca_primary = apca["results"]["stream_index_max"]
    apca_diff = apca["paired_primary_comparisons"]["source_order_tie_aware"]["balanced_accuracy"]
    codet5_diff = apca["paired_primary_comparisons"]["codet5p_similarity"]["balanced_accuracy"]
    mixed = data["plausible_apca"]["mixed_pool_ranking"]
    mixed_diff = mixed["paired_primary_comparisons"]["source_order_tie_aware"]["mrr"]
    weak = weak_oracle_statistics(data)
    pretest_test_failures = (
        data["dataset_audit"]["candidate_counts"]["hard"]
        - data["plausible_audit"]["labeled"]["candidate_count"]
    )
    pretest_test_failure_rate = (
        pretest_test_failures / data["dataset_audit"]["candidate_counts"]["hard"]
    )
    gate = data["memorization_lineage_gate"]
    exact_semantic_interaction = gate["defects4j"]["all_configurations"][
        "exact_vs_semantic_rank_advantage"
    ]
    named_family_diff = gate["lineage_holdout"]["named_model"]["overall"][
        "paired_comparisons"
    ]["unseen_stream_fallback"]["mrr_vs_source_order"]
    provider_family_diff = gate["lineage_holdout"]["provider"]["overall"][
        "paired_comparisons"
    ]["unseen_stream_fallback"]["mrr_vs_source_order"]
    gitbug_strata = gate["gitbugjava"]["all_configurations"][
        "correctness_evidence_strata"
    ]
    gitbug_exact_diff = gitbug_strata["exact_or_ast_present"][
        "minimum_rank_minus_random"
    ]["mrr"]
    gitbug_semantic_diff = gitbug_strata["semantic_only"][
        "minimum_rank_minus_random"
    ]["mrr"]
    funnel_signal = data["validation_funnel_signal"]["views"][
        "candidate_primary_no_conflicts"
    ]
    stage_policy = data["stage_aware_policy"]
    stage_metrics = stage_policy["stage_metrics"]
    stage_budget = stage_policy["all_context_budget_one"]
    provenance_budget_gain = stage_budget["paired_vs_native_order"][
        "provenance_factorized"
    ]
    fusion_final_gain = stage_policy["final_correctness_paired_bug_bootstrap"][
        "fusion_vs_raw_codet5_similarity"
    ]
    fusion_semantic_gain = stage_policy[
        "final_correctness_paired_bug_bootstrap"
    ]["semantic_nonreference_fusion_vs_raw_codet5_similarity"]
    risk_rows = stage_policy["risk_control"]["summaries"]
    low_risk_feasible_folds = sum(
        row["feasible_fold_count"]
        for row in risk_rows
        if row["unknown_policy"] == "pessimistic"
        and row["risk_target"] <= 0.30
    )
    scheduler = data["adaptive_validation_scheduler"]
    scheduler_pairs = {
        (
            row["cost_scenario"],
            row["unknown_world"],
            row["left"],
            row["right"],
        ): row
        for row in scheduler["paired_bug_bootstrap"]
    }
    scheduler_stratum_pairs = {
        (
            row["cost_scenario"],
            row["unknown_world"],
            row["left"],
            row["right"],
            row["correctness_stratum"],
        ): row
        for row in scheduler["stratified_paired_bug_bootstrap"]
    }
    equal_provenance_scheduler = scheduler_pairs[
        (
            "equal_actions",
            "pessimistic",
            "provenance_serial",
            "native_serial",
        )
    ]
    equal_fusion_scheduler = scheduler_pairs[
        ("equal_actions", "pessimistic", "fusion_serial", "native_serial")
    ]
    equal_fusion_adaptive = scheduler_pairs[
        (
            "equal_actions",
            "pessimistic",
            "fusion_adaptive",
            "fusion_serial",
        )
    ]
    exact_scheduler = scheduler_stratum_pairs[
        (
            "equal_actions",
            "pessimistic",
            "fusion_serial",
            "native_serial",
            "exact_or_ast",
        )
    ]
    semantic_scheduler = scheduler_stratum_pairs[
        (
            "equal_actions",
            "pessimistic",
            "fusion_serial",
            "native_serial",
            "semantic_only",
        )
    ]
    stream_health = data["outcome_conditioned_stream_health"]
    stream_diagnostics = stream_health["sibling_outcome_diagnostics"]
    stream_health_pairs = {
        (
            row["cost_scenario"],
            row["method"],
            row["reference"],
        ): row
        for row in stream_health["paired_bug_bootstrap"]
        if row["unknown_world"] == "pessimistic"
        and row["strength"] == 5.0
    }
    equal_provenance_health = stream_health_pairs[
        ("equal_actions", "provenance", "serial")
    ]
    equal_fusion_health = stream_health_pairs[
        ("equal_actions", "fusion", "serial")
    ]
    test_expensive_provenance_health = stream_health_pairs[
        ("test_expensive", "provenance", "serial")
    ]
    practical_pod = data["practical_pod_common_split"]
    practical_audit = practical_pod["label_provenance_audit"]
    practical_released = practical_pod["worlds"]["released"]
    practical_verified = practical_pod["worlds"]["verified_only"]
    practical_native = practical_released["operational_ranking"]["summaries"][
        "source_order"
    ]
    practical_primary = practical_released["operational_ranking"][
        "paired_vs_native_order"
    ]["stage_selected"]
    practical_llm4_ba = practical_released["classification"][
        "llm4patchcorrect"
    ]["metrics"]["balanced_accuracy"]
    prevarank_manifest = load_json(
        AUXILIARY_INPUTS["prevarank_preparation_manifest"]
    )
    prevarank_mixed = find_prevarank_protocol(
        data, "mixed", "adjudicated_only"
    )
    prevarank_stream = find_prevarank_protocol(
        data, "stream", "adjudicated_only"
    )
    prevarank_mixed_vs_native = prevarank_mixed[
        "paired_comparisons_vs_native"
    ]["prevarank_released_rank"]
    prevarank_stream_vs_native = prevarank_stream[
        "paired_comparisons_vs_native"
    ]["prevarank_released_rank"]
    prevarank_mixed_vs_random = prevarank_mixed[
        "paired_prevarank_comparisons_vs_random"
    ]["prevarank_released_rank"]
    prevarank_shift = data["prevarank_domain_shift"]
    prevarank_order = data["prevarank_input_order"]
    prevarank_order_reconciliation = prevarank_order["reconciliation"]
    prevarank_order_sensitivity = prevarank_order_reconciliation[
        "released_rank_order_sensitivity"
    ]
    prevarank_order_alignments = prevarank_order_reconciliation[
        "input_order_alignment_matrix"
    ]["alignments"]
    prevarank_order_adjudicated = find_prevarank_order_world(
        data, "adjudicated_only"
    )
    prevarank_order_pessimistic = find_prevarank_order_world(
        data, "pessimistic_unknown"
    )
    prevarank_order_adjudicated_mrr = prevarank_order_adjudicated[
        "paired_comparisons"
    ]["shuffled_rank_minus_canonical_rank"]["mrr"]
    prevarank_order_pessimistic_mrr = prevarank_order_pessimistic[
        "paired_comparisons"
    ]["shuffled_rank_minus_canonical_rank"]["mrr"]
    prevarank_shuffled_vs_native = prevarank_order_adjudicated[
        "paired_comparisons"
    ]["shuffled_rank_minus_native"]["mrr"]
    prevarank_reproduction = data["prevarank_reproduction"]
    shift_aware = data["shift_aware_safe_scheduler"]
    safe_internal = shift_aware["internal"]["primary_summary"]
    safe_human = shift_aware["external"]["humanevaljava"][
        "primary_summary"
    ]
    safe_gitbug = shift_aware["external"]["gitbugjava"][
        "primary_summary"
    ]
    safe_gitbug_top10 = shift_aware["external"]["gitbugjava_top10"][
        "primary_summary"
    ]
    safe_internal_strata = shift_aware["internal"]["ranking"][
        "paired_comparisons"
    ]["safe_gate_q95_r20"]["mrr_vs_source_order_by_stratum"]
    safe_primary_actions = shift_aware["internal"]["primary_actions"]
    safe_low_risk_overrides = sum(
        fold["test_actions"][method]["action_counts"].get("override", 0)
        for fold in shift_aware["internal"]["fold_audit"]
        for method in ("safe_gate_q95_r05", "safe_gate_q95_r10")
    )
    repairbench = data["repairbench_external_campaign"]
    repairbench_integrity = data["repairbench_campaign_integrity"]
    repairbench_primary = repairbench["worlds"]["test_plausibility"][
        "merged"
    ]["ranking"]
    repairbench_primary_index_random = repairbench_primary["comparisons"][
        "returned_index_minus_random"
    ]["mrr"]
    repairbench_primary_similarity_index = repairbench_primary[
        "comparisons"
    ]["codet5_similarity_minus_returned_index"]["mrr"]
    repairbench_budget_similarity_index = repairbench["worlds"][
        "test_plausibility"
    ]["merged"]["all_context_budget_one"]["comparisons"][
        "codet5_similarity_minus_returned_index"
    ]
    repairbench_pool_interactions = repairbench[
        "exploratory_pool_scale_diagnostics"
    ]["worlds"]
    repairbench_reference_pool = repairbench_pool_interactions[
        "reference_pessimistic"
    ]

    claims = [
        {
            "id": "C1",
            "status": "supported_scoped",
            "claim": "Minimum native candidate rank is a strong black-box signal with no additional learned inference after candidate generation.",
            "evidence": f"Minimum-native-rank MRR {known_results['source_order_tie_aware']['summary']['mrr']:.3f} versus random {known_results['random_expected']['summary']['mrr']:.3f} on 338 positive contexts, a paired gain of {-random_vs_source['observed_difference']:+.3f}, 95% CI [{-random_vs_source['ci_high']:+.3f}, {-random_vs_source['ci_low']:+.3f}]. Full rank adds only {all_vs_index0['observed_difference']:+.3f} MRR over an index-0-only baseline, CI [{all_vs_index0['ci_low']:+.3f}, {all_vs_index0['ci_high']:+.3f}], but after removing all index-0 candidates the remaining positions still beat random by {tail_vs_random['observed_difference']:+.3f}, CI [{tail_vs_random['ci_low']:+.3f}, {tail_vs_random['ci_high']:+.3f}]. Among singleton candidates, the gain over random is {singleton_vs_random['observed_difference']:+.3f}, CI [{singleton_vs_random['ci_low']:+.3f}, {singleton_vs_random['ci_high']:+.3f}]. On 40 semantic-only contexts, however, the minimum-rank gain over random is only {-semantic_random_vs_source['observed_difference']:+.3f}, CI [{-semantic_random_vs_source['ci_high']:+.3f}, {-semantic_random_vs_source['ci_low']:+.3f}]. The exact/AST-minus-semantic rank-advantage interaction is {exact_semantic_interaction['observed_difference_in_differences']:+.3f}, CI [{exact_semantic_interaction['ci_low']:+.3f}, {exact_semantic_interaction['ci_high']:+.3f}].",
            "scope": (
                "The score is the minimum within-stream index across selected source "
                "configurations, not a global chronological order. The aggregate "
                "effect is dominated by the first-position spike and by 298 contexts "
                "containing an exact/AST-equivalent correct patch. Later positions "
                "retain signal and duplicate occurrence is not the sole cause, but "
                "the semantic-only subset is underpowered and does not establish a "
                "general semantic-correctness prior. The exact-versus-semantic gap "
                "also appears within all three provider lineages, making one lineage "
                "an insufficient explanation; it remains compatible with reference "
                "reproduction, difficulty, and benchmark contamination. MRR is conditional on contexts "
                "where a verified correct candidate exists; it does not estimate the "
                "probability of repairing an arbitrary bug. The primary universe is pre-test: "
                f"{pretest_test_failures:,} candidates "
                f"({percent(pretest_test_failure_rate)}) still fail the available tests. "
                "The merged score also assumes that candidates from the selected "
                "configurations have already been generated; generation itself is not free."
            ),
        },
        {
            "id": "C2",
            "status": "supported_scoped",
            "claim": "Configuration-aware empirical-Bayes position calibration improves pre-test prioritization when configuration-specific evidence is available.",
            "evidence": f"Known-configuration MRR gain {known_diff['observed_difference']:+.3f}, 95% CI [{known_diff['ci_low']:+.3f}, {known_diff['ci_high']:+.3f}]. On semantic-only contexts the gain is {semantic_stream_vs_source['observed_difference']:+.3f}, 95% CI [{semantic_stream_vs_source['ci_low']:+.3f}, {semantic_stream_vs_source['ci_high']:+.3f}].",
            "scope": (
                "Known-configuration, bug-held-out evaluation. The aggregate "
                "improvement is concentrated in exact/AST-present contexts and in a "
                "universe dominated by candidates that fail tests. It is neither a "
                "model-family generalization result nor established on semantic-only "
                "or plausible-only ranking."
            ),
        },
        {
            "id": "C3",
            "status": "not_supported",
            "claim": "Stream calibration significantly improves over minimum native rank for held-out source configurations or model lineages.",
            "evidence": f"Merged configuration-LOCO gain {merged_diff['observed_difference']:+.3f}, 95% CI [{merged_diff['ci_low']:+.3f}, {merged_diff['ci_high']:+.3f}]. The crossed named-model-lineage fallback gain is {named_family_diff['observed_difference']:+.3f}, CI [{named_family_diff['ci_low']:+.3f}, {named_family_diff['ci_high']:+.3f}], and the conservative provider-lineage gain is {provider_family_diff['observed_difference']:+.3f}, CI [{provider_family_diff['ci_low']:+.3f}, {provider_family_diff['ci_high']:+.3f}].",
            "scope": (
                "Describe fallback as graceful, not superior. Configuration LOCO, "
                "four named-model-lineage x five bug-fold cells, and three conservative "
                "provider-lineage x five bug-fold cells all fail to establish an "
                "advantage over minimum native rank."
            ),
        },
        {
            "id": "C4",
            "status": "supported_scoped",
            "claim": "Calibration improves retrospective correct-patch coverage under a one-candidate Defects4J semantic-review budget.",
            "evidence": f"Budget-1 all-context gain {100 * defects_diff['observed_difference']:+.2f} percentage points, 95% CI [{100 * defects_diff['ci_low']:+.2f}, {100 * defects_diff['ci_high']:+.2f}].",
            "scope": "The curve assumes a perfect semantic adjudicator. It does not estimate savings from stopping at the first test-passing patch, and the advantage is not uniform curve dominance.",
        },
        {
            "id": "C5",
            "status": "supported_scoped",
            "claim": "Defects4J-trained configuration-position ranking scores transfer zero-shot to HumanEval-Java when the same source configurations are available.",
            "evidence": f"HumanEval-Java budget-1 gain {100 * human_diff['observed_difference']:+.2f} points, 95% CI [{100 * human_diff['ci_low']:+.2f}, {100 * human_diff['ci_high']:+.2f}]; configuration priors correlate with HumanEval correctness at Pearson {source_transfer['pearson_correlation']:.3f}, descriptive Fisher 95% CI [{transfer_ci['ci_low']:.3f}, {transfer_ci['ci_high']:.3f}], and Spearman {source_transfer['spearman_rank_correlation']:.3f}.",
            "scope": (
                "This is unseen-benchmark, seen-configuration ranking transport, not "
                "probability calibration, unseen-configuration superiority, or "
                "unseen-model-family generalization. HumanEval "
                f"occurrence correctness is {percent(transfer_diagnostics['empirical_correct_rate'])} "
                f"while the mean transferred score is {percent(transfer_diagnostics['mean_transferred_probability'])} "
                f"(ECE {transfer_diagnostics['expected_calibration_error_10_bins']:.3f}). "
                "HumanEval and Defects4J still come from the same RepairLLaMA campaign "
                "and adjudication process, so this is not independent-campaign validation. "
                f"GitBug-Java is inconclusive: budget-1 gain "
                f"{100 * gitbug_diff['observed_difference']:+.2f} points with only 26 solvable contexts. "
                f"Its minimum-rank gain over random is {gitbug_exact_diff['observed_difference']:+.3f} "
                f"in 22 exact/AST-present contexts but {gitbug_semantic_diff['observed_difference']:+.3f} "
                "in only four semantic-only contexts."
            ),
        },
        {
            "id": "C6",
            "status": "supported_scoped",
            "claim": "Configuration-position metadata provides modest above-chance discrimination between correct and overfitting test-passing patches.",
            "evidence": (
                f"Balanced accuracy {apca_primary['metrics']['balanced_accuracy']:.3f}, "
                f"95% CI [{apca_primary['bug_cluster_bootstrap_ci']['balanced_accuracy']['ci_low']:.3f}, "
                f"{apca_primary['bug_cluster_bootstrap_ci']['balanced_accuracy']['ci_high']:.3f}], "
                f"and ROC-AUC {apca_primary['metrics']['roc_auc']:.3f}. Its balanced-accuracy "
                f"gain over minimum native rank is only {apca_diff['observed_difference']:+.3f}, "
                f"95% CI [{apca_diff['ci_low']:+.3f}, {apca_diff['ci_high']:+.3f}]."
            ),
            "scope": (
                f"{weak['candidate_labeled']:,} adjudicated plausible patches; "
                f"{weak['candidate_unknown']:,} unresolved plausible patches are excluded "
                "and published separately. Because skipped reviews are concentrated "
                "in contexts already containing an exact/AST fix, this is a "
                "selectively adjudicated subset rather than a missing-at-random sample. "
                "The result supports signal, not superiority over minimum native rank."
            ),
        },
        {
            "id": "C7",
            "status": "not_supported",
            "claim": "The method significantly outperforms CodeT5+ on plausible-patch classification.",
            "evidence": f"Balanced-accuracy gain {codet5_diff['observed_difference']:+.3f}, 95% CI [{codet5_diff['ci_low']:+.3f}, {codet5_diff['ci_high']:+.3f}].",
            "scope": "Report the point estimate and null interval; do not claim superiority.",
        },
        {
            "id": "C8",
            "status": "not_supported",
            "claim": "The method beats minimum native rank for ranking within plausible mixed pools.",
            "evidence": f"MRR difference {mixed_diff['observed_difference']:+.3f}, 95% CI [{mixed_diff['ci_low']:+.3f}, {mixed_diff['ci_high']:+.3f}].",
            "scope": "Candidate-level APCA and within-pool prioritization are empirically distinct.",
        },
        {
            "id": "C9",
            "status": "not_supported",
            "claim": "The nested stage-selected policy outperforms native order or the five released Practical POD detectors on their RepairLLaMA common split.",
            "evidence": (
                f"Under released labels, stage-selected minus native MRR is "
                f"{practical_primary['observed']['mrr_diff']:+.4f}, 95% CI "
                f"[{practical_primary['confidence_intervals']['mrr_diff']['low']:+.4f}, "
                f"{practical_primary['confidence_intervals']['mrr_diff']['high']:+.4f}]. "
                "Every Holm-adjusted paired comparison against the five released "
                "detectors is non-significant."
            ),
            "scope": (
                "The exact 169-patch split has little ranking headroom: native "
                f"R@1 is {percent(practical_native['recall@1'])} and R@3 is "
                f"{percent(practical_native['recall@3'])}. This claim concerns the "
                "Practical POD common split only. PrevaRank is evaluated separately "
                "through its pinned executable on 99.52% of the full LLM plausible-"
                "patch population; APPT and ComPass still lack compatible direct "
                "runs and must not be compared through published headline numbers."
            ),
        },
        {
            "id": "C10",
            "status": "supported",
            "claim": "Passing the available tests substantially overstates correctness and apparent repair success in this LLM-generated patch corpus.",
            "evidence": (
                f"Of {weak['candidate_total']:,} test-passing candidates, "
                f"{weak['candidate_incorrect']:,} are known incorrect and "
                f"{weak['candidate_unknown']:,} unresolved, bounding the corpus-wide "
                f"incorrect share at {percent(weak['candidate_incorrect_lower'])}-"
                f"{percent(weak['candidate_incorrect_upper'])}; among "
                f"{weak['candidate_labeled']:,} adjudicated candidates, "
                f"{percent(weak['candidate_incorrect_adjudicated'])} are incorrect. "
                f"Tests make {weak['test_positive_contexts']:,} contexts appear solved "
                f"versus {weak['verified_correct_contexts']:,} with a verified correct "
                f"patch, and all {weak['false_solved_contexts']:,} excess contexts "
                "contain only known-incorrect patches, yielding "
                f"{percent(weak['false_solved_relative_inflation'])} relative inflation."
            ),
            "scope": (
                "The candidate-level interval is partial identification, not a "
                "point estimate. The context-level inflation is definitive because "
                f"none of the {weak['false_solved_contexts']} false-solved contexts "
                "contains an unresolved candidate."
            ),
        },
        {
            "id": "C11",
            "status": "supported",
            "claim": "Minimum native rank predicts different validation outcomes in different directions and is primarily a reference-reproduction signal, not a generic patch-quality score.",
            "evidence": (
                "Candidate-level native-rank AUC is "
                f"{funnel_signal['compile']['source_order_auc']:.3f} for compilation, "
                f"{funnel_signal['test_given_compile']['source_order_auc']:.3f} for "
                "test passage conditional on compilation, "
                f"{funnel_signal['reference_given_test']['source_order_auc']:.3f} for "
                "exact/AST reference equivalence conditional on test passage, and "
                f"{funnel_signal['semantic_correct_given_adjudicated_nonreference']['source_order_auc']:.3f} "
                "for semantic correctness among adjudicated non-reference patches, "
                "with 95% CI "
                f"[{funnel_signal['semantic_correct_given_adjudicated_nonreference']['bug_cluster_bootstrap_95ci']['source_order_auc']['low']:.3f}, "
                f"{funnel_signal['semantic_correct_given_adjudicated_nonreference']['bug_cluster_bootstrap_95ci']['source_order_auc']['high']:.3f}]."
            ),
            "scope": (
                "This is an associational decomposition of one repair campaign. "
                "It does not prove memorization, causal decoding behavior, or "
                "semantic generalization."
            ),
        },
        {
            "id": "C12",
            "status": "supported_scoped",
            "claim": "A validation-stage-factorized provenance policy improves all-context budget-1 patch prioritization over minimum native rank.",
            "evidence": (
                f"Verified budget-1 success is "
                f"{percent(stage_budget['summaries']['provenance_factorized']['verified_budget1_success'])} "
                f"versus {percent(stage_budget['summaries']['native_order']['verified_budget1_success'])}; "
                f"gain {points(provenance_budget_gain['verified_success_difference_vs_native_order'])} "
                "percentage points, 95% CI "
                f"[{points(provenance_budget_gain['low'])}, "
                f"{points(provenance_budget_gain['high'])}]."
            ),
            "scope": (
                "The policy uses deployable provenance and content features under "
                "nested bug-disjoint fitting, but the gain is concentrated in "
                "exact/AST reference-equivalent repairs. It prioritizes validation; "
                "it does not certify correctness."
            ),
        },
        {
            "id": "C13",
            "status": "not_supported",
            "claim": "Provenance-content fusion significantly improves semantic-correctness discrimination over raw CodeT5+ similarity.",
            "evidence": (
                f"Fusion minus raw CodeT5+ AUC is {fusion_final_gain['difference']:+.3f}, "
                f"95% CI [{fusion_final_gain['low']:+.3f}, "
                f"{fusion_final_gain['high']:+.3f}] for final correctness and "
                f"{fusion_semantic_gain['difference']:+.3f}, 95% CI "
                f"[{fusion_semantic_gain['low']:+.3f}, "
                f"{fusion_semantic_gain['high']:+.3f}] for semantic non-reference "
                "correctness."
            ),
            "scope": (
                f"The semantic endpoint contains only "
                f"{stage_metrics['semantic_correct_nonreference']['fusion']['positive_count']} "
                "positives. Stop adding backbone variants; independent semantic "
                "labels and a modern external campaign are the appropriate next test."
            ),
        },
        {
            "id": "C14",
            "status": "supported_negative",
            "claim": "The current weak-label evidence cannot support a useful low-risk automatic-acceptance guarantee.",
            "evidence": (
                f"Across the predeclared pessimistic analysis, the total number of "
                f"feasible fold-method cells at wrong-acceptance targets of 30% or "
                f"below is {low_risk_feasible_folds}. Complete-case analysis selects "
                "more contexts at 40%, demonstrating the optimism introduced by "
                "dropping selectively missing unknown labels."
            ),
            "scope": (
                "This is a feasibility result under separate calibration folds, "
                "simultaneous Clopper-Pearson bounds, and the observed campaign. "
                "The correct operational action is defer, not an unvalidated "
                "automatic-accept threshold."
            ),
        },
        {
            "id": "C15",
            "status": "supported_scoped",
            "claim": "Stage-factorized serial scheduling improves cost-normalized validation utility, while myopic adaptive interleaving adds no demonstrated benefit.",
            "evidence": (
                "Under equal action costs, normalized budget-AUC gains over native "
                f"serial order are {equal_provenance_scheduler['difference']:+.4f}, "
                f"95% CI [{equal_provenance_scheduler['low']:+.4f}, "
                f"{equal_provenance_scheduler['high']:+.4f}] for provenance and "
                f"{equal_fusion_scheduler['difference']:+.4f}, 95% CI "
                f"[{equal_fusion_scheduler['low']:+.4f}, "
                f"{equal_fusion_scheduler['high']:+.4f}] for fusion. Fusion adaptive "
                f"minus fusion serial is {equal_fusion_adaptive['difference']:+.4f}, "
                f"95% CI [{equal_fusion_adaptive['low']:+.4f}, "
                f"{equal_fusion_adaptive['high']:+.4f}]."
            ),
            "scope": (
                f"The fusion-serial gain is resolved in exact/AST contexts "
                f"({exact_scheduler['difference']:+.4f}, CI "
                f"[{exact_scheduler['low']:+.4f}, {exact_scheduler['high']:+.4f}]) "
                f"but not semantic-only contexts ({semantic_scheduler['difference']:+.4f}, "
                f"CI [{semantic_scheduler['low']:+.4f}, "
                f"{semantic_scheduler['high']:+.4f}]). Costs are scenario weights, "
                "not measured wall-clock or energy."
            ),
        },
        {
            "id": "C16",
            "status": "supported_negative",
            "claim": "Within-context sibling outcomes are highly correlated by generator stream, but outcome-conditioned stream-health updates add little incremental scheduling utility.",
            "evidence": (
                "Leave-one-candidate-out sibling-outcome AUC is "
                f"{stream_diagnostics['compile']['leave_one_candidate_out_sibling_auc']:.3f} "
                "for compilation and "
                f"{stream_diagnostics['test_given_compile']['leave_one_candidate_out_sibling_auc']:.3f} "
                "for test passage. At the predeclared k=5 setting under equal "
                "action costs, stream-health minus static serial budget AUC is "
                f"{equal_provenance_health['difference']:+.4f}, 95% CI "
                f"[{equal_provenance_health['low']:+.4f}, "
                f"{equal_provenance_health['high']:+.4f}] for provenance and "
                f"{equal_fusion_health['difference']:+.4f}, 95% CI "
                f"[{equal_fusion_health['low']:+.4f}, "
                f"{equal_fusion_health['high']:+.4f}] for fusion. Only the "
                "test-expensive provenance comparison is narrowly resolved: "
                f"{test_expensive_provenance_health['difference']:+.4f}, 95% CI "
                f"[{test_expensive_provenance_health['low']:+.4f}, "
                f"{test_expensive_provenance_health['high']:+.4f}]."
            ),
            "scope": (
                "The sibling AUC is a retrospective correlation diagnostic and "
                "the correctness endpoints are selectively adjudicated. The online "
                "policy itself uses only previously observed outcomes. No broad "
                "stream-health superiority claim is supported; the simpler static "
                "serial policy remains primary."
            ),
        },
        {
            "id": "C17",
            "status": "supported",
            "claim": "The released Practical POD RepairLLaMA benchmark contains substantial unadjudicated-negative label contamination and is nearly saturated for native-order ranking.",
            "evidence": (
                f"Of 169 candidates in the five-detector common split, "
                f"{practical_audit['common_unreviewed_candidates']} "
                "were assigned overfitting labels despite RepairLLaMA's final "
                "manual-review script skipping their bug rows after finding a "
                "correct sibling. This is "
                f"{percent(practical_audit['common_unreviewed_fraction_of_all'])} "
                "of the split and "
                f"{percent(practical_audit['common_unreviewed_fraction_of_released_overfitting'])} "
                "of released negatives. The released-label classifier replication "
                f"recovers LLM4PatchCorrect balanced accuracy {practical_llm4_ba:.3f}. "
                f"Native ranking reaches R@1 {percent(practical_native['recall@1'])} "
                f"and R@3 {percent(practical_native['recall@3'])}; verified-only "
                "native R@1 is "
                f"{percent(practical_verified['operational_ranking']['summaries']['source_order']['recall@1'])}."
            ),
            "scope": (
                "This is a provenance audit of the pinned one-generator "
                "RepairLLaMA subset, not proof that any unknown patch is correct or "
                "that the source study's broader classical-APR conclusions are "
                "invalid. Released, verified-only, and optimistic label worlds are "
                "reported separately; performance claims that change direction are "
                "withheld."
            ),
        },
        {
            "id": "C18",
            "status": "supported_scoped",
            "claim": "The pinned released PrevaRank ranker is inferior to native order on mixed-generator LLM patch pools, while superiority in its original per-generator setting remains unresolved.",
            "evidence": (
                "On 115 adjudicated mixed-generator pools, PrevaRank minus native "
                f"MRR is {prevarank_mixed_vs_native['mrr_vs_native']['observed_difference']:+.4f}, "
                f"95% CI [{prevarank_mixed_vs_native['mrr_vs_native']['ci_low']:+.4f}, "
                f"{prevarank_mixed_vs_native['mrr_vs_native']['ci_high']:+.4f}]; "
                "Recall@1 difference is "
                f"{prevarank_mixed_vs_native['recall_at_1_vs_native']['observed_difference']:+.4f}, "
                f"CI [{prevarank_mixed_vs_native['recall_at_1_vs_native']['ci_low']:+.4f}, "
                f"{prevarank_mixed_vs_native['recall_at_1_vs_native']['ci_high']:+.4f}], "
                "and pairwise-AUC difference is "
                f"{prevarank_mixed_vs_native['pairwise_auc_vs_native']['observed_difference']:+.4f}, "
                f"CI [{prevarank_mixed_vs_native['pairwise_auc_vs_native']['ci_low']:+.4f}, "
                f"{prevarank_mixed_vs_native['pairwise_auc_vs_native']['ci_high']:+.4f}]. "
                "On 62 adjudicated per-generator pools, the MRR difference reverses "
                f"to {prevarank_stream_vs_native['mrr_vs_native']['observed_difference']:+.4f}, "
                f"CI [{prevarank_stream_vs_native['mrr_vs_native']['ci_low']:+.4f}, "
                f"{prevarank_stream_vs_native['mrr_vs_native']['ci_high']:+.4f}]. "
                "Mixed-pool PrevaRank minus tie-aware random is "
                f"{prevarank_mixed_vs_random['mrr_vs_random']['observed_difference']:+.4f}, "
                f"CI [{prevarank_mixed_vs_random['mrr_vs_random']['ci_low']:+.4f}, "
                f"{prevarank_mixed_vs_random['mrr_vs_random']['ci_high']:+.4f}]."
            ),
            "scope": (
                "This is a direct run of the authors' content-hashed executable and "
                "database on the "
                f"{percent(prevarank_manifest['counts']['supported_candidate_count'] / prevarank_manifest['counts']['candidate_count'], 2)} "
                "released-parser-supported common population, "
                f"not a proxy implementation. The executable reproduces "
                f"{prevarank_reproduction['summary']['divergence_classes']['exact']}/"
                f"{prevarank_reproduction['summary']['workbook_count']} released "
                "workbooks logically exactly and preserves patch order for "
                f"{prevarank_reproduction['summary']['divergence_classes']['exact'] + prevarank_reproduction['summary']['divergence_classes']['metadata_only']}/"
                f"{prevarank_reproduction['summary']['workbook_count']}. Unknown-"
                "label worlds materially alter the stream result, so no broad "
                "PrevaRank-failure or worse-than-random claim is supported. The "
                "mixed native comparison was the predeclared authentic-baseline "
                "gate; exploratory method-wide multiplicity is reported separately. "
                "After a frozen stable-hash input intervention, PrevaRank minus "
                "native MRR is "
                f"{prevarank_shuffled_vs_native['observed_difference']:+.4f}, "
                f"95% CI [{prevarank_shuffled_vs_native['ci_low']:+.4f}, "
                f"{prevarank_shuffled_vs_native['ci_high']:+.4f}]. The inferiority "
                "claim therefore applies to the predeclared operational "
                "native-ordered adapter, not every arbitrary input permutation."
            ),
        },
        {
            "id": "C19",
            "status": "supported_scoped",
            "claim": "PrevaRank's classical repair-pattern taxonomy has lower coverage on LLM patches, and its released final ordering is causally sensitive to supplied candidate order.",
            "evidence": (
                "No-Category rises from "
                f"{percent(prevarank_shift['classical_apr']['no_category_rate'], 2)} "
                "on 22,993 reproduced classical-APR outputs to "
                f"{percent(prevarank_shift['llm_apr']['no_category_rate'], 2)} "
                "on 4,180 LLM candidates, a "
                f"{points(prevarank_shift['comparison']['no_category_rate_difference'], 2)}-point "
                "difference with 95% CI "
                f"{points_interval(prevarank_shift['comparison']['no_category_rate_difference_ci'], 2)}. "
                "Historical value ties cover "
                f"{percent(prevarank_shift['llm_released_rank_input_order_inheritance']['historical_value_tied_pair_rate'], 2)} "
                "of within-pool LLM candidate pairs. A frozen label-independent "
                "stable-hash intervention changes "
                f"{prevarank_order_reconciliation['input_position_change_count']:,}/"
                f"{prevarank_order_reconciliation['candidate_instance_count']:,} "
                "input positions and "
                f"{prevarank_order_reconciliation['released_rank_change_count']:,}/"
                f"{prevarank_order_reconciliation['candidate_instance_count']:,} "
                "released ranks; the top normalized patch changes in "
                f"{prevarank_order_sensitivity['pool_top_patch_change_count']:,}/"
                f"{prevarank_order_sensitivity['pool_count']:,} pools and "
                f"{percent(prevarank_order_sensitivity['pairwise_order_discordance_rate_micro'], 2)} "
                "of normalized-patch pair orders reverse. Within historical-value "
                "ties, canonical and permuted outputs agree with their own supplied "
                "orders at "
                f"{percent(prevarank_order_alignments['canonical_rank_vs_canonical_input']['historical_value_tied_pair_input_order_agreement'], 2)} "
                "and "
                f"{percent(prevarank_order_alignments['shuffled_rank_vs_shuffled_input']['historical_value_tied_pair_input_order_agreement'], 2)}, "
                "but cross-order agreement is only "
                f"{percent(prevarank_order_alignments['canonical_rank_vs_shuffled_input']['historical_value_tied_pair_input_order_agreement'], 2)} "
                "and "
                f"{percent(prevarank_order_alignments['shuffled_rank_vs_canonical_input']['historical_value_tied_pair_input_order_agreement'], 2)}. "
                "Category, bug type, and historical value change for zero candidates."
            ),
            "scope": (
                "The coverage comparison is bug/workbook-clustered and supports a "
                "classical-to-LLM representation-shift claim for this artifact. "
                "The intervention establishes causal output-order sensitivity for "
                "the pinned executable under one predeclared deterministic "
                "permutation; it does not estimate an average effect over every "
                "possible order. Adjudicated MRR changes by "
                f"{prevarank_order_adjudicated_mrr['observed_difference']:+.4f}, "
                f"95% CI [{prevarank_order_adjudicated_mrr['ci_low']:+.4f}, "
                f"{prevarank_order_adjudicated_mrr['ci_high']:+.4f}], while the "
                "pessimistic-Unknown difference is "
                f"{prevarank_order_pessimistic_mrr['observed_difference']:+.4f}, "
                f"CI [{prevarank_order_pessimistic_mrr['ci_low']:+.4f}, "
                f"{prevarank_order_pessimistic_mrr['ci_high']:+.4f}]. Therefore "
                "structural instability is supported, but a label-robust aggregate "
                "utility effect is not."
            ),
        },
        {
            "id": "C20",
            "status": "supported_scoped",
            "claim": "A fold-separated, shift-aware gate can selectively deploy configuration-position ranking under a predeclared incremental-harm calibration constraint relative to native order.",
            "evidence": (
                "On Defects4J, the predeclared q95/r20 gate overrides "
                f"{safe_primary_actions['action_counts'].get('override', 0):,}/"
                f"{safe_primary_actions['context_count']:,} contexts and improves "
                f"MRR by {safe_internal['safe_gate_mrr_vs_native']['observed_difference']:+.4f}, "
                f"95% CI [{safe_internal['safe_gate_mrr_vs_native']['ci_low']:+.4f}, "
                f"{safe_internal['safe_gate_mrr_vs_native']['ci_high']:+.4f}], "
                "while all-context verified budget-1 success rises by "
                f"{points(safe_internal['safe_gate_budget1_vs_native']['observed_difference'], 2)} "
                "points, 95% CI "
                f"{points_interval(safe_internal['safe_gate_budget1_vs_native'], 2)}. "
                "All five held-out folds have realized mean override harm below "
                "their separately calibrated upper bounds. Zero-shot HumanEval-"
                f"Java transfer remains positive: MRR {safe_human['safe_gate_mrr_vs_native']['observed_difference']:+.4f}, "
                f"CI [{safe_human['safe_gate_mrr_vs_native']['ci_low']:+.4f}, "
                f"{safe_human['safe_gate_mrr_vs_native']['ci_high']:+.4f}], "
                "and all-context budget-1 gain "
                f"{points(safe_human['safe_gate_budget1_vs_native']['observed_difference'], 2)} "
                f"points, CI {points_interval(safe_human['safe_gate_budget1_vs_native'], 2)}."
            ),
            "scope": (
                "The controlled quantity is expected worst-context budget-1 "
                "regression per overridden bug, not patch-incorrectness risk. "
                "The primary target permits a 20% calibration upper bound; at "
                "5% and 10% no fold certifies an override. The internal gate's "
                "MRR cost relative to always-stream is "
                f"{safe_internal['safe_gate_mrr_vs_always_stream']['observed_difference']:+.4f}, "
                f"CI [{safe_internal['safe_gate_mrr_vs_always_stream']['ci_low']:+.4f}, "
                f"{safe_internal['safe_gate_mrr_vs_always_stream']['ci_high']:+.4f}], "
                "but HumanEval deferral has a resolved utility cost of "
                f"{safe_human['safe_gate_mrr_vs_always_stream']['observed_difference']:+.4f}, "
                f"CI [{safe_human['safe_gate_mrr_vs_always_stream']['ci_low']:+.4f}, "
                f"{safe_human['safe_gate_mrr_vs_always_stream']['ci_high']:+.4f}]. "
                "Full GitBug-Java is entirely deferred because its index-59 "
                "generation budget is out of support, yielding "
                f"{safe_gitbug['safe_gate_mrr_vs_native']['observed_difference']:+.4f} "
                "MRR change. Its top-10 control has "
                f"MRR gain {safe_gitbug_top10['safe_gate_mrr_vs_native']['observed_difference']:+.4f}, "
                f"CI [{safe_gitbug_top10['safe_gate_mrr_vs_native']['ci_low']:+.4f}, "
                f"{safe_gitbug_top10['safe_gate_mrr_vs_native']['ci_high']:+.4f}]. "
                "Defects4J semantic-only MRR gain is "
                f"{safe_internal_strata['semantic_only']['observed_difference']:+.4f}, "
                f"CI [{safe_internal_strata['semantic_only']['ci_low']:+.4f}, "
                f"{safe_internal_strata['semantic_only']['ci_high']:+.4f}]; "
                "semantic generalization remains unresolved."
            ),
        },
        {
            "id": "C21",
            "status": "supported_negative",
            "claim": "Strict incremental-harm targets do not certify learned scheduler overrides on this corpus.",
            "evidence": (
                "Across the five nested test rotations, the total number of "
                "overrides selected at the predeclared 5% and 10% expected-"
                f"harm targets is {safe_low_risk_overrides}. Both policies reduce "
                "exactly to native order inside the support envelope, while the "
                "20% target is the first predeclared level that is feasible in "
                "every fold."
            ),
            "scope": (
                "This is a finite-sample limitation of simultaneous bug-level "
                "Hoeffding calibration, not evidence that the learned ranker is "
                "intrinsically unsafe. Do not relax the target after observing "
                "final utility or present the 20% bound as a correctness guarantee."
            ),
        },
        {
            "id": "C22",
            "status": "supported_negative",
            "claim": "Returned-sample position does not outperform random expectation in the newer RepairBench generation campaign.",
            "evidence": (
                "Across 21,144 candidates from 35 source configurations and 76 "
                "test-plausibility-positive merged pools, returned-index MRR is "
                f"{repairbench_primary['methods']['returned_index']['summary']['mrr']:.4f} "
                "versus "
                f"{repairbench_primary['methods']['random_expected']['summary']['mrr']:.4f} "
                "for exact-tie random expectation, a difference of "
                f"{repairbench_primary_index_random['observed_difference']:+.4f}, "
                f"95% CI [{repairbench_primary_index_random['ci_low']:+.4f}, "
                f"{repairbench_primary_index_random['ci_high']:+.4f}]. The "
                "reference-complete and pessimistic-Unknown sensitivity intervals "
                "also include zero."
            ),
            "scope": (
                "This is a failed replication under generator-configuration and "
                "generation-protocol shift, not evidence that order never matters. "
                "The new campaign has zero exact source-configuration overlap and "
                f"only {repairbench_integrity['candidate_overlap']['candidate_identity_overlap']} "
                "exact shared candidates, but it reuses the same 89 GitBug-Java "
                "contexts and comes from the same research lineage. Call the score "
                "returned-sample index because the campaign mixes repeated responses "
                "with single responses containing multiple choices."
            ),
        },
        {
            "id": "C23",
            "status": "supported_scoped",
            "claim": "The frozen shift-aware scheduler detects a wholly unseen RepairBench configuration set and abstains without changing the baseline ranking.",
            "evidence": (
                "All 35 exact source configurations are unseen. The frozen q95/r20 "
                "gate emits defer for all 89 contexts, and its MRR and all-context "
                "budget-1 success equal returned-index ranking exactly in every "
                "label world."
            ),
            "scope": (
                "This verifies graceful abstention and prevents unsupported "
                "configuration aliasing. It is not positive utility transport, a "
                "renewed risk guarantee, or evidence that an all-defer deployment "
                "is useful without later calibration data."
            ),
        },
        {
            "id": "C24",
            "status": "supported_negative",
            "claim": "Zero-shot buggy-patch CodeT5+ similarity is not an effective merged-pool prioritizer in the RepairBench campaign.",
            "evidence": (
                "On the frozen test-plausibility endpoint, CodeT5+ similarity "
                "trails returned index by "
                f"{repairbench_primary_similarity_index['observed_difference']:+.4f} "
                "MRR, 95% CI "
                f"[{repairbench_primary_similarity_index['ci_low']:+.4f}, "
                f"{repairbench_primary_similarity_index['ci_high']:+.4f}]. "
                "Across all 89 contexts, its budget-1 difference is "
                f"{points(repairbench_budget_similarity_index['observed'], 2)} "
                "points, 95% CI "
                f"{points_interval(repairbench_budget_similarity_index, 2)}. "
                "The MRR deficit remains resolved under reference-complete and "
                "pessimistic-Unknown labels."
            ),
            "scope": (
                "This tests one pinned zero-shot representation and one simple "
                "buggy-patch cosine score. It does not show that semantic models, "
                "task-specific training, or stream-normalized ranking cannot work. "
                "Both distance and the historically correct similarity direction "
                "are retained under disclosed Protocol Amendment A1."
            ),
        },
        {
            "id": "C25",
            "status": "exploratory",
            "claim": "Candidate-level discrimination can conceal a merged-generator top-rank failure caused by pool-scale tail accumulation.",
            "evidence": (
                "Under pessimistic reference labels, CodeT5+ similarity has macro "
                "AUC "
                f"{repairbench_reference_pool['metric_discordance']['merged_codet5_similarity_macro_auc']:.4f} "
                "but merged-pool MRR "
                f"{repairbench_reference_pool['metric_discordance']['merged_codet5_similarity_mrr']:.4f} "
                "and an MRR deficit from returned index of "
                f"{repairbench_reference_pool['metric_discordance']['merged_codet5_similarity_minus_returned_mrr']:+.4f}. "
                "Its per-generator MRR difference is "
                f"{repairbench_reference_pool['metric_discordance']['per_generator_codet5_similarity_minus_returned_mrr']:+.4f}. "
                "The merged-minus-per-generator relative-MRR interaction is "
                f"{repairbench_reference_pool['codet5_similarity_relative_to_returned_index']['observed']:+.4f}, "
                "95% CI "
                f"[{repairbench_reference_pool['codet5_similarity_relative_to_returned_index']['ci_low']:+.4f}, "
                f"{repairbench_reference_pool['codet5_similarity_relative_to_returned_index']['ci_high']:+.4f}]."
            ),
            "scope": (
                "This diagnostic was designed after observing the confirmatory "
                "AUC/top-rank discrepancy. Report it as an exploratory mechanism "
                "finding and motivation for pool-aware, budget-aware APCA metrics; "
                "confirm it on another untouched campaign before making it a "
                "primary general law."
            ),
        },
    ]
    threats = [
        {
            "category": "Construct validity",
            "threat": "Patch correctness depends on manual/equivalence judgments, available tests are incomplete, and correctness-evidence strata differ in difficulty.",
            "mitigation": "Adjudication provenance, exact/AST/semantic evidence, explicit unknown labels, a plausible-only analysis that never equates test passing with correctness, and separate exact/AST versus semantic-only ranking results.",
            "residual": f"Manual judgments can still be wrong; {weak['candidate_unknown']:,} plausible candidates remain unresolved, and only 40 positive contexts are semantic-only.",
        },
        {
            "category": "Internal validity",
            "threat": "Duplicate evidence conflicts, raw default labels, and threshold selection can create optimistic results.",
            "mitigation": "Conflict flags plus exclusion sensitivity, candidate deduplication, bug-level folds, nested 3/1/1 threshold selection, and executable evidence rules that preserve skipped manual reviews as Unknown.",
            "residual": "Deduplication and evidence precedence remain design choices, the curator depends on documented semantics of the upstream review scripts, and the adjudicated plausible subset is selectively labeled because skipped reviews are concentrated in contexts already containing an exact/AST fix.",
        },
        {
            "category": "Data leakage",
            "threat": "The same bug, candidate, or source-configuration evidence could enter fitting and evaluation.",
            "mitigation": "Bug-disjoint OOF evaluation, crossed bug/configuration and bug/model-lineage holdouts, candidate-disjoint unseen-stream checks, provider-stratified correctness evidence, a GitBug-Java stress test, and executable invariants.",
            "residual": (
                "Pretraining contamination of public Defects4J fixes is not measurable "
                "here. Concentration of gains in exact/AST-equivalent fixes makes a "
                "post-cutoff or recent-bug replication especially important."
            ),
        },
        {
            "category": "External validity",
            "threat": "The main corpus is Java/Defects4J from one repair campaign and 14 configurations.",
            "mitigation": (
                "Zero-shot HumanEval-Java and GitBug-Java transfer; held-out-"
                "configuration, named-model-lineage, and conservative provider-"
                "lineage stress tests; and a pinned newer RepairBench campaign "
                "with 35 exactly unseen source configurations and only 0.16% "
                "exact candidate overlap."
            ),
            "residual": (
                "Several configurations share model families and prompting/fine-tuning "
                "lineage. RepairBench is a distinct generation campaign but reuses "
                "the same 89 GitBug-Java contexts and comes from the same research "
                "lineage. Other languages, independent groups and benchmarks, "
                "agentic repair systems, and repository-level patches may behave "
                "differently."
            ),
        },
        {
            "category": "Statistical conclusion validity",
            "threat": "Candidates within a bug are dependent, exploratory aggregators increase multiplicity, and the 14 source configurations are not fully independent model families.",
            "mitigation": "Bug-clustered 10,000-replicate paired bootstrap intervals; stream-max was designated primary on Defects4J before external transfer; correlation uncertainty is reported at the configuration unit.",
            "residual": (
                "No preregistration or family-wise multiplicity correction is "
                "claimed. The RepairBench pool-scale interaction was designed "
                "after observing AUC/top-rank discordance and remains explicitly "
                "exploratory."
            ),
        },
        {
            "category": "Operational validity",
            "threat": "Validation actions have unequal real costs, test passing is not correctness, and retrospective labels can make scheduling look more deployable than it is.",
            "mitigation": f"Retain all unsolved contexts; simulate explicit compile, test, and semantic-review actions; report four predeclared cost scenarios; quantify that {weak['candidate_incorrect']:,} known-incorrect patches pass tests; and separately test automatic-accept risk under pessimistic Unknown handling.",
            "residual": (
                "Action costs are scenario weights rather than measured wall-clock. "
                "`VALIDATION_COST_MEASUREMENT_PROTOCOL.md` freezes the future "
                "timing study, but parallelism, flaky tests, incremental test "
                "selection, generation cost, and repository-specific validation "
                "remain unevaluated."
            ),
        },
        {
            "category": "Outcome-stage validity",
            "threat": "A ranking signal measured before test execution may predict test failure or reference reproduction rather than semantic correctness among plausible patches.",
            "mitigation": (
                "Candidate- and occurrence-level analyses separately estimate compile, "
                "test-given-compile, reference-match-given-test, and semantic-"
                "correctness endpoints. Stage-specific models and a factorized "
                "scheduler preserve those distinctions."
            ),
            "residual": (
                "Only 239 semantic non-reference positives and 40 semantic-only "
                "positive contexts are available. Aggregate scheduling gains are "
                "therefore not evidence of broad semantic-repair confidence."
            ),
        },
        {
            "category": "Selective-label and policy validity",
            "threat": "Unknown semantic labels are selectively missing, so complete-case risk estimates can understate wrong automatic acceptance.",
            "mitigation": "Treat every accepted Unknown as an error in the primary risk analysis, fit thresholds on a separate calibration fold, use simultaneous one-sided exact bounds, and report infeasible target-risk settings instead of silently relaxing them.",
            "residual": "The pessimistic bound may be conservative, while complete-case analysis is optimistic. More independent adjudication is needed before a useful low-risk auto-accept claim is possible.",
        },
        {
            "category": "Safe-scheduler transport validity",
            "threat": "A calibration bound for incremental scheduler harm can fail under nonexchangeable generator, candidate-budget, or campaign shift.",
            "mitigation": (
                "Separate fitting, threshold calibration, and final bug folds; "
                "control harm relative to native order rather than absolute "
                "correctness; use only pre-validation support features; retain "
                "native fallback; expose out-of-support contexts; and run zero-shot "
                "HumanEval-Java plus full and top-10 RepairLLaMA GitBug-Java stress "
                "tests. Freeze the gate before applying it to all 35 unseen "
                "RepairBench configurations."
            ),
            "residual": (
                "The primary 20% upper-bound target is not a low absolute risk "
                "guarantee, the robust-distance support model is heuristic, and "
                "external labels do not renew the Defects4J guarantee. The original "
                "full GitBug-Java campaign and the wholly unseen RepairBench campaign "
                "are entirely deferred; graceful abstention demonstrates scope "
                "control, not transported utility."
            ),
        },
        {
            "category": "Causal interpretation",
            "threat": "Observed minimum-rank effects do not prove why generators place correct patches earlier.",
            "mitigation": (
                "Ablate source prior and global index, inspect failure categories, "
                "document RepairLLaMA's native output order, audit RepairBench's "
                "repeated-response versus single-response multi-choice mechanics, "
                "and report the independent-campaign null result."
            ),
            "residual": (
                "Generation order is not a standardized construct across APIs, and "
                "the RepairBench generation-mechanics groups are observational "
                "rather than randomized. Position remains a campaign-specific "
                "empirical prior, not a causal theory."
            ),
        },
        {
            "category": "Adaptive-feedback validity",
            "threat": "Strong same-context sibling correlations can be mistaken for useful online decision information or can reflect selective adjudication.",
            "mitigation": "Exclude each target candidate from the retrospective sibling diagnostic, update the deployable policy only after an action is observed, isolate compile/test/correctness states, freeze shrinkage before evaluation, and compare against both static serial and fixed-belief adaptive policies.",
            "residual": "Correctness correlations are affected by selective manual review, and the predeclared online updater provides little incremental utility. No adaptive stream-health superiority claim is made.",
        },
        {
            "category": "Baseline completeness",
            "threat": "Published APCA methods use different data and evaluation protocols.",
            "mitigation": (
                "Include transparent lexical, order, occurrence, CodeT5+, and fully "
                "fine-tuned UniXcoder baselines; reproduce five Practical POD "
                "predictions at candidate identity; run the pinned released "
                "PrevaRank executable; and evaluate a pinned CodeT5+ revision "
                "zero-shot on the RepairBench campaign."
            ),
            "residual": "The Practical POD split is nearly saturated for ranking and has unresolved labels. APPT and ComPass still lack compatible direct runs in this artifact and must not be compared through non-common published headline numbers.",
        },
        {
            "category": "Third-party artifact adaptation",
            "threat": "PrevaRank consumes changed lines rather than full methods, its packaged outputs are not perfectly bit-reproducible, and arbitrary input order can influence tied candidates.",
            "mitigation": (
                "Pin archive, executable, and database hashes; reproduce all 348 "
                "released workbooks; preserve a lossless candidate-to-changed-line "
                "round trip; collapse representation duplicates into ties; exclude "
                "unsupported candidates for every method; independently verify all "
                "2,229 LLM output workbooks; and report mixed and per-generator pools "
                "under three label worlds. Re-run all 465 mixed pools after a frozen "
                "label-independent stable-hash permutation and compare candidate "
                "identity, features, ranks, top choices, pair order, and utility."
            ),
            "residual": (
                "Only 91.95% of released workbooks reproduce logically exactly, "
                "20 of 4,200 LLM candidates are outside executable support, and one "
                "deterministic permutation does not characterize every possible "
                "input order. The intervention establishes output instability, "
                "while adjudicated utility change remains unresolved and "
                "Unknown-label assumptions alter its direction. Results apply to "
                "the pinned released artifact, not every possible reimplementation "
                "of its feature design."
            ),
        },
        {
            "category": "External benchmark label validity",
            "threat": "A released comparison benchmark may encode default values as semantic-negative labels even when manual review was skipped.",
            "mitigation": "Trace every Practical POD patch through the original RepairLLaMA row, V2 annotation evidence, stable candidate ID, and nested fold; report released, verified-only, and optimistic-unknown label worlds.",
            "residual": (
                f"The true labels of {practical_audit['common_unreviewed_candidates']} "
                "common-split candidates remain unknown. Sensitivity worlds bound "
                "assumptions but do not replace independent adjudication."
            ),
        },
        {
            "category": "RepairBench endpoint validity",
            "threat": (
                "RepairBench test passage is plausibility, while test-passing "
                "non-reference patches may be semantically correct or overfitting."
            ),
            "mitigation": (
                "Separate test-plausibility, reference-complete, pessimistic-Unknown, "
                "and optimistic-Unknown worlds; preserve 2,710 semantic labels as "
                "Unknown; and freeze a method-blinded adjudication packet."
            ),
            "residual": (
                "The 325-item packet is not confirmatory until two independent "
                "reviewers and a third disagreement adjudicator complete it. "
                "Partial-identification bounds remain primary."
            ),
        },
        {
            "category": "Pool-composition validity",
            "threat": (
                "Candidate-level AUC and one-generator rankings may not predict "
                "first-correct retrieval after many generator streams are merged."
            ),
            "mitigation": (
                "Report exact-tie MRR, Recall@k, all-context budget-1, merged and "
                "per-generator pool views, and a bug-paired pool-scale interaction."
            ),
            "residual": (
                "The pool-scale diagnostic was post-confirmatory and currently "
                "demonstrated with one zero-shot score on one campaign; its mechanism "
                "requires confirmation on another untouched campaign."
            ),
        },
        {
            "category": "Artifact availability",
            "threat": "Redistributing generated source patches may require permission from the upstream artifact authors.",
            "mitigation": "Pin the upstream RepairLLaMA commit, publish hashes and deterministic curation scripts, and request explicit redistribution/license clarification before releasing raw derived code.",
            "residual": "If permission is not obtained, release a reproduce-from-upstream package rather than bundling raw patch text.",
        },
    ]
    return claims, threats


def render_tables(tables):
    lines = [
        "# Paper Tables",
        "",
        f"Generated by `make_paper_tables.py` ({VERSION}) from authoritative evidence artifacts.",
        "Do not hand-copy or combine these values with legacy Defects4J V1 tables.",
        "",
    ]
    for table in tables:
        lines.extend(
            [
                f"## {table['id']}: {table['title']}",
                "",
                markdown_table(table["headers"], table["rows"]),
                "",
                f"Note: {table['note']}",
                "",
            ]
        )
    return "\n".join(lines)


def render_csv(tables):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=["table_id", "table_title", "row_index", "field", "value"],
        lineterminator="\n",
    )
    writer.writeheader()
    for table in tables:
        for index, row in enumerate(table["rows"], start=1):
            for field in table["headers"]:
                writer.writerow(
                    {
                        "table_id": table["id"],
                        "table_title": table["title"],
                        "row_index": index,
                        "field": field,
                        "value": row.get(field, ""),
                    }
                )
    return output.getvalue()


def render_claims(claims, threats):
    lines = [
        "# Paper Claims and Threats",
        "",
        "This file is generated from authoritative evidence artifacts. Supported, scoped, null, and exploratory claims are intentionally separated.",
        "",
        "## Claim Ledger",
        "",
    ]
    for claim in claims:
        lines.extend(
            [
                f"### {claim['id']} [{claim['status']}]",
                "",
                claim["claim"],
                "",
                f"Evidence: {claim['evidence']}",
                "",
                f"Scope: {claim['scope']}",
                "",
            ]
        )
    lines.extend(["## Threats to Validity", ""])
    for threat in threats:
        lines.extend(
            [
                f"### {threat['category']}",
                "",
                f"Threat: {threat['threat']}",
                "",
                f"Mitigation: {threat['mitigation']}",
                "",
                f"Residual risk: {threat['residual']}",
                "",
            ]
        )
    return "\n".join(lines)


def render_packet(data, claims, threats):
    audit = data["dataset_audit"]
    plausible = data["plausible_audit"]
    weak = weak_oracle_statistics(data)
    transfer = human_transfer_diagnostics(data)
    transfer_ci = transfer["pearson_fisher_95_ci"]
    prevarank_manifest = load_json(
        AUXILIARY_INPUTS["prevarank_preparation_manifest"]
    )
    prevarank_mixed = find_prevarank_protocol(
        data, "mixed", "adjudicated_only"
    )
    prevarank_stream = find_prevarank_protocol(
        data, "stream", "adjudicated_only"
    )
    prevarank_mixed_vs_native = prevarank_mixed[
        "paired_comparisons_vs_native"
    ]["prevarank_released_rank"]
    prevarank_stream_vs_native = prevarank_stream[
        "paired_comparisons_vs_native"
    ]["prevarank_released_rank"]
    prevarank_shift = data["prevarank_domain_shift"]
    prevarank_order = data["prevarank_input_order"]
    prevarank_order_reconciliation = prevarank_order["reconciliation"]
    prevarank_order_sensitivity = prevarank_order_reconciliation[
        "released_rank_order_sensitivity"
    ]
    prevarank_order_alignments = prevarank_order_reconciliation[
        "input_order_alignment_matrix"
    ]["alignments"]
    prevarank_order_adjudicated_mrr = find_prevarank_order_world(
        data, "adjudicated_only"
    )["paired_comparisons"]["shuffled_rank_minus_canonical_rank"]["mrr"]
    prevarank_order_pessimistic_mrr = find_prevarank_order_world(
        data, "pessimistic_unknown"
    )["paired_comparisons"]["shuffled_rank_minus_canonical_rank"]["mrr"]
    shift_aware = data["shift_aware_safe_scheduler"]
    safe_internal = shift_aware["internal"]["primary_summary"]
    safe_human = shift_aware["external"]["humanevaljava"][
        "primary_summary"
    ]
    safe_actions = shift_aware["internal"]["primary_actions"]
    repairbench = data["repairbench_external_campaign"]
    repairbench_integrity = data["repairbench_campaign_integrity"]
    repairbench_review = data["repairbench_semantic_review_audit"]
    repairbench_primary = repairbench["worlds"]["test_plausibility"][
        "merged"
    ]["ranking"]
    repairbench_index_random = repairbench_primary["comparisons"][
        "returned_index_minus_random"
    ]["mrr"]
    repairbench_similarity_index = repairbench_primary["comparisons"][
        "codet5_similarity_minus_returned_index"
    ]["mrr"]
    repairbench_pool_interaction = repairbench[
        "exploratory_pool_scale_diagnostics"
    ]["worlds"]["reference_pessimistic"][
        "codet5_similarity_relative_to_returned_index"
    ]
    pretest_test_failures = (
        audit["candidate_counts"]["hard"]
        - plausible["labeled"]["candidate_count"]
    )
    pretest_test_failure_rate = (
        pretest_test_failures / audit["candidate_counts"]["hard"]
    )
    supported = [
        claim for claim in claims if claim["status"].startswith("supported")
    ]
    exploratory = [
        claim for claim in claims if claim["status"] == "exploratory"
    ]
    unsupported = [
        claim for claim in claims if claim["status"] == "not_supported"
    ]
    lines = [
        "# Co-Author Review Packet",
        "",
        f"Artifact version: {VERSION} evidence-corrected packet. The previous V1 and pre-correction V2 packets are superseded.",
        "",
        "## Project in One Sentence",
        "",
        "We model APR validation as a stage-factorized decision problem over compile, test, and semantic-review actions, wrap learned scheduling in a fold-separated override/fallback/defer gate, and test that deployment contract under a newer 35-configuration generation campaign.",
        "",
        "## Contribution Hierarchy",
        "",
        "1. Mechanistic finding: native generation rank changes meaning across the validation funnel and is strongest for reference reproduction, not generic semantic correctness.",
        "2. Method: a nested, stage-factorized provenance-content policy for serial compile/test/review scheduling under explicit action costs.",
        "3. Safe deployment method: a fold-separated support and harm gate selectively overrides native order, falls back when uncertified, and explicitly defers out-of-support campaigns.",
        "4. Safety result: bug-level risk calibration with explicit Unknown labels reports when automatic acceptance is statistically infeasible and must defer.",
        "5. Artifact: an adjudication-aware LLM-native corpus with correct, incorrect, unknown, provenance, conflict, and validation-stage views.",
        "6. External benchmark integrity: an identity-level Practical POD audit exposes unreviewed negatives, while a pinned PrevaRank run and controlled input-order intervention test an authentic APR-native ranker under LLM distribution shift.",
        "7. Campaign-shift evidence: a frozen RepairBench evaluation shows that returned position does not universally replicate and that the safe gate abstains on all 35 unseen configurations.",
        "8. Exploratory operational finding: modest candidate-level AUC can conceal severe first-correct degradation when many generator streams are merged.",
        "9. Boundary evidence: exact/AST versus semantic-only strata, label-world sensitivity, and failed adaptive interleaving prevent broad or misleading claims.",
        "",
        "## Authoritative Dataset",
        "",
        f"- {audit['source_file_count']} source configurations and {audit['raw_audit']['raw_official_occurrences']:,} official raw occurrences.",
        f"- {audit['candidate_counts']['all_included']:,} included deduplicated candidates; {audit['candidate_counts']['hard']:,} in the compile-filtered pre-test benchmark.",
        f"- Pre-test labels: {audit['candidate_labels_hard']['correct']:,} correct and {audit['candidate_labels_hard']['incorrect']:,} compile-passing incorrect.",
        f"- {pretest_test_failures:,} pre-test candidates ({percent(pretest_test_failure_rate)}) still fail the available tests; only {plausible['labeled']['candidate_count']:,} are both test-passing and adjudicated.",
        f"- Plausible APCA: {plausible['labeled']['candidate_count']:,} labeled test-passing candidates plus {plausible['unknown']['candidate_count']:,} unresolved candidates kept separate.",
        "- All main evaluation uses deterministic bug-level folds, exact tie expectations, and bug-clustered uncertainty.",
        "",
        "## Protocol Boundary That Prevents a False Contradiction",
        "",
        "- C2 is known-configuration, unseen-bug evaluation on Defects4J.",
        "- C3 is rotating leave-one-configuration-out evaluation: 14 configurations x 5 held-out bug folds = 70 crossed cells.",
        "- C3 is not leave-one-model-family-out because multiple configurations share model and prompting/fine-tuning lineage.",
        "- A separate decision-gate analysis now adds 20 named-model-lineage x bug-fold cells and 15 conservative provider-lineage x bug-fold cells; neither fallback comparison beats minimum native rank.",
        "- C5 is unseen-benchmark transfer to HumanEval-Java, but all 14 HumanEval source configurations were present in the Defects4J calibration data.",
        "- No HumanEval label was used to fit or tune the transferred scorer.",
        "- Therefore C3 and C5 test different axes: held-out configuration versus unseen benchmark with seen configurations.",
        "- C22 is a generation-campaign shift test: RepairBench reuses the same 89 GitBug-Java contexts but has 35 exactly unseen source-configuration IDs and only 34 exact shared candidates.",
        "- C23 freezes the Defects4J gate before RepairBench outcomes are used; all 89 contexts defer because every exact source configuration is unseen.",
        "- C25 is post-confirmatory and exploratory. It diagnoses merged-pool AUC/top-rank discordance but was not a frozen primary hypothesis.",
        "",
        "## Integrity Boundaries Added After Audit",
        "",
        "- Upstream review scripts skip further semantic review for a bug row once an exact/AST-matching patch is present. Test-passing nonmatching candidates in those rows are now Unknown, never negative; executable regression tests enforce this distinction.",
        "- The paper-facing baseline is minimum native rank: after exact patch deduplication, each candidate receives its best observed within-stream index across selected configurations. It is not one global chronological source order.",
        "- Minimum-native-rank MRR and Recall@k condition on the 338 contexts that contain a verified correct candidate. All-context budget success, which includes unsolved contexts, is the operational estimand and is reported separately.",
        "- Rank has no additional learned scoring-inference cost after generation, but the merged score assumes that multiple configuration streams have already been generated. The paper must not call the complete repair pipeline free.",
        f"- The primary ranking result is pre-test prioritization, not plausible-patch correctness assessment: {percent(pretest_test_failure_rate)} of its candidate universe still fails the available tests.",
        f"- HumanEval preserves relative configuration-quality/ranking signal, but not absolute probabilities: observed occurrence correctness is {percent(transfer['empirical_correct_rate'])}, mean transferred score is {percent(transfer['mean_transferred_probability'])}, and 10-bin ECE is {transfer['expected_calibration_error_10_bins']:.3f}.",
        f"- The Pearson association is {transfer['pearson_correlation']:.3f} with a descriptive Fisher 95% CI [{transfer_ci['ci_low']:.3f}, {transfer_ci['ci_high']:.3f}] over {transfer['config_count']} related configurations; it is not a population-level model-family estimate.",
        "- T4/T4b are retrospective semantic-review coverage curves that assume a perfect adjudicator. They are not literal test-suite savings or stop-at-first-test-pass simulations.",
        "- A 2025 multi-benchmark APR study already observed that correct patches often occur early. Our novelty is the adjudication-aware, multi-configuration ranking protocol, calibration boundary, and weak-oracle analysis, not the bare observation of early generation.",
        "- The index-0-only ablation nearly matches full order overall, but later positions remain significantly informative after all index-0 candidates are removed; singleton-only analysis rules out occurrence count as the sole explanation.",
        "- The strong aggregate minimum-rank effect is concentrated in 298 exact/AST-present contexts. On only 40 semantic-only contexts, minimum native rank versus random is unresolved and stream calibration does not improve it; the paper must show this boundary prominently.",
        "- The exact/AST-minus-semantic rank-advantage interaction is +0.147 MRR, 95% CI [+0.074, +0.217], and remains positive within CodeLlama/RepairLLaMA, DeepSeek, and OpenAI provider lineages. This is contamination-compatible evidence, not proof of memorization.",
        "- GitBug-Java reproduces the direction: minimum rank beats random by +0.149 MRR in 22 exact/AST-present contexts, while the four semantic-only contexts give +0.037 with an interval crossing zero. The semantic sample is too small for a decisive replication.",
        "- The 1,224 unknown plausible candidates are not missing at random: most were skipped because their context already contained an exact/AST fix. Plausible-only APCA therefore describes the adjudicated subset, not every test-passing patch.",
        "- HumanEval-Java and GitBug-Java are benchmark-transfer checks within the same RepairLLaMA campaign and review process, not an independent repair-campaign replication.",
        "- The supervised UniXcoder APCA experiment is a negative result; zero-shot CodeT5+ is stronger at candidate-level discrimination, while minimum native rank remains competitive for mixed-pool ranking.",
        "- ICSE 2026 already contains APR-specific accept/reject policies and a general risk-aware code deferral framework. Adding an abstain threshold alone is not a novelty claim; a new method must add bug-level risk control, weak-oracle handling, and configuration/model-family/campaign-shift analysis.",
        "- The validation-funnel decomposition is now complete: native-rank AUC is 0.491 for compilation, 0.537 for test passage conditional on compilation, 0.613 for exact/AST reference matching, and 0.542 for semantic correctness among adjudicated non-reference patches.",
        "- The deployable stage models never consume human-fix text, exact/AST match status, semantic labels, or a validation outcome before its action. Nested folds separate training, model selection, risk calibration, and final testing.",
        "- Stage-factorized provenance raises all-context verified budget-1 success from 9.08% to 14.60%, a +5.52-point gain with a bug-clustered interval excluding zero. This is prioritization utility, not a correctness certificate.",
        "- No pessimistic policy certifies any fold at target wrong-accept risk 30% or below. The paper must treat infeasibility and deferral as results, not tune until a nonzero coverage appears.",
        "- Serial factorized scheduling improves normalized validation-budget AUC across predeclared cost scenarios. Myopic adaptive interleaving does not beat the corresponding serial policy and must remain a negative result.",
        "- A separately frozen outcome-conditioned extension finds strong within-context generator-stream outcome correlation (compile AUC 0.849; test-given-compile AUC 0.872), but online residual updates do not reliably beat static serial scheduling. This predictive-versus-decision-utility gap is retained as a negative result.",
        "- Scheduling gains remain concentrated in exact/AST contexts; the semantic-only intervals cross zero even after adding CodeT5+ semantic scoring. This is the main external-validity gate for the new method.",
        f"- The Practical POD common split contains {data['practical_pod_common_split']['label_provenance_audit']['common_unreviewed_candidates']} unreviewed candidates labeled as overfitting, {percent(data['practical_pod_common_split']['label_provenance_audit']['common_unreviewed_fraction_of_all'])} of its 169 candidates. Native ranking is already at 81.0% R@1 and 100% R@3, and the stage-selected comparison is null; this split is a useful label/protocol audit but a poor headline ranking challenge.",
        f"- The authentic PrevaRank artifact is now complete on {prevarank_manifest['counts']['supported_candidate_count']:,}/{prevarank_manifest['counts']['candidate_count']:,} plausible LLM candidates. On adjudicated mixed-generator pools it trails native order by {prevarank_mixed_vs_native['mrr_vs_native']['observed_difference']:+.4f} MRR, 95% CI [{prevarank_mixed_vs_native['mrr_vs_native']['ci_low']:+.4f}, {prevarank_mixed_vs_native['mrr_vs_native']['ci_high']:+.4f}]. In one-generator stream pools its {prevarank_stream_vs_native['mrr_vs_native']['observed_difference']:+.4f} point estimate has an interval crossing zero, so the boundary is mixed-pool inferiority rather than universal failure.",
        f"- PrevaRank's No-Category rate rises from {percent(prevarank_shift['classical_apr']['no_category_rate'], 2)} on reproduced classical APR outputs to {percent(prevarank_shift['llm_apr']['no_category_rate'], 2)} on LLM patches. The completed stable-hash intervention changes {prevarank_order_reconciliation['released_rank_change_count']:,}/{prevarank_order_reconciliation['candidate_instance_count']:,} released ranks, {prevarank_order_sensitivity['pool_top_patch_change_count']:,}/{prevarank_order_sensitivity['pool_count']:,} top patches, and {percent(prevarank_order_sensitivity['pairwise_order_discordance_rate_micro'], 2)} of normalized-patch pair orders. Each output follows its own input within historical-value ties at {percent(prevarank_order_alignments['canonical_rank_vs_canonical_input']['historical_value_tied_pair_input_order_agreement'], 2)} and {percent(prevarank_order_alignments['shuffled_rank_vs_shuffled_input']['historical_value_tied_pair_input_order_agreement'], 2)}, while cross-order agreement is near chance.",
        f"- This is a causal structural-instability result, not a stable utility effect: adjudicated stable-minus-canonical MRR is {prevarank_order_adjudicated_mrr['observed_difference']:+.4f}, 95% CI [{prevarank_order_adjudicated_mrr['ci_low']:+.4f}, {prevarank_order_adjudicated_mrr['ci_high']:+.4f}], while pessimistic-Unknown MRR is {prevarank_order_pessimistic_mrr['observed_difference']:+.4f}, CI [{prevarank_order_pessimistic_mrr['ci_low']:+.4f}, {prevarank_order_pessimistic_mrr['ci_high']:+.4f}].",
        f"- The predeclared safe gate (support q95, expected incremental scheduler-harm target 20%) overrides {safe_actions['action_counts']['override']}/{safe_actions['context_count']} Defects4J candidate pools. It improves MRR over native order by {safe_internal['safe_gate_mrr_vs_native']['observed_difference']:+.4f}, 95% CI [{safe_internal['safe_gate_mrr_vs_native']['ci_low']:+.4f}, {safe_internal['safe_gate_mrr_vs_native']['ci_high']:+.4f}], and all-context budget-1 success by {100 * safe_internal['safe_gate_budget1_vs_native']['observed_difference']:+.2f} points.",
        f"- This is an internal scheduler-harm calibration target, not a patch-correctness certificate or arbitrary-shift guarantee. Targets at 5% and 10% select zero overrides; the primary 20% target is the first feasible predeclared operating point. The gate's internal MRR cost relative to always applying the stream policy is {safe_internal['safe_gate_mrr_vs_always_stream']['observed_difference']:+.4f}, with an interval crossing zero.",
        f"- On HumanEval-Java, the fixed gate improves MRR over native order by {safe_human['safe_gate_mrr_vs_native']['observed_difference']:+.4f}, but trails always-stream scheduling by {safe_human['safe_gate_mrr_vs_always_stream']['observed_difference']:+.4f}. It defers every full-budget GitBug-Java pool because candidate positions exceed Defects4J support; after a predeclared top-10 truncation, the positive gain over native order remains statistically unresolved. These are deployment boundaries, not failures to report.",
        f"- RepairBench adds {repairbench['campaign_counts']['candidates']:,} unique candidates from {repairbench['campaign_counts']['new_source_configs']} newer source configurations. Exact configuration overlap is zero and exact candidate overlap is {repairbench_integrity['candidate_overlap']['candidate_identity_overlap']} ({percent(repairbench_integrity['candidate_overlap']['new_candidate_overlap_rate'], 2)} of RepairBench), but all 89 benchmark contexts and the research lineage are shared.",
        f"- Returned-sample index does not replicate on RepairBench plausibility: MRR difference from exact-tie random is {repairbench_index_random['observed_difference']:+.4f}, 95% CI [{repairbench_index_random['ci_low']:+.4f}, {repairbench_index_random['ci_high']:+.4f}]. This narrows, rather than erases, the strong original RepairLLaMA finding.",
        "- All 35 RepairBench configurations are unseen, so the frozen safe gate defers in all 89 contexts and preserves returned ranking exactly. This is graceful abstention, not positive utility transfer.",
        f"- Zero-shot CodeT5+ similarity trails returned index by {repairbench_similarity_index['observed_difference']:+.4f} MRR, 95% CI [{repairbench_similarity_index['ci_low']:+.4f}, {repairbench_similarity_index['ci_high']:+.4f}], in the frozen merged-pool plausibility endpoint. Both distance and similarity remain reported under disclosed Protocol Amendment A1.",
        f"- The post-confirmatory pessimistic-reference pool-scale interaction is {repairbench_pool_interaction['observed']:+.4f}, 95% CI [{repairbench_pool_interaction['ci_low']:+.4f}, {repairbench_pool_interaction['ci_high']:+.4f}]. It is useful evidence that AUC can hide merged-pool top-rank tail risk, but it remains exploratory.",
        f"- The blinded RepairBench semantic packet contains {repairbench_review['counts']['selected_unique_candidates']} candidates from {repairbench_review['counts']['eligible_contexts']} contexts and hides method, rank, generator, and identity. Without two independent reviewers, all {data['repairbench_import_audit']['candidate_reference_labels']['unknown']:,} test-passing nonmatches remain Unknown.",
        "- Archived outcomes contain no elapsed times. Docker execution is now verified, but the required Defects4J/GitBug benchmark checkouts and bounded timing environment are not installed. `VALIDATION_COST_MEASUREMENT_PROTOCOL.md` freezes a future study; current cost ratios remain scenario weights and no wall-clock, energy, or monetary claim is allowed.",
        "",
        "## Main Results",
        "",
    ]
    for claim in supported:
        lines.extend([f"### {claim['id']}: {claim['claim']}", "", claim["evidence"], "", f"Scope: {claim['scope']}", ""])
    lines.extend(["## Exploratory Findings", ""])
    for claim in exploratory:
        lines.extend(
            [
                f"### {claim['id']}: {claim['claim']}",
                "",
                claim["evidence"],
                "",
                f"Scope: {claim['scope']}",
                "",
            ]
        )
    lines.extend(["## Claims We Must Not Make", ""])
    for claim in unsupported:
        lines.extend([f"- {claim['claim']} Evidence: {claim['evidence']}"])
    lines.extend(
        [
            "",
            "## Most Important Threats",
            "",
        ]
    )
    for threat in threats:
        lines.append(f"- {threat['category']}: {threat['residual']}")
    lines.extend(
        [
            "",
            "## Recommended Paper Structure",
            "",
            "1. Motivate the validation funnel and distinguish pre-test scheduling from post-test correctness assessment.",
            f"2. Motivate the weak-oracle problem with {percent(weak['candidate_incorrect_adjudicated'])} incorrect adjudicated test-passing patches, a {percent(weak['candidate_incorrect_lower'])}-{percent(weak['candidate_incorrect_upper'])} corpus-wide bound, and {percent(weak['false_solved_relative_inflation'])} apparent-solvability inflation.",
            "3. Define the adjudication-aware dataset, explain why unresolved patches remain unknown, and show the Practical POD provenance audit as external confirmation that this distinction matters.",
            "4. Establish minimum native rank under exact ties, index-0 and singleton confound checks, correctness-evidence strata, bug holdouts, and configuration shift.",
            "5. Decompose the rank signal across compile, test, reference reproduction, review selection, and semantic correctness.",
            "6. Introduce the nested stage-factorized policy and evaluate all-context budget-1 and full cost-normalized scheduling curves.",
            "7. Introduce the fold-separated safe deployment gate, distinguish incremental scheduler harm from correctness risk, and report override/fallback/defer actions under support and campaign shift.",
            "8. Report automatic-accept risk-coverage infeasibility under pessimistic Unknown handling, then expose the exact/AST versus semantic-only boundary and adaptive-policy null result.",
            "9. Test the frozen claims on RepairBench: report the returned-index null replication, all-defer gate, CodeT5+ negative result, and label-world bounds before any exploratory diagnosis.",
            "10. Present the merged-pool tail-risk interaction explicitly as post-confirmatory, then use the Practical POD provenance audit and controlled PrevaRank input-order intervention as supporting benchmark-integrity evidence before closing with artifact reproducibility.",
            "",
            "## Highest-Value Novelty Extensions",
            "",
            "1. Perform the final related-work and claim-language audit against the selected venue; the frozen PrevaRank causal mechanism check is now complete.",
            "2. If two independent reviewers are readily available, complete the already frozen 325-item blinded RepairBench adjudication packet; otherwise retain partial-identification bounds and keep this off the submission critical path.",
            "3. Confirm the exploratory merged-pool tail-risk interaction on one untouched campaign or score family before promoting it to a primary mechanism claim; do not tune on RepairBench and call the same analysis confirmatory.",
            "4. Execute the bounded wall-clock protocol only if a working benchmark environment is already available. Do not delay submission for a 130-GiB setup or replace timings with synthetic proxies.",
            "5. Package candidate-stage traces, Unknown-label bounds, fixed split roles, RepairBench provenance, third-party hashes, stable-hash intervention artifacts, and deterministic table generation as the reusable validation-funnel benchmark.",
            "",
            "## Questions for Co-Author Review",
            "",
            "1. Is the stage-factorized serial scheduler, with infeasible low-risk auto-accept as a safety result, now the correct primary method framing?",
            "2. Does the RepairBench null replication now make the safe override/fallback/defer contract the strongest central novelty, rather than a secondary deployment layer?",
            "3. Is the campaign boundary worded tightly enough: newer generation campaign and unseen configurations, but shared GitBug-Java contexts and research lineage?",
            "4. Should the post-confirmatory pool-scale tail-risk result remain one clearly marked exploratory subsection, or is another untouched confirmation essential before submission?",
            "5. Is the PrevaRank boundary sufficiently precise: causal output instability is established, but adjudicated utility change is unresolved and the pessimistic result is assumption-bound?",
            "",
            "## Files to Review",
            "",
            "- `results/v2/paper_tables.md`: generated numeric tables.",
            "- `PAPER_CLAIMS_AND_THREATS.md`: claim ledger and full threats.",
            "- `VALIDATION_FUNNEL_METHOD_SPEC.md`: frozen estimands, actions, feature restrictions, and leakage boundaries.",
            "- `results/v2/validation_funnel_signal.json`: stage-specific native-rank decomposition.",
            "- `results/v2/stage_aware_policy.json`: nested stage models, budget-1 policy, and risk-control feasibility.",
            "- `results/v2/adaptive_validation_scheduler.json`: cost scenarios, serial/adaptive policies, and correctness-stratum results.",
            "- `results/v2/outcome_conditioned_stream_health.json`: frozen sibling-correlation diagnostic and online stream-health null result.",
            "- `results/v2/practical_pod_common_split.json`: pinned common-split predictions, identity audit, label worlds, and paired ranking results.",
            "- `PRACTICAL_POD_COMMON_SPLIT_SPEC.md`: fixed reconciliation, uncertainty, tie, and licensing protocol.",
            "- `results/v2/prevarank_llm_evaluation.json`: authentic mixed- and per-generator PrevaRank ranking under three label worlds.",
            "- `results/v2/prevarank_domain_shift_mixed.json`: classical-to-LLM taxonomy coverage and input-order inheritance diagnostics.",
            "- `results/v2/prevarank_input_order_sensitivity.json`: frozen stable-hash intervention, 2x2 order-alignment matrix, structural changes, and paired label-world utility effects.",
            "- `PREVARANK_BASELINE_PROTOCOL.md`: pinned artifact, adapter contract, common support, and safe-claim boundary.",
            "- `results/v2/shift_aware_safe_scheduler.json`: frozen nested gate, risk sensitivities, external transfer, and paired comparisons.",
            "- `results/v2/shift_aware_safe_scheduler_actions.jsonl`: auditable fold/context action ledger.",
            "- `SHIFT_AWARE_SAFE_SCHEDULER_SPEC.md`: predeclared support, harm, fallback, defer, and external-evaluation protocol.",
            "- `results/v2/repairbench_external_campaign.json`: frozen newer-campaign ranking, label worlds, gate transport, and pool-scale diagnostic.",
            "- `results/v2/repairbench_campaign_integrity.json`: exact configuration, context, candidate, and manual-label overlap audit.",
            "- `REPAIRBENCH_EXTERNAL_PROTOCOL.md`: frozen endpoint, tie, uncertainty, score, amendment, and semantic-review rules.",
            "- `results/v2/repairbench_semantic_review/semantic_review_packet_audit.json`: blinded selection counts, hashes, and reviewer requirements.",
            "- `VALIDATION_COST_MEASUREMENT_PROTOCOL.md`: current reporting boundary and frozen future wall-clock study.",
            "- `FINAL_ANALYSIS_HIERARCHY.md`: frozen primary, confirmatory, supporting, exploratory, and forbidden-upgrade hierarchy.",
            "- `build_paper_artifacts.py`: one-command regeneration, integrity validation, top-level test execution, and environment report.",
            "- `SOURCE_CONFIG_PROVENANCE.md`: audited configuration-to-model-lineage map and proposed family holdouts.",
            "- `PAPER_FINDINGS_LOG.md`: complete chronological evidence, only if deeper audit is needed.",
            "- `results/source_order_failures/source_order_failure_review_packet.md`: optional qualitative examples, not required for first review.",
            "",
            "The compact packet intentionally excludes training logs and the 32-example qualitative appendix.",
        ]
    )
    return "\n".join(lines)


def write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def generate(args):
    data = {name: load_json(path) for name, path in INPUTS.items()}
    checks = validate_inputs(data)
    tables = build_tables(data)
    claims, threats = make_claims(data)

    write_text(args.tables, render_tables(tables))
    write_text(args.csv, render_csv(tables))
    write_text(
        args.claims_json,
        json.dumps(
            {"artifact_version": VERSION, "claims": claims, "threats": threats},
            indent=2,
            sort_keys=True,
        ),
    )
    write_text(args.claims_md, render_claims(claims, threats))
    write_text(args.packet, render_packet(data, claims, threats))

    outputs = [args.tables, args.csv, args.claims_json, args.claims_md, args.packet]
    manifest = {
        "artifact_version": VERSION,
        "generator": "make_paper_tables.py",
        "generator_sha256": sha256(Path(__file__)),
        "validation_checks": checks,
        "inputs": {
            name: {"path": str(path), "sha256": sha256(path)}
            for name, path in {**INPUTS, **AUXILIARY_INPUTS}.items()
        },
        "supporting_artifacts": {
            name: {"path": str(path), "sha256": sha256(path)}
            for name, path in SUPPORTING_ARTIFACTS.items()
        },
        "outputs": {str(path): sha256(path) for path in outputs},
        "table_ids": [table["id"] for table in tables],
        "claim_ids": [claim["id"] for claim in claims],
    }
    write_text(args.manifest, json.dumps(manifest, indent=2, sort_keys=True))
    return manifest


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate reviewer-auditable paper artifacts from authoritative evidence."
    )
    parser.add_argument("--tables", type=Path, default=DEFAULT_TABLES)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--claims-json", type=Path, default=DEFAULT_CLAIMS_JSON)
    parser.add_argument("--claims-md", type=Path, default=DEFAULT_CLAIMS_MD)
    parser.add_argument("--packet", type=Path, default=DEFAULT_PACKET)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    return parser.parse_args(argv)


def main():
    args = parse_args()
    manifest = generate(args)
    print(
        f"Generated {len(manifest['table_ids'])} tables and "
        f"{len(manifest['claim_ids'])} claims from validated evidence artifacts."
    )


if __name__ == "__main__":
    main()
