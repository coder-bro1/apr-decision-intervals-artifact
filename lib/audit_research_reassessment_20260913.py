"""Read-only audit of July evidence; write only a separate September report."""

import sys as _sys  # release layout: shared helper modules live in lib/
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / "lib").is_dir()) / "lib"))
import argparse
import csv
import hashlib
import itertools
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results/reassessment_2026_09_13/integrity_audit.json"
METHOD = "safe_gate_q95_r20"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_rows(path):
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def manifest_entries(node):
    if isinstance(node, dict):
        if "path" in node and "sha256" in node:
            yield node
        for value in node.values():
            yield from manifest_entries(value)
    elif isinstance(node, list):
        for value in node:
            yield from manifest_entries(value)


def coupled_bounds(coefficients, labels):
    # One shared unknown label per candidate, not separate worlds per policy.
    known = sum(c * y for c, y in zip(coefficients, labels) if y is not None)
    lower = known + sum(min(0, c) for c, y in zip(coefficients, labels) if y is None)
    upper = known + sum(max(0, c) for c, y in zip(coefficients, labels) if y is None)
    return lower, upper


def verify_bound_identity():
    cases = 0
    for coefficients in itertools.product((-1, 0, 1), repeat=4):
        if sum(coefficients) != 0:
            continue
        for labels in itertools.product((0, 1, None), repeat=4):
            unknown = [i for i, label in enumerate(labels) if label is None]
            values = []
            for completion in itertools.product((0, 1), repeat=len(unknown)):
                filled = list(labels)
                for index, label in zip(unknown, completion):
                    filled[index] = label
                values.append(sum(c * y for c, y in zip(coefficients, filled)))
            assert coupled_bounds(coefficients, labels) == (min(values), max(values))
            cases += 1
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-tests", action="store_true")
    args = parser.parse_args()
    import make_paper_tables as paper

    checks = paper.validate_inputs({name: paper.load_json(path) for name, path in paper.INPUTS.items()})
    manifest_path = ROOT / "results/v2/paper_artifact_manifest.json"
    manifest = read_json(manifest_path)
    entries = list(manifest_entries(manifest))
    mismatches = []
    for entry in entries:
        path = ROOT / entry["path"]
        actual = sha256(path) if path.is_file() else None
        if actual != entry["sha256"]:
            mismatches.append({"path": entry["path"], "expected": entry["sha256"], "actual": actual})
    scheduler_path = ROOT / "results/v2/shift_aware_safe_scheduler.json"
    scheduler = read_json(scheduler_path)
    folds = []
    for fold in scheduler["internal"]["fold_audit"]:
        selection = fold["selections"][METHOD]
        trial = next(row for row in selection["trials"] if row["threshold"] == selection["selected_threshold"])
        n = trial["selected_bug_count"]
        k = selection["threshold_grid_size"]
        floor = math.sqrt(math.log(k / 0.05) / (2 * n))
        folds.append({
            "fold": fold["test_fold"], "threshold": selection["selected_threshold"],
            "threshold_count": k, "selected_bugs": n,
            "mean_bug_harm": trial["mean_bug_harm"], "zero_harm_hoeffding_floor": floor,
            "reported_upper": trial["simultaneous_harm_upper"],
        })
    action_path = ROOT / "results/v2/shift_aware_safe_scheduler_actions.jsonl"
    actions = [r for r in read_rows(action_path) if r["benchmark"] == "defects4j" and r["method"] == METHOD]
    assert len({r["context_id"] for r in actions}) == len(actions)
    reviews = []
    for path in sorted((ROOT / "results/v2/repairbench_semantic_review").glob("reviewer_*_responses.csv")):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        reviews.append({"file": str(path.relative_to(ROOT)), "rows": len(rows),
                        "labeled": sum(bool(r["label"].strip()) for r in rows)})
    hard_path = ROOT / "llm_apr_dataset/llm_apr_defects4j_candidates_v2_candidates_hard.jsonl"
    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Read-only frozen-result audit; no training, new deployment evaluation, or semantic adjudication.",
        "script_sha256": sha256(Path(__file__)),
        "source_hashes": {str(p.relative_to(ROOT)): sha256(p) for p in (manifest_path, scheduler_path, action_path, hard_path)},
        "manifest_entries_checked": len(entries), "manifest_mismatches": mismatches,
        "artifact_integrity_checks": checks,
        "generator_matches_manifest": sha256(ROOT / manifest["generator"]) == manifest["generator_sha256"],
        "safe_gate_input_labels": dict(Counter(r["label"] for r in read_rows(hard_path))),
        "primary_gate_folds": folds,
        "primary_action_counts": dict(Counter(r["action"] for r in actions)),
        "primary_context_count": len(actions),
        "zero_margin_contexts": sum(r["override_margin"] == 0 for r in actions),
        "positive_margin_contexts": sum(r["override_margin"] > 0 for r in actions),
        "primary_matches_support_only_rule": all(
            r["action"] == ("defer" if r["out_of_support"] else "agreement" if r["top_sets_identical"] else "override")
            for r in actions
        ),
        "minimum_zero_harm_sample_sizes_K1_delta05": {
            str(alpha): math.ceil(math.log(1 / 0.05) / (2 * alpha ** 2)) for alpha in (0.05, 0.10, 0.20)
        },
        "semantic_review_progress": reviews,
        "partial_bound_exhaustive_cases": verify_bound_identity(),
        "unknown_difference_counterexample": {
            "policy_a_selects": "u1", "policy_b_selects": "u2",
            "all_unknown_wrong_delta": 0, "all_unknown_correct_delta": 0,
            "sharp_delta_bounds": coupled_bounds([1, -1], [None, None]),
            "status": "Mathematical example, not an empirical APR result or a novelty claim.",
        },
    }
    if args.run_tests:
        from build_paper_artifacts import run_top_level_tests

        report["regression_tests"] = run_top_level_tests()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    if mismatches or not all(checks.values()) or not report.get("regression_tests", {}).get("successful", True):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
