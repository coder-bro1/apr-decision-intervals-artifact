"""Decision robustness to individual evidence layers (Defects4J, 16 comparisons).

Versions the read-only sensitivity reported by the independent audit (docs/reviews/codex_v4_check/FINDINGS.md) and
extends it to every layer. The final evidence is rebuilt layer by layer, in the order used everywhere else:
  E0 archived -> census witnesses -> F2 witnesses -> F3 reference-behavior witnesses (whole AST class -> 0)
  -> F4 class verdicts -> R (re-executed fix-identical failures that pass lose their archived 0, then C1-fix)
and all 16 comparisons are recomputed with one layer left out at a time, plus
  * R without its C1-fix step,
  * the audit's combination: no F3 layer and R without C1-fix,
  * context-split AST identity (classes are not merged across the two prompt contexts of a bug).
Self-check: the full rebuild must equal the R view of c1_fixrerun_analysis.build() label for label, and its bounds must
equal the Final column of results/v4/decidability/decidability.json.
Exploratory sensitivity, designed after the final results were known.
Writes results/v4/decidability/sensitivity.json and SENSITIVITY.md."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import v4core as V  # noqa: E402
import final_evidence as FE  # noqa: E402
import c1_fixrerun_analysis as CF  # noqa: E402
from select_f2_topup import BASELINES  # noqa: E402

OUT = ROOT / "results/v4/decidability"
AUDIT = {"no F3, R without C1-fix": {"mra": [9.269, 10.367], "one_stage": [0.410, 0.820]},
         "context-split identity": {"mra": [9.202, 10.290], "classes": 39475}}


def main():
    built = CF.build()
    data, ast_pools, c1_pools = built["data"], built["ast_pools"], built["c1_pools"]
    klass_of = {m: kl.members for _, (_, cl) in ast_pools.items() for kl in cl for m in kl.members}
    f2w, f3w = FE.f2_witnesses(), FE.f3_witnesses()
    f4 = json.loads(FE.F4_LABELS.read_text())

    def census(ev):
        for k in data.witnesses:
            if ev[k] is None:
                ev[k] = 0
        return ev

    def f2(ev):
        for k in f2w:
            if ev[k] is None:
                ev[k] = 0
        return ev

    def f3(ev):
        for k in sorted(f3w):
            FE._set_class(ev, klass_of[k], 0, [], "F3", k)
        return ev

    def f4l(ev):
        for rep, row in sorted(f4.items()):
            val = {"correct": 1, "incorrect": 0}[row["label"]]
            FE._set_class(ev, sorted(set(row["class_members"]) | set(klass_of.get(rep, []))), val, [], "F4", rep)
        return ev

    def r_full(ev):
        return CF.apply_r(ev, built["passed"], built["fix_eq"], c1_pools, c1fix=True)[0]

    def r_noc1(ev):
        return CF.apply_r(ev, built["passed"], built["fix_eq"], c1_pools, c1fix=False)[0]

    layers = [("census", census), ("F2", f2), ("F3", f3), ("F4", f4l), ("R", r_full)]

    def rebuild(skip=(), replace=None):
        ev = dict(data.evidence("E0"))
        for name, fn in layers:
            if name in skip:
                continue
            ev = (replace or {}).get(name, fn)(ev)
        return ev

    full = rebuild()
    if full != built["R"]:
        diff = sum(1 for k in full if full[k] != built["R"].get(k))
        raise ValueError(f"full rebuild differs from the final R view in {diff} labels")
    ctx_pools = V.build_pools(data, "bug", "ast_ctx",
                              key_fn=lambda o: f"{o.ctx}|{V.identity_key(o, 'ast', data)}")
    scenarios = [("full (all layers)", full, ast_pools),
                 ("no census", rebuild(skip=("census",)), ast_pools),
                 ("no F2", rebuild(skip=("F2",)), ast_pools),
                 ("no F3", rebuild(skip=("F3",)), ast_pools),
                 ("no F4", rebuild(skip=("F4",)), ast_pools),
                 ("no R", rebuild(skip=("R",)), ast_pools),
                 ("R without C1-fix", rebuild(replace={"R": r_noc1}), ast_pools),
                 ("no F3, R without C1-fix", rebuild(skip=("F3",), replace={"R": r_noc1}), ast_pools),
                 ("context-split identity", full, ctx_pools)]
    final_ref = {r["b"]: r["Final (+R fix re-run)"]["pp"]
                 for r in json.loads((OUT / "decidability.json").read_text())["defects4j"]["comparisons"]}
    res = {"status": "exploratory sensitivity (designed after the final results were known)",
           "classes": {"ast": sum(len(c) for _, c in ast_pools.values()),
                       "context_split": sum(len(c) for _, c in ctx_pools.values())},
           "scenarios": []}
    for name, ev, pools in scenarios:
        rows = []
        for b in BASELINES:
            if b not in V.POLICIES:
                continue
            units, _ = V.evaluate_pair(data, pools, ev, "challenger", b)
            agg = V.aggregate(units, "bug", len(data.bugs))
            lo, hi = V.pp(agg["lo"]), V.pp(agg["hi"])
            rows.append({"b": b, "pp": [round(lo, 3), round(hi, 3)], "decided": lo > 0 or hi < 0,
                         "unknowns": V.relevant_unknowns(units)})
        if name == "full (all layers)":
            bad = [r["b"] for r in rows if r["pp"] != final_ref[r["b"]]]
            if bad:
                raise ValueError("full rebuild does not reproduce the decidability Final column: " + ", ".join(bad))
        res["scenarios"].append({"scenario": name, "decided": sum(r["decided"] for r in rows), "n": len(rows),
                                 "reopened": [r["b"] for r in rows if not r["decided"]], "rows": rows})
        print(f"{name:28s} decided {sum(r['decided'] for r in rows)}/{len(rows)}  reopened: "
              f"{[r['b'] for r in rows if not r['decided']]}  MRA {next(r['pp'] for r in rows if r['b'] == 'mra')}",
              flush=True)
    res["audit_cross_check"] = {
        "no F3, R without C1-fix": {b: next(r["pp"] for s in res["scenarios"] if s["scenario"] == "no F3, R without C1-fix"
                                            for r in s["rows"] if r["b"] == b) for b in ("mra", "one_stage")},
        "context-split identity": {"mra": next(r["pp"] for s in res["scenarios"] if s["scenario"] == "context-split identity"
                                           for r in s["rows"] if r["b"] == "mra"),
                                   "classes": res["classes"]["context_split"]},
        "audit_reported": AUDIT}
    (OUT / "sensitivity.json").write_text(json.dumps(res, indent=1))
    names = [s["scenario"] for s in res["scenarios"]]
    lines = ["# Decision robustness to individual evidence layers (Defects4J)", "",
             res["status"] + ". Bounds: challenger minus baseline, equal-bug points; * = decided.", "",
             "| Baseline | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for i, b in enumerate(r["b"] for r in res["scenarios"][0]["rows"]):
        cells = []
        for s in res["scenarios"]:
            r = s["rows"][i]
            cells.append(f"[{r['pp'][0]:+.2f}, {r['pp'][1]:+.2f}]{'*' if r['decided'] else ''}")
        lines.append(f"| {b} | " + " | ".join(cells) + " |")
    lines += ["", "Decided: " + ", ".join(f"{s['scenario']}: {s['decided']}/{s['n']}" for s in res["scenarios"]), "",
              f"Classes: AST {res['classes']['ast']:,}; context-split {res['classes']['context_split']:,}.", "",
              "Cross-check with the independent audit: " + json.dumps(res["audit_cross_check"])]
    (OUT / "SENSITIVITY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
