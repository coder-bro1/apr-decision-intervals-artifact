"""Target-aware pre-flight check (V8 submission review, finding V8-01; post hoc, read-only).

refutation_limit.py reports, for each refuting campaign, what evidence of that *type* could decide (a ceiling). This
script adds what each campaign could decide with the classes it actually *targeted*, and sorts every comparison that
was open when the campaign started into one outcome:

  decided                  the campaign decided it
  type cannot decide       even the optimistic ceiling of the evidence type cannot decide it (A0 = 0, or the helpful
                           classes are conflict-locked)
  type could, targets not  the evidence type could decide it, but no admissible set of refutations inside the
                           campaign's target list could
  targets could, too few   refutations inside the target list could decide it, but too few of the helpful targeted
  failed                   classes were refuted

Ceilings (same semantics as refutation_limit.py): 'candidate' = re-execution adds a 0 to one candidate and a
conflict-locked class stays unknown; 'execution' = candidate, and a class whose members all passed the archived tests
is outside reach; 'class' = the frozen F3 rule, which may set a whole class (also a conflict class) to 0.
Target-aware reach = the campaign's own update rule restricted to classes holding at least one targeted candidate.

Campaign target lists: census = data.census (re-executed candidates); top-up = f2_topup_package_v1 jobs; generated
tests = f3_tier1_package_v1 jobs; fresh campaign = G1 tier P (primary) and tier S (secondaries) jobs. Only the
G-E0 -> G-E1 step of the fresh campaign is reported (the optional G-E2 stage was not completed).
Writes only results/v4/target_aware_preflight_v1/. Java is never called (cached tool outputs only).
"""
from __future__ import annotations

import json
import sys
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
import refutation_limit as RL  # noqa: E402

OUT = ROOT / "results/v4/target_aware_preflight_v1"


def limit_in(rows, mode, targets):
    """refutation_limit.limit (refute polarity) with the refutable set restricted to classes in `targets`
    (None = no restriction, i.e. RL.limit itself). Same arithmetic as RL.limit; the restricted version omits only
    RL.limit's closing assertion that class-mode reach is the point A0, which holds only without a restriction."""
    if targets is None:
        return RL.limit(rows, "refute", mode)
    L, H, A0, _ = RL.bounds(rows)
    mv = [r for r in rows if RL.movable(r, mode) and r["key"] in targets]
    up = [-r["d"] for r in mv if r["d"] < 0]
    down = [r["d"] for r in mv if r["d"] > 0]
    L_best, H_best = L + sum(up, Fraction(0)), H - sum(down, Fraction(0))
    if L > 0 or H < 0:
        return {"status": "decided", "k_min": 0, "helpful_classes": 0, "direction": "+" if L > 0 else "-"}
    if L_best > 0:
        return {"status": "reachable +", "k_min": RL._greedy(up, -L), "helpful_classes": len(up), "direction": "+"}
    if H_best < 0:
        return {"status": "reachable -", "k_min": RL._greedy(down, H), "helpful_classes": len(down), "direction": "-"}
    why = "anchor = 0" if A0 == 0 else "targets leave 0 inside"
    return {"status": f"not reachable ({why})", "k_min": None, "helpful_classes": 0, "direction": None}


def helpful(rows, mode, direction, targets=None):
    return [r for r in RL.helpful_classes(rows, mode, direction) if targets is None or r["key"] in targets]


def assess(rows_start, rows_end, mode, ceilings, targets, n):
    """One comparison, one campaign."""
    res_t = limit_in(rows_start, mode, targets)
    ceil = {m: limit_in(rows_start, m, None) for m in ceilings}
    L, H, A0, _ = RL.bounds(rows_start)
    Le, He, A0e, _ = RL.bounds(rows_end)
    decided = Le > 0 or He < 0
    opt = ceil[ceilings[0]]
    direction = opt["direction"] or ("+" if A0 > 0 else "-" if A0 < 0 else None)
    help_all = helpful(rows_start, mode, direction) if direction else []
    help_tgt = [r for r in help_all if r["key"] in targets]
    end_y = {r["key"]: r["y"] for r in rows_end}
    refuted = [r for r in help_tgt if end_y.get(r["key"]) == 0]
    if decided:
        outcome = "decided"
    elif not opt["status"].startswith("reachable"):
        outcome = "type cannot decide"
    elif not res_t["status"].startswith("reachable"):
        outcome = "type could, targets not"
    else:
        outcome = "targets could, too few failed"
    return {"A0": RL.ppf(A0, n), "interval_start": [RL.ppf(L, n), RL.ppf(H, n)],
            "interval_end": [RL.ppf(Le, n), RL.ppf(He, n)], "A0_end": RL.ppf(A0e, n),
            "ceilings": {m: {"status": c["status"], "k_min": c["k_min"], "helpful_classes": c["helpful_classes"]}
                         for m, c in ceil.items()},
            "targeted": {"status": res_t["status"], "k_min": res_t["k_min"],
                         "helpful_classes_targeted": len(help_tgt), "helpful_classes_under_rule": len(help_all),
                         "helpful_targeted_refuted": len(refuted)},
            "decided_at_end": decided, "outcome": outcome}


def capture(fn):
    """Run a refutation_limit driver and record every rows_for call (args and result) in order."""
    calls, orig = [], RL.rows_for

    def rec(data, pools, ev, a, b, tp=None):
        out = orig(data, pools, ev, a, b, tp)
        calls.append({"data": data, "pools": pools, "a": a, "b": b, "rows": out[1]})
        return out
    RL.rows_for = rec
    try:
        res = fn()
    finally:
        RL.rows_for = orig
    return res, calls


def klass_map(pools):
    return {m: (bug, i) for _, (bug, classes) in pools.items() for i, kl in enumerate(classes) for m in kl.members}


def job_targets(package, run, klass_of):
    jobs = RL.job_hours(package, run)
    cands = {c for _, cs, _ in jobs.values() for c in cs}
    return {klass_of[c] for c in cands if c in klass_of}, len(cands), round(sum(h for *_, h in jobs.values()), 3)


def d4j():
    res, calls = capture(RL.d4j)
    steps = ["E0", "E1", "F2", "F3", "F4", "R"]
    comps = res["comparisons"]
    assert len(calls) == len(comps) * len(steps)
    rows = {(c["b"], steps[i % len(steps)]): c["rows"] for i, c in enumerate(calls)}
    data, pools = calls[0]["data"], calls[0]["pools"]
    n = res["n_bugs"]
    kof = klass_map(pools)
    census_t = {kof[c] for c in data.census if c in kof}
    f2_t, f2_c, f2_h = job_targets(ROOT / "results/v4/f2_topup_package_v1", ROOT / "results/v4/f2_topup_run_v1", kof)
    f3_t, f3_c, f3_h = job_targets(ROOT / "results/v4/f3_tier1_package_v1", ROOT / "results/v4/f3_tier1_run_v1", kof)
    campaigns = [
        ("Census", "E0", "E1", "candidate", ["candidate", "execution"], census_t, len(data.census), RL.CENSUS_HOURS),
        ("Top-up", "E1", "F2", "candidate", ["candidate", "execution"], f2_t, f2_c, f2_h),
        ("Generated tests", "F2", "F3", "class", ["class", "candidate"], f3_t, f3_c, f3_h),
    ]
    out = {}
    for name, s, e, mode, ceilings, tg, ncand, hours in campaigns:
        open_b = [b for b in comps if res["results"][b][s]["result"] == "open"]
        out[name] = {"start": s, "end": e, "update_rule": mode, "ceilings": ceilings,
                     "targeted_candidates": ncand, "targeted_classes": len(tg), "hours": hours,
                     "comparisons": {b: assess(rows[(b, s)], rows[(b, e)], mode, ceilings, tg, n) for b in open_b}}
        # strict variant for generated tests: conflict classes stay locked
        if name == "Generated tests":
            out[name]["strict_variant_candidate_rule"] = {
                b: assess(rows[(b, s)], rows[(b, e)], "candidate", ["candidate"], tg, n)["targeted"] for b in open_b}
    return {"n_bugs": n, "campaigns": out}


def g1():
    res, calls = capture(RL.g1)
    n = res["n_bugs"]
    p1 = res["P1"]
    data, pools = calls[0]["data"], calls[0]["pools"]
    kof = klass_map(pools)
    import g1_pools as G
    tp_t, tp_c, tp_h = job_targets(G.G1 / "exec_tierP_package_v1", G.G1 / "exec_tierP_run_v1", kof)
    ts_t, ts_c, ts_h = job_targets(G.G1 / "exec_tierS_package_v1", G.G1 / "exec_tierS_run_v1", kof)
    rows = {}
    for c in calls:
        name = f"{c['a']} vs {c['b']}"
        rows.setdefault(name, []).append(c["rows"])
    out = {}
    tg = tp_t | ts_t  # G-E1 is the evidence of both tiers, so every comparison is judged on both target lists
    for name, rs in rows.items():
        out[name] = assess(rs[0], rs[1], "candidate", ["candidate"], tg, n)  # G-E0 -> G-E1 only
    return {"n_bugs": n, "primary": p1,
            "tier_P": {"targeted_candidates": tp_c, "targeted_classes": len(tp_t), "hours": tp_h},
            "tier_S": {"targeted_candidates": ts_c, "targeted_classes": len(ts_t), "hours": ts_h},
            "comparisons": out}


def md(r):
    L = ["# Target-aware pre-flight check (post hoc, read-only)", "",
         "Outcome per comparison open at the start of each refuting campaign. 'ceil' = reach of the evidence type "
         "(first listed rule is the optimistic one); 'targeted' = reach restricted to the campaign's target classes "
         "under its own update rule; k = minimum refutations; helpful = targeted / all helpful classes under the "
         "rule; refuted = helpful targeted classes that ended refuted.", ""]
    for name, c in r["defects4j"]["campaigns"].items():
        L += [f"## Defects4J: {name} ({c['start']} -> {c['end']}; rule {c['update_rule']}; "
              f"{c['targeted_candidates']} candidates in {c['targeted_classes']} classes; {c['hours']} h)", "",
              "| Comparison | A0 | " + " | ".join(f"ceil {m}" for m in c["ceilings"]) +
              " | targeted (k) | helpful | refuted | outcome |",
              "|---|---|" + "---|" * len(c["ceilings"]) + "---|---|---|---|"]
        for b, a in c["comparisons"].items():
            t = a["targeted"]
            ce = " | ".join(f"{a['ceilings'][m]['status']} ({a['ceilings'][m]['k_min']})" for m in c["ceilings"])
            L.append(f"| {b} | {a['A0']:+.2f} | {ce} | {t['status']} ({t['k_min']}) | "
                     f"{t['helpful_classes_targeted']}/{t['helpful_classes_under_rule']} | "
                     f"{t['helpful_targeted_refuted']} | {a['outcome']} |")
        if "strict_variant_candidate_rule" in c:
            L += ["", "Strict variant (conflict classes locked): " + "; ".join(
                f"{b}: {t['status']} ({t['k_min']})" for b, t in c["strict_variant_candidate_rule"].items())]
        L.append("")
    g = r["g1"]
    L += [f"## Fresh campaign G-E0 -> G-E1 (tier P {g['tier_P']}; tier S {g['tier_S']})", "",
          "| Comparison | A0 | ceil candidate (k) | targeted (k) | helpful | refuted | outcome |",
          "|---|---|---|---|---|---|---|"]
    for b, a in g["comparisons"].items():
        t, ce = a["targeted"], a["ceilings"]["candidate"]
        L.append(f"| {b} | {a['A0']:+.2f} | {ce['status']} ({ce['k_min']}) | {t['status']} ({t['k_min']}) | "
                 f"{t['helpful_classes_targeted']}/{t['helpful_classes_under_rule']} | "
                 f"{t['helpful_targeted_refuted']} | {a['outcome']} |")
    return "\n".join(L) + "\n"


def main():
    RL.read_only_guards()
    r = {"status": "post hoc, read-only; V8 review finding V8-01", "defects4j": d4j(), "g1": g1()}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "target_aware_preflight.json").write_text(json.dumps(r, indent=1, default=str), encoding="utf-8")
    (OUT / "TARGET_AWARE_PREFLIGHT.md").write_text(md(r), encoding="utf-8")
    print(md(r))


if __name__ == "__main__":
    main()
