"""Corrective, exploratory audit of the v1 published-claim screen.

This never rewrites the frozen v1 artifacts. Run freeze, diagnose, then score.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

if __package__:
    from . import certification_screen as v1
else:
    import certification_screen as v1


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "certification_screen_v2"
SOURCE = ROOT / "repairllama" / "results"
EXCLUDED = {"Math-28", "Math-44", "JacksonDatabind-82"}
PAPER_URL = "https://arxiv.org/html/2312.15698v6"
PUBLISHED = copy.deepcopy(v1.PUBLISHED)
# Table IV and the authors' own results notebook: these two v1 entries were transposed.
PUBLISHED["gpt4"]["defects4j"] = (119, 47, 60, 72)
PUBLISHED["gpt4"]["humanevaljava"] = (124, 64, 74, 116)

# Only directions explicitly stated in the paper's results prose or table captions.
# Each tuple is family, benchmark, higher row, lower row, source lines, scope.
ASSERTIONS = [
    ("representation_vs_zero_shot", b, "repairllama", "baseline_ir3", "IV-A 264-268", "best representation versus no-fine-tuning baseline")
    for b in v1.BENCHMARKS
] + [
    ("representation_vs_zero_shot", b, "repairllama", "baseline_ir4", "IV-A 264-268", "best representation versus second no-fine-tuning baseline")
    for b in v1.BENCHMARKS
] + [
    ("representation_within_repairllama", "defects4j", "repairllama", "ir2_or2", "IV-A 268-271", "marginal reported gap; paper says not statistically significant"),
] + [
    ("code_llama_finetuning", b, "repairllama", "codellama_fft", "IV-B 303-307", "LoRA versus same-base full fine-tuning")
    for b in v1.BENCHMARKS
] + [
    ("deepseek_finetuning", b, "deepseek_fft", "deepseek_base", "IV-B 310-312", "full fine-tuning versus base")
    for b in v1.BENCHMARKS
] + [
    ("deepseek_finetuning", b, "deepseek_lora", "deepseek_base", "IV-B 310-312", "LoRA versus base")
    for b in ("defects4j", "humanevaljava")
] + [
    ("deepseek_fft_vs_lora", "defects4j", "deepseek_fft", "deepseek_lora", "IV-B 310-312", "paper says full fine-tuning does better"),
    ("deepseek_fft_vs_lora", "gitbugjava", "deepseek_fft", "deepseek_lora", "IV-B 310-312", "paper says full fine-tuning does better"),
    ("deepseek_fft_vs_lora", "humanevaljava", "deepseek_lora", "deepseek_fft", "IV-B 310-312", "paper says LoRA does better"),
] + [
    ("chatgpt_comparison", b, "repairllama", gpt, "IV-C 340-345", "paper says RepairLLaMA does better on Defects4J/GitBug-Java")
    for b in ("defects4j", "gitbugjava") for gpt in ("gpt35", "gpt4")
] + [
    ("chatgpt_comparison", "humanevaljava", "gpt4", "repairllama", "IV-C 341-342", "explicit semantic-match exception: GPT-4 does better"),
]


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f"Refusing to write empty table: {path}")
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def source_file(stage: str, benchmark: str, config: str) -> Path:
    suffix = "martin" if stage == "3_martin" else "merged"
    return SOURCE / stage / f"evaluation_{benchmark}_{config}_{suffix}.jsonl"


def excluded_bug_set(benchmark: str) -> set[str]:
    return v1.sf_bug_ids(benchmark) - EXCLUDED


def claims() -> list[dict]:
    rows = []
    seen = set()
    for family, benchmark, high, low, location, note in ASSERTIONS:
        key = (benchmark, high, low)
        if key in seen:
            raise ValueError(f"Duplicate assertion {key}")
        seen.add(key)
        a = PUBLISHED[high][benchmark][3]
        b = PUBLISHED[low][benchmark][3]
        if a <= b:
            raise ValueError(f"Paper assertion has nonpositive semantic margin: {key}, {a}-{b}")
        rows.append({
            "claim_id": f"RL2-{benchmark}-{high}-vs-{low}",
            "family": family,
            "benchmark": benchmark,
            "metric": "bugs with >=1 semantic-match candidate among 10 outputs",
            "config_a": PUBLISHED[high]["config"],
            "config_b": PUBLISHED[low]["config"],
            "display_a": PUBLISHED[high]["display"],
            "display_b": PUBLISHED[low]["display"],
            "reported_a": a,
            "reported_b": b,
            "reported_margin_bugs": a - b,
            "paper_location": location,
            "claim_scope": note,
            "source_url": PAPER_URL,
        })
    return rows


def freeze() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = OUT / "claims_repairllama_corrected.csv"
    digest_file = OUT / "frozen_claims_sha256.json"
    if manifest.exists() or digest_file.exists():
        raise FileExistsError("v2 claim freeze already exists; refusing overwrite")
    write_csv(manifest, claims())
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    digest_file.write_text(json.dumps({
        "sha256": digest,
        "paper": PAPER_URL,
        "classification": "exploratory correction, not preregistration",
        "excluded_bugs": sorted(EXCLUDED),
        "note": "Only specific prose-supported semantic directions, no inferred all-pairs claims; external comparators without per-bug data remain unscored.",
    }, indent=2) + "\n", encoding="utf-8")
    print(f"Frozen {len(claims())} paper-anchored claims: SHA-256 {digest}")


def stage_counts(stage: str, benchmark: str, config: str) -> tuple[dict[str, set[str]], dict]:
    bug_sets = {key: set() for key in v1.METRICS}
    info = {"rows": 0, "positive_flag_empty_patch_rows": 0, "positive_flag_empty_patch_candidates": 0}
    for row in v1.read_jsonl(source_file(stage, benchmark, config)):
        bug = row.get("identifier")
        if bug not in excluded_bug_set(benchmark):
            continue
        info["rows"] += 1
        evaluations = row.get("evaluation") or []
        if not isinstance(evaluations, list):
            continue
        row_empty_flag = False
        for ev in evaluations:
            if not isinstance(ev, dict):
                continue
            positive = any(ev.get(field) is True for field in ("exact_match", "ast_match", "semantical_match"))
            if positive and not (ev.get("generation") or "").strip():
                info["positive_flag_empty_patch_candidates"] += 1
                row_empty_flag = True
            if ev.get("test") is True or positive:
                bug_sets["plausible"].add(bug)
            if ev.get("exact_match") is True:
                bug_sets["exact"].add(bug)
            if ev.get("exact_match") is True or ev.get("ast_match") is True:
                bug_sets["ast"].add(bug)
            if positive:
                bug_sets["semantic"].add(bug)
        info["positive_flag_empty_patch_rows"] += int(row_empty_flag)
    return bug_sets, info


def diagnose() -> dict:
    if not (OUT / "frozen_claims_sha256.json").exists():
        raise FileNotFoundError("Freeze claims before diagnosing")
    rows = []
    hashes = []
    stage_differences = []
    for benchmark in v1.BENCHMARKS:
        for key, published in PUBLISHED.items():
            config = published["config"]
            merged, _ = stage_counts("2_merged", benchmark, config)
            final, info = stage_counts("3_martin", benchmark, config)
            for stage in ("2_merged", "3_martin"):
                path = source_file(stage, benchmark, config)
                hashes.append({"path": str(path.relative_to(ROOT)), "sha256": v1.sha256_file(path)})
            for index, metric in enumerate(v1.METRICS):
                expected = published[benchmark][index]
                rows.append({
                    "benchmark": benchmark, "config": config, "metric": metric,
                    "reported": expected, "merged_corrected_scope": len(merged[metric]),
                    "final_corrected_scope": len(final[metric]),
                    "final_minus_reported": len(final[metric]) - expected,
                    "within_2": abs(len(final[metric]) - expected) <= 2,
                    "paper_scope_bug_count": len(excluded_bug_set(benchmark)),
                    "final_rows": info["rows"],
                    "positive_flag_empty_patch_rows": info["positive_flag_empty_patch_rows"],
                })
                if metric == "semantic" and merged[metric] != final[metric]:
                    stage_differences.append({
                        "benchmark": benchmark, "config": config,
                        "merged_count": len(merged[metric]), "final_count": len(final[metric]),
                        "added_correct_bug_ids": ";".join(sorted(final[metric] - merged[metric])),
                        "removed_correct_bug_ids": ";".join(sorted(merged[metric] - final[metric])),
                    })
    write_csv(OUT / "repairllama_reproduction_corrected.csv", rows)
    write_csv(OUT / "repairllama_stage_changes.csv", stage_differences)
    write_csv(OUT / "repairllama_input_hashes.csv", hashes)
    outside = [row for row in rows if not row["within_2"]]
    summary = {
        "metric_cells": len(rows), "within_2": len(rows) - len(outside),
        "outside_2": outside, "nonzero_final_discrepancies": [row for row in rows if row["final_minus_reported"] != 0],
        "semantic_stage_change_configs": len(stage_differences),
    }
    (OUT / "reproduction_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


def verify_freeze() -> list[dict]:
    manifest = OUT / "claims_repairllama_corrected.csv"
    frozen = json.loads((OUT / "frozen_claims_sha256.json").read_text(encoding="utf-8"))
    actual = hashlib.sha256(manifest.read_bytes()).hexdigest()
    if actual != frozen["sha256"]:
        raise ValueError("Corrected claim manifest changed after freeze")
    return read_csv(manifest)


def verify_reproduction_inputs() -> None:
    for row in read_csv(OUT / "repairllama_input_hashes.csv"):
        path = ROOT / row["path"]
        if v1.sha256_file(path) != row["sha256"]:
            raise ValueError(f"RepairLLaMA input changed since diagnosis: {path}")


def load_final_evidence() -> tuple[dict, dict]:
    evidence = {benchmark: defaultdict(Counter) for benchmark in v1.BENCHMARKS}
    candidates = defaultdict(lambda: defaultdict(set))
    for benchmark in v1.BENCHMARKS:
        bugs = excluded_bug_set(benchmark)
        for published in PUBLISHED.values():
            config = published["config"]
            for row in v1.read_jsonl(source_file("3_martin", benchmark, config)):
                bug = row.get("identifier")
                if bug not in bugs:
                    continue
                for ev in row.get("evaluation") or []:
                    if not isinstance(ev, dict):
                        continue
                    patch = (ev.get("generation") or "").strip()
                    if not patch:
                        continue
                    candidate = (bug, patch)
                    candidates[(benchmark, config)][bug].add(candidate)
                    evidence[benchmark][candidate].update(v1.evidence_flags(ev))
    return evidence, candidates


def score() -> list[dict]:
    manifest = verify_freeze()
    summary_path = OUT / "reproduction_summary.json"
    if not summary_path.exists():
        raise FileNotFoundError("Run diagnose before score")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary["outside_2"]:
        raise ValueError("Reported counts not within the prerequested +/-2 gate; no scoring")
    verify_reproduction_inputs()
    evidence, candidates = load_final_evidence()
    label_maps = {}
    human_only_maps = {}
    for benchmark in v1.BENCHMARKS:
        for view in ("S0_all_released_labels", "S1_objective_only"):
            label_maps[(benchmark, view)] = {
                candidate: v1.candidate_label({field: bool(counts[field]) for field in (
                    "objective_positive", "objective_negative", "human_positive", "human_negative",
                    "disagreement", "conflict", "objective_conflict")}, view)
                for candidate, counts in evidence[benchmark].items()
            }
        human_only_maps[benchmark] = {
            candidate for candidate, counts in evidence[benchmark].items()
            if label_maps[(benchmark, "S0_all_released_labels")][candidate] is not None
            and not counts["objective_positive"] and not counts["objective_negative"]
            and bool(counts["human_positive"]) != bool(counts["human_negative"])
        }
    rows = []
    for claim in manifest:
        benchmark = claim["benchmark"]
        values = {}
        for short, view in (("S0", "S0_all_released_labels"), ("S1", "S1_objective_only")):
            labels = label_maps[(benchmark, view)]
            lower = upper = affected = 0
            for bug in excluded_bug_set(benchmark):
                a_ids = candidates[(benchmark, claim["config_a"])].get(bug, set())
                b_ids = candidates[(benchmark, claim["config_b"])].get(bug, set())
                lo, hi = v1.bug_diff_bounds(a_ids, b_ids, labels)
                lower += lo
                upper += hi
                affected += lo != hi
            values.update({
                f"{short}_lower_bugs": lower, f"{short}_upper_bugs": upper,
                f"{short}_status": "supported" if lower > 0 else "reversed" if upper < 0 else "contested",
                f"{short}_affected_bugs": affected,
            })
        withdrawal = "not_applicable_not_supported_S0"
        if values["S0_status"] == "supported":
            labels = label_maps[(benchmark, "S0_all_released_labels")]
            withdrawable = human_only_maps[benchmark]
            dp = {0: 0}
            for bug in excluded_bug_set(benchmark):
                a_ids = candidates[(benchmark, claim["config_a"])].get(bug, set())
                b_ids = candidates[(benchmark, claim["config_b"])].get(bug, set())
                options = v1.withdrawal_cost_for_bug(a_ids, b_ids, labels, withdrawable)
                dp = v1.combine_withdrawal_options(dp, options)
            costs = [cost for lower, cost in dp.items() if lower <= 0]
            withdrawal = min(costs) if costs else "not_withdrawable_by_human_labels"
        values["withdrawal_robustness"] = withdrawal
        rows.append({**claim, **values})
    write_csv(OUT / "claim_status_repairllama_corrected.csv", rows)
    print(json.dumps({
        "claims": len(rows),
        "S0": dict(Counter(row["S0_status"] for row in rows)),
        "S1": dict(Counter(row["S1_status"] for row in rows)),
        "changed_S0_to_S1": [row["claim_id"] for row in rows if row["S0_status"] != row["S1_status"]],
        "withdrawal_costs_for_changed_claims": [
            row["withdrawal_robustness"] for row in rows if row["S0_status"] != row["S1_status"]
        ],
    }, indent=2))
    return rows


def ranks(values: list[float]) -> list[float]:
    ordered = sorted(range(len(values)), key=values.__getitem__)
    output = [0.0] * len(values)
    for start in range(len(values)):
        if start and values[ordered[start]] == values[ordered[start - 1]]:
            continue
        end = start + 1
        while end < len(values) and values[ordered[end]] == values[ordered[start]]:
            end += 1
        rank = (start + 1 + end) / 2
        for position in ordered[start:end]:
            output[position] = rank
    return output


def pearson(a: list[float], b: list[float]) -> float:
    ma, mb = statistics.mean(a), statistics.mean(b)
    numerator = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = sum((x - ma) ** 2 for x in a)
    db = sum((y - mb) ** 2 for y in b)
    return numerator / math.sqrt(da * db) if da > 0 and db > 0 else float("nan")


def solve_linear(matrix: list[list[float]], target: list[float]) -> list[float]:
    augmented = [row[:] + [value] for row, value in zip(matrix, target)]
    n = len(target)
    for col in range(n):
        pivot = max(range(col, n), key=lambda i: abs(augmented[i][col]))
        augmented[col], augmented[pivot] = augmented[pivot], augmented[col]
        if abs(augmented[col][col]) < 1e-9:
            raise ValueError("Singular fit")
        scale = augmented[col][col]
        augmented[col] = [value / scale for value in augmented[col]]
        for row in range(n):
            if row == col:
                continue
            factor = augmented[row][col]
            augmented[row] = [x - factor * y for x, y in zip(augmented[row], augmented[col])]
    return [row[-1] for row in augmented]


def ols_predict(training: list[dict], heldout: dict, fields: tuple[str, ...]) -> float:
    # Ridge stabilization only; this is a descriptive sensitivity check, not a forecast.
    def vector(row: dict) -> list[float]:
        return [1.0] + [float(row[field]) for field in fields]
    dimension = len(fields) + 1
    gram = [[0.0] * dimension for _ in range(dimension)]
    rhs = [0.0] * dimension
    for row in training:
        x = vector(row)
        y = float(row["cost"])
        for i in range(dimension):
            rhs[i] += x[i] * y
            for j in range(dimension):
                gram[i][j] += x[i] * x[j]
    for i in range(1, dimension):
        gram[i][i] += 1e-8
    coefficients = solve_linear(gram, rhs)
    return sum(x * beta for x, beta in zip(vector(heldout), coefficients))


def cost_diagnostic() -> dict:
    source = ROOT / "results" / "certification_screen_v1" / "certification_cost_repairbench.csv"
    raw = read_csv(source)
    data = []
    for row in raw:
        if row["published_tie"] == "True" or row["correctness_status"] != "contested":
            continue
        if row["optimistic_certification_feasible"] != "True":
            continue
        lower = float(row["correctness_lower"])
        upper = float(row["correctness_upper"])
        data.append({
            "claim_id": row["claim_id"], "config_a": row["config_a"], "config_b": row["config_b"],
            "relation": row["relation"], "margin_pp": float(row["reported_margin_pp"]),
            "unknown_mass_pp": 100 * (upper - lower), "deficit_pp": max(0, -100 * lower),
            "unknown_actions": int(row["unknown_unique_patch_actions_with_nonzero_influence"]),
            "cost": int(row["optimistic_total_actions"]),
            "confirmations": int(row["optimistic_correctness_confirmations"]),
            "refutations": int(row["optimistic_incorrectness_refutations"]),
        })
    if not data:
        raise ValueError("No contested directional cost rows")
    y = [row["cost"] for row in data]
    correlations = {}
    for field in ("margin_pp", "unknown_mass_pp", "deficit_pp", "unknown_actions"):
        x = [float(row[field]) for row in data]
        correlations[field] = {"pearson": pearson(x, y), "spearman": pearson(ranks(x), ranks(y))}

    models = {
        "margin_only": ("margin_pp",),
        "margin_plus_unknown_mass": ("margin_pp", "unknown_mass_pp"),
        "margin_mass_and_unknown_count": ("margin_pp", "unknown_mass_pp", "unknown_actions"),
        "deficit_mass_and_unknown_count": ("deficit_pp", "unknown_mass_pp", "unknown_actions"),
    }
    model_results = {}
    for name, fields in models.items():
        predictions = [ols_predict(data[:i] + data[i + 1:], row, fields) for i, row in enumerate(data)]
        mae = statistics.mean(abs(prediction - actual) for prediction, actual in zip(predictions, y))
        mean_y = statistics.mean(y)
        denominator = sum((actual - mean_y) ** 2 for actual in y)
        r2 = 1 - sum((prediction - actual) ** 2 for prediction, actual in zip(predictions, y)) / denominator
        model_results[name] = {"fields": fields, "LOOCV_MAE_actions": mae, "LOOCV_R2": r2}
        for row, prediction in zip(data, predictions):
            row[f"{name}_LOOCV_pred"] = round(prediction, 3)
            row[f"{name}_residual"] = round(row["cost"] - prediction, 3)

    pairs = []
    controlled_pairs = []
    for i, left in enumerate(data):
        for right in data[i + 1:]:
            gap = abs(left["margin_pp"] - right["margin_pp"])
            if gap > 0.5:
                continue
            if min(left["cost"], right["cost"]) == 0:
                continue
            ratio = max(left["cost"], right["cost"]) / min(left["cost"], right["cost"])
            pairs.append({
                "claim_a": left["claim_id"], "claim_b": right["claim_id"],
                "margin_gap_pp": round(gap, 3), "cost_a": left["cost"], "cost_b": right["cost"],
                "cost_ratio": round(ratio, 3),
                "unknown_mass_a_pp": round(left["unknown_mass_pp"], 3),
                "unknown_mass_b_pp": round(right["unknown_mass_pp"], 3),
            })
            if abs(left["unknown_mass_pp"] - right["unknown_mass_pp"]) <= 2:
                controlled_pairs.append({
                    **pairs[-1], "unknown_actions_a": left["unknown_actions"],
                    "unknown_actions_b": right["unknown_actions"],
                })
    pairs.sort(key=lambda row: (-row["cost_ratio"], row["margin_gap_pp"]))
    controlled_pairs.sort(key=lambda row: (-row["cost_ratio"], row["margin_gap_pp"]))
    write_csv(OUT / "repairbench_cost_diagnostic.csv", data)
    if pairs:
        write_csv(OUT / "repairbench_similar_margin_pairs.csv", pairs)
    if controlled_pairs:
        write_csv(OUT / "repairbench_similar_margin_and_mass_pairs.csv", controlled_pairs)
    summary = {
        "scope": "derived GitBug-Java subscore, not official combined RepairBench leaderboard",
        "input_v1_cost_sha256": v1.sha256_file(source),
        "directional_contested_claims": len(data),
        "median_margin_pp": statistics.median(row["margin_pp"] for row in data),
        "median_cost_actions": statistics.median(y),
        "correlations": correlations,
        "LOOCV_descriptive_models": model_results,
        "similar_margin_pairs_with_cost_ratio_ge_2": sum(row["cost_ratio"] >= 2 for row in pairs),
        "top_similar_margin_pairs": pairs[:5],
        "similar_margin_and_mass_pairs_with_cost_ratio_ge_2": sum(row["cost_ratio"] >= 2 for row in controlled_pairs),
        "top_similar_margin_and_mass_pairs": controlled_pairs[:5],
        "largest_residuals_after_margin_mass_count": [
            {"claim_id": row["claim_id"], "margin_pp": row["margin_pp"],
             "unknown_mass_pp": row["unknown_mass_pp"], "cost": row["cost"],
             "predicted_cost": row["margin_mass_and_unknown_count_LOOCV_pred"],
             "residual": row["margin_mass_and_unknown_count_residual"]}
            for row in sorted(data, key=lambda item: -abs(item["margin_mass_and_unknown_count_residual"]))[:8]
        ],
        "interpretation_limit": "Optimistic costs assume favorable outcomes; claim pairs share models and are not independent. LOOCV is descriptive, not external validation.",
    }
    (OUT / "repairbench_cost_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("freeze", "diagnose", "score", "cost"))
    phase = parser.parse_args().phase
    if phase == "freeze":
        freeze()
    elif phase == "diagnose":
        diagnose()
    elif phase == "score":
        score()
    else:
        OUT.mkdir(parents=True, exist_ok=True)
        cost_diagnostic()


if __name__ == "__main__":
    main()
