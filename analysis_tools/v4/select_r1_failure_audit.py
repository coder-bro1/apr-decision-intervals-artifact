"""R1 failure audit selection (ADDENDUM_V4_R1_FAILURE_AUDIT.md): a stratified random sample of archived execution-
failure labels from the five configurations whose positive-control failure rate exceeds 10%, restricted to labels
that matter for the comparisons the S2 stress view reopens. Reads no new outcome. Writes
results/v4/r1_failure_audit/candidates.json (package input) and selection.json (population, strata, seed)."""
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
import r1_review_checks as R  # noqa: E402
import refutation_limit as RL  # noqa: E402

OUT = ROOT / "results/v4/r1_failure_audit"
SEED = 20261002
PER_CONFIG = 32


def main():
    RL.read_only_guards()
    chk = json.loads((ROOT / "results/v4/r1_review_v1/r1_review_checks.json").read_text(encoding="utf-8"))
    s2 = chk["A1"]["views"]["S2 configurations above 10%"]["comparisons"]
    reopened = sorted(b for b, v in s2.items() if not v["R"]["decided_view"])
    high = set(chk["A1"]["high_rate_configs"])
    data, pools, evs, basis, comps = R.build_d4j()
    raw = R.raw_records()
    recs = defaultdict(list)
    for o in raw["occ"]:
        if o["bench"] == "defects4j":
            recs[o["cid"]].append(o)
    copies = {r["cid"] for r in R.failing_copies()}
    c1 = {r["candidate_id"] for r in json.loads((ROOT / "results/v4/c1_fixrerun/candidates.json").read_text())}
    classes_of = {b: cl for b, (_, cl) in pools.items()}
    relevant = set()
    for b in reopened:
        rows, *_ = R.interval(data, pools, evs["R"], b)
        for r in rows:
            if r["d"] != 0:
                bug, i = r["key"]
                relevant |= set(classes_of[bug][i].members)
    pop = defaultdict(list)
    for m in sorted(relevant):
        if data.e0[m] != 0 or basis.get(m) != "exec" or evs["R"][m] != 0:
            continue
        if m in copies or m in c1 or m in data.witnesses:
            continue
        fails = [o for o in recs.get(m, []) if R.fail_kind(o)]
        if not fails or not all(o["cfg"] in high for o in fails):
            continue
        cfg = sorted({o["cfg"] for o in fails})[0]
        kind = "compile" if all(R.fail_kind(o) == "compile" for o in fails) else "test"
        pop[(cfg, kind)].append(m)
    rng = random.Random(SEED)
    chosen, strata = [], {}
    for cfg in sorted(high):
        tot = sum(len(pop[(cfg, k)]) for k in ("compile", "test"))
        for kind in ("compile", "test"):
            items = pop[(cfg, kind)]
            k = 0 if not tot else min(len(items), round(PER_CONFIG * len(items) / tot))
            pick = rng.sample(items, k) if k else []
            chosen += pick
            strata[f"{cfg}/{kind}"] = {"population": len(items), "sampled": k}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "candidates.json").write_text(json.dumps([{"candidate_id": m, "compile_only": False} for m in sorted(chosen)],
                                                    indent=1), encoding="utf-8")
    sel = {"seed": SEED, "per_config": PER_CONFIG, "reopened_comparisons": reopened, "high_rate_configs": sorted(high),
           "population": sum(len(v) for v in pop.values()), "sampled": len(chosen),
           "bugs": len({data.occ[m].bug for m in chosen}), "strata": strata}
    (OUT / "selection.json").write_text(json.dumps(sel, indent=1), encoding="utf-8")
    print(json.dumps(sel, indent=1))


if __name__ == "__main__":
    main()
