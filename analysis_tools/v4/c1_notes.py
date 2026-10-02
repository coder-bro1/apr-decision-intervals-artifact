"""C1 remaining items (primary spec: bug unit, AST identity, known-wins, N-a, E1, challenger vs MRA).

(a) Label-error frontier by rate. For each basis group g (reference match, execution failure, human-judged, witness),
    suppose a share eps of ALL accepted classes of g in the pool are wrong and the adversary chooses which ones. The
    worst case puts every error on the relevant classes with the most harmful flips, so L(eps) is exact by sorting.
    eps*_g = smallest rate that reaches L <= 0 (None = impossible even if every relevant class of g is wrong).
(b) Base rates (R1 M2): correct share among all labelled classes, among labelled test-passing classes, among
    human-judged test-passing classes, per project; this is the base rate the MAR frontier (mar.py) conditions on.
(c) Is "unknown" more common among classes returned by many configurations (R1 M2)? Unknown share by
    occurrence-count bin, over all classes and over test-passing classes.
"""
import json
import sys
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_evidence_pilot_step2 as S  # noqa: E402
import v4core as V  # noqa: E402
import provenance as P  # noqa: E402
import breakdown as BD  # noqa: E402

EPS = [0.001, 0.0025, 0.005, 0.01, 0.02, 0.03, 0.05, 0.1, 0.2]


def main():
    data = V.load()
    basis, _ = P.basis_map(data)
    _, _, _, training, _ = S.load_inputs()
    tpass = {r["candidate_id"]: (r["compile"] == 1 and r["test_given_compile"] == 1) for r in training}
    pools = V.build_pools(data, "bug", "ast")
    ev = data.evidence("E1")
    units, _ = V.evaluate_pair(data, pools, ev, "challenger", "mra")
    n = len(data.bugs)
    L = sum(u.lo for u in units)

    def group_of(kl, y):
        if y is None:
            return None
        raw, _ = V.class_label(kl.members, ev, "known_wins")
        if raw is None:
            return "noop_rule"
        b = BD.class_bases(kl, ev, y, basis, data.witnesses)
        if y == 1 and "ref" in b:
            return "reference_match"
        if b == {"witness"}:
            return "witness"
        if y == 0 and "exec" in b:
            return "exec_failure"
        if b == {"human"}:
            return "human"
        return "other"

    totals = defaultdict(int)
    for bug, classes in pools.values():
        for kl in classes:
            y, _ = V.class_label(kl.members, ev, "known_wins")
            g = group_of(kl, y)
            if g:
                totals[g] += 1
    flips = defaultdict(list)
    for u, (bug, classes) in zip(units, pools.values()):
        for d, y, i in u.coeffs:
            if y is None:
                continue
            delta = d * (1 - 2 * y)
            if delta < 0:
                flips[group_of(classes[i], y)].append(delta)
    frontier = {}
    for g, tot in sorted(totals.items()):
        f = sorted(flips.get(g, []))
        acc, kstar = L, None
        for k, dlt in enumerate(f, 1):
            acc += dlt
            if acc <= 0:
                kstar = k
                break
        curve = []
        for e in EPS:
            k = int(e * tot)
            curve.append({"eps": e, "errors": k, "L_pp": V.pp((L + sum(f[:k])) / n)})
        frontier[g] = {"accepted_classes_in_pool": tot, "harmful_relevant_classes": len(f), "min_errors_to_L<=0": kstar,
                       "eps_star": (kstar / tot) if kstar else None, "curve": curve}
    # (b) base rates
    proj = lambda b: b.rsplit("-", 1)[0]
    br = defaultdict(lambda: [0, 0])
    for bug, classes in pools.values():
        for kl in classes:
            y, _ = V.class_label(kl.members, ev, "known_wins")
            if y is None:
                continue
            tp = all(tpass[m] for m in kl.members)
            hum = all(basis.get(m) == "human" for m in kl.members if ev[m] == y)
            for key in ("all_labelled", "labelled_test_pass" if tp else None,
                        "human_judged_test_pass" if tp and hum else None,
                        f"human_judged_test_pass::{proj(bug)}" if tp and hum else None):
                if key:
                    br[key][0] += y
                    br[key][1] += 1
    base_rates = {k: {"correct": v[0], "classes": v[1], "share": v[0] / v[1]} for k, v in sorted(br.items())}
    # (c) unknown share by multiplicity
    bins = lambda c: "1" if c == 1 else "2" if c == 2 else "3-4" if c <= 4 else "5-9" if c <= 9 else "10+"
    mult = defaultdict(lambda: {"all": [0, 0], "test_pass": [0, 0]})
    for bug, classes in pools.values():
        for kl in classes:
            y, conflict = V.class_label(kl.members, ev, "known_wins")
            c = bins(V.pol_occurrence(data, kl))
            unk = y is None
            mult[c]["all"][0] += unk
            mult[c]["all"][1] += 1
            if all(tpass[m] for m in kl.members):
                mult[c]["test_pass"][0] += unk
                mult[c]["test_pass"][1] += 1
    mult_out = {c: {k: {"unknown": v[0], "classes": v[1], "share": (v[0] / v[1]) if v[1] else None}
                    for k, v in d.items()} for c, d in sorted(mult.items())}
    res = {"primary_L_pp": V.pp(L / n), "label_error_frontier": frontier, "base_rates": base_rates,
           "unknown_by_occurrence_count": mult_out}
    out = ROOT / "results/v4/assumptions"
    (out / "c1_notes.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({g: {k: v for k, v in f.items() if k != "curve"} for g, f in frontier.items()}, indent=1))
    print(json.dumps({k: v for k, v in base_rates.items() if "::" not in k}, indent=1))
    print(json.dumps(mult_out, indent=1))


if __name__ == "__main__":
    main()
