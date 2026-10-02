"""Decidability table: every pre-registered comparison, under every evidence step, in one place.

Defects4J (488 bugs, challenger vs every baseline, bug unit, AST identity, known-wins, N-a, equal-bug weights):
  E0 archived -> E1 +census -> +F2 -> +F3 -> +F4 -> Final (+R: fix-identical re-run + C1-fix), and Final under the
  rename-aware C1 identity. For every comparison decided in Final: the smallest number of label flips that would
  reopen it (all labels; and per evidence layer: labels that layer set or changed).
Recomputed here from final_evidence.py and c1_fixrerun_analysis.py. Other studies are read from their result files:
HumanEval-Java E3, G1 (G-E0/G-E1, plus G-E2a = generated tests only, which is NOT the pre-registered G-E2), RepairBench, D4C (G2), D2 plausible pools, PrevaRank E2, POD.
Writes results/v4/decidability/decidability.json and DECIDABILITY.md."""
import json
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import v4core as V  # noqa: E402
import final_evidence as FE  # noqa: E402
import c1_fixrerun_analysis as CF  # noqa: E402
import breakdown as BD  # noqa: E402
from select_f2_topup import BASELINES  # noqa: E402

OUT = ROOT / "results/v4/decidability"
R = ROOT / "results"


def status(lo, hi):
    return "identified +" if lo > 0 else "identified -" if hi < 0 else "open"


def evaluate(data, pools, ev, b):
    units, _ = V.evaluate_pair(data, pools, ev, "challenger", b)
    agg = V.aggregate(units, "bug", len(data.bugs))
    lo, hi = V.pp(agg["lo"]), V.pp(agg["hi"])
    return units, {"pp": [round(lo, 3), round(hi, 3)], "result": status(agg["lo"], agg["hi"]),
                   "unknowns": V.relevant_unknowns(units)}


def flips_to_reopen(units, allowed=None):
    """Smallest number of known class labels that, if wrong (flipped), make an identified comparison open."""
    L, H = sum(u.lo for u in units), sum(u.hi for u in units)
    if L > 0:
        deltas = [d * (1 - 2 * y) for u in units for d, y, i in u.coeffs
                  if y is not None and (allowed is None or (u.bug, i) in allowed)]
        k, _ = BD.minimal_count([x for x in deltas if x < 0], L)
    elif H < 0:
        deltas = [-(d * (1 - 2 * y)) for u in units for d, y, i in u.coeffs
                  if y is not None and (allowed is None or (u.bug, i) in allowed)]
        k, _ = BD.minimal_count([x for x in deltas if x < 0], -H)
    else:
        return None
    return k if k is not None else "not possible"


def changed_classes(before, after):
    """(bug, class index) whose label (as used in the comparison, after N-a) differs between two evaluations."""
    yb = {(u.bug, i): y for u in before for _, y, i in u.coeffs}
    return {(u.bug, i) for u in after for _, y, i in u.coeffs if yb.get((u.bug, i)) != y}


def d4j():
    built = CF.build()
    data, ast_pools, c1_pools = built["data"], built["ast_pools"], built["c1_pools"]
    views, log = FE.build(data, ast_pools)
    steps = [("E0 archived", data.evidence("E0")), ("E1 +census", views["E1"]), ("+F2 census top-up", views["E1+F2"]),
             ("+F3 generated tests", views["E1+F2+F3"]), ("+F4 human review", views["E1+F2+F3+F4"]),
             ("Final (+R fix re-run)", built["R"])]
    rows = []
    for b in BASELINES:
        if b not in V.POLICIES:
            continue
        row, units_by_step = {"b": b}, {}
        for name, ev in steps:
            units_by_step[name], row[name] = evaluate(data, ast_pools, ev, b)
        _, row["Final, rename-aware identity"] = evaluate(data, c1_pools, built["R"], b)
        fin = units_by_step["Final (+R fix re-run)"]
        if row["Final (+R fix re-run)"]["result"] != "open":
            layer = {}
            names = [n for n, _ in steps]
            for prev, cur in zip(names[:-1], names[1:]):
                layer[cur] = flips_to_reopen(fin, changed_classes(units_by_step[prev], units_by_step[cur]) &
                                             {(u.bug, i) for u in fin for _, _, i in u.coeffs})
            row["robustness"] = {"label_flips_to_reopen_any": flips_to_reopen(fin), "only_labels_set_by_layer": layer}
        rows.append(row)
        print(f"{b:20s} " + " | ".join(f"{row[n]['pp'][0]:+.2f},{row[n]['pp'][1]:+.2f} {row[n]['result'][:3]}"
                                       for n, _ in steps) + f" | rob {row.get('robustness', {}).get('label_flips_to_reopen_any')}",
              flush=True)
    decided = {n: sum(1 for r in rows if r[n]["result"] != "open") for n, _ in steps}
    return {"comparisons": rows, "decided_by_step": decided, "n": len(rows), "evidence_log": log,
            "fix_rerun": built["facts"]}


def humaneval():
    e = json.loads((R / "v4/humaneval/e3_results.json").read_text())
    rows = [{"b": m, **{rule: e["comparisons"][rule][m] for rule in ("A0", "HE-E1", "X4-posthoc")}}
            for m in e["comparisons"]["A0"]]
    return {"comparisons": rows, "decided_A0": sum(r["A0"]["result"] != "open" for r in rows),
            "decided_HE-E1": sum(r["HE-E1"]["result"] != "open" for r in rows)}


def g1():
    g = json.loads((R / "g1/g1_final.json").read_text())
    f = json.loads((R / "g1/g1_f3_results.json").read_text())
    rows = []
    for r0, r1 in zip(g["G-E0"], g["G-E1"]):
        rows.append({"a": r0["a"], "b": r0["b"], "G-E0": {"pp": r0["bounds_pp"], "result": r0["result"]},
                     "G-E1": {"pp": r1["bounds_pp"], "result": r1["result"], "unknowns": r1["relevant_unknown_classes"]}})
    rows[0]["G-E2a"] = {"pp": f["G-E2"]["bounds_pp"], "result": f["G-E2"]["result"],
                       "unknowns": f["G-E2"]["relevant_unknown_classes"]}
    return {"comparisons": rows, "executed": g["executed"], "g1_f3": {k: f[k] for k in
            ("status", "counterexamples", "candidates_with_counterexample", "witness_classes")}}


def others():
    rb = json.loads((R / "v4/repairbench/repairbench_v4.json").read_text())
    g2 = json.loads((R / "v4/d4c_frozen/g2_results.json").read_text())
    d2 = json.loads((R / "v4/dp2/d2_results.json").read_text())
    e2 = json.loads((R / "v4/prevarank/e2_analysis.json").read_text())
    pod = json.loads((R / "v4/pod/pod_analysis.json").read_text())
    perms = {k: v for k, v in e2["views"]["E1"]["per_run"].items() if v.get("vs_canonical_pp")}
    d2_last = [r for r in d2["rows"] if r["evidence"] == max(x["evidence"] for x in d2["rows"])]
    return {
        "repairbench": [{"a": p["a"], "b": p["b"], "pp": p["budget_one_pp"], "identified": p["identified"],
                         "unknowns": p["relevant_unknown_classes"]} for p in rb["pairs"]],
        "d4c_trigger_passage": [{"a": r["a"], "b": r["b"], "pp": r["bounds_pp"], "result": r["result"]}
                                for r in g2["endpoints"]["trigger_passage"]],
        "d2_plausible_pools": [{"a": r["a"], "b": r["b"], "evidence": r["evidence"], "pp": [r["lo_pp"], r["hi_pp"]],
                                "identified": r["identified"]} for r in d2_last],
        "prevarank_input_order": {"permutations_vs_canonical": len(perms),
                                  "decided": sum(1 for v in perms.values() if v["vs_canonical_pp"][0] > 0 or v["vs_canonical_pp"][1] < 0)},
        "pod_pairs": {"pairs": len(pod["pairs"]), "identified": sum(1 for p in pod["pairs"] if p["identified"])},
    }


def fmt(c):
    return f"[{c['pp'][0]:+.2f}, {c['pp'][1]:+.2f}]{'*' if c['result'] != 'open' else ''}"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    res = {"defects4j": d4j(), "humaneval": humaneval(), "g1": g1(), "others": others()}
    (OUT / "decidability.json").write_text(json.dumps(res, indent=1, default=str))
    D = res["defects4j"]
    steps = list(D["decided_by_step"])
    lines = ["# Decidability table", "",
             "Bounds are challenger minus baseline, equal-bug percentage points; * = decided (interval excludes 0).", "",
             "## Defects4J (488 bugs)", "",
             "| Baseline | " + " | ".join(steps) + " | Final, rename-aware | Flips to reopen |",
             "|---|" + "---|" * (len(steps) + 2)]
    for r in D["comparisons"]:
        rob = r.get("robustness", {}).get("label_flips_to_reopen_any", "-")
        lines.append(f"| {r['b']} | " + " | ".join(fmt(r[s]) for s in steps) +
                     f" | {fmt(r['Final, rename-aware identity'])} | {rob} |")
    lines += ["", "Decided per step: " + ", ".join(f"{s}: {D['decided_by_step'][s]}/{D['n']}" for s in steps), "",
              "Flips to reopen that only the labels set by one layer could cause (per decided comparison):", ""]
    for r in D["comparisons"]:
        if "robustness" in r:
            lines.append(f"- {r['b']}: " + ", ".join(f"{k}: {v}" for k, v in r["robustness"]["only_labels_set_by_layer"].items()))
    H = res["humaneval"]
    lines += ["", "## HumanEval-Java (E3)", "", "| Baseline | A0 archived | HE-E1 primary | X4 post hoc |", "|---|---|---|---|"]
    for r in H["comparisons"]:
        lines.append(f"| {r['b']} | " + " | ".join(
            f"[{r[k]['equal_bug_pp'][0]:+.2f}, {r[k]['equal_bug_pp'][1]:+.2f}]{'*' if r[k]['result'] != 'open' else ''}"
            for k in ("A0", "HE-E1", "X4-posthoc")) + " |")
    G = res["g1"]
    lines += ["", "## G1 fresh campaign (confirmatory)", "", "| Comparison | G-E0 | G-E1 (pre-registered primary) | G-E2a (generated tests only; NOT the pre-registered G-E2, which was not completed) |", "|---|---|---|---|"]
    for r in G["comparisons"]:
        lines.append(f"| {r['a']} vs {r['b']} | {fmt(r['G-E0'])} | {fmt(r['G-E1'])} | {fmt(r['G-E2a']) if 'G-E2a' in r else '-'} |")
    O = res["others"]
    lines += ["", "## Other studies", "",
              f"- RepairBench: {sum(p['identified'] for p in O['repairbench'])}/{len(O['repairbench'])} pairs decided.",
              f"- D4C trigger passage: {sum(r['result'] != 'open' for r in O['d4c_trigger_passage'])}/{len(O['d4c_trigger_passage'])} decided.",
              f"- D2 plausible pools: {sum(r['identified'] for r in O['d2_plausible_pools'])}/{len(O['d2_plausible_pools'])} decided.",
              f"- PrevaRank input order: {O['prevarank_input_order']['decided']}/{O['prevarank_input_order']['permutations_vs_canonical']} permutation-vs-canonical comparisons decided.",
              f"- POD detector pairs: {O['pod_pairs']['identified']}/{O['pod_pairs']['pairs']} decided."]
    (OUT / "DECIDABILITY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
