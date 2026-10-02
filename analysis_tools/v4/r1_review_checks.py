"""Checks requested by the updated Reviewer 1 review (2026-10-02; post hoc, read-only, no execution).

A1  Suspect-cell views (M4/Q1). A (bug, configuration) cell is *suspect* when a token-identical copy of the developer
    fix from that configuration is recorded as failing on that bug (positive controls, level 1, in scope): there the
    harness demonstrably rejected a correct patch. View S1 returns to unknown every archived execution-failure label
    whose supporting failure records all come from suspect cells; S2 does the same for every cell of a configuration
    whose positive-control rate exceeds 10%; S3 for every label supported only by compile failures. All 16 Defects4J
    comparisons are recomputed in the archive (E0) and with the final evidence.
A2  Positive-control root cause (E6/Q5): failing level-1 copies split into cell-level patterns.
A3  Calibrated error budget (M3/Q2): Monte Carlo over label errors at rates measured in this study, per label source
    (archived execution failures at configuration-specific rates derived from the positive controls).
A5  Pilot-yield planner (M1/Q4): for each refuting campaign, the refutation yield of a random pilot (20% of the
    targeted relevant classes) predicts P(decide) for every comparison open at the start; compared with the outcome.
A6  Tolerance to false refutations for the decisions reached by refutation.
Writes only results/v4/r1_review_v1/. Never touches results/v4/annotation_key/.
"""
from __future__ import annotations

import base64
import hashlib
import json
import pickle
import random
import re
import sys
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
import refutation_limit as RL  # noqa: E402
import v4core as V  # noqa: E402

OUT = ROOT / "results/v4/r1_review_v1"
PC = ROOT / "results/v4/positive_controls"
SEED = 20261002


def build_d4j():
    import c1_equivalence as C

    def run_tool_ro(cmd, texts, name):
        out, stamp = C.OUT / f"{name}_output.tsv", C.OUT / f"{name}_input.sha256"
        body = "".join(k + "\t" + base64.b64encode(t.encode()).decode() + "\n" for k, t in sorted(texts.items()))
        if not (out.exists() and stamp.exists() and stamp.read_text() == hashlib.sha256(body.encode()).hexdigest()):
            raise RuntimeError(f"cached javac output {name} is stale; refusing to call java")
        return {line.split("\t")[0]: line.split("\t")[1:] for line in out.read_text(encoding="utf-8").splitlines()}

    C.run_tool = run_tool_ro
    import final_evidence as FE
    import c1_fixrerun_analysis as CF
    import provenance as P
    from select_f2_topup import BASELINES
    built = CF.build()
    data, pools = built["data"], built["ast_pools"]
    views, _ = FE.build(data, pools)
    evs = {"E0": data.evidence("E0"), "E1": views["E1"], "F2": views["E1+F2"], "F3": views["E1+F2+F3"],
           "F4": views["E1+F2+F3+F4"], "R": built["R"]}
    basis, _ = P.basis_map(data)
    comps = [b for b in BASELINES if b in V.POLICIES]
    return data, pools, evs, basis, comps


def interval(data, pools, ev, b):
    _, rows = RL.rows_for(data, pools, ev, "challenger", b)
    L, H, A0, _ = RL.bounds(rows)
    return rows, L, H, A0


# ------------------------------------------------------------------ positive-control records
def raw_records():
    with (PC / "cache/raw.pkl").open("rb") as f:
        raw = pickle.load(f)
    return raw


def failing_copies():
    rows = [json.loads(l) for l in (PC / "flagged_occurrences.jsonl").read_text(encoding="utf-8").splitlines()]
    return [r for r in rows if r["bench"] == "defects4j" and r.get("level") == 1 and r.get("in_scope")]


def pc_rates():
    d = json.loads((PC / "positive_controls.json").read_text(encoding="utf-8"))
    pc = d["artifacts"]["repairllama_defects4j"]["levels"]["L1_text"]["per_config"]
    return {c: v["occurrences"]["k"] / v["occurrences"]["n"] for c, v in pc.items() if v["occurrences"]["n"]}


def fail_kind(o):
    if o["compile"] is False:
        return "compile"
    if o["test"] is False:
        return "test"
    return None


# ------------------------------------------------------------------ A1
def a1(data, pools, evs, basis, comps, recs_by_cid):
    copies = failing_copies()
    suspect = {(r["bug"], r["cfg"]) for r in copies}
    rates = pc_rates()
    high = {c for c, r in rates.items() if r > 0.10}

    def view(rule):
        """Revert to unknown each E0 execution-failure label whose failure records all satisfy rule(record)."""
        reverted = set()
        for m, y in data.e0.items():
            if y != 0 or basis.get(m) != "exec":
                continue
            fails = [o for o in recs_by_cid.get(m, []) if fail_kind(o)]
            if fails and all(rule(o) for o in fails):
                reverted.add(m)
        return reverted

    rules = {
        "S1 suspect cells": lambda o: (o["bug"], o["cfg"]) in suspect,
        "S2 configurations above 10%": lambda o: o["cfg"] in high,
        "S3 compile failures only": lambda o: fail_kind(o) == "compile",
    }
    out = {"suspect_cells": len(suspect), "suspect_bugs": len({b for b, _ in suspect}),
           "high_rate_configs": sorted(high), "views": {}}
    n = len(data.bugs)
    base = {}
    for b in comps:
        for st in ("E0", "R"):
            _, L, H, _ = interval(data, pools, evs[st], b)
            base[(b, st)] = (L, H)
    for name, rule in rules.items():
        rev = view(rule)
        res = {"reverted_labels": len(rev), "comparisons": {}}
        for st in ("E0", "R"):
            ev = dict(evs[st])
            changed = 0
            for m in rev:
                if ev[m] == 0 and data.e0[m] == 0:
                    ev[m] = None
                    changed += 1
            res[f"changed_{st}"] = changed
            for b in comps:
                _, L, H, _ = interval(data, pools, ev, b)
                L0, H0 = base[(b, st)]
                res["comparisons"].setdefault(b, {})[st] = {
                    "contract": [RL.ppf(L0, n), RL.ppf(H0, n)], "view": [RL.ppf(L, n), RL.ppf(H, n)],
                    "decided_contract": L0 > 0 or H0 < 0, "decided_view": L > 0 or H < 0}
        res["decided_E0"] = sum(v["E0"]["decided_view"] for v in res["comparisons"].values())
        res["decided_final"] = sum(v["R"]["decided_view"] for v in res["comparisons"].values())
        out["views"][name] = res
    return out


# ------------------------------------------------------------------ A2
def a2(raw, recs_by_bugcfg):
    copies = failing_copies()
    rates = pc_rates()
    cells = defaultdict(list)
    for r in copies:
        cells[(r["bug"], r["cfg"])].append(r)
    # all recorded verdicts of copies (passing too) come from the positive-control summary; here the cell context
    out = {"failing_copies": len(copies), "cells": len(cells), "bugs": len({b for b, _ in cells}),
           "by_config": {}, "cell_patterns": Counter()}
    by_cfg = defaultdict(lambda: Counter())
    for (bug, cfg), rows in cells.items():
        recs = recs_by_bugcfg.get((bug, cfg), [])
        kinds = Counter(fail_kind(o) or "pass" for o in recs)
        tot = sum(kinds.values())
        all_compile_fail = tot > 0 and kinds["compile"] == tot
        pattern = ("every output of the cell fails to compile" if all_compile_fail else
                   "copy fails, other outputs of the cell compile")
        out["cell_patterns"][pattern] += 1
        by_cfg[cfg][pattern] += 1
        by_cfg[cfg]["copies_compile"] += sum(1 for r in rows if r["compile"] is False)
        by_cfg[cfg]["copies_test"] += sum(1 for r in rows if r["compile"] is not False)
    out["by_config"] = {c: dict(v) | {"positive_control_rate": round(rates.get(c, 0), 4)} for c, v in sorted(by_cfg.items())}
    # configuration-wide compile-failure rate of all outputs, for comparison
    cfg_tot, cfg_cf = Counter(), Counter()
    for o in raw["occ"]:
        if o["bench"] != "defects4j":
            continue
        cfg_tot[o["cfg"]] += 1
        cfg_cf[o["cfg"]] += o["compile"] is False
    out["config_compile_failure_rate_all_outputs"] = {c: round(cfg_cf[c] / cfg_tot[c], 4) for c in sorted(cfg_tot)}
    out["cell_patterns"] = dict(out["cell_patterns"])
    return out


# ------------------------------------------------------------------ A3
def class_sources(data, pools, evs, basis, recs_by_cid, rows_final):
    """Source of each known class label in the final view: ref, exec(configs), human, wit, f3, f4, R, noop."""
    steps = ["E0", "E1", "F2", "F3", "F4", "R"]
    classes_of = {b: cl for b, (_, cl) in pools.items()}
    out = {}
    for r in rows_final:
        if r["y"] is None:
            continue
        bug, i = r["key"]
        kl = classes_of[bug][i]
        raw_final = {evs["R"][m] for m in kl.members} - {None}
        if not raw_final:
            out[r["key"]] = ("noop", ())
            continue
        origin = "E0"
        for prev, cur in zip(steps[:-1], steps[1:]):
            yp = RL.classify([evs[prev][m] for m in kl.members])[0]
            yc = RL.classify([evs[cur][m] for m in kl.members])[0]
            if yp != yc:
                origin = cur
        if origin in ("E1", "F2"):
            out[r["key"]] = ("wit", ())
        elif origin == "F3":
            out[r["key"]] = ("f3", ())
        elif origin == "F4":
            out[r["key"]] = ("f4", ())
        elif origin == "R":
            out[r["key"]] = ("R", ())
        else:
            bs = {basis.get(m) for m in kl.members if evs["E0"][m] == r["y"]}
            if r["y"] == 1:
                out[r["key"]] = ("ref", ()) if "ref" in bs else ("human", ())
            elif "exec" in bs:
                cfgs = set()
                for m in kl.members:
                    if evs["E0"][m] == 0 and basis.get(m) == "exec":
                        cfgs |= {o["cfg"] for o in recs_by_cid.get(m, []) if fail_kind(o)}
                out[r["key"]] = ("exec", tuple(sorted(cfgs)))
            else:
                out[r["key"]] = ("human", ())
    return out


def a3(data, pools, evs, basis, comps, recs_by_cid):
    rates = pc_rates()
    n = len(data.bugs)
    # per-configuration error rate of an execution-failure label: falsely rejected correct candidates over failure labels
    K, F = Counter(), Counter()
    for m, y in evs["R"].items():
        cf = {c for c, _ in data.occ[m].sources}
        if y == 1:
            for c in cf:
                K[c] += 1
        if data.e0[m] == 0 and basis.get(m) == "exec":
            for c in cf:
                F[c] += 1
    e_cfg = {c: min(1.0, (rates.get(c, 0) / (1 - rates.get(c, 0))) * K[c] / F[c]) if F[c] else 0.0 for c in F}
    scen = {
        "measured": {"ref": 0.0, "wit": 4 / 185, "f3": 0.10, "f4_1": 3 / 30, "f4_0": 3 / 30, "R": 3 / 71,
                     "human_1": 3 / 30, "human_0": 3 / 30, "noop": 0.0, "exec_scale": 1.0},
        "harsh": {"ref": 0.0, "wit": 4 / 185, "f3": 0.10, "f4_1": 3 / 30, "f4_0": 13 / 30, "R": 3 / 71,
                  "human_1": 13 / 30, "human_0": 3 / 30, "noop": 0.0, "exec_scale": 3.0},
    }
    rng = random.Random(SEED)
    N = 20000
    out = {"exec_error_rate_by_config": {c: round(v, 5) for c, v in sorted(e_cfg.items())}, "draws": N,
           "scenarios": {k: {kk: (round(vv, 4) if isinstance(vv, float) else vv) for kk, vv in v.items()}
                         for k, v in scen.items()}, "comparisons": {}}
    for b in comps:
        rows, L, H, _ = interval(data, pools, evs["R"], b)
        src = class_sources(data, pools, evs, basis, recs_by_cid, rows)
        known = [r for r in rows if r["y"] is not None and r["d"] != 0]
        res = {"L_pp": RL.ppf(L, n)}
        for sname, s in scen.items():
            probs, deltas = [], []
            for r in known:
                kind, cfgs = src[r["key"]]
                if kind == "exec":
                    p = 1.0
                    for c in cfgs:
                        p *= min(1.0, e_cfg.get(c, 0.0) * s["exec_scale"])
                    if not cfgs:
                        p = 0.0
                elif kind in ("human", "f4"):
                    p = s[f"{kind}_{r['y']}"]
                else:
                    p = s[kind]
                if p > 0:
                    probs.append(p)
                    deltas.append(float(r["d"] * (1 - 2 * r["y"])))
            import numpy as np
            Lf = float(L)
            hold = N
            if probs:
                gen = np.random.default_rng(SEED)
                pa, da = np.array(probs), np.array(deltas)
                tot = np.zeros(N) + Lf
                for start in range(0, len(pa), 500):
                    flips = gen.random((N, len(pa[start:start + 500]))) < pa[start:start + 500]
                    tot += flips @ da[start:start + 500]
                hold = int((tot > 0).sum())
            res[sname] = {"p_hold": round(hold / N, 4), "labels_at_risk": len(probs),
                          "expected_flips": round(sum(probs), 2)}
        out["comparisons"][b] = res
    return out


# ------------------------------------------------------------------ A5 / A6
def planner(rows_start, rows_end, targets, yield_p, rng, draws=4000):
    """P(decide) if each helpful targeted class is refuted independently with probability yield_p."""
    L, H, A0, _ = RL.bounds(rows_start)
    if L > 0 or H < 0:
        return None
    direction = "+" if A0 > 0 else "-" if A0 < 0 else None
    if direction is None:
        return 0.0
    need = float(-L) if direction == "+" else float(H)
    gains = [float(abs(r["d"])) for r in rows_start
             if r["y"] is None and r["key"] in targets and not r["conflict"]
             and ((r["d"] < 0) if direction == "+" else (r["d"] > 0))]
    if sum(gains) <= need:
        return 0.0
    hit = 0
    for _ in range(draws):
        hit += sum(g for g in gains if rng.random() < yield_p) > need
    return hit / draws


def a5_a6(data, pools, evs, comps):
    import target_aware_preflight as TA
    n = len(data.bugs)
    kof = TA.klass_map(pools)
    census_t = {kof[c] for c in data.census if c in kof}
    f2_t, _, _ = TA.job_targets(ROOT / "results/v4/f2_topup_package_v1", ROOT / "results/v4/f2_topup_run_v1", kof)
    f3_t, _, _ = TA.job_targets(ROOT / "results/v4/f3_tier1_package_v1", ROOT / "results/v4/f3_tier1_run_v1", kof)
    camps = [("Census", "E0", "E1", census_t), ("Top-up", "E1", "F2", f2_t), ("Generated tests", "F2", "F3", f3_t)]
    rng = random.Random(SEED)
    out = {"pilot_share": 0.2, "repeats": 50, "campaigns": {}}
    for name, s, e, tg in camps:
        rows_s = {b: interval(data, pools, evs[s], b)[0] for b in comps}
        rows_e = {b: interval(data, pools, evs[e], b)[0] for b in comps}
        # targeted relevant classes and their outcome (refuted by the campaign)
        rel = {}
        for b in comps:
            ye = {r["key"]: r["y"] for r in rows_e[b]}
            for r in rows_s[b]:
                if r["key"] in tg and r["y"] is None and not r["conflict"]:
                    rel[r["key"]] = ye.get(r["key"]) == 0
        keys = sorted(rel)
        camp = {"targeted_relevant_classes": len(keys), "realised_yield": round(sum(rel.values()) / max(1, len(keys)), 4),
                "comparisons": {}}
        preds = defaultdict(list)
        yields = []
        for _ in range(out["repeats"]):
            pilot = rng.sample(keys, max(1, int(round(out["pilot_share"] * len(keys))))) if keys else []
            yp = sum(rel[k] for k in pilot) / len(pilot) if pilot else 0.0
            yields.append(yp)
            for b in comps:
                p = planner(rows_s[b], rows_e[b], tg, yp, rng, draws=1000)
                if p is not None:
                    preds[b].append(p)
        camp["pilot_yield_mean"] = round(sum(yields) / len(yields), 4) if yields else None
        for b, ps in preds.items():
            Le, He, *_ = RL.bounds(rows_e[b])
            camp["comparisons"][b] = {"p_decide_mean": round(sum(ps) / len(ps), 3), "p_decide_min": round(min(ps), 3),
                                      "p_decide_max": round(max(ps), 3), "decided": Le > 0 or He < 0}
        # A6: tolerance of a refutation-reached decision to false refutations
        tol = {}
        for b, v in camp["comparisons"].items():
            if not v["decided"]:
                continue
            ys = {r["key"]: r["y"] for r in rows_s[b]}
            Le, *_ = RL.bounds(rows_e[b])
            gains = sorted((float(abs(r["d"])) for r in rows_e[b]
                            if ys.get(r["key"]) is None and r["y"] == 0 and r["d"] < 0), reverse=True)
            acc, k = 0.0, 0
            for g in gains:
                acc += g
                k += 1
                if acc >= float(Le):
                    break
            tol[b] = {"refutations_in_campaign": len(gains), "false_refutations_to_reopen": k if acc >= float(Le) else None,
                      "L_end_pp": RL.ppf(Le, n)}
        camp["tolerance"] = tol
        out["campaigns"][name] = camp
    return out


def g1_planner():
    """Fresh campaign: pilot yield on tier P/S targets, plus a prior-only prediction at the archive's failure rate."""
    import target_aware_preflight as TA
    res, calls = TA.capture(RL.g1)
    n = res["n_bugs"]
    rows = defaultdict(list)
    for c in calls:
        rows[f"{c['a']} vs {c['b']}"].append(c["rows"])
    rng = random.Random(SEED + 1)
    out = {"comparisons": {}}
    prior = 50449 / 55466  # share of RepairLLaMA Defects4J candidates archived as failing
    for name, rs in rows.items():
        s, e = rs[0], rs[1]
        tg = {r["key"] for r in s}
        ye = {r["key"]: r["y"] for r in e}
        keys = sorted(r["key"] for r in s if r["y"] is None)
        realised = sum(ye.get(k) == 0 for k in keys) / len(keys)
        ps = []
        for _ in range(20):
            pilot = rng.sample(keys, max(1, int(round(0.2 * len(keys)))))
            yp = sum(ye.get(k) == 0 for k in pilot) / len(pilot)
            ps.append(planner(s, e, tg, yp, rng, draws=500))
        Le, He, *_ = RL.bounds(e)
        out["comparisons"][name] = {"realised_yield": round(realised, 4),
                                    "p_decide_pilot_mean": round(sum(ps) / len(ps), 4), "p_decide_pilot_max": round(max(ps), 4),
                                    "p_decide_prior": round(planner(s, e, tg, prior, rng, draws=2000), 4),
                                    "decided": Le > 0 or He < 0}
    out["prior_yield"] = round(prior, 4)
    return out


def main():
    RL.read_only_guards()
    OUT.mkdir(parents=True, exist_ok=True)
    data, pools, evs, basis, comps = build_d4j()
    raw = raw_records()
    recs_by_cid, recs_by_bugcfg = defaultdict(list), defaultdict(list)
    for o in raw["occ"]:
        if o["bench"] == "defects4j":
            recs_by_cid[o["cid"]].append(o)
            recs_by_bugcfg[(o["bug"], o["cfg"])].append(o)
    n = len(data.bugs)
    res = {"status": "post hoc, read-only; Reviewer 1 (updated) checks", "seed": SEED}
    res["delta_margin"] = {}
    finals = {b: interval(data, pools, evs["R"], b)[1] for b in comps}
    for dpp in (0, 1, 2, 5):
        res["delta_margin"][dpp] = sum(RL.ppf(L, n) > dpp for L in finals.values())
    print("delta", res["delta_margin"], flush=True)
    res["A1"] = a1(data, pools, evs, basis, comps, recs_by_cid)
    print("A1 done", {k: (v["decided_E0"], v["decided_final"]) for k, v in res["A1"]["views"].items()}, flush=True)
    res["A2"] = a2(raw, recs_by_bugcfg)
    print("A2 done", res["A2"]["cell_patterns"], flush=True)
    res["A3"] = a3(data, pools, evs, basis, comps, recs_by_cid)
    print("A3 done", flush=True)
    res["A5_A6"] = a5_a6(data, pools, evs, comps)
    print("A5 done", flush=True)
    res["A5_G1"] = g1_planner()
    print("G1 done", flush=True)
    (OUT / "r1_review_checks.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(json.dumps(res, indent=1, default=str)[:20000])


if __name__ == "__main__":
    main()
