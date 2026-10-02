"""K1: deployment cost model (R3 Q5, suggestion 4). Plain arithmetic on measured quantities; no new data.

Inputs: measured seconds of census variant runs (compile + trigger tests per candidate, v3 image, 2 CPUs), the exact
top-k bounds (results/v4/topk/topk_bounds.json), and measured selector latency (--latency writes
results/v4/cost/latency.json on the GPU; otherwise that part is left empty).
Model: a developer validates candidates in the policy's order until one is correct, at most 5 per bug. Each attempt
costs machine time t_m (median measured compile+trigger run) and, for the human-review scenario, R minutes of review.
Saved time per 100 bugs = -(e5 difference) * 100 * cost per attempt, reported as an interval because e5 is bounded.
"""
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/v4/cost"
REVIEW_MIN = (5, 15, 30)


def census_seconds():
    xs = []
    for p in (ROOT / "results/conflict_census").rglob("result.json"):
        try:
            r = json.loads(p.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue  # empty or partial record of an unresolved container run
        for v in r.get("variants", []):
            if v.get("variant") not in ("fixed", "buggy") and v.get("seconds") and v.get("compile"):
                xs.append(v["seconds"])
    return xs


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    xs = census_seconds()
    tm = statistics.median(xs) / 60
    rows = json.loads((ROOT / "results/v4/topk/topk_bounds.json").read_text())["rows"]
    lat = json.loads((OUT / "latency.json").read_text()) if (OUT / "latency.json").exists() else {}
    res = {"machine_minutes_per_attempt": {"median": tm, "p90": sorted(xs)[int(0.9 * len(xs))] / 60, "runs": len(xs)},
           "selector_latency_ms_per_candidate": lat, "comparisons": []}
    for r in rows:
        lo, hi = r["e5"]  # difference in expected attempts (a - b); negative = a needs fewer
        saved = [-hi * 100, -lo * 100]  # attempts saved per 100 bugs by a over b
        res["comparisons"].append({
            "evidence": r["evidence"], "a": r["a"], "b": r["b"], "success1_pp": r["s1"],
            "attempts_saved_per_100_bugs": saved,
            "machine_hours_saved_per_100_bugs": [s * tm / 60 for s in saved],
            "review_hours_saved_per_100_bugs": {str(m): [s * m / 60 for s in saved] for m in REVIEW_MIN}})
    (OUT / "k1_cost.json").write_text(json.dumps(res, indent=1))
    for c in res["comparisons"]:
        if c["evidence"] == "E1":
            print(c["a"], c["b"], "attempts saved/100 bugs", [round(x, 1) for x in c["attempts_saved_per_100_bugs"]],
                  "review h @15min", [round(x, 1) for x in c["review_hours_saved_per_100_bugs"]["15"]])
    print(res["machine_minutes_per_attempt"])


if __name__ == "__main__":
    main()
