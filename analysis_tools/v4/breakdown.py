"""B3: exact break-down analysis for a policy comparison under a v4 specification.

Unit of withdrawal/flip = one identity class (a distinct candidate program). All minima are exact because each
class changes the lower bound independently, so sorting by the change and accumulating is optimal.
"""
import argparse
import json
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v4core as V  # noqa: E402
import provenance as P  # noqa: E402


def class_bases(kl, ev, y, basis, witnesses):
    """Bases of the members that support class label y (witness occurrences are basis 'witness')."""
    out = set()
    for m in kl.members:
        if ev[m] == y:
            out.add("witness" if m in witnesses else basis.get(m))
    return out


def minimal_count(deltas, target):
    """Smallest number of (negative) deltas whose sum reaches -target (target = N*L > 0). Returns (k or None, total)."""
    need = target
    neg = sorted((d for d in deltas if d < 0))
    acc = Fraction(0)
    for i, d in enumerate(neg, 1):
        acc += -d
        if acc >= need:
            return i, acc
    return None, acc


def analyse(data, pair, spec, basis):
    a, b = pair
    pools = V.build_pools(data, spec["unit"], spec["identity"])
    ev = data.evidence(spec["evidence"])
    noop_fn = V.noop_variant(data, spec.get("noop_variant", "base"))
    units, _ = V.evaluate_pair(data, pools, ev, a, b, rule=spec["rule"], noop=spec["noop"], noop_fn=noop_fn)
    n = len(data.bugs)
    per_bug = {}
    for u in units:
        per_bug[u.bug] = per_bug.get(u.bug, 0) + 1
    weight = [Fraction(1, per_bug[u.bug]) for u in units]  # equal-bug weighting (1 for the bug unit)
    L = sum(w * u.lo for w, u in zip(weight, units))
    H = sum(w * u.hi for w, u in zip(weight, units))
    rows = []  # per relevant class
    unit_pools = list(pools.values())
    for w, u, (bug, classes) in zip(weight, units, unit_pools):
        for d0, y, i in u.coeffs:
            d = w * d0
            kl = classes[i]
            raw_y, _ = V.class_label(kl.members, ev, spec["rule"])
            noop_derived = (y is not None and raw_y is None)  # label supplied only by the no-op evidence rule
            bases = class_bases(kl, ev, y, basis, data.witnesses) if (y is not None and not noop_derived) else set()
            if noop_derived:
                bases = {"noop_rule"}
            rows.append({"bug": bug, "d": d, "y": y, "bases": bases, "members": kl.members})
    res = {"spec": spec, "pair": f"{a}-{b}", "L_pp": V.pp(L / n), "H_pp": V.pp(H / n),
           "L_exact": str(L / n), "H_exact": str(H / n)}
    target = L
    # (i) witnesses withdrawn (classes whose label rests only on witnesses)
    w_deltas = [min(Fraction(0), r["d"]) - r["d"] * r["y"] for r in rows if r["y"] == 0 and r["bases"] == {"witness"}]
    k, tot = minimal_count(w_deltas, target) if target > 0 else (0, Fraction(0))
    res["witness_withdrawal"] = {"classes_resting_on_witnesses": len(w_deltas),
                                 "min_classes_to_reach_L<=0": k,
                                 "L_pp_if_all_withdrawn": V.pp((L + sum(w_deltas)) / n)}
    # (ii) accepted labels: withdraw to unknown / flip, by basis group
    groups = {"human_incorrect": lambda r: r["y"] == 0 and r["bases"] == {"human"},
              "human_correct": lambda r: r["y"] == 1 and r["bases"] == {"human"},
              "human_any": lambda r: r["y"] is not None and r["bases"] == {"human"},
              "exec_failure": lambda r: r["y"] == 0 and r["bases"] <= {"exec", "human"} and "exec" in r["bases"],
              "reference_match": lambda r: r["y"] == 1 and "ref" in r["bases"],
              "noop_rule": lambda r: r["bases"] == {"noop_rule"},
              "any_accepted": lambda r: r["y"] is not None}
    for name, pred in groups.items():
        sel = [r for r in rows if pred(r)]
        wd = [min(Fraction(0), r["d"]) - r["d"] * r["y"] for r in sel]
        fl = [r["d"] * (1 - 2 * r["y"]) for r in sel]
        kw, _ = minimal_count(wd, target) if target > 0 else (0, 0)
        kf, _ = minimal_count(fl, target) if target > 0 else (0, 0)
        res[f"accepted_{name}"] = {"relevant_classes": len(sel),
                                    "min_withdrawals_to_L<=0": kw, "L_pp_if_all_withdrawn": V.pp((L + sum(wd)) / n),
                                    "min_flips_to_L<=0": kf}
    # label-error budget curve (adversarial flips of any accepted class label), first 60 steps
    flips = sorted((r["d"] * (1 - 2 * r["y"]) for r in rows if r["y"] is not None and r["d"] * (1 - 2 * r["y"]) < 0))
    curve, acc = [], L
    for m, dlt in enumerate(flips[:60], 1):
        acc += dlt
        curve.append({"flips": m, "L_pp": V.pp(acc / n)})
    res["flip_curve_any_accepted"] = curve
    # (iii) re-executed consistent compile failures counted as incorrect
    compile_fail = {k for k, c in data.census.items() if c["evidence_status"] == "compile_command_failed_twice"}
    ev2 = dict(ev)
    for k in compile_fail:
        if ev2[k] is None:
            ev2[k] = 0
    u2, _ = V.evaluate_pair(data, pools, ev2, a, b, rule=spec["rule"], noop=spec["noop"], noop_fn=noop_fn)
    res["compile_failures_as_incorrect"] = {"candidates": len(compile_fail),
                                            "L_pp": V.pp(sum(w * u.lo for w, u in zip(weight, u2)) / n),
                                            "H_pp": V.pp(sum(w * u.hi for w, u in zip(weight, u2)) / n)}
    # (iv) width decomposition of remaining unknown classes by census status
    census_status = {}
    for r in rows:
        if r["y"] is None:
            sts = {data.census[m]["evidence_status"] for m in r["members"] if m in data.census}
            key = "not_in_census" if not sts else "+".join(sorted(sts))
            census_status[key] = census_status.get(key, Fraction(0)) + abs(r["d"])
    res["width_by_census_status_pp"] = {k: V.pp(v / n) for k, v in sorted(census_status.items())}
    res["unknown_relevant_classes"] = sum(1 for r in rows if r["y"] is None)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default="challenger")
    ap.add_argument("--b", default="mra")
    args = ap.parse_args()
    data = V.load()
    basis, _ = P.basis_map(data)
    specs = [
        {"unit": "bug", "identity": "ast", "rule": "known_wins", "noop": "N-a", "evidence": "E1", "tag": "primary"},
        {"unit": "bug", "identity": "ast", "rule": "known_wins", "noop": "N-a", "evidence": "E0", "tag": "primary_archived"},
        {"unit": "bug", "identity": "ast", "rule": "known_wins", "noop": "N-b", "evidence": "E1", "tag": "filtered"},
        {"unit": "bug", "identity": "exact", "rule": "known_wins", "noop": "N-a", "evidence": "E1", "tag": "exact_identity"},
        {"unit": "context", "identity": "occ", "rule": "known_wins", "noop": "N-b", "evidence": "E1", "tag": "draft_cell"},
    ]
    out = V.RES / "v4" / "breakdown"
    out.mkdir(parents=True, exist_ok=True)
    results = [analyse(data, (args.a, args.b), s, basis) for s in specs]
    (out / f"breakdown_{args.a}_vs_{args.b}.json").write_text(json.dumps(
        {"protocol_sha256": data.input_hashes["protocol"], "results": results}, indent=1, default=str))
    for r in results:
        print(json.dumps({k: v for k, v in r.items() if k != "flip_curve_any_accepted"}, indent=1, default=str))


if __name__ == "__main__":
    main()
