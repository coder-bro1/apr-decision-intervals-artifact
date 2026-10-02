"""G1-F3 targets (ADDENDUM_V4_G1_F3.md): the classes that keep G1's pre-registered primary comparison P1
(challenger_frozen vs occurrence) open under G-E1 whose executed representative passed its triggers in both
repetitions (status admissible_triggers_pass_semantics_unknown). One representative per class (the executed one).
Uses only tier P (finished; tier S classes are not relevant to P1). Reads no generated-test outcome.
Writes results/g1/f3_targets/candidates.json and selection.json."""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import v4core as V  # noqa: E402
import g1_pools as G  # noqa: E402
import g1_analysis as A  # noqa: E402

OUT = ROOT / "results/g1/f3_targets"
PASS = "admissible_triggers_pass_semantics_unknown"


def g_e1(data):
    fp, _, _ = A.findings("P")
    fs, _, _ = A.findings("S")
    status = {**fs, **fp}
    e1 = dict(data.e0)
    for k, st in status.items():
        if k in e1 and st in (A.CTF, A.CF) and e1[k] is None:
            e1[k] = 0
    return e1, status


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = G.load_generations()
    data, _ = G.build(rows)
    G.register(data)
    pools = V.build_pools(data, "bug", "ast")
    e1, status = g_e1(data)
    units, _ = V.evaluate_pair(data, pools, e1, *G.P1)
    rel = []
    for (unit_id, (_, classes)), u in zip(pools.items(), units):  # evaluate_pair keeps the pools order
        if u.bug != unit_id:
            raise ValueError("unit order mismatch")
        rel += [classes[i] for d, y, i in u.coeffs if y is None and d != 0]
    if len(rel) != V.relevant_unknowns(units):
        raise ValueError("relevant-unknown count mismatch")
    chosen, skipped = [], Counter()
    for kl in rel:
        reps = [m for m in kl.members if m in status]
        passing = [m for m in reps if status[m] == PASS]
        if passing:
            chosen.append(sorted(passing)[0])
        else:
            skipped[status[reps[0]] if reps else "not_executed"] += 1
    chosen = sorted(set(chosen))
    (OUT / "candidates.json").write_text(json.dumps([{"candidate_id": c, "compile_only": False} for c in chosen], indent=1))
    detail = {"p1_relevant_unknown_classes": len(rel), "selected": len(chosen),
              "bugs": len({data.occ[c].bug for c in chosen}), "not_selected_by_status": dict(skipped)}
    (OUT / "selection.json").write_text(json.dumps(detail, indent=1))
    print(json.dumps(detail, indent=1))


if __name__ == "__main__":
    main()
