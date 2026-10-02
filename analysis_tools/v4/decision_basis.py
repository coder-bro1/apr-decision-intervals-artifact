"""Decision basis of every decided Defects4J comparison (novelty panel 2026-10-01, item C3-lite).

For each of the 16 comparisons (challenger vs each baseline in select_f2_topup.BASELINES), under the final view
(E1+F2+F3+F4+R: bug unit, AST identity, known-wins, N-a, equal-bug weights), every class with a known label adds its
own, independent gain to the lower bound:
    g_i = s*d_i*y_i - min(0, s*d_i) >= 0,     s = sign of the decision,
so the bound with every label unknown is A = sum_i min(0, s*d_i), and s*L = A + sum_i g_i.
A *decision basis* is a set S of known labels with A + sum_{i in S} g_i > 0: if the labels in S are correct, the
decision holds whatever every other label is. Minimal bases are not unique; this script reports *a* basis built by
one deterministic rule (below).

Source of a class label (tiers, most trustworthy first):
  T1 reference identity   archived exact/AST match to the developer fix (provenance.basis_map 'ref')
  T2 execution failure    archived harness failure ('exec'), census witness (E1), F2 witness
  R  post-hoc re-run      labels set by the R layer: a fix-identical re-run that removed a contradicting archived
                          failure, or the C1-fix rule (rename-aware equivalence to the developer fix). Kept as its own
                          tier, placed between T2 and T3.
  T3 human judgment       archived reviewers ('human': two-reviewer agreement or third-reviewer tiebreak) and F4
  T4 F3                   generated-test reference-behavior witness
  T5 no-op rule           label supplied only by N-a (no-op class with no known label -> incorrect)
A class label comes from the layer that made it known and kept it (the earliest step from which the raw class label
equals its final value), plus any later member labels that agree with it; the class takes the most trustworthy of
those sources. A class whose raw label is unknown but is labelled by N-a is T5.

Basis rule (deterministic): minimise the count from the least trustworthy tier first, then the next, and so on
(T5, T4, T3, R, T2, T1). At each tier, all labels of the not-yet-processed (more trustworthy) tiers are assumed
available; the tier contributes its k highest-gain labels (ties: bug id, class index), k the smallest number that
keeps A + gains > 0. The result is inclusion-minimal, and its count in the least trustworthy tier it uses is the
minimum over all bases. Also reported: whether each tier is *necessary* (the decision fails with every other label).

Margin: smallest number of known labels whose flip reopens the decision (as decidability_table.flips_to_reopen).
eps* = L / sum of all gains (break-even random error rate). Exploratory, post hoc analysis.
Writes results/v4/decision_basis/decision_basis.json, decision_basis_members.json and DECISION_BASIS.md.
Read-only elsewhere: the c1_equivalence tool cache must already match (no tool run, nothing else is written)."""
import csv
import json
import sys
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import c1_equivalence as C  # noqa: E402

_run_tool = C.run_tool


def _cached_only(cmd, texts, name):
    """Refuse to (re)run the javac tools: the cached output must match the input hash, so nothing is written."""
    import base64
    import hashlib
    body = "".join(k + "\t" + base64.b64encode(t.encode()).decode() + "\n" for k, t in sorted(texts.items()))
    stamp = C.OUT / f"{name}_input.sha256"
    if not (stamp.exists() and stamp.read_text() == hashlib.sha256(body.encode()).hexdigest()):
        raise RuntimeError(f"c1_equivalence cache for {name} is stale; refusing to rewrite it")
    return _run_tool(cmd, texts, name)


C.run_tool = _cached_only

import v4core as V  # noqa: E402
import final_evidence as FE  # noqa: E402
import c1_fixrerun_analysis as CF  # noqa: E402
import breakdown as BD  # noqa: E402
import provenance as P  # noqa: E402
from select_f2_topup import BASELINES  # noqa: E402

OUT = ROOT / "results/v4/decision_basis"
DECIDABILITY = ROOT / "results/v4/decidability/decidability.json"
KEY = ROOT / "results/v4/annotation_key/KEY_private.json"
ANSWERS = [ROOT / f"results/v4/annotation_simple/ANSWERS_reviewer{i}.csv" for i in (1, 2)]

TIERS = ["T1", "T2", "R", "T3", "T4", "T5"]  # most trustworthy first
TIER_NAME = {"T1": "reference identity", "T2": "execution failure", "R": "R (fix re-run / C1-fix)",
             "T3": "human judgment", "T4": "F3 generated test", "T5": "no-op rule"}
SOURCE_TIER = {"ref": "T1", "exec": "T2", "census": "T2", "F2": "T2", "R": "R", "human": "T3", "F4": "T3",
               "F3": "T4", "noop": "T5"}
STEPS = ["E0", "census", "F2", "F3", "F4", "R"]


def flips_to_reopen(items, L):
    """items: (d, y) known labels, s = +1 assumed by caller orientation. Same rule as decidability_table."""
    k, _ = BD.minimal_count([x for x in (d * (1 - 2 * y) for d, y in items) if x < 0], L)
    return k if k is not None else "not possible"


def lexicographic_basis(base, gains_by_tier):
    """gains_by_tier: {tier: [(g, key)]}. Weakest tier first; returns {tier: [keys]} or None if undecided."""
    total = base + sum(g for lst in gains_by_tier.values() for g, _ in lst)
    if total <= 0:
        return None
    chosen, fixed = {}, Fraction(0)
    for t in reversed(TIERS):
        stronger = sum(g for tt in TIERS[:TIERS.index(t)] for g, _ in gains_by_tier.get(tt, []))
        acc = base + fixed + stronger
        picked = []
        for g, key in sorted(gains_by_tier.get(t, []), key=lambda x: (-x[0], x[1])):
            if acc > 0:
                break
            acc += g
            fixed += g
            picked.append(key)
        assert acc > 0
        chosen[t] = picked
    return chosen


def main():
    built = CF.build()
    data, pools = built["data"], built["ast_pools"]
    views, _ = FE.build(data, pools)
    evs = {"E0": data.evidence("E0"), "census": views["E1"], "F2": views["E1+F2"], "F3": views["E1+F2+F3"],
           "F4": views["E1+F2+F3+F4"], "R": built["R"]}
    n = len(data.bugs)
    basis_occ, _ = P.basis_map(data)
    arch = P.load_archive()
    legacy = {r["candidate_id"]: r["legacy_candidate_ids"] for r in V.jsonl(V.INPUTS["evaluation_evidence"])}
    classes_of = {b: cl for b, (_, cl) in pools.items()}

    # member-level: step at which each occurrence's label last changed
    last_change = {}
    for m in data.occ:
        st = "E0"
        for prev, cur in zip(STEPS[:-1], STEPS[1:]):
            if evs[cur][m] != evs[prev][m]:
                st = cur
        last_change[m] = st
    member_source = {"census": "census", "F2": "F2", "F3": "F3", "F4": "F4", "R": "R"}

    src_cache = {}

    def class_source(bug, i):
        """Returns (tier, sources set, origin step) of the final label of class (bug, i)."""
        if (bug, i) in src_cache:
            return src_cache[(bug, i)]
        kl = classes_of[bug][i]
        raw = {s: V.class_label(kl.members, evs[s], "known_wins")[0] for s in STEPS}
        y = raw["R"]
        if y is None:
            res = ("T5", {"noop"}, None)
        else:
            t = len(STEPS) - 1
            while t > 0 and raw[STEPS[t - 1]] == y:
                t -= 1
            origin = STEPS[t]
            srcs = set() if origin == "E0" else {member_source[origin]}
            for m in kl.members:
                if evs["R"][m] == y and STEPS.index(last_change[m]) >= t:
                    srcs.add(basis_occ[m] if last_change[m] == "E0" else member_source[last_change[m]])
            unknown = srcs - set(SOURCE_TIER)
            if unknown:
                raise ValueError(f"unmapped label source {unknown} for {bug}#{i}")
            tier = min((SOURCE_TIER[s] for s in srcs), key=TIERS.index)
            res = (tier, srcs, origin)
        src_cache[(bug, i)] = res
        return res

    def archived_provenance(bug, i, y):
        prov, recs = Counter(), 0
        for m in classes_of[bug][i].members:
            if evs["R"][m] == y and basis_occ.get(m) == "human":
                for old in legacy[m]:
                    r = arch[old]
                    if r["label"] == ("correct" if y == 1 else "incorrect"):
                        prov.update(r["reviewer_provenance_statuses"])
                        recs += 1
        return ("tiebreak" if prov.get("third_reviewer_tiebreak") else "agreement"), recs, dict(prov)

    # F5 audit items (accepted human-judged labels; strata accepted-correct / accepted-incorrect)
    key = json.loads(KEY.read_text())
    answers = []
    for p in ANSWERS:
        with open(p, encoding="utf-8-sig") as f:
            answers.append({r["id"]: r["verdict"] for r in csv.DictReader(f)})
    klass_idx = {m: (bug, i) for bug, cl in classes_of.items() for i, kl in enumerate(cl) for m in kl.members}
    f5 = {}
    for it in key["items"]:
        if it["set"] != "F5":
            continue
        v = {a[it["id"]] for a in answers}
        verdict = next(iter(v)) if len(v) == 1 else "annotators differ"
        acc = it["existing_label"]
        disputed = verdict in ("correct", "incorrect") and ({"correct": 1, "incorrect": 0}[verdict] != acc)
        f5[klass_idx[it["candidate_id"]]] = {"id": it["id"], "accepted": acc, "verdict": verdict,
                                             "disputed": disputed}

    dec_ref = {r["b"]: r for r in json.loads(DECIDABILITY.read_text())["defects4j"]["comparisons"]}

    rows, members_out = [], {}
    for b in BASELINES:
        if b not in V.POLICIES:
            continue
        units, _ = V.evaluate_pair(data, pools, evs["R"], "challenger", b)
        L, H = sum(u.lo for u in units), sum(u.hi for u in units)
        s = 1 if L > 0 else -1 if H < 0 else 0
        row = {"b": b, "interval_pp": [V.pp(L / n), V.pp(H / n)], "L_exact": str(L / n), "H_exact": str(H / n)}
        ref = dec_ref[b]["Final (+R fix re-run)"]["pp"]
        assert [round(x, 3) for x in row["interval_pp"]] == ref, (b, row["interval_pp"], ref)
        if s == 0:
            row["decided"] = False
            rows.append(row)
            continue
        sL = L if s > 0 else -H
        coeffs = [(u.bug, i, d, y) for u in units for d, y, i in u.coeffs]
        base = sum(min(Fraction(0), s * d) for _, _, d, _ in coeffs)
        gains_by_tier, src_by_key, fav = defaultdict(list), {}, Counter()
        known = []
        for bug, i, d, y in coeffs:
            if y is None:
                continue
            known.append((s * d, y))
            g = s * d * y - min(Fraction(0), s * d)
            tier, srcs, origin = class_source(bug, i)
            src_by_key[(bug, i)] = (tier, srcs, origin, y, d, g)
            if g > 0:
                gains_by_tier[tier].append((g, (bug, i)))
                fav[tier] += 1
        total_gain = sum(g for lst in gains_by_tier.values() for g, _ in lst)
        assert base + total_gain == sL, b
        chosen = lexicographic_basis(base, gains_by_tier)
        basis_keys = [k for t in TIERS for k in chosen[t]]
        basis_gain = sum(src_by_key[k][5] for k in basis_keys)
        # necessity and sufficiency of tiers
        necessary = {t: base + total_gain - sum(g for g, _ in gains_by_tier.get(t, [])) <= 0 for t in TIERS}
        prefix_needed = next(TIERS[j] for j in range(len(TIERS))
                             if base + sum(g for t in TIERS[:j + 1] for g, _ in gains_by_tier.get(t, [])) > 0)
        t12_alone = base + sum(g for t in ("T1", "T2") for g, _ in gains_by_tier.get(t, [])) > 0
        human = []
        for k in chosen["T3"]:
            tier, srcs, origin, y, d, g = src_by_key[k]
            h = {"bug": k[0], "class_index": k[1], "representative": min(classes_of[k[0]][k[1]].members),
                 "label": "correct" if y == 1 else "incorrect", "gain_pp": V.pp(g / n),
                 "source": "F4" if "F4" in srcs else "archived"}
            if h["source"] == "archived":
                h["archived_review"], h["supporting_records"], h["review_status_counts"] = \
                    archived_provenance(k[0], k[1], y)
                h["f5_stratum"] = "accepted-correct" if y == 1 else "accepted-incorrect"
            if k in f5:
                h["in_f5_sample"] = f5[k]
            human.append(h)
        flips = flips_to_reopen(known, sL)
        flips_basis = flips_to_reopen([(s * src_by_key[k][4], src_by_key[k][3]) for k in basis_keys], sL)
        dec_flips = dec_ref[b]["robustness"]["label_flips_to_reopen_any"]
        # F5-disputed labels flipped together
        dl_f5 = sum(s * src_by_key[k][4] * (1 - 2 * src_by_key[k][3]) for k, v in f5.items()
                    if v["disputed"] and k in src_by_key)
        row.update({
            "decided": True, "sign": s,
            "all_unknown_bound_pp": V.pp(base / n),
            "favourable_labels_by_tier": {t: fav[t] for t in TIERS},
            "basis_size_by_tier": {t: len(chosen[t]) for t in TIERS},
            "basis_size": len(basis_keys),
            "L_with_basis_only_pp": V.pp((base + basis_gain) / n),
            "weakest_tier_needed": prefix_needed,
            "rests_on_reference_and_execution_only": t12_alone,
            "tier_necessary": necessary,
            "needs_F3": len(chosen["T4"]) > 0, "needs_noop_rule": len(chosen["T5"]) > 0,
            "needs_R": len(chosen["R"]) > 0,
            "human_judgments": human,
            "human_archived": sum(h["source"] == "archived" for h in human),
            "human_F4": sum(h["source"] == "F4" for h in human),
            "flips_to_reopen": flips, "flips_to_reopen_decidability_json": dec_flips,
            "flips_to_reopen_within_basis": flips_basis,
            "sum_of_gains_pp": V.pp(total_gain / n),
            "eps_star": round(float(sL / total_gain), 6),
            "L_change_if_all_F5_disputed_flipped_pp": V.pp(dl_f5 / n),
        })
        assert flips == dec_flips, (b, flips, dec_flips)
        members_out[b] = {t: [f"{k[0]}#{k[1]}" for k in chosen[t]] for t in TIERS}
        rows.append(row)
        print(f"{b:20s} [{row['interval_pp'][0]:+.3f},{row['interval_pp'][1]:+.3f}] basis "
              f"{row['basis_size_by_tier']} human {len(human)} (arch {row['human_archived']}, F4 {row['human_F4']}) "
              f"T1+T2 alone {t12_alone} flips {flips} eps* {row['eps_star']:.4f}", flush=True)

    dec = [r for r in rows if r.get("decided")]
    hum = defaultdict(lambda: {"comparisons": []})
    for r in dec:
        for h in r["human_judgments"]:
            e = hum[(h["bug"], h["class_index"])]
            e.update({k: v for k, v in h.items() if k != "gain_pp"})
            e["comparisons"].append(r["b"])
    hum_list = sorted(hum.values(), key=lambda e: (e["bug"], e["class_index"]))
    arch_h = [e for e in hum_list if e["source"] == "archived"]
    summary = {
        "decided": len(dec), "n": len(rows),
        "rest_on_reference_and_execution_only": [r["b"] for r in dec if r["rests_on_reference_and_execution_only"]],
        "need_human": {r["b"]: len(r["human_judgments"]) for r in dec if r["human_judgments"]},
        "need_R_in_basis": [r["b"] for r in dec if r["needs_R"]],
        "R_tier_necessary": [r["b"] for r in dec if r["tier_necessary"]["R"]],
        "human_tier_necessary": [r["b"] for r in dec if r["tier_necessary"]["T3"]],
        "need_F3": [r["b"] for r in dec if r["needs_F3"]],
        "need_noop_rule": [r["b"] for r in dec if r["needs_noop_rule"]],
        "distinct_human_classes": len(hum_list),
        "distinct_human_bugs": len({e["bug"] for e in hum_list}),
        "archived": len(arch_h), "F4": sum(e["source"] == "F4" for e in hum_list),
        "archived_by_label": dict(Counter(e["label"] for e in arch_h)),
        "archived_by_review": dict(Counter(e["archived_review"] for e in arch_h)),
        "archived_by_f5_stratum": dict(Counter(e["f5_stratum"] for e in arch_h)),
        "F4_by_label": dict(Counter(e["label"] for e in hum_list if e["source"] == "F4")),
        "load_bearing_for_several": [{"bug": e["bug"], "class_index": e["class_index"], "source": e["source"],
                                      "label": e["label"], "comparisons": e["comparisons"]}
                                     for e in hum_list if len(e["comparisons"]) > 1],
        "load_bearing_in_f5_sample": [e for e in hum_list if "in_f5_sample" in e],
        "f5_disputed_labels": sum(v["disputed"] for v in f5.values()),
    }
    res = {"status": "exploratory, post hoc (designed after the final results were known)",
           "view": "final Defects4J evidence E1+F2+F3+F4+R; bug unit, AST identity, known-wins, N-a, equal-bug",
           "basis_rule": "a basis, not the basis: minimise the count from the least trustworthy tier first "
                         "(T5, T4, T3, R, T2, T1), top gains within a tier, ties by (bug, class index)",
           "tiers": {t: TIER_NAME[t] for t in TIERS},
           "summary": summary, "human_judgments": hum_list, "comparisons": rows}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "decision_basis.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    (OUT / "decision_basis_members.json").write_text(json.dumps(members_out), encoding="utf-8")
    write_md(res)
    print(json.dumps(summary, indent=1, default=str))


def write_md(res):
    S = res["summary"]
    lines = ["# Decision basis of the Defects4J decisions", "",
             f"{res['status']}. View: {res['view']}.", "",
             "A decision basis is a set of known labels whose correctness alone keeps the decision, with every other "
             "label treated as unknown. Minimal bases are not unique; this is *a* basis, built by one deterministic "
             "rule: use as few labels as possible from the least trustworthy tier, then the next, and so on "
             "(no-op rule, F3, human, R, execution failure, reference identity), highest gain first within a tier.", "",
             "Tiers: T1 reference identity (archived exact/AST match to the developer fix); T2 execution failure "
             "(archived harness failure, census witness, F2 witness); R labels set by the fix-identical re-run or "
             "C1-fix; T3 human judgment (archived reviewers, F4); T4 F3 generated-test witness; T5 no-op rule.", "",
             "Bounds are challenger minus baseline, equal-bug percentage points over 488 bugs. Flips to reopen = the "
             "smallest number of known labels whose flip makes the interval contain 0 (equal to the robustness "
             "column of results/v4/decidability). eps* = L / sum of all label gains (break-even random error rate).",
             "",
             "| Comparison | Decided interval (pp) | Basis size by tier (T1 / T2 / R / T3 / T4 / T5) | Human judgments needed | F3 / no-op needed? | Flips to reopen | eps* |",
             "|---|---|---|---|---|---|---|"]
    for r in res["comparisons"]:
        if not r.get("decided"):
            lines.append(f"| {r['b']} | [{r['interval_pp'][0]:+.2f}, {r['interval_pp'][1]:+.2f}] open | - | - | - | - | - |")
            continue
        t = r["basis_size_by_tier"]
        hs = r["human_judgments"]
        if hs:
            hj = f"{len(hs)} ({r['human_archived']} archived, {r['human_F4']} F4): " + ", ".join(
                f"{h['bug']}{'*' if h['source'] == 'F4' else ''}({'c' if h['label'] == 'correct' else 'i'})"
                for h in sorted(hs, key=lambda h: (h['bug'], h['class_index'])))
        else:
            hj = "0"
        f3n = "/".join("yes" if r[k] else "no" for k in ("needs_F3", "needs_noop_rule"))
        lines.append(f"| {r['b']} | [{r['interval_pp'][0]:+.2f}, {r['interval_pp'][1]:+.2f}] | "
                     f"{t['T1']} / {t['T2']} / {t['R']} / {t['T3']} / {t['T4']} / {t['T5']} | {hj} | {f3n} | "
                     f"{r['flips_to_reopen']} | {100 * r['eps_star']:.2f}% |")
    lines += ["", "Human judgments: * = F4 (second annotation layer), otherwise archived reviewers; (c) correct, "
                  "(i) incorrect.", "",
              "## Totals", "",
              f"- Decided: {S['decided']}/{S['n']}.",
              f"- Rest only on reference-identity and execution-failure labels (T1+T2 suffice): "
              f"{len(S['rest_on_reference_and_execution_only'])}/{S['decided']} "
              f"({', '.join(S['rest_on_reference_and_execution_only'])}).",
              f"- Need human judgments: " + ", ".join(f"{k} {v}" for k, v in S["need_human"].items()) +
              f"; {S['distinct_human_classes']} distinct classes in {S['distinct_human_bugs']} bugs "
              f"({S['archived']} archived, {S['F4']} F4).",
              f"- Archived load-bearing judgments by label: {S['archived_by_label']}; by review: "
              f"{S['archived_by_review']} (agreement = first-round two-reviewer agreement).",
              f"- F5 strata of the archived load-bearing judgments: {S['archived_by_f5_stratum']} (F5 found "
              f"accepted-correct the most disputed stratum, 13/30, vs accepted-incorrect 3/30). F4 labels: "
              f"{S['F4_by_label']}.",
              f"- Load-bearing for more than one decision: " + "; ".join(
                  f"{e['bug']}#{e['class_index']} ({e['source']}, {e['label']}): {', '.join(e['comparisons'])}"
                  for e in S["load_bearing_for_several"]) + ".",
              f"- Load-bearing classes that are themselves F5 audit items: {len(S['load_bearing_in_f5_sample'])}.",
              f"- Need an F3 label: {S['need_F3'] or 'none'}. Need the no-op rule: {S['need_noop_rule'] or 'none'}.",
              f"- Bases that use R labels (R placed before human in trust): {S['need_R_in_basis'] or 'none'}; "
              f"decisions that fail without any R label: {S['R_tier_necessary'] or 'none'}; "
              f"decisions that fail without any human label: {S['human_tier_necessary'] or 'none'}.",
              "- Flipping all " + str(S["f5_disputed_labels"]) + " F5-disputed labels changes the lower bounds by: " +
              ", ".join(f"{r['b']} {r['L_change_if_all_F5_disputed_flipped_pp']:+.3f}" for r in res["comparisons"]
                        if r.get("decided")) + " pp.", ""]
    (OUT / "DECISION_BASIS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
