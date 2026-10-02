"""Refutation limit ("testing can only refute"): what one-sided evidence can and cannot decide (novelty panel C1).

Post hoc, read-only analysis of evidence already collected. Writes only results/v4/refutation_limit/.

Definitions (per comparison A - B, after the N-a no-op rule, equal-bug weights, exact Fractions):
  L, H   shared-label bounds (v4core.evaluate_pair / aggregate)
  A0     value of the all-unknown-incorrect completion (every unknown relevant class = 0)
  A1     value of the all-unknown-correct completion
A refute-only layer can only turn unknown labels into 0. Refuting an unknown class with d < 0 raises L by |d|; refuting
one with d > 0 lowers H by d; A0 never changes (both completions put that class at 0). So refutation drives [L, H]
towards A0 and can decide only in the direction of sign(A0), never when A0 = 0.

Three refutation semantics ("modes"):
  class       a refutation sets a whole identity class to 0, even a class that is unknown only because its members carry
              contradictory archived labels (the class-level overwrite allowed by final_evidence._set_class for F3).
              Refute-only limit = the point A0.
  candidate   a refutation adds a 0 to one candidate (census, F2, G-E1). Under known-wins a conflict class (known member
              labels {0, 1}) stays unknown however many 0s are added: it is conflict-locked.
              Limit = [A0 + sum_locked min(0, d), A0 + sum_locked max(0, d)].
  execution   candidate-level, and in addition a class is refutable by re-running the existing tests only if at least
              one member is NOT archived as test-passing (compile and tests passed in the archive). Classes whose
              members all passed their tests can be refuted only by new (generated) tests. This is the
              "execution ceiling".
Confirm-only evidence mirrors everything with A1 (it can only turn unknown labels into 1).
Minimum number of refutations: every refutation moves the bound by its own |d| and the moves add up, so taking the
largest |d| first is exact (the breakdown.minimal_count argument); test_refutation_limit.py checks it by brute force.

Inputs: final_evidence.build(), c1_fixrerun_analysis.build() (Defects4J E0 -> E1 -> F2 -> F3 -> F4 -> R), g1_pools /
g1_analysis / select_g1_f3_targets (G1 G-E0, G-E1, G-E2a), e3_analysis (HumanEval-Java E3 views), RepairBench JSON,
package jobs.json + run terminal.json (container seconds). Java is never called: the cached javac outputs are read
through read-only replacements of c1_equivalence.run_tool and g1_pools.fingerprints, and subprocess.run is blocked.
"""
from __future__ import annotations

import glob
import json
import subprocess
import sys
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import v4core as V  # noqa: E402

OUT = ROOT / "results/v4/refutation_limit"
PASS = "admissible_triggers_pass_semantics_unknown"
CENSUS_HOURS = 16.0  # census (E0 -> E1) container-hours, from the paper's cost ledger (no per-job join here)
MODES = ("class", "candidate", "execution")


# ===================================================================== pure core (tested by test_refutation_limit.py)

def classify(member_labels, noop=False):
    """Class label under known-wins plus the N-a rule. Returns (y, conflict): y in {0, 1, None};
    conflict = the known member labels are {0, 1} (the class is unknown because of contradictory labels)."""
    known = {v for v in member_labels if v is not None}
    conflict = len(known) > 1
    y = next(iter(known)) if len(known) == 1 else None
    if noop and y is None:
        y = 0
    return y, conflict


def bounds(rows):
    """rows: dicts with d (Fraction) and y. Returns (L, H, A0, A1)."""
    L = H = A0 = A1 = Fraction(0)
    for r in rows:
        d, y = r["d"], r["y"]
        if y is None:
            L += min(Fraction(0), d)
            H += max(Fraction(0), d)
            A1 += d
        else:
            L += d * y
            H += d * y
            A0 += d * y
            A1 += d * y
    return L, H, A0, A1


def movable(r, mode):
    """Can one-sided evidence of this mode resolve this relevant class?"""
    if r["y"] is not None or r["d"] == 0:
        return False
    if mode == "class":
        return True
    if r["conflict"]:
        return False
    return mode == "candidate" or r.get("exec_ok", True)


def _greedy(gains, need):
    """Smallest number of gains (each > 0) whose sum strictly exceeds need (need >= 0)."""
    acc = Fraction(0)
    for k, g in enumerate(sorted(gains, reverse=True), 1):
        acc += g
        if acc > need:
            return k
    return None


def limit(rows, polarity="refute", mode="candidate"):
    """Reach of one-sided evidence. polarity 'refute' (unknown -> 0) or 'confirm' (unknown -> 1).
    Returns L, H, the anchor (A0 or A1), the reachable interval [L_best, H_best], whether a decision is reachable,
    the exact minimum number of resolutions, and the locked / helpful masses."""
    L, H, A0, A1 = bounds(rows)
    anchor = A0 if polarity == "refute" else A1
    mv = [r for r in rows if movable(r, mode)]
    if polarity == "refute":
        up = [-r["d"] for r in mv if r["d"] < 0]    # each raises L
        down = [r["d"] for r in mv if r["d"] > 0]   # each lowers H
    else:
        up = [r["d"] for r in mv if r["d"] > 0]
        down = [-r["d"] for r in mv if r["d"] < 0]
    L_best, H_best = L + sum(up, Fraction(0)), H - sum(down, Fraction(0))
    locked = [r for r in rows if r["y"] is None and r["d"] != 0 and not movable(r, mode)]
    res = {"L": L, "H": H, "A0": A0, "A1": A1, "anchor": anchor, "L_best": L_best, "H_best": H_best,
           "locked_classes": len(locked), "locked_conflict_classes": sum(1 for r in locked if r["conflict"]),
           "locked_lo": sum((min(Fraction(0), r["d"]) for r in locked), Fraction(0)),
           "locked_hi": sum((max(Fraction(0), r["d"]) for r in locked), Fraction(0))}
    if L > 0 or H < 0:
        res.update(status="decided +" if L > 0 else "decided -", direction="+" if L > 0 else "-", k_min=0,
                   helpful_classes=0, helpful_mass=Fraction(0), need=Fraction(0))
    elif L_best > 0:
        res.update(status="reachable +", direction="+", k_min=_greedy(up, -L), helpful_classes=len(up),
                   helpful_mass=sum(up, Fraction(0)), need=-L)
    elif H_best < 0:
        res.update(status="reachable -", direction="-", k_min=_greedy(down, H), helpful_classes=len(down),
                   helpful_mass=sum(down, Fraction(0)), need=H)
    else:
        why = "anchor = 0" if anchor == 0 else "locked or non-refutable mass keeps 0 inside"
        side = up if anchor > 0 else down if anchor < 0 else []
        res.update(status="not reachable (" + why + ")", direction=None, k_min=None, helpful_classes=len(side),
                   helpful_mass=sum(side, Fraction(0)), need=(-L if anchor > 0 else H if anchor < 0 else None))
    res["share_of_helpful_mass_needed"] = (float(res["need"] / res["helpful_mass"])
                                           if res["helpful_mass"] and res["need"] is not None else None)
    if polarity == "refute" and mode == "class":
        assert L_best == A0 and H_best == A0, "class-mode refutation limit must be the point A0"
    return res


def hazard(member_labels_before, member_labels_after, noop=False, polarity="refute"):
    """The proposition needs admissible evidence: a refutation must not touch a known-correct class, and a
    confirmation must not touch a class that is incorrect (archived 0, or 0 by the N-a rule). Under known-wins such a
    hit makes the class unknown (or, for a no-op class, incorrect) and moves A0 (A1). Returns True for such a hit."""
    yb, _ = classify(member_labels_before, noop)
    ya, _ = classify(member_labels_after, noop)
    bad = 1 if polarity == "refute" else 0
    return yb == bad and ya != bad


# ===================================================================== helpers

def ppf(x, n=1):
    return round(float(100 * Fraction(x) / n), 4)


def close(mine, ref, tol=0.0011):
    """Stored result files are rounded (3 or 6 decimals, HumanEval 2); compare within that rounding."""
    return all(abs(a - b) <= tol for a, b in zip(mine, ref))


def lim_json(res, n):
    out = {}
    for k, v in res.items():
        out[k] = ppf(v, n) if isinstance(v, Fraction) else v
    return out


def read_only_guards():
    def blocked(*a, **k):
        raise RuntimeError("subprocess blocked: refutation_limit.py is read-only")
    subprocess.run = blocked


def job_hours(package, run):
    """{job_id: (bug_id, [candidate ids], hours)} from a package's jobs.json and its run's terminal.json files."""
    jobs = json.loads((package / "jobs.json").read_text())
    secs = {}
    for t in glob.glob(str(run / "*/terminal.json")):
        d = json.loads(Path(t).read_text())
        secs[d.get("job_id", Path(t).parent.name)] = d.get("seconds", 0.0)
    return {j["job_id"]: (j["bug_id"], [c["candidate_id"] for c in j["cases"]], secs.get(j["job_id"], 0.0) / 3600)
            for j in jobs}


def rows_for(data, pools, ev, a, b, tp=None):
    """Relevant classes of comparison a-b under evidence ev (one row per (bug, class) with d != 0). tp: candidate ->
    archived test-pass flag (None = no information, every class execution-refutable)."""
    units, _ = V.evaluate_pair(data, pools, ev, a, b)
    out = []
    for (uid, (bug, classes)), u in zip(pools.items(), units):
        assert u.bug == bug
        for d, y, i in u.coeffs:
            kl = classes[i]
            raw = [ev[m] for m in kl.members]
            noop = any(data.occ[m].noop for m in kl.members)
            yc, conflict = classify(raw, noop)
            assert yc == y, (bug, i)
            exec_ok = True if tp is None else any(not tp.get(m, False) for m in kl.members)
            out.append({"key": (bug, i), "bug": bug, "d": d, "y": y, "conflict": conflict and y is None,
                        "exec_ok": exec_ok, "members": kl.members})
    return units, out


def summarise(rows, n, modes=MODES):
    L, H, A0, A1 = bounds(rows)
    res = {"L": ppf(L, n), "H": ppf(H, n), "A0": ppf(A0, n), "A1": ppf(A1, n),
           "A0_exact": str(A0 / n), "A1_exact": str(A1 / n),
           "result": "identified +" if L > 0 else "identified -" if H < 0 else "open",
           "unknown_classes": sum(1 for r in rows if r["y"] is None),
           "conflict_unknown_classes": sum(1 for r in rows if r["y"] is None and r["conflict"]),
           "neg_unknown_pp": ppf(sum((-r["d"] for r in rows if r["y"] is None and r["d"] < 0), Fraction(0)), n),
           "pos_unknown_pp": ppf(sum((r["d"] for r in rows if r["y"] is None and r["d"] > 0), Fraction(0)), n),
           "refute": {m: lim_json(limit(rows, "refute", m), n) for m in modes},
           "confirm": {m: lim_json(limit(rows, "confirm", m), n) for m in modes if m != "execution"}}
    return res


def class_states(pools, ev):
    """Pool-level state of every class: '1', '0', 'conflict' or 'unknown' (raw known-wins, before N-a)."""
    st = {}
    for uid, (bug, classes) in pools.items():
        for i, kl in enumerate(classes):
            y, c = classify([ev[m] for m in kl.members])
            st[(bug, i)] = "conflict" if c else "unknown" if y is None else str(y)
    return st


def a0_decomposition(rows_prev, rows_cur, states_prev, n):
    """Change of A0 between two evidence states, split by the transition of each relevant class."""
    yp = {r["key"]: r["y"] for r in rows_prev}
    parts = defaultdict(lambda: [Fraction(0), 0])
    for r in rows_cur:
        before = yp[r["key"]]
        if before == r["y"]:
            continue
        delta = r["d"] * ((r["y"] or 0) - (before or 0))
        tag = (f"{'conflict' if states_prev[r['key']] == 'conflict' else 'unknown' if before is None else before}"
               f" -> {'unknown' if r['y'] is None else r['y']}")
        parts[tag][0] += delta
        parts[tag][1] += 1
    return {k: {"dA0_pp": ppf(v[0], n), "classes": v[1]} for k, v in sorted(parts.items())}


def helpful_classes(rows, mode, direction):
    mv = [r for r in rows if movable(r, mode)]
    return [r for r in mv if (r["d"] < 0 if direction == "+" else r["d"] > 0)]


def campaign_capability(rows_by_cmp, mode, jobs, klass_of, n):
    """Which open comparisons a refute-only campaign of this mode could decide from its start state, the minimum
    refutations, and the container-hours of jobs that touch at least one class able to move such a comparison."""
    out, capable_classes, relevant_classes = {}, set(), set()
    for name, rows in rows_by_cmp.items():
        res = limit(rows, "refute", mode)
        if res["status"].startswith("decided"):
            continue
        relevant_classes |= {r["key"] for r in rows if r["y"] is None and r["d"] != 0}
        if res["direction"]:
            capable_classes |= {r["key"] for r in helpful_classes(rows, mode, res["direction"])}
        out[name] = {"status": res["status"], "A0": ppf(res["A0"], n), "limit": [ppf(res["L_best"], n), ppf(res["H_best"], n)],
                     "k_min": res["k_min"], "helpful_classes": res["helpful_classes"],
                     "share_of_helpful_mass_needed": (round(float(res["need"] / res["helpful_mass"]), 4)
                                                      if res["helpful_mass"] and res["need"] is not None else None)}
    cap_jobs = rel_jobs = 0
    cap_h = rel_h = tot_h = bug_h = 0.0
    cap_list, bug_list = [], []
    cap_bugs = {k[0] for k in capable_classes}
    for jid, (bug, cands, h) in jobs.items():
        tot_h += h
        if bug in cap_bugs:  # looser join: any job in a bug that holds a capable class
            bug_h += h
            bug_list.append(bug)
        ks = {klass_of[c] for c in cands if c in klass_of}
        if ks & relevant_classes:
            rel_jobs += 1
            rel_h += h
        if ks & capable_classes:
            cap_jobs += 1
            cap_h += h
            cap_list.append(bug)
    return {"comparisons_open_at_start": out,
            "jobs": len(jobs), "hours": round(tot_h, 3),
            "jobs_touching_a_relevant_unknown": rel_jobs, "hours_touching_a_relevant_unknown": round(rel_h, 3),
            "jobs_able_to_move_a_decidable_comparison": cap_jobs,
            "hours_able_to_move_a_decidable_comparison": round(cap_h, 3),
            "bugs_of_those_jobs": sorted(cap_list),
            "bug_level_join": {"jobs": len(bug_list), "hours": round(bug_h, 3), "bugs": sorted(bug_list)}}


# ===================================================================== Defects4J

def d4j():
    import c1_equivalence as C

    def run_tool_ro(cmd, texts, name):
        import base64
        import hashlib
        out, stamp = C.OUT / f"{name}_output.tsv", C.OUT / f"{name}_input.sha256"
        body = "".join(k + "\t" + base64.b64encode(t.encode()).decode() + "\n" for k, t in sorted(texts.items()))
        if not (out.exists() and stamp.exists() and stamp.read_text() == hashlib.sha256(body.encode()).hexdigest()):
            raise RuntimeError(f"cached javac output {name} is stale; refusing to call java")
        res = {line.split("\t")[0]: line.split("\t")[1:] for line in out.read_text(encoding="utf-8").splitlines()}
        if set(res) != set(texts):
            raise ValueError(name)
        return res

    C.run_tool = run_tool_ro
    import final_evidence as FE
    import c1_fixrerun_analysis as CF
    import run_evidence_pilot_step2 as S
    from select_f2_topup import BASELINES

    built = CF.build()
    data, pools = built["data"], built["ast_pools"]
    views, log = FE.build(data, pools)
    n = len(data.bugs)
    _, _, _, training, _ = S.load_inputs()
    tp_arch = {r["candidate_id"]: (r["compile"] == 1 and r["test_given_compile"] == 1) for r in training}
    # observed variant: also count candidates whose triggers passed when the census / F2 re-ran them
    f2_status = {}
    for t in glob.glob(str(FE.F2_RUNS / "*/terminal.json")):
        for f in json.loads(Path(t).read_text())["findings"]:
            f2_status[f["candidate_id"]] = f["evidence_status"]
    census_status = {k: c["evidence_status"] for k, c in data.census.items()}
    tp_obs_e1 = {k: v or census_status.get(k) == PASS for k, v in tp_arch.items()}
    tp_obs_f2 = {k: v or f2_status.get(k) == PASS for k, v in tp_obs_e1.items()}
    steps = [("E0", data.evidence("E0"), "archived labels (start)", tp_arch, tp_arch),
             ("E1", views["E1"], "refute-only, candidate-level (census re-execution)", tp_arch, tp_obs_e1),
             ("F2", views["E1+F2"], "refute-only, candidate-level (F2 re-execution)", tp_arch, tp_obs_f2),
             ("F3", views["E1+F2+F3"], "refute-only, class-level (generated tests; may overwrite conflict classes)",
              tp_arch, tp_obs_f2),
             ("F4", views["E1+F2+F3+F4"], "two-sided, class-level (human review verdicts)", tp_arch, tp_obs_f2),
             ("R", built["R"], "retraction + confirmation (re-run archived failures; C1-fix)", tp_arch, tp_obs_f2)]
    comps = [b for b in BASELINES if b in V.POLICIES]
    states = {name: class_states(pools, ev) for name, ev, *_ in steps}
    # pool-level class transitions per step (all classes, raw known-wins)
    transitions = {}
    for (pn, *_), (cn, _, pol, *_) in zip(steps[:-1], steps[1:]):
        c = Counter(f"{states[pn][k]} -> {states[cn][k]}" for k in states[cn] if states[pn][k] != states[cn][k])
        transitions[cn] = {"polarity": pol, "transitions": dict(sorted(c.items())),
                           "known_correct_lost (hazard)": sum(v for t, v in c.items() if t.startswith("1 ->"))}
    rows, res = {}, {}
    for b in comps:
        res[b] = {}
        for name, ev, pol, tpa, tpo in steps:
            _, rw = rows_for(data, pools, ev, "challenger", b, tpa)
            rows[(b, name)] = rw
            s = summarise(rw, n)
            rw_obs = [dict(r, exec_ok=any(not tpo.get(m, False) for m in r["members"])) for r in rw]
            s["refute"]["execution_observed"] = lim_json(limit(rw_obs, "refute", "execution"), n)
            if s["result"] == "open":
                s["open_unknown_classes"] = [
                    {"bug": r["bug"], "d_pp": ppf(r["d"], n), "conflict": r["conflict"], "archived_test_pass_all":
                     not r["exec_ok"]} for r in sorted(rw, key=lambda r: r["d"]) if r["y"] is None]
            res[b][name] = s
        prev = None
        for name, *_ in steps:
            if prev:
                res[b][name]["A0_change_by_transition"] = a0_decomposition(rows[(b, prev)], rows[(b, name)],
                                                                         states[prev], n)
            prev = name
    # cross-check against the decidability table
    ref = json.loads((ROOT / "results/v4/decidability/decidability.json").read_text())["defects4j"]["comparisons"]
    colmap = {"E0": "E0 archived", "E1": "E1 +census", "F2": "+F2 census top-up", "F3": "+F3 generated tests",
              "F4": "+F4 human review", "R": "Final (+R fix re-run)"}
    mism = [(r["b"], s) for r in ref for s, c in colmap.items()
            if not close([res[r["b"]][s]["L"], res[r["b"]][s]["H"]], r[c]["pp"])]
    # campaigns (pre-flight from each campaign's start state)
    klass_of = {m: (bug, i) for _, (bug, classes) in pools.items() for i, kl in enumerate(classes) for m in kl.members}
    f2_jobs = job_hours(ROOT / "results/v4/f2_topup_package_v1", ROOT / "results/v4/f2_topup_run_v1")
    f3_jobs = job_hours(ROOT / "results/v4/f3_tier1_package_v1", ROOT / "results/v4/f3_tier1_run_v1")
    r_jobs = job_hours(ROOT / "results/v4/c1_fixrerun_package_v1", ROOT / "results/v4/c1_fixrerun_run_v1")

    def at(step):
        return {b: rows[(b, step)] for b in comps}

    def decided(step):
        return sorted(b for b in comps if res[b][step]["result"] != "open")

    campaigns = {
        "census (E0 -> E1)": {"start": "E0", "end": "E1", "semantics": "execution (archived test-pass)",
                              **campaign_capability(at("E0"), "execution", {}, klass_of, n)},
        "F2 (E1 -> F2)": {"start": "E1", "end": "F2", "semantics": "execution (archived test-pass)",
                          **campaign_capability(at("E1"), "execution", f2_jobs, klass_of, n)},
        "F3 strict (F2 -> F3)": {"start": "F2", "end": "F3", "semantics": "candidate (conflict classes locked)",
                                 **campaign_capability(at("F2"), "candidate", f3_jobs, klass_of, n)},
        "F3 permissive (F2 -> F3)": {"start": "F2", "end": "F3", "semantics": "class (frozen F3 rule may overwrite conflict classes)",
                                     **campaign_capability(at("F2"), "class", f3_jobs, klass_of, n)},
    }
    campaigns["census (E0 -> E1)"]["hours"] = CENSUS_HOURS
    campaigns["census (E0 -> E1)"]["note"] = "census jobs not joined per job; hours from the cost ledger"
    for c in campaigns.values():
        c["decided_at_start"], c["decided_at_end"] = decided(c["start"]), decided(c["end"])
        c["newly_decided"] = sorted(set(c["decided_at_end"]) - set(c["decided_at_start"]))
    campaigns["R (F4 -> R)"] = {"start": "F4", "end": "R", "semantics": "retraction + confirmation (not refute-only)",
                                "jobs": len(r_jobs), "hours": round(sum(h for *_, h in r_jobs.values()), 3),
                                "decided_at_start": decided("F4"), "decided_at_end": decided("R"),
                                "newly_decided": sorted(set(decided("R")) - set(decided("F4")))}
    a0_inv = {b: len({res[b][s]["A0_exact"] for s in ("E0", "E1", "F2", "F3")}) == 1 for b in comps}
    return {"n_bugs": n, "comparisons": comps, "steps": {s[0]: s[2] for s in steps}, "results": res,
            "class_transitions": transitions, "A0_invariant_E0_to_F3": a0_inv,
            "A0_changes_at": {b: [s for p, s in zip(["E0", "E1", "F2", "F3", "F4"], ["E1", "F2", "F3", "F4", "R"])
                                  if res[b][p]["A0_exact"] != res[b][s]["A0_exact"]] for b in comps},
            "evidence_log": {"f2_witnesses_applied": log["f2_witnesses_applied"], "overwrites": len(log["overwrites"]),
                             "overwrites_by_source": dict(Counter(o["source"] for o in log["overwrites"]))},
            "test_pass_info": {"archived_test_passing_candidates": sum(tp_arch.values()), "candidates": len(tp_arch),
                               "census_status_counts": dict(Counter(census_status.values())),
                               "f2_status_counts": dict(Counter(f2_status.values()))},
            "decidability_crosscheck_mismatches": mism, "campaigns": campaigns}


# ===================================================================== G1

def g1():
    import g1_pools as G

    def ro_fp(texts):
        fp = {}
        for line in (G.G1 / "parser_cache.tsv").read_text(encoding="utf-8").splitlines():
            k, st, h = line.split("\t")
            fp[k] = h if st == "ok" else None
        missing = set(texts) - set(fp)
        if missing:
            raise RuntimeError(f"{len(missing)} G1 texts not in the parser cache; refusing to call java")
        return fp

    G.fingerprints = ro_fp
    import g1_analysis as GA
    from select_g1_f3_targets import g_e1
    data, _ = G.build(G.load_generations())
    G.register(data)
    pools = V.build_pools(data, "bug", "ast")
    n = len(data.bugs)
    e1, status = g_e1(data)
    items = json.loads((ROOT / "results/g1/f3_difftest/relevance_review.json").read_text())
    if any(i["verdict"] is None for i in items):
        raise ValueError("G1-F3 review incomplete")
    wit = {i["candidate_id"] for i in items if i["verdict"] == "witness"}
    klass_members = {m: kl.members for _, (_, cl) in pools.items() for kl in cl for m in kl.members}
    e2 = dict(e1)
    for k in wit:
        if {e2[m] for m in klass_members[k] if e2[m] is not None} - {0}:
            raise ValueError("G1-F3 witness in a known-correct class")
        for m in klass_members[k]:
            e2[m] = 0
    tp_e1 = {k: st == PASS for k, st in status.items()}  # re-running the same triggers cannot refute these
    comps = [G.P1] + [c for c in G.SECONDARY if c[0] in V.POLICIES and c[1] in V.POLICIES]
    steps = [("G-E0", data.e0, "reference matches + N-a (start)", None),
             ("G-E1", e1, "refute-only, candidate-level (tier P + tier S execution)", tp_e1),
             ("G-E2a", e2, "refute-only, class-level (G1-F3 generated tests; NOT the pre-registered G-E2)", tp_e1)]
    states = {s: class_states(pools, ev) for s, ev, *_ in steps}
    transitions = {}
    for (pn, *_), (cn, _, pol, _) in zip(steps[:-1], steps[1:]):
        c = Counter(f"{states[pn][k]} -> {states[cn][k]}" for k in states[cn] if states[pn][k] != states[cn][k])
        transitions[cn] = {"polarity": pol, "transitions": dict(sorted(c.items())),
                           "known_correct_lost (hazard)": sum(v for t, v in c.items() if t.startswith("1 ->"))}
    res, rows = {}, {}
    for a, b in comps:
        name = f"{a} vs {b}"
        res[name] = {}
        for s, ev, pol, tp in steps:
            if s == "G-E2a" and (a, b) != G.P1:
                continue
            _, rw = rows_for(data, pools, ev, a, b, tp)
            rows[(name, s)] = rw
            res[name][s] = summarise(rw, n)
            if s != "G-E0":
                # P1 negative unknown mass (the side refutation must clear) by execution status of the class
                by = defaultdict(lambda: [0, Fraction(0)])
                for r in rw:
                    if r["y"] is None and r["d"] < 0:
                        sts = {status[m] for m in r["members"] if m in status}
                        key = "+".join(sorted(sts)) if sts else "not_executed"
                        by[key][0] += 1
                        by[key][1] += -r["d"]
                res[name][s]["neg_unknown_by_execution_status"] = {k: {"classes": v[0], "pp": ppf(v[1], n)}
                                                                   for k, v in sorted(by.items())}
    ref = json.loads((ROOT / "results/g1/g1_final.json").read_text())
    ref_f3 = json.loads((ROOT / "results/g1/g1_f3_results.json").read_text())
    mism = []
    for view in ("G-E0", "G-E1"):
        for r in ref[view]:
            mine = res[f"{r['a']} vs {r['b']}"][view]
            if not close([mine["L"], mine["H"]], r["bounds_pp"]):
                mism.append((r["a"], r["b"], view))
    p1 = f"{G.P1[0]} vs {G.P1[1]}"
    if not close([res[p1]["G-E2a"]["L"], res[p1]["G-E2a"]["H"]], ref_f3["G-E2"]["bounds_pp"]):
        mism.append((G.P1[0], G.P1[1], "G-E2a"))
    klass_of = {m: (bug, i) for _, (bug, classes) in pools.items() for i, kl in enumerate(classes) for m in kl.members}
    jp = job_hours(G.G1 / "exec_tierP_package_v1", G.G1 / "exec_tierP_run_v1")
    js = job_hours(G.G1 / "exec_tierS_package_v1", G.G1 / "exec_tierS_run_v1")
    jf = job_hours(G.G1 / "f3_package_v1", G.G1 / "f3_run_v1")
    sec = [f"{a} vs {b}" for a, b in comps[1:]]
    campaigns = {
        "G1 tier P execution (G-E0 -> G-E1), P1": {
            "start": "G-E0", "end": "G-E1", "semantics": "candidate (no test-pass information before execution)",
            **campaign_capability({p1: rows[(p1, "G-E0")]}, "candidate", jp, klass_of, n)},
        "G1 tier S execution (G-E0 -> G-E1), secondaries": {
            "start": "G-E0", "end": "G-E1", "semantics": "candidate (no test-pass information before execution)",
            **campaign_capability({s: rows[(s, "G-E0")] for s in sec}, "candidate", js, klass_of, n)},
        "G1-F3 generated tests (G-E1 -> G-E2a), P1": {
            "start": "G-E1", "end": "G-E2a", "semantics": "class (generated tests; G1 has no conflict classes)",
            **campaign_capability({p1: rows[(p1, "G-E1")]}, "class", jf, klass_of, n)},
    }
    for c in campaigns.values():
        names = list(c["comparisons_open_at_start"])
        c["decided_at_end"] = sorted(x for x in names if res[x].get(c["end"], {}).get("result", "open") != "open")
    return {"n_bugs": n, "P1": p1, "results": res, "class_transitions": transitions,
            "witness_classes_G1F3": len(wit), "executed_representatives": len(status),
            "execution_status_counts": dict(Counter(status.values())),
            "crosscheck_mismatches": mism, "campaigns": campaigns}


# ===================================================================== HumanEval-Java (E3)

def humaneval():
    import e3_analysis as E
    from analysis_tools.evaluate_matched_baselines import METHODS, rows as jrows
    from review_humaneval_contract_replication import distributions, paired_bounds
    from validation_policy_contract import project_candidate
    cand = {r["candidate_id"]: r for r in jrows(E.SRC / "candidate_contract.jsonl")}
    decisions = list(jrows(E.SRC / "decisions.jsonl"))
    base = {k: {"correct": 1, "incorrect": 0, "unknown": None}[r["evidence"]["label"]] for k, r in cand.items()}
    legacy = defaultdict(list)
    for path in E.LEGACY:
        for row in jrows(path):
            legacy[project_candidate(row).candidate_id].append(row)
    equiv = {json.loads(line)["candidate_id"]: json.loads(line)["equivalent"]
             for line in open(E.OUT / "equivalence.jsonl", encoding="utf-8")}
    st = E.statuses()
    unknown = [k for k, v in base.items() if v is None]
    neg = lambda k: st.get(k, {}).get("status") in ("controlled_test_failure", "compile_command_failed_twice")  # noqa: E731
    passes = lambda k: st.get(k, {}).get("status") == "admissible_all_tests_pass"  # noqa: E731
    reviewed_correct = lambda k: {r["label"] for r in legacy[k]} == {"correct"}  # noqa: E731
    conflicts = {k for k in unknown if equiv.get(k) and neg(k)}

    def view(rule):  # copied from e3_analysis.main (the rules used below), unchanged
        ev = dict(base)
        for k in unknown:
            if rule == "X1":
                ev[k] = 0 if neg(k) else None
            elif rule == "X2":
                ev[k] = 1 if equiv.get(k) else None
            elif rule == "X4-posthoc":
                ev[k] = None if k in conflicts else 1 if equiv.get(k) else 0 if neg(k) else None
            elif rule == "HE-E1":
                if k in conflicts:
                    ev[k] = None
                elif equiv.get(k):
                    ev[k] = 1
                elif neg(k):
                    ev[k] = 0
                elif passes(k) and reviewed_correct(k):
                    ev[k] = 1
                else:
                    ev[k] = None
        return ev

    def arch_tp(k):  # archived: every record compiled and passed its tests
        vals = lambda f: {v for r in legacy[k] for v, c in (r.get(f) or {}).items() if c and v in ("true", "false")}  # noqa: E731
        return bool(legacy[k]) and vals("compile_values") == {"true"} and vals("test_values") == {"true"} and \
            not any(r.get("test_conflict") or r.get("compile_conflict") for r in legacy[k])

    tp = {k: arch_tp(k) for k in unknown}
    rules = [("archived", base, "archived contract labels (E3 rule 'A0')"),
             ("X1", view("X1"), "refute-only (execution failures -> incorrect)"),
             ("X2", view("X2"), "confirm-only (fix-equivalence -> correct)"),
             ("HE-E1", view("HE-E1"), "two-sided (pre-registered primary)"),
             ("X4-posthoc", view("X4-posthoc"), "two-sided (post hoc)")]
    nbug = len({d["bug_id"] for d in decisions})
    per_bug = Counter(d["bug_id"] for d in decisions)
    ref = json.loads((E.OUT / "e3_results.json").read_text())["comparisons"]
    res, mism = {}, []
    for m in METHODS:
        if m == "challenger":
            continue
        coef = defaultdict(Fraction)
        for d in decisions:
            pol = distributions(d)
            w = Fraction(1, per_bug[d["bug_id"]] * nbug)
            for k in set(pol["challenger"]) | set(pol[m]):
                coef[k] += w * (pol["challenger"].get(k, 0) - pol[m].get(k, 0))
        res[m] = {}
        for name, ev, pol in rules:
            rw = [{"key": k, "d": c, "y": ev[k], "conflict": False, "exec_ok": not tp.get(k, False)}
                  for k, c in coef.items() if c != 0]
            s = summarise(rw, 1)
            res[m][name] = s
            pb = paired_bounds(decisions, ev, "challenger", m)["equal_bug_bounds"]
            if not close([s["L"], s["H"]], [pb[0] * 100, pb[1] * 100], 6e-5):  # mine are rounded to 4 decimals
                mism.append((m, name, "paired_bounds"))
            key = {"archived": "A0"}.get(name, name)
            if key in ref and not close([s["L"], s["H"]], ref[key][m]["equal_bug_pp"], 0.006):
                mism.append((m, name, "e3_results"))
    return {"note": "candidate-level labels (no identity classes, no known-wins lock; the rules leave fix-equivalent "
                    "but failing candidates unknown, and X1 refutes regardless of the archived-unknown reason)",
            "rules": {r[0]: r[2] for r in rules}, "results": res, "crosscheck_mismatches": mism,
            "archived_test_passing_unknowns": sum(tp.values()), "unknown_candidates": len(unknown),
            "equivalent_but_failing": len(conflicts)}


def repairbench():
    rb = json.loads((ROOT / "results/v4/repairbench/repairbench_v4.json").read_text())
    return [{"a": p["a"], "b": p["b"], "bounds_pp": p["budget_one_pp"], "A0": p["all_unknown_incorrect_pp"],
             "A1": p["all_unknown_correct_pp"], "identified": p["identified"],
             "decision_sign_matches_A0": (None if not p["identified"] else
                                          (p["budget_one_pp"][0] > 0) == (p["all_unknown_incorrect_pp"] > 0))}
            for p in rb["pairs"]]


# ===================================================================== report

def fmt(x):
    return "-" if x is None else f"{x:+.2f}"


def lim_cell(r):
    if r["status"].startswith("decided"):
        return "decided"
    if r["status"].startswith("reachable"):
        return f"yes ({r['status'][-1]}), k={r['k_min']}/{r['helpful_classes']}"
    return "no" + (" (A0=0)" if "anchor = 0" in r["status"] else " (locked)")


def report(res):
    D, G, HE = res["defects4j"], res["g1"], res["humaneval"]
    L = ["# Refutation limit: what one-sided evidence can decide", "",
         "Post hoc, read-only analysis of evidence already collected (novelty panel C1). Script: "
         "`analysis_tools/v4/refutation_limit.py`; brute-force test: `analysis_tools/v4/test_refutation_limit.py`. "
         "Numbers are percentage points (challenger minus baseline for Defects4J), equal-bug weights, AST identity, "
         "known-wins, N-a.", "",
         "## The proposition (an operational pre-flight check, not a new theorem)", "",
         "Every comparison has a lower bound L and an upper bound H, taken over all ways the unknown patch labels "
         "could turn out. Two completions matter here. A0 is the value when every unknown class is incorrect. "
         "A1 is the value when every unknown class is correct. Both are taken after the N-a no-op rule.", "",
         "**Claim.** Evidence that can only mark unknown patches incorrect (re-execution, the census, F2, generated "
         "tests, G1 execution) never changes A0. Each step moves [L, H] towards A0. So such evidence can decide a "
         "comparison only in the direction of sign(A0). It can never decide one with A0 = 0. Confirm-only evidence "
         "does the same thing with A1.", "",
         "**Why.** A0 is computed only from classes whose label is known: it is the sum of d times y over those "
         "classes. Refuting an unknown class changes its label from unknown to 0, and it contributed 0 to A0 before "
         "as well, so A0 stays the same. If that class has d < 0, L goes up by |d|. If it has d > 0, H goes down by d. "
         "So L <= A0 <= H holds at every state, and refuting every refutable class gives the limit. "
         "Each refutation moves the bound by its own |d|, and the moves simply add up. So taking the largest |d| "
         "first gives the exact minimum number of refutations. This is the same argument as "
         "`breakdown.minimal_count`.", "",
         "**Two conditions.** First, the refutation must not hit a class that is already known correct. "
         "Under known-wins, such a hit would make the class unknown and lower A0 (for a no-op class, the N-a rule "
         "would even turn it into 0). The script counts these cases in the hazard column below. Second, some classes are *conflict-locked*: their identical members carry both a 0 and a 1 "
         "in the archive. Adding more 0s to single candidates (census, F2, G1 execution) cannot resolve such a class. "
         "The candidate-level limit is therefore [A0 + sum over locked classes of min(0, d), A0 + sum over locked "
         "classes of max(0, d)]. Only a class-level rule can resolve a locked class: the frozen F3 rule and F4 may "
         "overwrite one, and R removes archived 0s. The *execution ceiling* also locks the classes whose members all "
         "passed their tests in the archive. Re-running the same tests cannot refute them; only new tests can.", "",
         "**Positioning.** This is the closed-world, worst-case completion. A0 is the base score of rank-biased "
         "precision, where unjudged items count as non-relevant, and A1 is base plus residual (Moffat & Zobel, TOIS "
         "2008). A0 and A1 are also Manski's worst-case and best-case completions (2003). Carterette, Allan & "
         "Sitaraman's minimal test collections (SIGIR 2006) pick the judgments that decide a pairwise difference, "
         "but with two-sided judgments. What we add is an operational use. We tag each evidence source by polarity "
         "(refute, confirm, retract), apply the label-conflict rule, and compute before any container time is spent "
         "which open comparisons a planned campaign can decide at all, and with how many refutations at least. "
         "Everything here is post hoc: the check was not run before the campaigns.", ""]
    # ---- A0 per step
    steps = list(D["steps"])
    L += ["## Defects4J: A0 at every evidence step (16 comparisons)", "",
          "Layers: " + "; ".join(f"**{s}** = {p}" for s, p in D["steps"].items()) + ".", "",
          "| Baseline | " + " | ".join(f"A0 {s}" for s in steps) + " | A0 constant E0..F3 | [L, H] at E0 | [L, H] at R |",
          "|---|" + "---|" * (len(steps) + 3)]
    for b in D["comparisons"]:
        r = D["results"][b]
        L.append(f"| {b} | " + " | ".join(fmt(r[s]["A0"]) for s in steps) +
                 f" | {'yes' if D['A0_invariant_E0_to_F3'][b] else 'NO'} | [{fmt(r['E0']['L'])}, {fmt(r['E0']['H'])}]"
                 f"{'*' if r['E0']['result'] != 'open' else ''} | [{fmt(r['R']['L'])}, {fmt(r['R']['H'])}]"
                 f"{'*' if r['R']['result'] != 'open' else ''} |")
    moved = Counter(s for v in D["A0_changes_at"].values() for s in v)
    L += ["", f"A0 is constant from E0 to F3 for {sum(D['A0_invariant_E0_to_F3'].values())}/{len(D['comparisons'])} "
              f"comparisons. Steps at which A0 moved (number of comparisons): {dict(moved)}. * = decided.", "",
          "### Class-level transitions per layer (all AST classes in the pool, raw known-wins labels)", "",
          "| Step | Polarity | Transitions | Known-correct classes lost (hazard) |", "|---|---|---|---|"]
    for s, t in D["class_transitions"].items():
        L.append(f"| {s} | {t['polarity']} | " + ", ".join(f"{k}: {v}" for k, v in t["transitions"].items()) +
                 f" | {t['known_correct_lost (hazard)']} |")
    L += ["", f"Overwrites of conflict classes recorded by final_evidence: {D['evidence_log']['overwrites_by_source']}. "
              f"F3 overwrote {D['evidence_log']['overwrites_by_source'].get('F3', 0)} conflict classes, so the strict and "
              "permissive readings of F3 coincide in what F3 actually did.", "",
          "Where each comparison's A0 change at F4 and R came from, by class transition (pp, number of classes in "
          "brackets; 'conflict' = the class was conflict-locked at the previous step):", "",
          "| Baseline | F4 | R |", "|---|---|---|"]
    for b in D["comparisons"]:
        cells = []
        for s in ("F4", "R"):
            dec = D["results"][b][s].get("A0_change_by_transition", {})
            cells.append("; ".join(f"{k}: {v['dA0_pp']:+.3f} ({v['classes']})" for k, v in dec.items()
                                   if v["dA0_pp"] != 0) or "0")
        L.append(f"| {b} | {cells[0]} | {cells[1]} |")
    # ---- limits at E0 and at each campaign start
    L += ["", "## Defects4J: refute-only and confirm-only limits", "",
          "k = minimum refutations (or confirmations) / helpful classes available. 'strict' = candidate-level "
          "(conflict-locked); 'permissive' = class-level; 'exec ceiling' = candidate-level and only classes with a "
          "member not archived as test-passing; 'exec obs.' also locks classes whose triggers passed when the "
          "census/F2 re-ran them.", ""]
    for s in ("E0", "E1", "F2", "F3", "F4"):
        open_b = [b for b in D["comparisons"] if D["results"][b][s]["result"] == "open"]
        L += [f"### Open at {s} ({len(open_b)})", "",
              "| Baseline | [L, H] | A0 | A1 | locked conflict classes | strict limit | refute strict | refute permissive | "
              "exec ceiling | exec obs. | confirm strict |", "|---|---|---|---|---|---|---|---|---|---|---|"]
        for b in open_b:
            r = D["results"][b][s]
            st = r["refute"]["candidate"]
            L.append(f"| {b} | [{fmt(r['L'])}, {fmt(r['H'])}] | {fmt(r['A0'])} | {fmt(r['A1'])} | "
                     f"{r['conflict_unknown_classes']} | [{fmt(st['L_best'])}, {fmt(st['H_best'])}] | {lim_cell(st)} | "
                     f"{lim_cell(r['refute']['class'])} | {lim_cell(r['refute']['execution'])} | "
                     f"{lim_cell(r['refute']['execution_observed'])} | {lim_cell(r['confirm']['candidate'])} |")
        L.append("")
    # ---- G1
    L += ["## G1 fresh campaign", "",
          "G-E2a is the generated-test-only view (G1-F3). It is NOT the pre-registered G-E2 (F3 plus blinded review), "
          "which was not completed.", "",
          "| Comparison | View | [L, H] | A0 | A1 | refute limit (strict) | refute: reachable? k | share of helpful mass "
          "needed | exec ceiling | confirm: k |", "|---|---|---|---|---|---|---|---|---|---|"]
    for name, rs in G["results"].items():
        for v, r in rs.items():
            st = r["refute"]["candidate"]
            share = st.get("share_of_helpful_mass_needed")
            L.append(f"| {name} | {v} | [{fmt(r['L'])}, {fmt(r['H'])}] | {r['A0']:+.4f} | {fmt(r['A1'])} | "
                     f"[{st['L_best']:+.4f}, {st['H_best']:+.4f}] | {lim_cell(st)} | "
                     f"{'-' if share is None else f'{100 * share:.1f}%'} | {lim_cell(r['refute']['execution'])} | "
                     f"{lim_cell(r['confirm']['candidate'])} |")
    p1 = G["results"][G["P1"]]
    L += ["", f"P1 negative unknown mass by execution status at G-E1: " +
          ", ".join(f"{k}: {v['classes']} classes, {v['pp']:.2f} pp" for k, v in
                    p1["G-E1"]["neg_unknown_by_execution_status"].items()) + ".",
          f"At G-E2a: " + ", ".join(f"{k}: {v['classes']} classes, {v['pp']:.2f} pp" for k, v in
                                    p1["G-E2a"]["neg_unknown_by_execution_status"].items()) + ".", "",
          "Class transitions: " + "; ".join(f"{s}: {t['transitions']} (hazard {t['known_correct_lost (hazard)']})"
                                           for s, t in G["class_transitions"].items()) + "."]
    # ---- HumanEval
    L += ["", "## HumanEval-Java (E3)", "", HE["note"] + ".", "",
          "| Baseline | View | [L, H] | A0 | A1 | refute: reachable? k | exec ceiling | confirm: reachable? k |",
          "|---|---|---|---|---|---|---|---|"]
    for m, rs in HE["results"].items():
        for v, r in rs.items():
            L.append(f"| {m} | {v} | [{fmt(r['L'])}, {fmt(r['H'])}] | {fmt(r['A0'])} | {fmt(r['A1'])} | "
                     f"{lim_cell(r['refute']['candidate'])} | {lim_cell(r['refute']['execution'])} | "
                     f"{lim_cell(r['confirm']['candidate'])} |")
    inv_x1 = all(rs["archived"]["A0_exact"] == rs["X1"]["A0_exact"] for rs in HE["results"].values())
    inv_x2 = all(rs["archived"]["A1_exact"] == rs["X2"]["A1_exact"] for rs in HE["results"].values())
    L += ["", f"A0 unchanged archived -> X1 (refute-only) for every baseline: {inv_x1}. "
              f"A1 unchanged archived -> X2 (confirm-only): {inv_x2}."]
    # ---- RepairBench
    L += ["", "## RepairBench (from repairbench_v4.json; conflict classes not recomputed)", "",
          "| Pair | bounds | A0 | A1 | decided | decision sign = sign(A0) |", "|---|---|---|---|---|---|"]
    for p in res["repairbench"]:
        L.append(f"| {p['a']} vs {p['b']} | [{p['bounds_pp'][0]:+.2f}, {p['bounds_pp'][1]:+.2f}] | {p['A0']:+.2f} | "
                 f"{p['A1']:+.2f} | {p['identified']} | {p['decision_sign_matches_A0']} |")
    # ---- pre-flight
    L += ["", "## Pre-flight table: could each refute-only campaign decide what was open at its start?", "",
          "Formal reach from the start state, under the campaign's semantics. 'k' = minimum refutations / helpful "
          "classes. 'Capable hours' = container-hours of jobs that touch at least one class able to move a "
          "comparison that the campaign could decide. This is relative to the decision objective only: the campaigns "
          "also tightened comparisons that were already decided, so the rest is not waste.", "",
          "'Bug-level join' counts every job in a bug that holds such a class, even if the job targeted other classes.", "",
          "| Campaign | Semantics | Open at start: reach (k) | Newly decided | Jobs | Hours | Capable jobs / hours "
          "(class join) | Bug-level join |",
          "|---|---|---|---|---|---|---|---|"]
    camps = {**D["campaigns"], **G["campaigns"]}
    for name, c in camps.items():
        if "comparisons_open_at_start" in c:
            reach = "; ".join(f"{b}: {('yes ' + v['status'][-1] + ' k=' + str(v['k_min']) + '/' + str(v['helpful_classes'])) if v['k_min'] is not None else ('no, A0=0' if 'anchor = 0' in v['status'] else 'no, locked')}"
                              for b, v in c["comparisons_open_at_start"].items())
            newly = c.get("newly_decided", c.get("decided_at_end"))
            cap = (f"{c['jobs_able_to_move_a_decidable_comparison']} / {c['hours_able_to_move_a_decidable_comparison']:.2f} h"
                   if c["jobs"] else "not joined")
            bj = c["bug_level_join"]
            bjs = (f"{bj['jobs']} / {bj['hours']:.2f} h" if c["jobs"] else "not joined")
            L.append(f"| {name} | {c['semantics']} | {reach} | {', '.join(newly) or 'none'} | {c['jobs'] or '-'} | "
                     f"{c['hours']:.2f} | {cap} | {bjs} |")
        else:
            L.append(f"| {name} | {c['semantics']} | n/a (not refute-only) | {', '.join(c['newly_decided']) or 'none'} | "
                     f"{c['jobs']} | {c['hours']:.2f} | n/a | n/a |")
    he_open = [m for m, rs in HE["results"].items() if rs["archived"]["result"] == "open"]
    L += ["", "HumanEval-Java, comparisons open at the archived labels (E3 tier A/B hours are not in the cost ledger "
              "used here):", "",
          "| Baseline | A0 | refute-only (k) | exec ceiling (k) | decided by X1 (refute-only part of E3) | "
          "decided by X2 (confirm-only part) | decided by HE-E1 |", "|---|---|---|---|---|---|---|"]
    for m in he_open:
        rs = HE["results"][m]
        L.append(f"| {m} | {fmt(rs['archived']['A0'])} | {lim_cell(rs['archived']['refute']['candidate'])} | "
                 f"{lim_cell(rs['archived']['refute']['execution'])} | {rs['X1']['result']} | {rs['X2']['result']} | "
                 f"{rs['HE-E1']['result']} |")
    L += ["", "## Choices and caveats", "",
          "- Archived test-pass (execution ceiling, Defects4J): a candidate counts as test-passing when every archived "
          "record of it compiled and passed its tests (`run_evidence_pilot_step2.load_inputs`, compile = 1 and "
          "test_given_compile = 1). A class is refutable by re-execution if at least one member is not test-passing "
          "in that sense; that includes members with no or conflicting archived outcomes. "
          "'exec obs.' also treats candidates whose triggers passed in the census or F2 as unrefutable by re-execution.",
          "- G1: before execution there is no test-pass information (G-E0 execution ceiling = strict limit). From G-E1 "
          "on, a class is unrefutable by re-execution when its executed representative passed its triggers "
          f"({PASS}). HumanEval: a candidate is test-passing when all its legacy records compiled and passed and none "
          "is flagged as a compile/test conflict.",
          "- F3 semantics: the frozen F3 rule sets whole classes and may overwrite conflict classes, so the "
          "'permissive' (class) reading is what F3 actually did. The 'strict' reading respects accepted-correct "
          "labels. R is tagged retraction + confirmation, not as refute-only or plain positive evidence.",
          "- Hours: F2, F3, R and G1 from terminal.json 'seconds' joined to package jobs.json; census 16.0 h from the "
          "cost ledger (not joined per job). Capable hours count whole bug jobs.",
          "- Several 'predictions' are guaranteed by the arithmetic. The check flags futility in advance; it is not a "
          "forecast with a hit rate. Everything is post hoc and computed by Claude; not yet checked by a human."]
    return "\n".join(L) + "\n"


def to_jsonable(o):
    if isinstance(o, Fraction):
        return float(o)
    if isinstance(o, tuple):
        return list(o)
    raise TypeError(type(o))


def main():
    read_only_guards()
    OUT.mkdir(parents=True, exist_ok=True)
    res = {"status": "post hoc, read-only (novelty panel C1)"}
    res["defects4j"] = d4j()
    print("D4J done; cross-check mismatches:", res["defects4j"]["decidability_crosscheck_mismatches"], flush=True)
    res["g1"] = g1()
    print("G1 done; cross-check mismatches:", res["g1"]["crosscheck_mismatches"], flush=True)
    res["humaneval"] = humaneval()
    print("HumanEval done; cross-check mismatches:", res["humaneval"]["crosscheck_mismatches"], flush=True)
    res["repairbench"] = repairbench()
    (OUT / "refutation_limit.json").write_text(json.dumps(res, indent=1, default=to_jsonable), encoding="utf-8")
    (OUT / "REFUTATION_LIMIT.md").write_text(report(res), encoding="utf-8")
    D = res["defects4j"]
    for b in D["comparisons"]:
        print(f"{b:20s} A0 " + " ".join(f"{s}:{D['results'][b][s]['A0']:+.3f}" for s in D["steps"]))
    print(json.dumps({k: v for k, v in D["campaigns"].items()}, indent=1, default=str)[:4000])


if __name__ == "__main__":
    main()
