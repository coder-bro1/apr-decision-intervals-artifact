"""D2 (ADDENDUM_V4_D2_DECISION_POINT_2.md): comparisons at decision point 2 (plausible-only eligibility)."""
import sys as _sys  # release layout: shared helper modules live in lib/
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / "lib").is_dir()) / "lib"))
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_evidence_pilot_step2 as S  # noqa: E402
import v4core as V  # noqa: E402
import baselines as B  # noqa: E402
import topk as T  # noqa: E402

LEDGER = ROOT / "results/v2/prevarank_llm_mixed_evaluation_ledger.jsonl"
APPT = ROOT / "results/v4/content_scores/appt.jsonl"
GATE = ROOT / "results/v4/content_scores/appt.gate.json"


def register_dp2(data):
    V.POLICIES["correctness_stage"] = lambda d, kl: max(d.occ[m].correct_p for m in kl.members)
    legacy = {}
    for r in V.jsonl(V.INPUTS["evaluation_evidence"]):
        for lk in r["legacy_candidate_ids"]:
            legacy[lk] = r["candidate_id"]
    size = defaultdict(int)
    rows = list(V.jsonl(LEDGER))
    for r in rows:
        size[r["pool_id"]] += 1
    pv = {}
    for r in rows:
        ob = legacy.get(r["candidate_id"])
        if ob:
            s = -(r["prevarank_rank"] - 1) / size[r["pool_id"]]
            pv[ob] = max(pv.get(ob, -2.0), s)
    V.POLICIES["prevarank"] = lambda d, kl: max(pv.get(m, -2.0) for m in kl.members)
    appt_ok = GATE.exists() and APPT.exists() and json.loads(GATE.read_text())["auc_correct_vs_1_minus_p_overfit"] >= 0.6
    if appt_ok:
        sc = {r["candidate_id"]: r["score"] for r in V.jsonl(APPT)}
        V.POLICIES["appt"] = lambda d, kl: max(sc[m] for m in kl.members)
    return pv, appt_ok


def main():
    data = V.load()
    B.register(data)
    pv, appt_ok = register_dp2(data)
    _, _, _, training, _ = S.load_inputs()
    plaus = {r["candidate_id"]: r["compile"] == 1 and r["test_given_compile"] == 1 for r in training}
    elig = lambda d, kl: any(plaus[m] for m in kl.members)
    pools = V.build_pools(data, "bug", "ast")
    plaus_classes = [kl for _, cl in pools.values() for kl in cl if elig(data, kl)]
    unranked = sum(1 for kl in plaus_classes if all(m not in pv for m in kl.members))
    others = ["mra", "occurrence", "codet5_similarity", "naturalness", "entropy_delta", "prevarank", "appt", "uniform"]
    pairs = [(a, b) for a in ("challenger", "correctness_stage") for b in ["correctness_stage"] + others if a != b]
    pairs += [("prevarank", "mra"), ("prevarank", "occurrence"), ("appt", "mra"), ("appt", "occurrence")]
    rows = []
    for ev_name in ("E0", "E1"):
        ev = data.evidence(ev_name)
        for a, b in pairs:
            if a not in V.POLICIES or b not in V.POLICIES:
                continue
            saved = dict(V.POLICY_ELIG)
            for p in (a, b):
                V.POLICY_ELIG[p] = elig
            units, _ = V.evaluate_pair(data, pools, ev, a, b)
            tk = T.run(data, pools, ev, a, b)
            V.POLICY_ELIG.clear()
            V.POLICY_ELIG.update(saved)
            agg = V.aggregate(units, "bug", len(data.bugs))
            rows.append({"evidence": ev_name, "a": a, "b": b, "lo_pp": V.pp(agg["lo"]), "hi_pp": V.pp(agg["hi"]),
                         "identified": agg["lo"] > 0 or agg["hi"] < 0, "relevant_unknown_classes": V.relevant_unknowns(units),
                         "topk_pp": tk})
            print(ev_name, a, b, [rows[-1]["lo_pp"], rows[-1]["hi_pp"]], "s3", tk["s3"], "rel", rows[-1]["relevant_unknown_classes"], flush=True)
    out = V.RES / "v4" / "dp2"
    out.mkdir(parents=True, exist_ok=True)
    (out / "d2_results.json").write_text(json.dumps({"protocol_sha256": data.input_hashes["protocol"],
                                                     "plausible_classes": len(plaus_classes),
                                                     "plausible_classes_unranked_by_prevarank": unranked,
                                                     "appt_included": appt_ok, "rows": rows}, indent=1))


if __name__ == "__main__":
    main()
