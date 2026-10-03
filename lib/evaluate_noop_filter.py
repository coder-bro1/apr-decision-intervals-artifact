"""Equal-treatment full-pool no-op filtering of frozen budget-1 policies."""

import sys as _sys  # release layout: shared helper modules live in lib/
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / "lib").is_dir()) / "lib"))
import argparse
import base64
from collections import Counter, defaultdict
from fractions import Fraction
import json
import math
from pathlib import Path
import subprocess
import time

from audit_first_choice_disagreements import ROOT, JAVA, digest, rows, text_id, parse_fingerprints, structural_status
from evidence_budget_bounds import comparison_bounds

NAMES = ("native", "challenger", "native_filtered", "challenger_filtered")
PAIRS = (("native_filtered", "native"), ("challenger_filtered", "challenger"),
         ("challenger_filtered", "native_filtered"), ("challenger", "native"))


def choose(scores, excluded=frozenset()):
    if not set(excluded) <= set(scores) or any(not math.isfinite(v) for v in scores.values()):
        raise ValueError("Invalid exclusion set or nonfinite score")
    eligible = {k: v for k, v in scores.items() if k not in excluded}
    result = {k: Fraction(0) for k in scores}
    if not eligible:
        return result
    best = max(eligible.values())
    top = [k for k, v in eligible.items() if v == best]
    for k in top:
        result[k] = Fraction(1, len(top))
    return result


def paired(proposed, baseline, evidence):
    if set(proposed) != set(baseline):
        raise ValueError("Policies must retain the full same candidate universe")
    return comparison_bounds({k: proposed[k] - baseline[k] for k in proposed}, evidence)


def aggregate(bounds, bugs):
    if not bounds or len(bounds) != len(bugs):
        raise ValueError("Invalid aggregation")
    groups = defaultdict(list)
    for bound, bug in zip(bounds, bugs):
        groups[bug].append(bound)
    macro = [tuple(sum((b[i] for b in group), Fraction(0)) / len(group) for i in range(2))
             for group in groups.values()]
    return {"context_bounds": [float(sum((b[i] for b in bounds), Fraction(0)) / len(bounds)) for i in range(2)],
            "equal_bug_bounds": [float(sum((b[i] for b in macro), Fraction(0)) / len(macro)) for i in range(2)],
            "contexts": len(bounds), "bugs": len(groups)}


def evaluate(decisions, evidence):
    bugs = [r["bug_id"] for r in decisions]
    return {
        "success": {name: aggregate([comparison_bounds(r["policies"][name], evidence) for r in decisions], bugs)
                    for name in NAMES},
        "paired": {a + "_minus_" + b: aggregate([paired(r["policies"][a], r["policies"][b], evidence)
                                                for r in decisions], bugs) for a, b in PAIRS}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.relative_to((ROOT / "results").resolve())
    if out.exists():
        raise FileExistsError("Use a new output directory")
    contract, pilot = ROOT / "results/contract_step1", ROOT / "results/pilot_step2"
    inputs = [contract / n for n in ("contexts.jsonl", "decision_candidates.jsonl", "evaluation_evidence.jsonl")]
    inputs += [pilot / "predictions.jsonl", pilot / "context_comparisons.jsonl", JAVA, Path(__file__),
               ROOT / "audit_first_choice_disagreements.py", ROOT / "evidence_budget_bounds.py",
               ROOT / "NOOP_FILTER_PROTOCOL.md"]
    before = {str(p.relative_to(ROOT)).replace("\\", "/"): digest(p) for p in inputs}
    contexts = list(rows(inputs[0]))
    views = {r["candidate_id"]: r for r in rows(inputs[1])}
    context_map = {r["context_id"]: r for r in contexts}
    scores = {}
    for prediction in rows(pilot / "predictions.jsonl"):
        if prediction["role"] != "test":
            continue
        key = prediction["candidate_id"]
        if key in scores or key not in views:
            raise ValueError("Duplicate/unknown held-out prediction")
        fold = context_map[views[key]["context_id"]]["fold"]
        if fold != f"fold_{prediction['rotation']}":
            raise ValueError("Held-out fold mismatch")
        scores[key] = prediction["score"]
    if set(scores) != set(views):
        raise ValueError("Incomplete held-out scores")
    methods = {text_id(text): text for v in views.values() for text in (v["anchor"], v["patch"])}
    out.mkdir(parents=True)
    with (out / "parser_input.tsv").open("w", encoding="utf-8", newline="\n") as stream:
        for key, text in sorted(methods.items()):
            stream.write(key + "\t" + base64.b64encode(text.encode()).decode() + "\n")
    start = time.monotonic()
    with (out / "parser_input.tsv").open(encoding="utf-8") as stream, \
            (out / "parser_output.tsv").open("w", encoding="utf-8") as result, \
            (out / "parser_stderr.log").open("w", encoding="utf-8") as error:
        subprocess.run(["java", "-Xmx1g", str(JAVA)], stdin=stream, stdout=result, stderr=error,
                       check=True, timeout=600)
    elapsed = time.monotonic() - start
    fingerprints = parse_fingerprints((out / "parser_output.tsv").read_text(encoding="utf-8"), methods)
    structures = {k: structural_status(v["anchor"], v["patch"], fingerprints) for k, v in views.items()}
    excluded = {k for k, status in structures.items() if status in {"exact_noop", "normalized_noop"}}
    frozen = {r["context_id"]: r for r in rows(pilot / "context_comparisons.jsonl")}
    if set(frozen) != set(context_map):
        raise ValueError("Context inventory mismatch")
    decisions = []
    changed, abstained = Counter(), Counter()
    for ctx in contexts:
        ids = ctx["candidate_ids"]
        if any(views[k]["context_id"] != ctx["context_id"] for k in ids):
            raise ValueError("Candidate/context mismatch")
        native = {k: -min(s["candidate_index"] for s in views[k]["sources"]) for k in ids}
        challenger = {k: scores[k] for k in ids}
        removed = set(ids) & excluded
        policies = {"native": choose(native), "challenger": choose(challenger),
                    "native_filtered": choose(native, removed), "challenger_filtered": choose(challenger, removed)}
        for name, old in (("native", "baseline"), ("challenger", "challenger")):
            reconstructed = {k: float(v) for k, v in policies[name].items()}
            if reconstructed != frozen[ctx["context_id"]][old]:
                raise ValueError("Original decisions do not reproduce frozen artifact")
            changed[name] += policies[name] != policies[name + "_filtered"]
        for name in NAMES:
            abstained[name] += not any(policies[name].values())
        decisions.append({"context_id": ctx["context_id"], "bug_id": ctx["bug_id"], "fold": ctx["fold"],
                          "removed_count": len(removed), "policies": policies})
    # Labels are loaded only after the code-only decisions have been constructed.
    evidence_rows = list(rows(contract / "evaluation_evidence.jsonl"))
    evidence = {r["candidate_id"]: {"correct": 1, "incorrect": 0, "unknown": None}[r["label"]] for r in evidence_rows}
    if set(evidence) != set(views):
        raise ValueError("Evidence inventory mismatch")
    primary = evaluate(decisions, evidence)
    contradictions = sorted(k for k in excluded if evidence[k] == 1)
    sensitivity = None
    if not contradictions:
        assumed = {k: (0 if k in excluded else value) for k, value in evidence.items()}
        sensitivity = evaluate(decisions, assumed)
    with (out / "candidate_structure.jsonl").open("w", encoding="utf-8") as stream:
        for k in sorted(views):
            stream.write(json.dumps({"candidate_id": k, "structure": structures[k], "excluded": k in excluded}) + "\n")
    with (out / "decisions.jsonl").open("w", encoding="utf-8") as stream:
        for decision in decisions:
            stream.write(json.dumps(decision, default=str) + "\n")
    local = []
    for r in decisions:
        local.append({"context_id": r["context_id"], "bug_id": r["bug_id"],
                      "paired": {a + "_minus_" + b: list(map(float, paired(r["policies"][a], r["policies"][b], evidence)))
                                 for a, b in PAIRS}})
    with (out / "context_bounds.jsonl").open("w", encoding="utf-8") as stream:
        for r in local:
            stream.write(json.dumps(r) + "\n")
    unchanged = before == {str(p.relative_to(ROOT)).replace("\\", "/"): digest(p) for p in inputs}
    if not unchanged:
        raise ValueError("Inputs changed during evaluation")
    summary = {"contexts": len(contexts), "bugs": len({c['bug_id'] for c in contexts}), "candidates": len(views),
               "structure_counts": dict(Counter(structures.values())), "excluded_candidates": len(excluded),
               "excluded_evidence_counts": dict(Counter(str(evidence[k]) for k in excluded)),
               "correct_label_contradictions": contradictions, "changed_contexts": dict(changed),
               "abstention_contexts_including_original_empty": dict(abstained),
               "primary_frozen_labels": primary, "sensitivity_noops_assumed_incorrect": sensitivity,
               "parser_seconds": elapsed, "unique_method_texts": len(methods),
               "java_version": subprocess.run(["java", "-version"], capture_output=True, text=True, check=True).stderr.strip(),
               "inputs_unchanged": unchanged, "original_decisions_reproduced": True,
               "input_sha256": before,
               "scope": "Exploratory frozen-score budget-1 evaluation; identification bounds, not sampling CIs; no runtime-saving or novel-method claim.",
               "abstention_contract": "All-zero selection weights on the retained full pool mean no returned patch and success 0. This is an explicit new evaluation adapter, not a mutation of PolicyDecision.",
               "sensitivity_assumption": "Detected normalized no-ops cannot repair the represented bug through this complete method-only intervention; all other labels unchanged. Not a new accepted label set."}
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    lines = ["# Equal-Treatment Full-Pool No-Op Filter", "", summary["scope"], "",
             f"All {len(contexts)} contexts retained; {len(excluded)} of {len(views)} candidates filtered.", "",
             "## Primary: Frozen Labels", "", "| Policy | Budget-1 success bounds (%) |", "| --- | ---: |"]
    for name, result in primary["success"].items():
        lo, hi = result["context_bounds"]
        lines.append(f"| {name} | [{100*lo:.4f}, {100*hi:.4f}] |")
    lines += ["", "| Paired difference | Bounds (percentage points) |", "| --- | ---: |"]
    for name, result in primary["paired"].items():
        lo, hi = result["context_bounds"]
        lines.append(f"| {name} | [{100*lo:.4f}, {100*hi:.4f}] |")
    lines += ["", "## Sensitivity Only: No-Ops Assumed Unfixed", "", summary["sensitivity_assumption"], ""]
    if sensitivity:
        for name, result in sensitivity["paired"].items():
            lo, hi = result["context_bounds"]
            lines.append(f"- {name}: [{100*lo:.4f}, {100*hi:.4f}] percentage points.")
    else:
        lines.append("Suppressed because accepted-correct/no-op contradictions require inspection.")
    lines += ["", "Parse-unresolved candidates were retained. No original labels, scores or tables changed.",
              "A filter removing a bad first choice does not establish that its replacement is correct.",
              "Structural identity and the sensitivity assumption need external validation; no new patch executions occurred."]
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "input_sha256"}, indent=2))


if __name__ == "__main__":
    main()
