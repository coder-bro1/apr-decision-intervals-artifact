"""E3 scope (ADDENDUM_V4_E3_HUMANEVAL.md): rebuild the decision-relevant unknown HumanEval-Java records for
challenger vs native_position exactly as review_humaneval_contract_replication.py does, and attach each record's
method texts and archived evidence. Reads no new outcome. Writes results/v4/humaneval/e3_targets.jsonl."""
import sys as _sys  # release layout: shared helper modules live in lib/
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / "lib").is_dir()) / "lib"))
import json
import sys
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analysis_tools"))
from analysis_tools.evaluate_matched_baselines import METHODS, rows  # noqa: E402
from review_humaneval_contract_replication import distributions, primary_reason  # noqa: E402
from validation_policy_contract import project_candidate  # noqa: E402

SRC = ROOT / "results/humaneval_contract_replication/v2"
LEGACY = [ROOT / f"llm_apr_dataset/external/llm_apr_humanevaljava_candidates_v2_candidates_{k}.jsonl"
          for k in ("all", "excluded")]
OUT = ROOT / "results/v4/humaneval"


def ws(text):
    return "".join(text.split())


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    candidates = {r["candidate_id"]: r for r in rows(SRC / "candidate_contract.jsonl")}
    decisions = list(rows(SRC / "decisions.jsonl"))
    evidence = {k: {"correct": 1, "incorrect": 0, "unknown": None}[r["evidence"]["label"]] for k, r in candidates.items()}
    per_bug = Counter(d["bug_id"] for d in decisions)
    legacy = defaultdict(list)
    for path in LEGACY:
        for row in rows(path):
            legacy[project_candidate(row).candidate_id].append(row)
    targets = []
    for d in decisions:
        pol = distributions(d)
        for key in sorted(set(pol["challenger"]) | set(pol["native_position"])):
            coef = pol["challenger"].get(key, 0) - pol["native_position"].get(key, 0)
            if not coef or evidence[key] is not None:
                continue
            leg = legacy[key]
            anchor, patch, fix = leg[0]["anchor"], leg[0]["patch"], leg[0]["human_fix"]
            if any(r["anchor"] != anchor or r["patch"] != patch for r in leg):
                raise ValueError("legacy rows disagree on method text: " + key)
            targets.append({
                "candidate_id": key, "bug_id": d["bug_id"], "context_id": d["context_id"],
                "coefficient": str(coef), "equal_bug_weight_pp": 100 * float(abs(coef) / per_bug[d["bug_id"]] / len(per_bug)),
                "challenger_pick": key in pol["challenger"], "reason": primary_reason(candidates[key]["evidence"]),
                "unresolved_reasons": candidates[key]["evidence"]["unresolved_reasons"],
                "legacy_labels": sorted({r["label"] for r in leg}),
                "compile_values": dict(sum((Counter(r.get("compile_values") or {}) for r in leg), Counter())),
                "test_values": dict(sum((Counter(r.get("test_values") or {}) for r in leg), Counter())),
                "annotation_evidence": dict(sum((Counter(r.get("annotation_evidence") or {}) for r in leg), Counter())),
                "whitespace_equal_to_fix": ws(patch) == ws(fix),
                "anchor": anchor, "patch": patch, "human_fix": fix})
    with open(OUT / "e3_targets.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for t in targets:
            f.write(json.dumps(t) + "\n")
    # Tier B: every other non-filtered archived unknown that any challenger comparison depends on
    tier_a = {t["candidate_id"] for t in targets}
    tier_b = set()
    for d in decisions:
        pol = distributions(d)
        for m in METHODS:
            if m == "challenger":
                continue
            for key in set(pol["challenger"]) | set(pol[m]):
                if pol["challenger"].get(key, 0) != pol[m].get(key, 0) and evidence[key] is None and key not in tier_a:
                    tier_b.add(key)
    with open(OUT / "e3_tierB.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for key in sorted(tier_b):
            leg, c = legacy[key], candidates[key]
            f.write(json.dumps({"candidate_id": key, "bug_id": c["bug_id"], "context_id": c["context_id"],
                                "reason": primary_reason(c["evidence"]), "legacy_labels": sorted({r["label"] for r in leg}),
                                "whitespace_equal_to_fix": ws(leg[0]["patch"]) == ws(leg[0]["human_fix"]),
                                "anchor": leg[0]["anchor"], "patch": leg[0]["patch"], "human_fix": leg[0]["human_fix"]}) + "\n")
    print(f"tier B {len(tier_b)} records, {len({candidates[k]['bug_id'] for k in tier_b})} bugs")
    width = sum(t["equal_bug_weight_pp"] for t in targets)
    print(f"targets {len(targets)}  bugs {len({t['bug_id'] for t in targets})}  width {width:.2f} pp")
    print("by reason", Counter(t["reason"] for t in targets))
    print("challenger picks", sum(t["challenger_pick"] for t in targets),
          f"{sum(t['equal_bug_weight_pp'] for t in targets if t['challenger_pick']):.2f} pp")
    print("whitespace-equal to fix", sum(t["whitespace_equal_to_fix"] for t in targets),
          f"{sum(t['equal_bug_weight_pp'] for t in targets if t['whitespace_equal_to_fix']):.2f} pp")
    for reason in sorted({t["reason"] for t in targets}):
        sub = [t for t in targets if t["reason"] == reason]
        print(reason, "labels", Counter(tuple(t["legacy_labels"]) for t in sub).most_common(4))
        print("   ann", Counter(k for t in sub for k in t["annotation_evidence"]).most_common(6))
        print("   compile", Counter(tuple(sorted(t["compile_values"])) for t in sub).most_common(4),
              "test", Counter(tuple(sorted(t["test_values"])) for t in sub).most_common(4))


if __name__ == "__main__":
    main()
