"""C1 fix re-run analysis (ADDENDUM_V4_C1_FIXRERUN.md). A re-executed archived failure whose triggers now pass (both
repetitions, valid controls) loses its archived 'incorrect' label; a controlled trigger failure keeps it (flagged);
anything else keeps it. Then the unchanged C1-fix rule: a class with no known label and a fix-equivalent member ->
correct. View E1+F2+F3+F4+R, all comparisons, AST identity and C1-id. Partial runs are allowed (unrun = unchanged).
Writes results/v4/c1_fixrerun/c1_fixrerun_results.json."""
import glob
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import v4core as V  # noqa: E402
import baselines as B  # noqa: E402
import final_evidence as FE  # noqa: E402
import c1_equivalence as C  # noqa: E402
from select_f2_topup import BASELINES  # noqa: E402
from validation_policy_contract import context_id  # noqa: E402

RUN = ROOT / "results/v4/c1_fixrerun_run_v1"
OUT = ROOT / "results/v4/c1_fixrerun"


def apply_r(ev, passed, fix_eq, c1_pools, c1fix=True):
    """The R layer: a re-executed archived failure that now passes loses its archived 0; then (c1fix) the unchanged
    C1-fix rule sets correct every rename-aware class with a fix-equivalent member and no known label.
    Returns (new evidence dict, list of member lists set correct by C1-fix)."""
    ev = dict(ev)
    for k in passed:
        if ev[k] == 0:
            ev[k] = None
    set_correct = []
    if c1fix:
        for _, (_, classes) in c1_pools.items():
            for kl in classes:
                if any(m in fix_eq for m in kl.members) and all(ev[m] is None for m in kl.members):
                    for m in kl.members:
                        ev[m] = 1
                    set_correct.append(list(kl.members))
    return ev, set_correct


def build():
    """Returns a dict with data, ast_pools, c1_pools, base (E1+F2+F3+F4), R (base + re-run + C1-fix), the R-layer
    ingredients (passed, fix_eq) and run facts."""
    selected = {r["candidate_id"] for r in json.loads((OUT / "candidates.json").read_text())}
    status = {}
    for t in glob.glob(str(RUN / "*/terminal.json")):
        for f in json.loads(Path(t).read_text()).get("findings", []):
            status[f["candidate_id"]] = f["evidence_status"]
    data = V.load()
    B.register(data)
    tid = C.tid
    fixes = defaultdict(set)
    for p in C.LEGACY:
        for line in open(p, encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                fixes[context_id(r["bug_id"], r["anchor"])].add(r["human_fix"])
    pa = C.normalise({tid(o.patch): o.patch for o in data.occ.values()}, "d4j_candidates_norm")
    ft = {tid(f): f for fs in fixes.values() for f in fs}
    fa, ff = C.normalise(ft, "d4j_fixes_norm"), C.fingerprint(ft, "d4j_fixes_fp")

    def keys(o):
        ks = {("ast", o.ast) if o.ast else ("txt", o.patch.strip())}
        if pa[tid(o.patch)]:
            ks.add(("alpha", pa[tid(o.patch)]))
        return ks

    fixkeys = {c: ({("alpha", fa[tid(f)]) for f in fs if fa[tid(f)]} | {("ast", ff[tid(f)]) for f in fs if ff[tid(f)]})
               for c, fs in fixes.items()}
    uf, first = C.UF(), {}
    for cid in sorted(data.occ):
        o = data.occ[cid]
        uf.find(cid)
        for k in keys(o):
            uf.union(first.setdefault((o.bug, k), cid), cid)
    comp = {cid: f"c1:{data.occ[cid].bug}:{uf.find(cid)}" for cid in data.occ}
    fix_eq = {cid for cid, o in data.occ.items() if keys(o) & fixkeys.get(o.ctx, set())}
    ast_pools = V.build_pools(data, "bug", "ast")
    c1_pools = V.build_pools(data, "bug", "c1", key_fn=lambda o: comp[o.cid])
    views, _ = FE.build(data, ast_pools)
    base = views["E1+F2+F3+F4"]
    passed = sorted(k for k in selected if status.get(k) == "admissible_triggers_pass_semantics_unknown")
    reproduced = [k for k in selected if status.get(k) == "controlled_trigger_failure"]
    ev, set_correct = apply_r(base, passed, fix_eq, c1_pools)
    facts = {"selected": len(selected), "with_result": len(set(status) & selected),
             "statuses": dict(sorted(Counter(status[k] for k in selected if k in status).items())),
             "failures_not_reproduced": len(passed), "failures_reproduced": sorted(reproduced),
             "c1_fix_classes_set_correct": len(set_correct)}
    return {"data": data, "ast_pools": ast_pools, "c1_pools": c1_pools, "base": base, "R": ev, "facts": facts,
            "passed": passed, "fix_eq": fix_eq, "c1fix_classes": set_correct}


def main():
    b_ = build()
    data, ast_pools, c1_pools, base, ev = b_["data"], b_["ast_pools"], b_["c1_pools"], b_["base"], b_["R"]
    res = {**b_["facts"], "comparisons": []}
    for b in BASELINES:
        if b not in V.POLICIES:
            continue
        row = {"b": b}
        for setting, pools, e in (("before_ast", ast_pools, base), ("R_ast", ast_pools, ev), ("R_c1", c1_pools, ev)):
            units, _ = V.evaluate_pair(data, pools, e, "challenger", b)
            agg = V.aggregate(units, "bug", len(data.bugs))
            lo, hi = V.pp(agg["lo"]), V.pp(agg["hi"])
            row[setting] = {"pp": [round(lo, 3), round(hi, 3)], "unknowns": V.relevant_unknowns(units),
                            "result": "identified +" if lo > 0 else "identified -" if hi < 0 else "open"}
        res["comparisons"].append(row)
        print(f"challenger vs {b:20s} " + "  ".join(f"{s} [{row[s]['pp'][0]:+.2f},{row[s]['pp'][1]:+.2f}] "
                                                    f"{row[s]['result'][:12]:12s}(unk {row[s]['unknowns']})"
                                                    for s in ("before_ast", "R_ast", "R_c1")), flush=True)
    (OUT / "c1_fixrerun_results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k != "comparisons"}, indent=1))


if __name__ == "__main__":
    main()
