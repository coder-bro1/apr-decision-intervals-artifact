"""G2 (ADDENDUM_V4_G2_D4C_FROZEN.md): frozen, pre-specified transfer of the Defects4J selectors to D4C patches.
Order: (1) build pools and compute + save every policy score WITHOUT reading any outcome; (2) only then read the
execution findings and compute the bounds. Pre-specified on already-inspected data, not confirmatory."""
import sys as _sys  # release layout: shared helper modules live in lib/
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / "lib").is_dir()) / "lib"))
import base64
import hashlib
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import v4core as V  # noqa: E402
import topk as T  # noqa: E402

PREP = ROOT / "results/d4c_external/preparation_v2/cases"
FIND = ROOT / "results/d4c_external/combined_v1/candidate_findings.jsonl"
OUT = ROOT / "results/v4/d4c_frozen"
JAVA = ROOT / "execution_tools/BatchMethodFingerprint.java"
PAIRS = [("challenger_frozen", "mra"), ("challenger_frozen", "occurrence"), ("challenger_frozen", "uniform"),
         ("source_agnostic_frozen", "mra")]


def tid(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def fingerprints(texts):
    cache = OUT / "parser_cache.tsv"
    fp = {}
    if cache.exists():
        for line in cache.read_text(encoding="utf-8").splitlines():
            k, st, h = line.split("\t")
            fp[k] = h if st == "ok" else None
    todo = {k: t for k, t in texts.items() if k not in fp}
    if todo:
        req = OUT / "parser_input.tsv"
        with req.open("w", encoding="utf-8", newline="\n") as f:
            for k, t in sorted(todo.items()):
                f.write(k + "\t" + base64.b64encode(t.encode()).decode() + "\n")
        with req.open(encoding="utf-8") as i:
            out = subprocess.run(["java", "-Xmx1g", str(JAVA)], stdin=i, capture_output=True, text=True, check=True).stdout
        with cache.open("a", encoding="utf-8", newline="\n") as c:
            for line in out.splitlines():
                k, st, h = line.split("\t")
                fp[k] = h if st == "ok" else None
                c.write(line + "\n")
    return fp


def frozen_scores(rb_views, feature_cls):
    """D4J three-stage model refit on all 488 bugs (C by the rotation-0 tuning rule), applied unchanged."""
    from threadpoolctl import threadpool_limits
    import run_evidence_pilot_step2 as S
    with threadpool_limits(limits=1):
        views, _, _, training, _ = S.load_inputs()
        roles = S.role_folds(0)
        idx = {r: [i for i, row in enumerate(training) if row["fold"] in f] for r, f in roles.items()}
        allrows = list(range(len(training)))
        design, full = feature_cls([views[i] for i in idx["training"]]), feature_cls(views)
        xd, xf, xo = design.transform(views), full.transform(views), full.transform(rb_views)
        joint, audit = np.ones(len(rb_views)), []
        for stage in S.STAGES:
            el = {r: [i for i in ix if training[i][stage] is not None] for r, ix in {**idx, "all": allrows}.items()}
            y = {r: np.array([training[i][stage] for i in ix], dtype=np.int8) for r, ix in el.items()}
            trials = [(S.safe_log_loss(y["tuning"], S.fit_logistic(xd[el["training"]], y["training"], c)
                                       .predict_proba(xd[el["tuning"]])[:, 1]), c) for c in S.C_GRID]
            best = min(trials)[1]
            joint = joint * S.fit_logistic(xf[el["all"]], y["all"], best).predict_proba(xo)[:, 1]
            audit.append({"stage": stage, "C": best})
    return joint, audit


def main():
    from validation_policy_contract import CandidateView, SourcePosition
    from learners import AgnosticFeatures
    import run_evidence_pilot_step2 as S
    OUT.mkdir(parents=True, exist_ok=True)
    cases = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(PREP.glob("*.json"))]
    for c in cases:
        c["idx"] = json.loads(c["source_indices"]) if isinstance(c["source_indices"], str) else c["source_indices"]
    views = [CandidateView(c["candidate_id"], "d4cctx_" + c["bug_id"], c["anchor"], c["patch"] or "<empty>",
                           tuple(sorted(SourcePosition("d4c", int(i)) for i in c["idx"]))) for c in cases]
    ch, a1 = frozen_scores(views, S.ProvenanceFeatures)
    ag, a2 = frozen_scores(views, AgnosticFeatures)
    # (1) scores are written before any outcome is read
    with open(OUT / "policy_scores.jsonl", "w", encoding="utf-8") as f:
        for c, s1, s2 in zip(cases, ch, ag):
            f.write(json.dumps({"candidate_id": c["candidate_id"], "challenger_frozen": float(s1),
                                "source_agnostic_frozen": float(s2), "sample_indices": c["idx"]}) + "\n")
    texts = {}
    for c in cases:
        for t in (c["patch"], c["anchor"]):
            if t:
                texts[tid(t)] = t
    fp = fingerprints(texts)
    occ, ctx_members = {}, defaultdict(list)
    for n, (c, s1, s2) in enumerate(zip(cases, ch, ag)):
        pa, an = fp.get(tid(c["patch"])) if c["patch"] else None, fp.get(tid(c["anchor"]))
        structure = (("exact_noop" if c["patch"] == c["anchor"] else "normalized_noop") if (pa and an and pa == an)
                     else ("different_parse" if (pa and an) else "parse_unresolved"))
        o = V.Occ(cid=c["candidate_id"], ctx="d4cctx_" + c["bug_id"], bug=c["bug_id"], patch=c["patch"],
                  sources=[("d4c", int(i)) for i in c["idx"]], ctx_order=0, pos_in_ctx=n, score=float(s1),
                  structure=structure, ast=pa)
        occ[o.cid] = o
        ctx_members[o.ctx].append(o.cid)
    agn = {c["candidate_id"]: float(s) for c, s in zip(cases, ag)}
    contexts = [{"context_id": k, "bug_id": k[len("d4cctx_"):], "candidate_ids": v} for k, v in sorted(ctx_members.items())]
    bugs = sorted({c["bug_id"] for c in cases})
    data = V.Data(occ=occ, contexts=contexts, bugs=bugs, ctx_bug={c["context_id"]: c["bug_id"] for c in contexts},
                  ctx_fold={}, e0={}, witnesses=set(), census={})
    data.ctx_anchor = {"d4cctx_" + c["bug_id"]: c["anchor"] for c in cases}
    V.POLICIES["challenger_frozen"] = V.pol_challenger
    V.POLICIES["source_agnostic_frozen"] = lambda d, kl: max(agn[m] for m in kl.members)
    pools = V.build_pools(data, "bug", "ast")
    # (2) only now read the outcomes
    status = {json.loads(l)["candidate_id"]: json.loads(l)["evidence_status"] for l in open(FIND, encoding="utf-8") if l.strip()}
    trig = {k: (1 if status.get(k) == "admissible_triggers_pass_semantics_unknown" else
                0 if status.get(k) in ("controlled_trigger_failure", "compile_command_failed_twice") else None) for k in occ}
    sem = {k: (0 if status.get(k) in ("controlled_trigger_failure", "compile_command_failed_twice") else None) for k in occ}
    res = {"status": "pre-specified on already-inspected data; not confirmatory", "bugs": len(bugs),
           "candidates": len(occ), "classes": sum(len(c) for _, c in pools.values()),
           "noop_candidates": sum(o.noop for o in occ.values()),
           "challenger_fit": a1, "agnostic_fit": a2, "endpoints": {}}
    for name, ev in (("trigger_passage", trig), ("semantic_negatives_only", sem)):
        rows = []
        for a, b in PAIRS:
            units, _ = V.evaluate_pair(data, pools, ev, a, b)
            agg = V.aggregate(units, "bug", len(bugs))
            identical = sum(1 for u in units if not u.coeffs)
            rows.append({"a": a, "b": b, "bounds_pp": [V.pp(agg["lo"]), V.pp(agg["hi"])],
                         "result": "identified +" if agg["lo"] > 0 else "identified -" if agg["hi"] < 0 else "open",
                         "bugs_with_identical_choice": identical, "relevant_unknown_classes": V.relevant_unknowns(units),
                         "topk_pp": T.run(data, pools, ev, a, b)})
            print(f"{name:24s} {a:22s} vs {b:11s} {rows[-1]['bounds_pp']} {rows[-1]['result']:12s} same-choice bugs {identical}/{len(bugs)}", flush=True)
        res["endpoints"][name] = rows
    (OUT / "g2_results.json").write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
