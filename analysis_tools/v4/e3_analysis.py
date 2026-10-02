"""E3 analysis (ADDENDUM_V4_E3_HUMANEVAL.md): candidate statuses from the tier A/B runs, the evidence views
(A0, A1, A2, X1, X2, HE-E1, X3) and challenger-minus-method bounds for every method. Tier B may be partial: an unrun
record stays unknown. Writes results/v4/humaneval/e3_statuses.jsonl, e3_results.json and E3_REPORT.md."""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analysis_tools"))
from analysis_tools.evaluate_matched_baselines import METHODS, rows  # noqa: E402
from review_humaneval_contract_replication import distributions, paired_bounds  # noqa: E402
from validation_policy_contract import project_candidate  # noqa: E402

SRC = ROOT / "results/humaneval_contract_replication/v2"
OUT = ROOT / "results/v4/humaneval"
RUNS = [("A", ROOT / "results/v4/e3_tierA_package_v1", ROOT / "results/v4/e3_tierA_run_v1"),
        ("B", ROOT / "results/v4/e3_tierB_package_v1", ROOT / "results/v4/e3_tierB_run_v1")]
LEGACY = [ROOT / f"llm_apr_dataset/external/llm_apr_humanevaljava_candidates_v2_candidates_{k}.jsonl" for k in ("all", "excluded")]
FAIL_NAME = re.compile(r"^\d+\) (.+?)\(humaneval\.TEST_\w+\)", re.M)
RUN_LINE = re.compile(r"Tests run: (\d+),\s+Failures: (\d+)")


def outcome(res, v, rep):
    rc_file = res / f"{v}.{rep}.javac.rc"
    if not rc_file.exists():
        return ("missing",)
    rc = int(rc_file.read_text().strip())
    if rc == 124:
        return ("timeout",)
    if rc != 0:
        return ("compile_fail",)
    jrc = int((res / f"{v}.{rep}.junit.rc").read_text().strip())
    txt = (res / f"{v}.{rep}.junit.txt").read_text(encoding="utf-8", errors="replace")
    if jrc == 124:
        return ("timeout",)
    m = re.search(r"^OK \((\d+) tests?\)", txt, re.M)
    if jrc == 0 and m:
        return ("pass", int(m.group(1)))
    m = RUN_LINE.search(txt)
    if jrc != 0 and m and int(m.group(2)) > 0:
        return ("fail", frozenset(FAIL_NAME.findall(txt)))
    return ("error",)


def statuses():
    result = {}
    for tier, pkg, run in RUNS:
        if not run.exists():
            continue
        for bug_dir in sorted(p for p in run.iterdir() if p.is_dir()):
            term = bug_dir / "terminal.json"
            if not term.exists() or not json.loads(term.read_text())["container_ok"]:
                continue
            res = bug_dir / "res"
            job = json.loads((pkg / bug_dir.name / "job.json").read_text())
            fx = [outcome(res, "fixed", r) for r in (1, 2)]
            bg = [outcome(res, "buggy", r) for r in (1, 2)]
            valid = (all(o[0] == "pass" for o in fx) and all(o[0] == "fail" for o in bg) and bg[0][1] == bg[1][1])
            trigger = bg[0][1] if valid else frozenset()
            for v, meta in job["candidates"].items():
                o = [outcome(res, v, r) for r in (1, 2)]
                kinds = [x[0] for x in o]
                if not valid:
                    st = "unresolved_setup_or_controls"
                elif kinds == ["compile_fail"] * 2:
                    st = "compile_command_failed_twice"
                elif kinds == ["fail"] * 2:
                    st = "controlled_test_failure"
                elif kinds == ["pass"] * 2:
                    st = "admissible_all_tests_pass"
                elif "timeout" in kinds:
                    st = "unresolved_timeout"
                elif "compile_fail" in kinds:
                    st = "unresolved_placement_or_repetition"
                elif set(kinds) == {"pass", "fail"}:
                    st = "unresolved_test_disagreement"
                else:
                    st = "unresolved_harness_output"
                row = {"candidate_id": meta["candidate_id"], "bug_id": bug_dir.name, "tier": tier, "status": st}
                if st == "controlled_test_failure":
                    failed = o[0][1] | o[1][1]
                    row["trigger_failure"] = bool(failed & trigger)
                    row["failed_tests"] = sorted(failed)
                result[meta["candidate_id"]] = row
        placement = json.loads((pkg / "placement.json").read_text())
        for cid, p in placement.items():
            if p != "placed":
                result.setdefault(cid, {"candidate_id": cid, "tier": tier, "status": "unresolved_placement"})
    return result


def main():
    cand = {r["candidate_id"]: r for r in rows(SRC / "candidate_contract.jsonl")}
    decisions = list(rows(SRC / "decisions.jsonl"))
    base = {k: {"correct": 1, "incorrect": 0, "unknown": None}[r["evidence"]["label"]] for k, r in cand.items()}
    legacy = defaultdict(list)
    for path in LEGACY:
        for row in rows(path):
            legacy[project_candidate(row).candidate_id].append(row)
    equiv = {json.loads(l)["candidate_id"]: json.loads(l)["equivalent"] for l in open(OUT / "equivalence.jsonl", encoding="utf-8")}
    st = statuses()
    with open(OUT / "e3_statuses.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for k in sorted(st):
            f.write(json.dumps(st[k]) + "\n")
    tier_a = [json.loads(l) for l in open(OUT / "e3_targets.jsonl", encoding="utf-8")]
    unknown = [k for k, v in base.items() if v is None]

    def single(k):
        labels = {r["label"] for r in legacy[k]}
        return {"correct": 1, "incorrect": 0}.get(next(iter(labels))) if len(labels) == 1 else None

    def archived_test_failure(k):
        return any("false" in (r.get("test_values") or {}) or "false" in (r.get("compile_values") or {}) for r in legacy[k])

    neg = lambda k: st.get(k, {}).get("status") in ("controlled_test_failure", "compile_command_failed_twice")
    passes = lambda k: st.get(k, {}).get("status") == "admissible_all_tests_pass"
    reviewed_correct = lambda k: {r["label"] for r in legacy[k]} == {"correct"}
    conflicts = sorted(k for k in unknown if equiv.get(k) and neg(k))

    def view(rule):
        ev = dict(base)
        if rule == "A1":  # exactly as review_humaneval_contract_replication.legacy_label_sensitivity (all records)
            return {k: single(k) for k in cand}
        for k in unknown:
            if rule == "A2":
                ev[k] = 0 if archived_test_failure(k) else single(k)
            elif rule == "X1":
                ev[k] = 0 if neg(k) else None
            elif rule == "X2":
                ev[k] = 1 if equiv.get(k) else None
            elif rule == "X4-posthoc":  # added after tier A: rules 1-2 only, i.e. no archived review label is trusted
                ev[k] = None if k in conflicts else 1 if equiv.get(k) else 0 if neg(k) else None
            elif rule in ("HE-E1", "X3"):
                if k in conflicts:
                    ev[k] = None
                elif equiv.get(k):
                    ev[k] = 1
                elif neg(k):
                    ev[k] = 0
                elif passes(k) and (reviewed_correct(k) or rule == "X3"):
                    ev[k] = 1
                else:
                    ev[k] = None
        return ev

    # X4-posthoc is not in the addendum: added after tier A because F5 questioned archived "correct" review labels
    rules = ["A0", "A1", "A2", "X1", "X2", "HE-E1", "X3", "X4-posthoc"]
    views = {r: (dict(base) if r == "A0" else view(r)) for r in rules}
    table = {}
    for r in rules:
        table[r] = {}
        for m in METHODS:
            if m == "challenger":
                continue
            b = paired_bounds(decisions, views[r], "challenger", m)
            lo, hi = (100 * float(x) for x in b["equal_bug_bounds"])
            clo, chi = (100 * float(x) for x in b["context_bounds"])
            table[r][m] = {"equal_bug_pp": [round(lo, 2), round(hi, 2)], "width_pp": round(hi - lo, 2),
                           "context_pp": [round(clo, 2), round(chi, 2)],
                           "result": "identified +" if lo > 0 else "identified -" if hi < 0 else "open"}
    # primary: remaining relevant unknowns, challenger vs native under HE-E1
    ev = views["HE-E1"]
    remaining = []
    for d in decisions:
        pol = distributions(d)
        for k in set(pol["challenger"]) | set(pol["native_position"]):
            if pol["challenger"].get(k, 0) != pol["native_position"].get(k, 0) and ev[k] is None:
                remaining.append({"candidate_id": k, "bug_id": d["bug_id"], "status": st.get(k, {}).get("status", "not_run"),
                                  "legacy_labels": sorted({r["label"] for r in legacy[k]})})
    ta = [t["candidate_id"] for t in tier_a]
    res = {
        "tier_A_run": sum(1 for k in ta if k in st), "tier_A_total": len(ta),
        "tier_B_run": sum(1 for v in st.values() if v["tier"] == "B"), "tier_B_total": sum(1 for _ in open(OUT / "e3_tierB.jsonl")),
        "tier_A_status_by_reason": {reason: dict(Counter(st.get(t["candidate_id"], {}).get("status", "not_run")
                                                         for t in tier_a if t["reason"] == reason))
                                    for reason in sorted({t["reason"] for t in tier_a})},
        "tier_A_trigger_failures": sum(1 for k in ta if st.get(k, {}).get("trigger_failure")),
        "tier_A_equivalent": sum(1 for k in ta if equiv.get(k)),
        "equivalent_but_failing": conflicts,
        "reviewed_correct_but_failing_tier_A": sum(1 for k in ta if neg(k) and reviewed_correct(k)),
        "reviewed_correct_and_passing_tier_A": sum(1 for k in ta if passes(k) and reviewed_correct(k)),
        "resolved_unknowns_by_rule": {r: sum(1 for k in unknown if views[r][k] is not None) for r in rules if r not in ("A0", "A1")},
        "comparisons": table,
        "primary_remaining_relevant_unknowns": len(remaining),
        "primary_remaining_by_status": dict(Counter(x["status"] for x in remaining)),
        "remaining": remaining,
    }
    (OUT / "e3_results.json").write_text(json.dumps(res, indent=1))
    lines = ["# E3: HumanEval-Java re-execution", "",
             f"Tier A executed: {res['tier_A_run']}/{res['tier_A_total']}; tier B executed: {res['tier_B_run']}/{res['tier_B_total']}.", "",
             "Challenger minus method, equal-bug bounds (points), by evidence rule:", "",
             "| Rule | " + " | ".join(m for m in METHODS if m != "challenger") + " |",
             "|---|" + "---|" * (len(METHODS) - 1)]
    for r in rules:
        lines.append(f"| {r} | " + " | ".join(f"[{table[r][m]['equal_bug_pp'][0]:+.2f}, {table[r][m]['equal_bug_pp'][1]:+.2f}]"
                                              for m in METHODS if m != "challenger") + " |")
    lines += ["", f"Primary (challenger vs native, HE-E1): {table['HE-E1']['native_position']['equal_bug_pp']} "
              f"({table['HE-E1']['native_position']['result']}); {len(remaining)} relevant unknowns remain "
              f"{dict(Counter(x['status'] for x in remaining))}.",
              f"Equivalent to the fix but failing (kept unknown): {len(conflicts)}."]
    (OUT / "E3_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(json.dumps({k: res[k] for k in ("tier_A_status_by_reason", "tier_A_trigger_failures", "tier_A_equivalent",
                                         "reviewed_correct_but_failing_tier_A", "reviewed_correct_and_passing_tier_A",
                                         "resolved_unknowns_by_rule", "primary_remaining_by_status")}, indent=1))


if __name__ == "__main__":
    main()
