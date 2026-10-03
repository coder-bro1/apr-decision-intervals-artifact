"""Independently review the completed HumanEval-Java contract replication."""

import sys as _sys  # release layout: shared helper modules live in lib/
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / "lib").is_dir()) / "lib"))
import argparse
from collections import Counter, defaultdict
from fractions import Fraction
import json
from pathlib import Path

from analysis_tools.evaluate_matched_baselines import digest, rows
from evaluate_noop_filter import aggregate
from evidence_budget_bounds import comparison_bounds


ROOT = Path(__file__).resolve().parents[1]


def primary_reason(evidence):
    reasons = set(evidence["unresolved_reasons"])
    for reason in ("reference_label_contradiction", "label_evidence_conflict",
                   "test_conflict", "compile_conflict", "observable_identity_label_disagreement"):
        if reason in reasons:
            return reason
    return "archived_unknown"


def distributions(decision):
    result = {}
    for method, selected in decision["selected_ties"].items():
        probability = Fraction(1, len(selected)) if selected else Fraction(0)
        result[method] = {key: probability for key in selected}
    return result


def paired_bounds(decisions, evidence, challenger="challenger", baseline="native_position"):
    values, bugs = [], []
    for decision in decisions:
        policies = distributions(decision)
        keys = set(policies[challenger]) | set(policies[baseline])
        coefficients = {key: policies[challenger].get(key, 0) - policies[baseline].get(key, 0)
                        for key in keys}
        values.append(comparison_bounds(coefficients, evidence))
        bugs.append(decision["bug_id"])
    return aggregate(values, bugs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source, output = args.input.resolve(), args.output.resolve()
    for path in (source, output):
        path.relative_to((ROOT / "results").resolve())
    if output.exists():
        raise FileExistsError(output)
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest["outputs"].items():
        if digest(source / name) != expected:
            raise ValueError(f"Replication output hash mismatch: {name}")
    summary = json.loads((source / "summary.json").read_text(encoding="utf-8"))
    candidates = {row["candidate_id"]: row for row in rows(source / "candidate_contract.jsonl")}
    decisions = list(rows(source / "decisions.jsonl"))
    if (len(candidates), len(decisions), len({row['bug_id'] for row in decisions})) != (16925, 164, 162):
        raise ValueError("Unexpected replication population")
    evidence = {key: {"correct": 1, "incorrect": 0, "unknown": None}[row["evidence"]["label"]]
                for key, row in candidates.items()}
    reviewed = paired_bounds(decisions, evidence)
    recorded = summary["results"]["challenger_minus"]["native_position"]
    for key in ("equal_bug_bounds", "context_bounds"):
        if any(abs(float(left) - right) > 1e-12 for left, right in zip(reviewed[key], recorded[key])):
            raise ValueError("Independent selected-set reconstruction disagrees")

    bug_context_counts = Counter(row["bug_id"] for row in decisions)
    relevant = {}
    agreement = 0
    for decision in decisions:
        policies = distributions(decision)
        if policies["challenger"] == policies["native_position"]:
            agreement += 1
        keys = set(policies["challenger"]) | set(policies["native_position"])
        for key in keys:
            coefficient = policies["challenger"].get(key, 0) - policies["native_position"].get(key, 0)
            if coefficient and evidence[key] is None:
                if key in relevant:
                    raise ValueError("Candidate identity unexpectedly spans contexts")
                relevant[key] = {"coefficient": coefficient, "bug_id": decision["bug_id"],
                                 "context_id": decision["context_id"],
                                 "reason": primary_reason(candidates[key]["evidence"])}
    widths = defaultdict(lambda: {"candidates": 0, "equal_context": Fraction(0), "equal_bug": Fraction(0)})
    for item in relevant.values():
        row = widths[item["reason"]]
        row["candidates"] += 1
        row["equal_context"] += abs(item["coefficient"]) / len(decisions)
        row["equal_bug"] += abs(item["coefficient"]) / bug_context_counts[item["bug_id"]] / len(bug_context_counts)

    legacy_evidence = {}
    for key, row in candidates.items():
        labels = row["evidence"]["legacy_labels"]
        legacy_evidence[key] = ({"correct": 1, "incorrect": 0, "unknown": None}[labels[0]]
                                if len(labels) == 1 else None)
    legacy_bounds = paired_bounds(decisions, legacy_evidence)
    filtered_counts = Counter((row["structure"], row["evidence"]["label"])
                              for row in candidates.values() if row["excluded"])
    finding = {
        "replication_outputs_verified": len(manifest["outputs"]),
        "population": {"candidates": len(candidates), "contexts": len(decisions),
                       "bugs": len(bug_context_counts)},
        "primary_reconstructed": reviewed,
        "contexts_with_identical_policies": agreement,
        "decision_relevant_unknown_candidates": len(relevant),
        "unknown_width_decomposition": {reason: {
            "candidates": row["candidates"],
            "equal_bug_pp": 100 * float(row["equal_bug"]),
            "equal_context_pp": 100 * float(row["equal_context"])}
            for reason, row in sorted(widths.items())},
        "width_reconciliation_pp": {
            "equal_bug": 100 * sum(float(row["equal_bug"]) for row in widths.values()),
            "equal_context": 100 * sum(float(row["equal_context"]) for row in widths.values()),
        },
        "legacy_label_sensitivity_same_full_pool": legacy_bounds,
        "filtered_structure_by_evidence": {f"{structure}|{label}": count
                                           for (structure, label), count in sorted(filtered_counts.items())},
        "interpretation": "Current-contract HumanEval-Java does not identify challenger versus native. Earlier labeled-only stream-calibration results are a different policy and population, not a failed reproduction of this estimand.",
    }
    for key in ("equal_bug", "equal_context"):
        bounds_key = "equal_bug_bounds" if key == "equal_bug" else "context_bounds"
        width = 100 * (reviewed[bounds_key][1] - reviewed[bounds_key][0])
        if abs(width - finding["width_reconciliation_pp"][key]) > 1e-10:
            raise ValueError("Unknown-width decomposition does not reconcile")
    output.mkdir(parents=True)
    (output / "review.json").write_text(json.dumps(finding, indent=2) + "\n", encoding="utf-8")
    lines = ["# HumanEval-Java Contract Replication Review", "", finding["interpretation"], "",
             f"The full challenger and native policy are identical in {agreement}/164 contexts.",
             f"There are {len(relevant)} decision-relevant Unknown candidates.", "",
             "| Primary Unknown category | Candidates | Equal-bug width (pp) | Equal-context width (pp) |",
             "|---|---:|---:|---:|"]
    for reason, row in finding["unknown_width_decomposition"].items():
        lines.append(f"| {reason} | {row['candidates']} | {row['equal_bug_pp']:.4f} | {row['equal_context_pp']:.4f} |")
    lines += ["", "Legacy-label sensitivity on the same full pool (not the primary contract):",
              f"- Equal bug: [{100*legacy_bounds['equal_bug_bounds'][0]:+.4f}, {100*legacy_bounds['equal_bug_bounds'][1]:+.4f}] pp.",
              f"- Equal context: [{100*legacy_bounds['context_bounds'][0]:+.4f}, {100*legacy_bounds['context_bounds'][1]:+.4f}] pp."]
    (output / "REVIEW.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({
        "inputs": {f"{source.relative_to(ROOT).as_posix()}/{name}": digest(source / name)
                   for name in ("manifest.json", "summary.json", "candidate_contract.jsonl", "decisions.jsonl")},
        "outputs": {name: digest(output / name) for name in ("review.json", "REVIEW.md")}}, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps(finding, indent=2))


if __name__ == "__main__":
    main()
