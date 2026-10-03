"""Build an outcome-blind full-pool inventory, not a method evaluation.

Writes only results/contract_step1 and the explicitly named Step 1 packet.
Frozen V3.2 inputs and outputs are checked without regeneration.
"""

import sys as _sys  # release layout: shared helper modules live in lib/
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / "lib").is_dir()) / "lib"))
import json
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path

from audit_research_reassessment_20260913 import manifest_entries, sha256
from validation_policy_contract import candidate_id, context_id, label_blind_fold, project_candidate, support_only_action


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/contract_step1"
DATA = ROOT / "llm_apr_dataset"
PREFIX = "llm_apr_defects4j_candidates_v2"


def json_rows(path):
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_rows(path, rows):
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def audit_frozen():
    path = ROOT / "results/v2/paper_artifact_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    entries = list(manifest_entries(manifest))
    entries += [{"path": name, "sha256": digest} for name, digest in manifest["outputs"].items()]
    entries.append({"path": manifest["generator"], "sha256": manifest["generator_sha256"]})
    for entry in entries:
        if sha256(ROOT / entry["path"]) != entry["sha256"]:
            raise ValueError(f"Frozen artifact differs: {entry['path']}")
    return {"manifest_sha256": sha256(path), "verified_entries_including_outputs_and_generator": len(entries)}


def conservative_evidence(legacy):
    labels = {r["label"] for r in legacy}
    flags = {flag for r in legacy for flag in ("compile_conflict", "test_conflict", "label_evidence_conflict") if r.get(flag)}
    if any(r.get("exclusion_reason") == "noncorrect_label_but_same_as_human_fix" for r in legacy):
        flags.add("reference_label_contradiction")
    if len(labels) > 1:
        flags.add("observable_identity_label_disagreement")
    if not legacy:
        flags.add("no_legacy_evidence")
    label = next(iter(labels)) if len(labels) == 1 and not flags else "unknown"
    return {"label": label, "legacy_labels": sorted(labels), "unresolved_reasons": sorted(flags),
            "legacy_candidate_ids": sorted(r["candidate_id"] for r in legacy)}


def main():
    frozen = audit_frozen()
    manifest_path = ROOT / "repairllama/results/benchmarks/defects4j_sf.txt"
    bugs = set(manifest_path.read_text(encoding="utf-8").split())
    paths = [DATA / f"{PREFIX}_candidates_{kind}.jsonl" for kind in ("all", "excluded")]
    legacy = defaultdict(list)
    old_contexts = defaultdict(set)
    old_counts = Counter()
    for path in paths:
        for row in json_rows(path):
            key = candidate_id(row["bug_id"], row["anchor"], row["patch"])
            legacy[key].append(row)
            old_contexts[context_id(row["bug_id"], row["anchor"])].add(row["human_fix"])
            old_counts[row.get("exclusion_reason", "included")] += 1

    inventory, contexts = {}, {}
    counts = Counter()
    source_paths = sorted((ROOT / "repairllama/results/3_martin").glob("evaluation_defects4j_*_martin.jsonl"))
    archive_audit_path = DATA / f"{PREFIX}_audit_summary.json"
    archive_hashes = json.loads(archive_audit_path.read_text(encoding="utf-8"))["source_file_sha256"]
    if {path.name: sha256(path) for path in source_paths} != archive_hashes:
        raise ValueError("Raw generation files do not match the pinned dataset provenance.")
    for path in source_paths:
        config = path.name.removeprefix("evaluation_defects4j_").removesuffix("_martin.jsonl")
        for raw in json_rows(path):
            if raw.get("identifier") not in bugs:
                counts["out_of_manifest_rows"] += 1
                continue
            bug = raw["identifier"]
            anchor = (raw.get("buggy_code") or "").strip()
            evaluations = raw.get("evaluation") or []
            counts["official_occurrences_including_missing_context"] += len(evaluations)
            if not anchor:
                counts["missing_buggy_context_rows"] += 1
                counts["missing_buggy_context_occurrences"] += len(evaluations)
                continue
            ctx = context_id(bug, anchor)
            contexts.setdefault(ctx, {"context_id": ctx, "bug_id": bug, "anchor": anchor, "candidate_ids": set()})
            for index, evaluation in enumerate(evaluations):
                patch = (evaluation.get("generation") or "").strip()
                if not patch:
                    counts["empty_patch_occurrences"] += 1
                    continue
                key = candidate_id(bug, anchor, patch)
                row = inventory.setdefault(key, {"bug_id": bug, "anchor": anchor, "patch": patch, "sources": []})
                row["sources"].append({"source_config": config, "candidate_index": index})
                contexts[ctx]["candidate_ids"].add(key)
                counts["eligible_occurrences"] += 1
                if not (raw.get("fixed_code") or "").strip():
                    counts["eligible_occurrences_without_reference_fix"] += 1
    if set(legacy) - set(inventory):
        raise ValueError("Some archived candidates disappeared from the observable raw pool.")
    # Keep all official bugs in accounting, even when no buggy context was recorded.
    represented = {row["bug_id"] for row in contexts.values()}
    for bug in sorted(bugs - represented):
        ctx = context_id(bug, "")
        contexts[ctx] = {"context_id": ctx, "bug_id": bug, "anchor": "", "candidate_ids": set(),
                         "empty_reason": "no_observable_buggy_context"}
    views = [asdict(project_candidate(inventory[key])) for key in sorted(inventory)]
    evidence = [{"candidate_id": key, **conservative_evidence(legacy[key])} for key in sorted(inventory)]
    ledger = []
    for ctx, row in sorted(contexts.items()):
        ledger.append({**row, "candidate_ids": sorted(row["candidate_ids"]), "fold": label_blind_fold(row["bug_id"])})
    hard_ids = {candidate_id(r["bug_id"], r["anchor"], r["patch"])
                for r in json_rows(DATA / f"{PREFIX}_candidates_hard.jsonl")}
    actions = [r for r in json_rows(ROOT / "results/v2/shift_aware_safe_scheduler_actions.jsonl")
               if r["benchmark"] == "defects4j" and r["method"] == "safe_gate_q95_r20"]
    matches = all(r["action"] == support_only_action(r["out_of_support"], r["top_sets_identical"]) for r in actions)
    if not matches:
        raise ValueError("Recorded primary gate no longer equals the audited support-only rule.")
    report = {
        "protocol": "validation-contract-step1-2026-09-13-v1", "status": "inventory_and_contract_only",
        "frozen_v32": frozen, "raw_accounting": dict(counts), "old_candidate_accounting": dict(old_counts),
        "raw_source_hashes_match_archive": True,
        "candidate_count": len(views), "context_count_including_empty": len(ledger), "official_bug_count": len(bugs),
        "nonempty_contexts": sum(bool(r["candidate_ids"]) for r in ledger),
        "empty_contexts": sum(not r["candidate_ids"] for r in ledger),
        "placeholder_contexts": len(bugs - represented),
        "observable_contexts_with_multiple_legacy_reference_fixes": sum(len(fixes) > 1 for fixes in old_contexts.values()),
        "legacy_candidate_count": sum(len(rows) for rows in legacy.values()),
        "observable_candidates_merging_legacy_ids": sum(len(rows) > 1 for rows in legacy.values()),
        "legacy_correct_now_unresolved": sum(r["label"] == "unknown" and "correct" in r["legacy_labels"] for r in evidence),
        "legacy_unknown_retained": sum("unknown" in r["legacy_labels"] and r["label"] == "unknown" for r in evidence),
        "candidates_without_legacy_evidence": sum(not legacy[key] for key in inventory),
        "restored_candidates_vs_hard_pool": len(set(inventory) - hard_ids),
        "evidence_labels": dict(Counter(r["label"] for r in evidence)),
        "unresolved_reasons": dict(Counter(reason for r in evidence for reason in r["unresolved_reasons"])),
        "fold_bug_counts": dict(Counter(label_blind_fold(bug) for bug in bugs)),
        "legacy_primary_support_only_equivalence": matches,
        "legacy_primary_action_counts": dict(Counter(r["action"] for r in actions)),
        "decision_view_fields": sorted(asdict(project_candidate(next(iter(inventory.values()))))),
        "new_training_or_policy_performance_evaluation": False,
        "inputs": {str(path.relative_to(ROOT)): sha256(path) for path in paths + source_paths + [manifest_path, archive_audit_path]},
    }
    assert counts["official_occurrences_including_missing_context"] == counts["eligible_occurrences"] + counts["empty_patch_occurrences"] + counts["missing_buggy_context_occurrences"]
    OUT.mkdir(parents=True, exist_ok=True)
    write_rows(OUT / "decision_candidates.jsonl", views)
    write_rows(OUT / "evaluation_evidence.jsonl", evidence)
    write_rows(OUT / "contexts.jsonl", ledger)
    write_json(OUT / "eligibility_audit.json", report)
    packet = f"""# Step 1 Co-Author Review Packet

Status: Step 1 complete; Step 2 has NOT started. This packet supersedes the
interpretation/plan in the July packet, not its frozen numerical evidence.

## What Was Fixed

- Decision inputs are projected from raw generation artifacts using only buggy
  code, generated code, source configuration, and native position.
- Human-fix text no longer defines context/candidate identities. Evidence and
  conflicts live in a separate evaluation file, never the ranker input.
- Retained all nonempty generated patches with available buggy context,
  including unchanged patches and the three reference-dependent exclusions.
- Reference/label contradictions and conflicting historical outcomes become
  unresolved evidence, not candidate exclusions or newly adjudicated labels.
- Added a strict common policy interface, exact top-tie probabilities, and an
  explicit support-only baseline. Missing scores fail instead of dropping patches.
- The amended risk contract specifies fixed policy families, independent bug
  calibration, no post-calibration refit, and conditional guarantees only.

## Audit Numbers

| Quantity | Count |
| --- | ---: |
| Official bugs | {len(bugs)} |
| Observable contexts, including empty accounting slots | {len(ledger)} |
| Nonempty contexts | {report['nonempty_contexts']} |
| Empty contexts | {report['empty_contexts']} |
| Decision candidates | {len(views)} |
| Eligible raw occurrences | {counts['eligible_occurrences']} |
| Candidates restored relative to the legacy hard-pool identity set | {report['restored_candidates_vs_hard_pool']} |
| Correct evidence under the conservative contract | {report['evidence_labels'].get('correct', 0)} |
| Incorrect evidence under the conservative contract | {report['evidence_labels'].get('incorrect', 0)} |
| Unknown evidence under the conservative contract | {report['evidence_labels'].get('unknown', 0)} |

These are eligibility/evidence counts, not new performance scores. They have a
different universe and conflict policy from V3.2 and must not replace July
denominators in existing results. Missing-context occurrences remain explicitly
unreconstructable; full pool means the observable archived pool, not all attempts.

## Claims Corrected

| Existing claim | Current permitted interpretation |
| --- | --- |
| C12/C15 | Separate historical factorized-policy utility results, not a safety-wrapped full-pool system |
| C14 | Observed infeasibility under the old acceptance procedure; population guarantee pending repair |
| C20 | Restricted hard-pool empirical improvement; primary actions equal support-only gating |
| C21 | Old bound/sample-size infeasibility, not impossibility of safer ranking |
| C23 | Configuration membership triggers deferral; no demonstrated learned shift detection |
| Label-world comparisons | Sensitivity scenarios, not extremal bounds on the paired difference |

The primary historical gate still has 684 overrides, 126 agreements, and 43
deferrals; exact support-only equivalence is checked against the stored ledger.
No new safety guarantee, acquisition benefit, runtime saving, or semantic
generalization result has been obtained in Step 1.

## Read Next

1. `VALIDATION_CONTRACT_STEP1.md`: precise eligibility, estimands, risk proof,
   limitations, and stopping boundary.
2. `results/contract_step1/eligibility_audit.json`: generated counts/hashes.
3. `results/contract_step1/verification.json`: test and artifact verification.
4. `RESEARCH_REASSESSMENT_2026_09_13.md`: literature and proposed Step 2 pilot.

Rebuild inventory/packet: `.venv\\Scripts\\python.exe -B build_validation_contract_step1.py`.
The July builder remains unchanged and recreates historical packets only.
Use this Step 1 packet for current co-author review.

## Review Questions

1. Does the fixed-pool task and separate evidence budget make the deployment
   boundary unambiguous, without implying automatic patch acceptance?
2. Are the conditional iid-bug risk assumptions and new outcome-blind folds
   sufficiently explicit, including the absence of fresh external evidence?
3. Is the planned Step 2 comparison against simple disagreement acquisition
   strong enough to justify any later method claim?
"""
    packet_path = ROOT / "docs/reviews/COAUTHOR_REVIEW_PACKET_STEP1.md"
    packet_path.write_text(packet, encoding="utf-8")
    products = list(OUT.glob("*.jsonl")) + [OUT / "eligibility_audit.json", packet_path]
    products += [ROOT / name for name in ("VALIDATION_CONTRACT_STEP1.md", "validation_policy_contract.py", "build_validation_contract_step1.py", "test_validation_contract_step1.py", "verify_validation_contract_step1.py")]
    write_json(OUT / "manifest.json", {"protocol": report["protocol"], "files": {str(p.relative_to(ROOT)): sha256(p) for p in products}})
    print(json.dumps({key: value for key, value in report.items() if key != "inputs"}, indent=2))


if __name__ == "__main__":
    main()
