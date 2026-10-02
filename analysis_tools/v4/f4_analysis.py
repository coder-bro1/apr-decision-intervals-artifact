"""F4 analysis: what the two-annotator review of decision-relevant test-passing unknown classes changes.
Evidence views:
  E2      = E1 + F2 witnesses (as in f2_analysis.py);
  E2+F4   = E2 + every F4 class verdict (both annotators agree, non-unsure: the frozen resolution rule);
  E2+F4c  = E2 + only the F4 'correct' verdicts. The packet's rubric is stricter than the archived labels (it marks
            valid-but-different fixes and exception-message differences incorrect), so a strict 'correct' implies
            archived-style correct but a strict 'incorrect' does not; this view keeps strict 'incorrect' unknown.
Also cross-checks F4 verdicts against F3 generated-test counterexamples (before the F3 relevance review).
Writes results/v4/annotation_results/f4_analysis.json."""
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import v4core as V  # noqa: E402
import baselines as B  # noqa: E402
from select_f2_topup import BASELINES  # noqa: E402

RES = ROOT / "results/v4/annotation_results"


def main():
    status = {}
    for t in glob.glob(str(ROOT / "results/v4/f2_topup_run_v1/*/terminal.json")):
        for f in json.loads(Path(t).read_text())["findings"]:
            status[f["candidate_id"]] = f["evidence_status"]
    f4 = json.loads((RES / "f4_resolved_labels.json").read_text())
    data = V.load()
    B.register(data)
    pools = V.build_pools(data, "bug", "ast")
    e2 = dict(data.evidence("E1"))
    for k, s in status.items():
        if s == "controlled_trigger_failure" and e2[k] is None:
            e2[k] = 0
    views = {"E2": e2, "E2+F4": dict(e2), "E2+F4c": dict(e2)}
    already, overridden = [], []
    for rep, row in f4.items():
        val = {"correct": 1, "incorrect": 0}[row["label"]]
        known = {e2[m] for m in row["class_members"] if e2.get(m) is not None}
        if known and known != {0, 1} and known != {val}:
            raise ValueError(f"F4 verdict contradicts a consistent known class label: {rep}")
        # the frozen rule makes the whole class known; a class can only have known members here if their archived
        # labels contradict each other (identical AST, labels 0 and 1), which is why it was unknown
        already += [m for m in row["class_members"] if e2.get(m) is not None]
        if known == {0, 1}:
            overridden.append({"representative": rep, "f4_label": row["label"],
                               "archived_member_labels": [e2.get(m) for m in row["class_members"]]})
        for m in row["class_members"]:
            views["E2+F4"][m] = val
            if val == 1:
                views["E2+F4c"][m] = 1
    rows = []
    for b in BASELINES:
        if b not in V.POLICIES:
            continue
        row = {"a": "challenger", "b": b}
        for name, ev in views.items():
            units, _ = V.evaluate_pair(data, pools, ev, "challenger", b)
            agg = V.aggregate(units, "bug", len(data.bugs))
            lo, hi = V.pp(agg["lo"]), V.pp(agg["hi"])
            row[name] = [lo, hi]
            row[name + "_result"] = "identified +" if lo > 0 else "identified -" if hi < 0 else "open"
            row[name + "_relevant_unknowns"] = V.relevant_unknowns(units)
        rows.append(row)
    # cross-check with F3 counterexamples (pre-relevance-review)
    f3 = {}
    rr = ROOT / "results/v4/f3_difftest/relevance_review.json"
    if rr.exists():
        for item in json.loads(rr.read_text()):
            f3[item["candidate_id"]] = f3.get(item["candidate_id"], 0) + 1
    f3_targets = set()
    for p in glob.glob(str(ROOT / "results/v4/f3_targets/tier1_candidates.json")):
        for r in json.loads(Path(p).read_text()):
            f3_targets.add(r["candidate_id"] if isinstance(r, dict) else r)
    cross = []
    for rep, row in f4.items():
        members = set(row["class_members"])
        hit = sorted(members & set(f3))
        cross.append({"f4_representative": rep, "f4_label": row["label"], "f3_tested": bool(members & f3_targets),
                      "f3_counterexample_candidates": hit, "f3_counterexamples": sum(f3[h] for h in hit)})
    tested = [c for c in cross if c["f3_tested"]]
    res = {"f4_classes": len(f4), "f4_members_already_labelled_in_E2": already,
           "f4_resolves_contradictory_archived_classes": overridden,
           "comparisons": rows,
           "f3_cross_check": {"f4_classes_also_in_f3_tier1": len(tested),
                              "correct_with_counterexample": sum(1 for c in tested if c["f4_label"] == "correct" and c["f3_counterexamples"]),
                              "correct_without": sum(1 for c in tested if c["f4_label"] == "correct" and not c["f3_counterexamples"]),
                              "incorrect_with_counterexample": sum(1 for c in tested if c["f4_label"] == "incorrect" and c["f3_counterexamples"]),
                              "incorrect_without": sum(1 for c in tested if c["f4_label"] == "incorrect" and not c["f3_counterexamples"]),
                              "items": cross}}
    (RES / "f4_analysis.json").write_text(json.dumps(res, indent=1))
    for r in rows:
        print(f"challenger vs {r['b']:20s} E2 {r['E2']} {r['E2_result']:12s} (unk {r['E2_relevant_unknowns']:3d}) | "
              f"+F4 {r['E2+F4']} {r['E2+F4_result']:12s} (unk {r['E2+F4_relevant_unknowns']:3d}) | "
              f"+F4c {r['E2+F4c']} {r['E2+F4c_result']}")
    print(json.dumps({k: v for k, v in res["f3_cross_check"].items() if k != "items"}, indent=1))
    print("F4 members already labelled in E2:", len(already))


if __name__ == "__main__":
    main()
