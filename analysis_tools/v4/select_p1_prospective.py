"""P1 prospective campaign (ADDENDUM_V4_P1_PROSPECTIVE.md): selection and frozen predictions. Reads no new outcome.

Start state: the final Defects4J evidence (E1+F2+F3+F4+R) at the second decision point (plausible-only eligibility,
as in d2.py). For every comparison still open, the target-aware pre-flight check and the pilot-yield planner predict
whether generated tests on the untested helpful classes can decide it. Targets: one representative (lowest candidate
id among archived test-passing members) of every helpful class of an open comparison with A0 != 0 that the earlier
generated-test campaign (F3 tier 1) did not test. The yield prior is F3's realised yield per targeted class.
Writes results/v4/p1_prospective/{candidates.json, predictions.json, PREDICTIONS.md}.
"""
import json
import random
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

OUT = ROOT / "results/v4/p1_prospective"
YIELD = 0.142   # F3 tier 1: refuted share of targeted relevant classes (results/v4/r1_review_v1, A5)
SEED = 20261002
DRAWS = 20000


def pairs():
    others = ["mra", "occurrence", "codet5_similarity", "naturalness", "entropy_delta", "prevarank", "appt", "uniform"]
    ps = [(a, b) for a in ("challenger", "correctness_stage") for b in ["correctness_stage"] + others if a != b]
    return ps + [("prevarank", "mra"), ("prevarank", "occurrence"), ("appt", "mra"), ("appt", "occurrence")]


def main():
    RL.read_only_guards()
    data, pools, evs, basis, comps = R.build_d4j()
    B.register(data)
    D2.register_dp2(data)
    _, _, _, training, _ = S.load_inputs()
    tpass = {r["candidate_id"]: r["compile"] == 1 and r["test_given_compile"] == 1 for r in training}
    elig = lambda d, kl: any(tpass[m] for m in kl.members)
    kof = TA.klass_map(pools)
    f3_t, _, _ = TA.job_targets(ROOT / "results/v4/f3_tier1_package_v1", ROOT / "results/v4/f3_tier1_run_v1", kof)
    classes_of = {b: cl for b, (_, cl) in pools.items()}
    n = len(data.bugs)
    rng = random.Random(SEED)
    preds, targets = [], {}
    for a, b in pairs():
        if a not in V.POLICIES or b not in V.POLICIES:
            continue
        saved = dict(V.POLICY_ELIG)
        V.POLICY_ELIG[a] = elig
        V.POLICY_ELIG[b] = elig
        _, rows = RL.rows_for(data, pools, evs["R"], a, b)
        V.POLICY_ELIG.clear()
        V.POLICY_ELIG.update(saved)
        L, H, A0, _ = RL.bounds(rows)
        rec = {"comparison": f"{a} vs {b}", "start_interval_pp": [RL.ppf(L, n), RL.ppf(H, n)], "A0_pp": RL.ppf(A0, n)}
        if L > 0 or H < 0:
            rec["start"] = "decided"
            preds.append(rec)
            continue
        rec["start"] = "open"
        if A0 == 0:
            rec.update({"prediction": "cannot be decided by refutation (A0 = 0)", "p_decide": 0.0, "targets": 0})
            preds.append(rec)
            continue
        plus = A0 > 0
        need = (-L) if plus else H
        helpful = [r for r in rows if r["y"] is None and ((r["d"] < 0) if plus else (r["d"] > 0)) and r["key"] not in f3_t]
        gains = sorted((abs(r["d"]) for r in helpful), reverse=True)
        acc, k = 0, None
        for i, g in enumerate(gains, 1):
            acc += g
            if acc > need:
                k = i
                break
        gf = [float(g) for g in gains]
        hits = sum(sum(g for g in gf if rng.random() < YIELD) > float(need) for _ in range(DRAWS))
        p = hits / DRAWS
        rec.update({"direction": "+" if plus else "-", "need_pp": RL.ppf(need, n), "helpful_untested_classes": len(helpful),
                    "k_min": k, "p_decide": round(p, 4), "targets": len(helpful),
                    "prediction": ("decided" if p >= 0.5 else "open") if k else "cannot be decided with these targets"})
        preds.append(rec)
        for r in helpful:
            kl = classes_of[r["key"][0]][r["key"][1]]
            passing = [m for m in kl.members if tpass[m]]
            targets[r["key"]] = min(passing or kl.members)
    OUT.mkdir(parents=True, exist_ok=True)
    cands = sorted(set(targets.values()))
    (OUT / "candidates.json").write_text(json.dumps([{"candidate_id": m, "compile_only": False} for m in cands], indent=1),
                                         encoding="utf-8")
    res = {"start_state": "final Defects4J evidence (E1+F2+F3+F4+R), decision point 2", "yield_prior": YIELD,
           "seed": SEED, "draws": DRAWS, "target_classes": len(targets), "target_candidates": len(cands),
           "target_bugs": len({data.occ[m].bug for m in cands}),
           "decided_at_start": sum(p["start"] == "decided" for p in preds), "comparisons": preds}
    (OUT / "predictions.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    md = ["# P1 prospective campaign: frozen predictions", "",
          f"Start: {res['start_state']}. Decided at start: {res['decided_at_start']} of {len(preds)}.",
          f"Targets: {len(targets)} untested helpful classes ({len(cands)} candidates, {res['target_bugs']} bugs). "
          f"Yield prior {YIELD} per targeted class.", "",
          "| Comparison | Start interval (pp) | A0 | Need (pp) | Helpful untested | Min. refutations | P(decide) | Prediction |",
          "|---|---|---|---|---|---|---|---|"]
    for p in preds:
        if p["start"] == "decided":
            continue
        md.append(f"| {p['comparison']} | [{p['start_interval_pp'][0]:+.2f}, {p['start_interval_pp'][1]:+.2f}] | "
                  f"{p['A0_pp']:+.2f} | {p.get('need_pp', '-')} | {p.get('helpful_untested_classes', '-')} | "
                  f"{p.get('k_min', '-')} | {p['p_decide']} | {p['prediction']} |")
    (OUT / "PREDICTIONS.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
