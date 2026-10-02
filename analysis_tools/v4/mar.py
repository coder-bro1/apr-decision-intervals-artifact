"""C1: missing-at-random (MAR) sensitivity frontier (PROTOCOL_V4 section 5).

Unknown classes whose members all have archived unanimous test pass ('unknown test-passers') are correct with
probability pi in [rho_s - delta, rho_s + delta] (clipped to [0,1]), where rho_s is the correct share among reviewed
test-passing classes of the same project s (reference-match classes excluded from rho_s, since unknown test-passers
are by construction not reference matches). Other unknown classes stay unrestricted in [0,1]. Expected-value bounds
are linear in pi, hence exact by coefficient sign. delta = 1 reproduces the worst case. Reports the frontier
delta* at which each comparison's sign becomes identified (or stops being identified).
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
import baselines as B  # noqa: E402
import provenance as P  # noqa: E402

DELTAS = [Fraction(i, 20) for i in range(21)]


def main():
    data = V.load()
    B.register(data)
    basis, _ = P.basis_map(data)
    _, _, _, training, _ = S.load_inputs()
    tpass = {r["candidate_id"]: (r["compile"] == 1 and r["test_given_compile"] == 1) for r in training}
    pools = V.build_pools(data, "bug", "ast")
    project = lambda bug: bug.rsplit("-", 1)[0]
    rows = []
    for ev_name in ("E0", "E1"):
        ev = data.evidence(ev_name)
        # rho per project from reviewed (human-judged) test-passing classes
        num, den = defaultdict(int), defaultdict(int)
        for bug, classes in pools.values():
            for kl in classes:
                y, conflict = V.class_label(kl.members, ev, "known_wins")
                if conflict or y is None or not all(tpass[m] for m in kl.members):
                    continue
                if any(basis.get(m) == "ref" for m in kl.members):
                    continue
                if all(basis.get(m) == "human" for m in kl.members if ev[m] == y):
                    num[project(bug)] += y
                    den[project(bug)] += 1
        tot_num, tot_den = sum(num.values()), sum(den.values())
        rho = {p: (Fraction(num[p], den[p]) if den[p] >= 10 else Fraction(tot_num, tot_den)) for p in
               {project(b) for b in data.bugs}}
        for a, b in [("challenger", x) for x in ("mra", "best_config_top1", "occurrence", "testability",
                                                  "one_stage", "source_agnostic", "codet5_similarity")]:
            if b not in V.POLICIES:
                continue
            units, _ = V.evaluate_pair(data, pools, ev, a, b, noop="N-a")
            frontier = []
            for delta in DELTAS:
                lo = hi = Fraction(0)
                for u, (bug, classes) in zip(units, pools.values()):
                    r = rho[project(bug)]
                    for d, y, i in u.coeffs:
                        if y is not None:
                            lo += d * y
                            hi += d * y
                            continue
                        members = classes[i].members
                        if all(tpass[m] for m in members):
                            pl, ph = max(Fraction(0), r - delta), min(Fraction(1), r + delta)
                        else:
                            pl, ph = Fraction(0), Fraction(1)
                        lo += min(d * pl, d * ph)
                        hi += max(d * pl, d * ph)
                n = len(data.bugs)
                frontier.append({"delta": float(delta), "lo_pp": V.pp(lo / n), "hi_pp": V.pp(hi / n)})
            identified = [f["delta"] for f in frontier if f["lo_pp"] > 0 or f["hi_pp"] < 0]
            rows.append({"evidence": ev_name, "a": a, "b": b, "frontier": frontier,
                         "max_delta_identified": max(identified) if identified else None})
            print(ev_name, a, b, "identified up to delta =", rows[-1]["max_delta_identified"],
                  "| delta=0:", frontier[0]["lo_pp"], frontier[0]["hi_pp"], flush=True)
    out = V.RES / "v4" / "assumptions"
    out.mkdir(parents=True, exist_ok=True)
    (out / "mar_frontier.json").write_text(json.dumps({"protocol_sha256": data.input_hashes["protocol"],
                                                       "rho_note": "project share among human-judged test-passing classes (>=10 reviewed; else pooled)",
                                                       "rows": rows}, indent=1))


if __name__ == "__main__":
    main()
