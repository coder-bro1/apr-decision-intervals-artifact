"""C1 fix re-run selection (ADDENDUM_V4_C1_FIXRERUN.md): every candidate with an archived 'incorrect' label that sits
in a rename-aware (C1-id) class containing a member equivalent to its context's developer fix. Reads no new outcome.
Writes results/v4/c1_fixrerun/candidates.json (the census package input) and selection.json (details)."""
import sys as _sys  # release layout: shared helper modules live in lib/
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / "lib").is_dir()) / "lib"))
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import v4core as V  # noqa: E402
import c1_equivalence as C  # noqa: E402
from validation_policy_contract import context_id  # noqa: E402

OUT = ROOT / "results/v4/c1_fixrerun"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    data = V.load()
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
    comp = defaultdict(list)
    for cid in data.occ:
        comp[uf.find(cid)].append(cid)
    e0, e1 = data.evidence("E0"), data.evidence("E1")
    chosen = []
    for root, members in comp.items():
        if not any(keys(data.occ[m]) & fixkeys.get(data.occ[m].ctx, set()) for m in members):
            continue
        for m in members:
            if e0[m] == 0:
                chosen.append(m)
    chosen.sort()
    census_witness = [m for m in chosen if m in data.witnesses]
    sel = [{"candidate_id": m, "compile_only": False} for m in chosen]
    (OUT / "candidates.json").write_text(json.dumps(sel, indent=1))
    detail = {"candidates": len(chosen), "bugs": len({data.occ[m].bug for m in chosen}),
              "classes": len({uf.find(m) for m in chosen}), "already_census_witnesses": census_witness,
              "e1_labels": dict(Counter(str(e1[m]) for m in chosen)),
              "by_bug": dict(Counter(data.occ[m].bug for m in chosen).most_common())}
    (OUT / "selection.json").write_text(json.dumps(detail, indent=1))
    print(json.dumps({k: v for k, v in detail.items() if k != "by_bug"}, indent=1))


if __name__ == "__main__":
    main()
