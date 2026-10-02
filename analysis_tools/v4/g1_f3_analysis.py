"""G1-F3 analysis (ADDENDUM_V4_G1_F3.md): G-E2 = G-E1 + generated-test witnesses (class incorrect), for the
pre-registered primary P1. Counterexamples come from f3_analysis.py (results/g1/f3_difftest/relevance_review.json).
Until every counterexample has a hand verdict, only a PREVIEW is written: P1 if every counterexample were a witness
(largest possible effect) next to G-E1. Writes results/g1/g1_f3_results.json."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import v4core as V  # noqa: E402
import g1_pools as G  # noqa: E402
import g1_analysis as A  # noqa: E402
from select_g1_f3_targets import g_e1  # noqa: E402

RR = ROOT / "results/g1/f3_difftest/relevance_review.json"


def main():
    rows = G.load_generations()
    data, _ = G.build(rows)
    G.register(data)
    pools = V.build_pools(data, "bug", "ast")
    e1, _ = g_e1(data)
    items = json.loads(RR.read_text()) if RR.exists() else []
    reviewed = bool(items) and all(i["verdict"] is not None for i in items)
    witnesses = {i["candidate_id"] for i in items if (i["verdict"] == "witness" if reviewed else True)}
    klass = {m: kl.members for _, (_, cl) in pools.items() for kl in cl for m in kl.members}
    e2 = dict(e1)
    for k in witnesses:
        known = {e2[m] for m in klass[k] if e2[m] is not None}
        if known - {0}:
            raise ValueError("witness contradicts a known correct label: " + k)
        for m in klass[k]:
            e2[m] = 0
    res = {"status": "final (all counterexamples reviewed)" if reviewed else "PREVIEW: every counterexample treated as a witness",
           "counterexamples": len(items), "candidates_with_counterexample": len({i["candidate_id"] for i in items}),
           "witness_classes": len(witnesses),
           "G-E1": A.evaluate(data, pools, e1, [G.P1])[0], "G-E2": A.evaluate(data, pools, e2, [G.P1])[0],
           "P1_breakdown_G-E2": A.breakdown_p1(data, pools, e2)}
    for k in ("G-E1", "G-E2"):
        res[k].pop("topk_pp", None)
    (ROOT / "results/g1/g1_f3_results.json").write_text(json.dumps(res, indent=1, default=str))
    print(res["status"])
    for k in ("G-E1", "G-E2"):
        print(f"{k}: P1 {res[k]['bounds_pp']} {res[k]['result']} (relevant unknowns {res[k]['relevant_unknown_classes']})")
    print("witness classes:", len(witnesses), "breakdown:", res["P1_breakdown_G-E2"])


if __name__ == "__main__":
    main()
