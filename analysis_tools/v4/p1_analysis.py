"""P1 prospective campaign: score the frozen predictions (ADDENDUM_V4_P1_PROSPECTIVE.md). Read-only except its outputs.

Each witnessed candidate's whole class becomes incorrect (F3 class rule) on top of the start state (final Defects4J
evidence). The 21 decision-point-2 comparisons are recomputed; for each comparison open at the start, the realised
outcome is compared with the frozen prediction, and the Brier score of P(decide) is reported with the realised yield.
Writes results/v4/p1_prospective/{outcomes.json, OUTCOMES.md}.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
import r1_review_checks as R  # noqa: E402
import refutation_limit as RL  # noqa: E402
import target_aware_preflight as TA  # noqa: E402
import v4core as V  # noqa: E402
import baselines as B  # noqa: E402
import d2 as D2  # noqa: E402
import run_evidence_pilot_step2 as S  # noqa: E402
import select_p1_prospective as SP  # noqa: E402

P = ROOT / "results/v4/p1_prospective"


def main():
    RL.read_only_guards()
    preds = {p["comparison"]: p for p in json.loads((P / "predictions.json").read_text())["comparisons"]}
    review = json.loads((P / "difftest/relevance_review.json").read_text())
    if any(i["verdict"] is None for i in review):
        raise SystemExit("relevance review incomplete")
    witnessed = {i["candidate_id"] for i in review if i["verdict"] == "witness"}
    targets = {c["candidate_id"] for c in json.loads((P / "candidates.json").read_text())}
    data, pools, evs, basis, comps = R.build_d4j()
    B.register(data)
    D2.register_dp2(data)
    _, _, _, training, _ = S.load_inputs()
    tpass = {r["candidate_id"]: r["compile"] == 1 and r["test_given_compile"] == 1 for r in training}
    elig = lambda d, kl: any(tpass[m] for m in kl.members)
    kof = TA.klass_map(pools)
    classes_of = {b: cl for b, (_, cl) in pools.items()}
    ev = dict(evs["R"])
    hazard = []
    for m in witnessed:
        bug, i = kof[m]
        for mm in classes_of[bug][i].members:
            if ev[mm] == 1:
                hazard.append(mm)
            ev[mm] = 0
    n = len(data.bugs)
    out, brier, scored = [], 0.0, 0
    for a, b in SP.pairs():
        if a not in V.POLICIES or b not in V.POLICIES:
            continue
        name = f"{a} vs {b}"
        saved = dict(V.POLICY_ELIG)
        V.POLICY_ELIG[a] = elig
        V.POLICY_ELIG[b] = elig
        _, rows = RL.rows_for(data, pools, ev, a, b)
        V.POLICY_ELIG.clear()
        V.POLICY_ELIG.update(saved)
        L, H, A0, _ = RL.bounds(rows)
        decided = L > 0 or H < 0
        p = preds[name]
        rec = {"comparison": name, "start": p["start"], "end_interval_pp": [RL.ppf(L, n), RL.ppf(H, n)],
               "decided_at_end": decided}
        if p["start"] == "open":
            rec.update(prediction=p["prediction"], p_decide=p["p_decide"],
                       correct=(decided == (p["p_decide"] >= 0.5)))
            brier += (p["p_decide"] - (1.0 if decided else 0.0)) ** 2
            scored += 1
        out.append(rec)
    res = {"witnessed_candidates": len(witnessed), "targeted": len(targets),
           "realised_yield": round(len(witnessed & targets) / len(targets), 4),
           "known_correct_members_overwritten": len(hazard), "scored": scored,
           "brier": round(brier / scored, 4) if scored else None,
           "predictions_correct": sum(r.get("correct", False) for r in out if "correct" in r),
           "decided_at_end": sum(r["decided_at_end"] for r in out), "comparisons": out}
    (P / "outcomes.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    md = ["# P1 prospective campaign: outcomes", "",
          f"Witnessed candidates {len(witnessed)} of {len(targets)} targeted (yield {res['realised_yield']}); "
          f"predictions correct {res['predictions_correct']} of {scored}; Brier {res['brier']}; "
          f"decided at end {res['decided_at_end']} of {len(out)}.", "",
          "| Comparison | Prediction | P(decide) | End interval (pp) | Decided | Correct |", "|---|---|---|---|---|---|"]
    for r in out:
        if r["start"] != "open":
            continue
        md.append(f"| {r['comparison']} | {r['prediction']} | {r['p_decide']} | "
                  f"[{r['end_interval_pp'][0]:+.2f}, {r['end_interval_pp'][1]:+.2f}] | {r['decided_at_end']} | {r['correct']} |")
    (P / "OUTCOMES.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
