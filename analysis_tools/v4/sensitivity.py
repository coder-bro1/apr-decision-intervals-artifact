"""B5 (tie handling) and B6 (eligibility) sensitivities for the primary pair and the key baselines.

Ties: uniform (primary), archived file order, label-independent hash.
Eligibility: all (primary), compilable-only, plausible-only (archived unanimous compile/test outcomes, defined exactly as
in run_evidence_pilot_step2.load_inputs; conflicting/missing outcomes -> not eligible in the restricted pools).
"""
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

PAIRS = [("challenger", "mra"), ("challenger", "best_config_top1"), ("challenger", "occurrence"),
         ("challenger", "testability"), ("challenger", "codet5_similarity"), ("mra", "best_config_top1")]


def main():
    data = V.load()
    B.register(data)
    _, _, _, training, _ = S.load_inputs()
    comp = {r["candidate_id"]: r["compile"] for r in training}
    test = {r["candidate_id"]: r["test_given_compile"] for r in training}
    pools = V.build_pools(data, "bug", "ast")
    rows = []
    for ev_name in ("E0", "E1"):
        ev = data.evidence(ev_name)
        for a, b in PAIRS:
            if b not in V.POLICIES:
                continue
            for ties in ("uniform", "file_order", "hash"):
                units, _ = V.evaluate_pair(data, pools, ev, a, b, noop="N-a", ties=ties)
                agg = V.aggregate(units, "bug", len(data.bugs))
                rows.append({"kind": "ties", "setting": ties, "evidence": ev_name, "a": a, "b": b,
                             "lo_pp": V.pp(agg["lo"]), "hi_pp": V.pp(agg["hi"])})
            for elig_name, pred in (("compilable", lambda m: comp[m] == 1),
                                    ("plausible", lambda m: comp[m] == 1 and test[m] == 1)):
                saved = dict(V.POLICY_ELIG)
                for p in (a, b):
                    base = saved.get(p)
                    V.POLICY_ELIG[p] = (lambda base, pred: (lambda d, kl: any(pred(m) for m in kl.members)
                                                            and (base is None or base(d, kl))))(base, pred)
                units, _ = V.evaluate_pair(data, pools, ev, a, b, noop="N-a")
                V.POLICY_ELIG.clear()
                V.POLICY_ELIG.update(saved)
                agg = V.aggregate(units, "bug", len(data.bugs))
                rows.append({"kind": "eligibility", "setting": elig_name, "evidence": ev_name, "a": a, "b": b,
                             "lo_pp": V.pp(agg["lo"]), "hi_pp": V.pp(agg["hi"]),
                             "relevant_unknown_classes": V.relevant_unknowns(units)})
    for r in rows:
        print(f"{r['kind']:11s} {r['setting']:10s} {r['evidence']} {r['a']}-{r['b']:20s} [{r['lo_pp']:+.3f},{r['hi_pp']:+.3f}]")
    out = V.RES / "v4" / "sensitivity"
    out.mkdir(parents=True, exist_ok=True)
    (out / "ties_eligibility.json").write_text(json.dumps({"protocol_sha256": data.input_hashes["protocol"],
                                                           "rows": rows}, indent=1))


if __name__ == "__main__":
    main()
