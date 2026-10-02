"""G1 final analysis (PROTOCOL_G1_FRESH_CAMPAIGN.md s.6-7): execution evidence -> G-E1 labels -> pre-registered bounds.

G-E0: reference matches (correct) + N-a no-op rule, nothing executed (from g1_pools.py).
G-E1: + census results of the executed representatives (tier P; tier S jobs finished so far are included and counted):
  controlled_trigger_failure                  -> class incorrect;
  compile_command_failed_twice                -> class incorrect (primary) / unknown (sensitivity 'compile_unknown');
  anything else                               -> unknown.
Label on the representative; class labels follow the frozen known-wins rule (a class with contradicting evidence
becomes unknown and is counted). Reports every comparison, top-k for P1 and S1, break-down counts for P1, executions
and container hours used. Writes results/g1/g1_final.json.
"""
import glob
import json
import sys
from collections import Counter
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import v4core as V  # noqa: E402
import topk as T  # noqa: E402
import g1_pools as G  # noqa: E402
import breakdown as BD  # noqa: E402

CTF, CF = "controlled_trigger_failure", "compile_command_failed_twice"


def findings(tier):
    out, secs, jobs = {}, 0.0, 0
    for t in glob.glob(str(ROOT / f"results/g1/exec_tier{tier}_run_v1/*/terminal.json")):
        d = json.loads(Path(t).read_text())
        jobs += 1
        secs += d.get("seconds", 0)
        for f in d["findings"]:
            out[f["candidate_id"]] = f["evidence_status"]
    return out, secs, jobs


def evaluate(data, pools, ev, comps):
    rows = []
    for a, b in comps:
        units, stats = V.evaluate_pair(data, pools, ev, a, b)
        agg = V.aggregate(units, "bug", len(data.bugs))
        row = {"a": a, "b": b, "bounds_pp": [V.pp(agg["lo"]), V.pp(agg["hi"])],
               "result": "identified +" if agg["lo"] > 0 else "identified -" if agg["hi"] < 0 else "open",
               "relevant_unknown_classes": V.relevant_unknowns(units), **stats}
        if (a, b) in (G.P1, ("occurrence", "uniform")):
            row["topk_pp"] = T.run(data, pools, ev, a, b)
        rows.append(row)
    return rows


def breakdown_p1(data, pools, ev):
    units, _ = V.evaluate_pair(data, pools, ev, *G.P1)
    n = len(data.bugs)
    L = sum(u.lo for u in units)
    H = sum(u.hi for u in units)
    flips = sorted(d * (1 - 2 * y) for u in units for d, y, _ in u.coeffs if y is not None)
    need_target = L if L > 0 else -H if H < 0 else None
    if need_target is None:
        return {"note": "P1 open; no break-down"}
    if L > 0:
        k, _ = BD.minimal_count([f for f in flips if f < 0], L)
    else:
        k, _ = BD.minimal_count([-f for f in flips if f > 0], -H)
    return {"min_label_flips_to_open": k, "L_pp": V.pp(L / n), "H_pp": V.pp(H / n)}


def main():
    rows = G.load_generations()
    data, _ = G.build(rows)
    G.register(data)
    pools = V.build_pools(data, "bug", "ast")
    comps = [G.P1] + [c for c in G.SECONDARY if c[0] in V.POLICIES and c[1] in V.POLICIES]
    fp, sp, jp = findings("P")
    fs, ss, js = findings("S")
    status = {**fs, **fp}
    e1 = dict(data.e0)
    e1c = dict(data.e0)
    for k, st in status.items():
        if k not in e1:
            continue
        if st == CTF:
            e1[k] = e1c[k] = 0 if e1[k] is None else e1[k]
        elif st == CF:
            e1[k] = 0 if e1[k] is None else e1[k]
    conflicts = sum(1 for _, cl in pools.values() for kl in cl if V.class_label(kl.members, e1, "known_wins")[1])
    res = {"bugs": len(data.bugs), "candidates": len(data.occ),
           "executed": {"tier_P_representatives": len(fp), "tier_P_jobs": jp, "tier_P_container_hours": round(sp / 3600, 1),
                        "tier_S_representatives_so_far": len(fs), "tier_S_jobs_so_far": js,
                        "tier_S_container_hours_so_far": round(ss / 3600, 1)},
           "execution_statuses": dict(Counter(status.values())),
           "class_label_conflicts_G-E1": conflicts,
           "G-E0": evaluate(data, pools, data.e0, comps),
           "G-E1": evaluate(data, pools, e1, comps),
           "G-E1_compile_unknown": evaluate(data, pools, e1c, [G.P1]),
           "P1_breakdown_G-E1": breakdown_p1(data, pools, e1)}
    (ROOT / "results/g1/g1_final.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps({k: res[k] for k in ("executed", "execution_statuses", "class_label_conflicts_G-E1", "P1_breakdown_G-E1")}, indent=1))
    for view in ("G-E0", "G-E1", "G-E1_compile_unknown"):
        for r in res[view]:
            print(f"{view:22s} {r['a']:18s} vs {r['b']:12s} {r['bounds_pp']}  {r['result']:12s} relevant unknowns {r['relevant_unknown_classes']}")


if __name__ == "__main__":
    main()
