"""B1 + B4: full specification grid for a policy pair (default: challenger vs minimum-rank aggregation).

Grid: unit x identity x label rule x no-op treatment (and no-op variant) x evidence. Writes results/v4/grid/.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v4core as V  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default="challenger")
    ap.add_argument("--b", default="mra")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    data = V.load()
    out = Path(args.out or (V.RES / "v4" / "grid"))
    out.mkdir(parents=True, exist_ok=True)
    noop_fns = {"base": V.noop_variant(data, "base"), "strong": V.noop_variant(data, "strong")}
    rows = []
    specs = []
    for identity in ("occ", "ast", "ast_noann"):
        specs.append(("context", identity))
    for identity in ("exact", "ast", "ast_noann", "alpha"):
        specs.append(("bug", identity))
    for unit, identity in specs:
        pools = V.build_pools(data, unit, identity)
        n_classes = sum(len(c) for _, c in pools.values())
        for rule in ("known_wins", "strict"):
            if identity == "occ" and rule == "strict":
                continue  # identical to known_wins for single-member classes
            for noop in ("N-a", "N-b", "N-c"):
                for variant in (("base", "strong") if noop != "N-c" else ("base",)):
                    for ev_name in ("E0", "E1"):
                        units, st = V.evaluate_pair(data, pools, data.evidence(ev_name), args.a, args.b, rule=rule,
                                                    noop=noop, noop_fn=noop_fns[variant])
                        weights = ("bug", "unit") if unit == "context" else ("bug",)
                        for w in weights:
                            agg = V.aggregate(units, w, len(data.bugs) if w == "bug" else None)
                            rows.append({
                                "pair": f"{args.a}-{args.b}", "unit": unit, "identity": identity, "label_rule": rule,
                                "noop": noop, "noop_variant": variant, "evidence": ev_name, "weighting": w,
                                "lo_pp": V.pp(agg["lo"]), "hi_pp": V.pp(agg["hi"]), "all0_pp": V.pp(agg["all0"]),
                                "all1_pp": V.pp(agg["all1"]), "width_pp": V.pp(agg["hi"] - agg["lo"]),
                                "identified_sign": ("+" if agg["lo"] > 0 else "-" if agg["hi"] < 0 else "open"),
                                "lo_exact": str(agg["lo"]), "hi_exact": str(agg["hi"]),
                                "relevant_unknown_classes": V.relevant_unknowns(units), "classes": n_classes,
                                "class_label_conflicts": st["class_label_conflicts"],
                                "noop_correct_contradictions": st["noop_correct_contradictions"],
                            })
                            print(f"{unit:7s} {identity:9s} {rule:10s} {noop} {variant:6s} {ev_name} {w:4s} "
                                  f"[{rows[-1]['lo_pp']:+.3f},{rows[-1]['hi_pp']:+.3f}] {rows[-1]['identified_sign']}",
                                  flush=True)
    stem = f"grid_{args.a}_vs_{args.b}"
    with open(out / f"{stem}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (out / f"{stem}.json").write_text(json.dumps({"protocol_sha256": data.input_hashes["protocol"],
                                                  "input_sha256": data.input_hashes, "rows": rows}, indent=1))


if __name__ == "__main__":
    main()
