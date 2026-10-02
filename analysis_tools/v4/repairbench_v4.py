"""E4: RepairBench (GitBug-Java, 35 configurations) under the frozen v4 contract. PREVIOUSLY INSPECTED - TRANSFER ONLY.

Contract, unchanged from PROTOCOL_V4: bug unit, javac AST identity (BatchMethodFingerprint; text fallback), class
label known-wins over the imported reference labels (exact/AST match = correct, test failure = incorrect, test-passing
non-match = unknown), no-op rule N-a (patch AST == buggy-method AST), uniform ties, exact shared-label bounds, equal-bug
weighting; top-k via topk.py. No execution (GitBug-Java needs ~130 GiB), so only archived evidence (E0).

Selectors: mra (returned index), uniform (random), occurrence (number of returning configurations), codet5_similarity
(the frozen v2 CodeT5+ patch-to-buggy cosine), and challenger_frozen: the Defects4J three-stage challenger refit once on
all 488 Defects4J bugs (C chosen by the unchanged tuning rule of rotation 0) and applied as is. Its per-source features
are all zero here (no RepairBench configuration was seen in training), so it acts through position/count features only.
"""
import base64
import hashlib
import json
import subprocess
import sys
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import v4core as V  # noqa: E402
import topk as T  # noqa: E402

SRC = ROOT / "llm_apr_dataset/external/repairbench_gitbugjava_2025_v1/repairbench_gitbugjava_v1_candidates_all.jsonl"
CT5 = ROOT / "results/v2/repairbench_zero_shot_scores/Salesforce_codet5p-110m-embedding_all_similarity_scores.jsonl"
JAVA = ROOT / "execution_tools/BatchMethodFingerprint.java"
OUT = ROOT / "results/v4/repairbench"
PAIRS = [("mra", "uniform"), ("occurrence", "mra"), ("occurrence", "uniform"), ("codet5_similarity", "mra"),
         ("codet5_similarity", "uniform"), ("challenger_frozen", "mra"), ("challenger_frozen", "uniform"),
         ("challenger_frozen", "occurrence"), ("challenger_frozen", "codet5_similarity")]
LABEL = {"correct": 1, "incorrect": 0, "unknown": None}


def tid(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fingerprints(texts):
    OUT.mkdir(parents=True, exist_ok=True)
    out_path = OUT / "parser_output.tsv"
    if not out_path.exists():
        req = OUT / "parser_input.tsv"
        with req.open("w", encoding="utf-8", newline="\n") as f:
            for k, t in sorted(texts.items()):
                f.write(k + "\t" + base64.b64encode(t.encode()).decode() + "\n")
        with req.open(encoding="utf-8") as i, out_path.open("w", encoding="utf-8") as o, \
                (OUT / "parser_stderr.log").open("w", encoding="utf-8") as e:
            subprocess.run(["java", "-Xmx2g", str(JAVA)], stdin=i, stdout=o, stderr=e, check=True, timeout=3600)
    fp = {}
    for line in out_path.read_text(encoding="utf-8").splitlines():
        k, st, h = line.split("\t")
        fp[k] = h if st == "ok" else None
    assert set(fp) == set(texts), "parser did not cover every text"
    return fp


def frozen_challenger(rb_views):
    """Refit the D4J three-stage challenger on all D4J rows (C tuned as in rotation 0) and score RepairBench views."""
    from threadpoolctl import threadpool_limits
    import run_evidence_pilot_step2 as S
    with threadpool_limits(limits=1):
        views, _, _, training, _ = S.load_inputs()
        roles = S.role_folds(0)
        idx = {r: [i for i, row in enumerate(training) if row["fold"] in f] for r, f in roles.items()}
        allrows = list(range(len(training)))
        design = S.ProvenanceFeatures([views[i] for i in idx["training"]])
        full = S.ProvenanceFeatures(views)
        xd = design.transform(views)
        xf, xrb = full.transform(views), full.transform(rb_views)
        joint = np.ones(len(rb_views))
        audit = []
        for stage in S.STAGES:
            el = {r: [i for i in ix if training[i][stage] is not None] for r, ix in {**idx, "all": allrows}.items()}
            y = {r: np.array([training[i][stage] for i in ix], dtype=np.int8) for r, ix in el.items()}
            trials = []
            for c in S.C_GRID:
                m = S.fit_logistic(xd[el["training"]], y["training"], c)
                trials.append((S.safe_log_loss(y["tuning"], m.predict_proba(xd[el["tuning"]])[:, 1]), c))
            best = min(trials)[1]
            m = S.fit_logistic(xf[el["all"]], y["all"], best)
            joint = joint * m.predict_proba(xrb)[:, 1]
            audit.append({"stage": stage, "C": best})
    return joint, {"d4j_sources": full.sources, "d4j_max_index": full.max_index, "stages": audit}


def main():
    from validation_policy_contract import CandidateView, SourcePosition
    rows = [json.loads(line) for line in open(SRC, encoding="utf-8") if line.strip()]
    texts = {}
    for r in rows:
        texts[tid(r["patch"])] = r["patch"]
        texts[tid(r["anchor"])] = r["anchor"]
    fp = fingerprints(texts)
    ct5 = {json.loads(x)["candidate_id"]: json.loads(x)["score"] for x in open(CT5, encoding="utf-8") if x.strip()}
    rb_views = [CandidateView(r["candidate_id"], r["context_id"], r["anchor"], r["patch"],
                              tuple(sorted(SourcePosition(s["source_config"], int(s["candidate_index"])) for s in r["sources"])))
                for r in rows]
    ch, ch_audit = frozen_challenger(rb_views)
    occ, ctx_members, ctx_bug = {}, defaultdict(list), {}
    for n, (r, s) in enumerate(zip(rows, ch)):
        pa, an = fp[tid(r["patch"])], fp[tid(r["anchor"])]
        structure = ("exact_noop" if r["patch"] == r["anchor"] else "normalized_noop") if (pa and an and pa == an) \
            else ("different_parse" if pa and an else "parse_unresolved")
        o = V.Occ(cid=r["candidate_id"], ctx=r["context_id"], bug=r["bug_id"], patch=r["patch"],
                  sources=[(x["source_config"], int(x["candidate_index"])) for x in r["sources"]],
                  ctx_order=0, pos_in_ctx=n, score=float(s), structure=structure, ast=pa)
        occ[o.cid] = o
        ctx_members[r["context_id"]].append(o.cid)
        ctx_bug[r["context_id"]] = r["bug_id"]
    contexts = [{"context_id": c, "bug_id": ctx_bug[c], "candidate_ids": m} for c, m in sorted(ctx_members.items())]
    e0 = {r["candidate_id"]: LABEL[r["reference_label"]] for r in rows}
    data = V.Data(occ=occ, contexts=contexts, bugs=sorted(set(ctx_bug.values())), ctx_bug=ctx_bug,
                  ctx_fold={}, e0=e0, witnesses=set(), census={})
    data.ctx_anchor = {r["context_id"]: r["anchor"] for r in rows}
    V.POLICIES["challenger_frozen"] = V.pol_challenger
    V.POLICIES["codet5_similarity"] = lambda d, kl: max(ct5[m] for m in kl.members)
    pools = V.build_pools(data, "bug", "ast")
    ev = data.e0
    res = {"status": "previously inspected; transfer only; archived evidence only (no execution)",
           "candidates": len(rows), "contexts": len(contexts), "bugs": len(data.bugs),
           "classes": sum(len(c) for _, c in pools.values()),
           "labels": {k: sum(1 for v in e0.values() if v == LABEL[k]) for k in LABEL},
           "structures": {k: sum(1 for o in occ.values() if o.structure == k) for k in
                          ("exact_noop", "normalized_noop", "different_parse", "parse_unresolved")},
           "challenger_frozen": ch_audit, "pairs": []}
    n = len(data.bugs)
    for a, b in PAIRS:
        units, stats = V.evaluate_pair(data, pools, ev, a, b)
        agg = V.aggregate(units, "bug", n)
        tk = T.run(data, pools, ev, a, b)
        row = {"a": a, "b": b, "budget_one_pp": [V.pp(agg["lo"]), V.pp(agg["hi"])],
               "all_unknown_incorrect_pp": V.pp(agg["all0"]), "all_unknown_correct_pp": V.pp(agg["all1"]),
               "identified": agg["lo"] > 0 or agg["hi"] < 0, "relevant_unknown_classes": V.relevant_unknowns(units),
               "topk_pp": tk, **stats}
        res["pairs"].append(row)
        print(a, b, row["budget_one_pp"], "relevant unknowns:", row["relevant_unknown_classes"], flush=True)
    (OUT / "repairbench_v4.json").write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
