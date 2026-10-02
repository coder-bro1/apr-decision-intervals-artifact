"""Descriptive, post-pilot audit of frozen first choices; no training or label updates."""

import argparse
import base64
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "results/contract_step1"
COMPARISONS = ROOT / "results/pilot_step2/context_comparisons.jsonl"
JAVA = ROOT / "execution_tools/BatchMethodFingerprint.java"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def text_id(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def rows(path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def parse_fingerprints(output, expected):
    result = {}
    for line in output.splitlines():
        key, status, fingerprint = line.split("\t")
        if key in result or status not in {"ok", "parse_error", "unsupported_shape"}:
            raise ValueError("Invalid or duplicate parser result")
        if status == "ok" and (len(fingerprint) != 64 or any(c not in "0123456789abcdef" for c in fingerprint)):
            raise ValueError("Invalid fingerprint")
        result[key] = {"status": status, "fingerprint": fingerprint}
    if set(result) != set(expected):
        raise ValueError("Parser did not cover exactly the input methods")
    return result


def structural_status(anchor, patch, fingerprints):
    a, p = fingerprints[text_id(anchor)], fingerprints[text_id(patch)]
    if a["status"] != "ok" or p["status"] != "ok":
        return "parse_unresolved"
    if a["fingerprint"] == p["fingerprint"]:
        return "exact_noop" if anchor == patch else "normalized_noop"
    return "different_parse"


def category(structure, label, reasons, tests):
    if structure in {"exact_noop", "normalized_noop"}:
        return "structural_noop"
    if structure == "parse_unresolved":
        return "parse_unresolved"
    if reasons:
        return "evidence_conflict"
    if label == "unknown":
        if tests.get("true", 0) > 0 and tests.get("false", 0) == 0:
            return "unknown_observed_test_pass_no_false"
        return "unknown_other"
    return "known_" + label


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.relative_to((ROOT / "results").resolve())
    if out.exists():
        raise FileExistsError("Use a new output directory; do not overwrite an audit")
    legacy_paths = [ROOT / f"llm_apr_dataset/llm_apr_defects4j_candidates_v2_candidates_{kind}.jsonl"
                    for kind in ("all", "excluded")]
    paths = [COMPARISONS, CONTRACT / "decision_candidates.jsonl", CONTRACT / "evaluation_evidence.jsonl",
             JAVA, Path(__file__), *legacy_paths]
    before = {str(p.relative_to(ROOT)).replace("\\", "/"): digest(p) for p in paths}
    comparisons = list(rows(COMPARISONS))
    # Selection depends on frozen decisions only, not labels, references, or fresh outcomes.
    disagree = [r for r in comparisons if r["baseline"] != r["challenger"]]
    selected = {k for r in disagree for method in ("baseline", "challenger")
                for k, p in r[method].items() if p > 0}
    views = {r["candidate_id"]: r for r in rows(CONTRACT / "decision_candidates.jsonl")
             if r["candidate_id"] in selected}
    if set(views) != selected:
        raise ValueError("Missing first-choice candidate code")
    methods = {text_id(text): text for r in views.values() for text in (r["anchor"], r["patch"])}
    out.mkdir(parents=True)
    request = out / "parser_input.tsv"
    with request.open("w", encoding="utf-8", newline="\n") as stream:
        for key, text in sorted(methods.items()):
            stream.write(key + "\t" + base64.b64encode(text.encode()).decode() + "\n")
    started = time.monotonic()
    with request.open(encoding="utf-8") as stream, (out / "parser_output.tsv").open("w", encoding="utf-8") as result, \
            (out / "parser_stderr.log").open("w", encoding="utf-8") as error:
        subprocess.run(["java", "-Xmx1g", str(JAVA)], stdin=stream, stdout=result, stderr=error,
                       check=True, timeout=600)
    fingerprints = parse_fingerprints((out / "parser_output.tsv").read_text(encoding="utf-8"), methods)
    elapsed = time.monotonic() - started
    evidence = {r["candidate_id"]: r for r in rows(CONTRACT / "evaluation_evidence.jsonl")
                if r["candidate_id"] in selected}
    legacy_ids = {k for r in evidence.values() for k in r["legacy_candidate_ids"]}
    legacy = {r["candidate_id"]: r for path in legacy_paths for r in rows(path)
              if r["candidate_id"] in legacy_ids}
    if set(legacy) != legacy_ids:
        raise ValueError("Incomplete legacy execution provenance")
    records = []
    for context in disagree:
        for key in sorted(k for k in context["baseline"] if context["baseline"][k] > 0 or context["challenger"][k] > 0):
            view, ev = views[key], evidence[key]
            tests, compiles = Counter(), Counter()
            for old in ev["legacy_candidate_ids"]:
                tests.update(legacy[old]["test_values"])
                compiles.update(legacy[old]["compile_values"])
            structure = structural_status(view["anchor"], view["patch"], fingerprints)
            records.append({"candidate_id": key, "context_id": context["context_id"],
                            "bug_id": context["bug_id"], "fold": context["fold"],
                            "baseline_probability": context["baseline"][key],
                            "challenger_probability": context["challenger"][key],
                            "structure": structure, "evidence_label": ev["label"],
                            "unresolved_reasons": ev["unresolved_reasons"],
                            "test_values": dict(tests), "compile_values": dict(compiles),
                            "category": category(structure, ev["label"], ev["unresolved_reasons"], tests)})
    with (out / "candidate_audit.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
    policy = {}
    for method in ("baseline", "challenger"):
        key = method + "_probability"
        chosen = [r for r in records if r[key] > 0]
        noops = [r for r in chosen if r["structure"] in {"exact_noop", "normalized_noop"}]
        mass = sum(r[key] for r in noops)
        policy[method] = {"first_choice_candidates": len(chosen),
                          "category_counts": dict(Counter(r["category"] for r in chosen)),
                          "noop_candidates": len(noops), "noop_contexts": len({r["context_id"] for r in noops}),
                          "noop_bugs": len({r["bug_id"] for r in noops}),
                          "noop_probability_mass": mass,
                          "noop_mass_per_disagreement_context": mass / len(disagree) if disagree else 0,
                          "noop_evidence_labels": dict(Counter(r["evidence_label"] for r in noops))}
    contradictions = [r["candidate_id"] for r in records if r["evidence_label"] == "correct"
                      and r["structure"] in {"exact_noop", "normalized_noop"}]
    unchanged = before == {str(p.relative_to(ROOT)).replace("\\", "/"): digest(p) for p in paths}
    if not unchanged:
        raise ValueError("An input changed during the audit")
    summary = {"all_contexts": len(comparisons), "disagreement_contexts": len(disagree),
               "disagreement_bugs": len({r["bug_id"] for r in disagree}), "selected_unique_candidates": len(selected),
               "candidate_records": len(records), "unique_method_texts": len(methods),
               "parser_status_counts": dict(Counter(r["status"] for r in fingerprints.values())),
               "category_counts": dict(Counter(r["category"] for r in records)),
               "structure_counts": dict(Counter(r["structure"] for r in records)),
               "policy": policy, "correct_label_noop_contradictions": contradictions,
               "parser_end_to_end_seconds": elapsed,
               "java_version": subprocess.run(["java", "-version"], capture_output=True, text=True, check=True).stderr.strip(),
               "inputs_unchanged": unchanged, "input_sha256": before,
               "scope": "Post-Closure diagnostic, frozen first choices in disagreement contexts only; no reranking, no label updates, no novel-method or speedup claim.",
               "category_priority": ["structural_noop", "parse_unresolved", "evidence_conflict", "unknown_observed_test_pass_no_false", "unknown_other", "known_correct_or_incorrect"],
               "limitations": ["Parser-normalized identity is not universal semantic equivalence; parse-only JDK wrapper failures are not compile failures.",
                               "Unknown observed test passes are historical evidence, not new test executions or correctness labels.",
                               "Noop selection mass is diagnostic exposure, not measured correct-fix improvement from filtering.",
                               "This hypothesis was motivated by the exposed Closure-78 case; the audit is exploratory."]}
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    lines = ["# Frozen First-Choice Disagreement Audit", "", summary["scope"], "",
             f"Contexts: {len(comparisons)} total; {len(disagree)} disagree. Candidates audited: {len(selected)}.", "",
             "| Category (exclusive priority order) | Candidate records |", "| --- | ---: |"]
    lines += [f"| {k} | {v} |" for k, v in sorted(summary["category_counts"].items())]
    lines += ["", "| Policy | No-op candidates | Contexts affected | No-op probability mass |",
              "| --- | ---: | ---: | ---: |"]
    lines += [f"| {k} | {v['noop_candidates']} | {v['noop_contexts']} | {v['noop_probability_mass']:.6f} |" for k, v in policy.items()]
    lines += ["", "No-op mass respects all frozen first-rank ties. It is not a reranking benefit.",
              f"Correct-label/no-op contradictions requiring inspection: {len(contradictions)}.", "",
              *summary["limitations"], "", "All source hashes verified unchanged; no dataset labels updated."]
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "input_sha256"}, indent=2))


if __name__ == "__main__":
    main()
