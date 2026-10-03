"""F3 targets (ADDENDUM_V4_F3_DIFFTEST.md): decision-relevant unknown classes whose every member passed the archived
tests unanimously; tier 1 = relevant to challenger vs any non-uniform baseline, tier 2 = uniform only.
Writes results/v4/f3_targets/{tier1,tier2}_candidates.json (one representative per class)."""
import sys as _sys  # release layout: shared helper modules live in lib/
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / "lib").is_dir()) / "lib"))
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_evidence_pilot_step2 as S  # noqa: E402
import v4core as V  # noqa: E402
import baselines as B  # noqa: E402
from select_f2_topup import BASELINES  # noqa: E402


def main():
    data = V.load()
    B.register(data)
    _, _, _, training, _ = S.load_inputs()
    tpass = {r["candidate_id"]: (r["compile"] == 1 and r["test_given_compile"] == 1) for r in training}
    pools = V.build_pools(data, "bug", "ast")
    ev = data.evidence("E1")
    tiers = {}
    missing = []
    for other in BASELINES:
        if other not in V.POLICIES:
            missing.append(other)
            continue
        units, _ = V.evaluate_pair(data, pools, ev, "challenger", other)
        for u, (bug, classes) in zip(units, pools.values()):
            for d, y, i in u.coeffs:
                kl = classes[i]
                if y is None and all(tpass[m] for m in kl.members):
                    rep = min(kl.members)
                    t = tiers.setdefault(rep, {"bug": bug, "comparisons": set()})
                    t["comparisons"].add(other)
    out = ROOT / "results/v4/f3_targets"
    out.mkdir(parents=True, exist_ok=True)
    t1 = sorted(k for k, v in tiers.items() if v["comparisons"] - {"uniform"})
    t2 = sorted(k for k, v in tiers.items() if v["comparisons"] == {"uniform"})
    for name, ids in (("tier1", t1), ("tier2", t2)):
        (out / f"{name}_candidates.json").write_text(json.dumps([{"candidate_id": k, "compile_only": False} for k in ids], indent=1))
    detail = {"missing_baselines": missing, "tier1": len(t1), "tier1_bugs": len({tiers[k]["bug"] for k in t1}),
              "tier2": len(t2), "tier2_bugs": len({tiers[k]["bug"] for k in t2}),
              "classes": {k: {"bug": v["bug"], "comparisons": sorted(v["comparisons"])} for k, v in sorted(tiers.items())}}
    (out / "f3_selection_detail.json").write_text(json.dumps(detail, indent=1))
    print(json.dumps({k: v for k, v in detail.items() if k != "classes"}, indent=1))


if __name__ == "__main__":
    main()
