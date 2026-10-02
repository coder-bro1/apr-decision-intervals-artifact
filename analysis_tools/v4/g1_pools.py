"""G1 pools, G-E0 labels, policies, pre-registered bounds and the execution selection (PROTOCOL_G1_FRESH_CAMPAIGN.md).

Input: results/g1/generations.jsonl (from g1_generate.py). For each bug: identical sample texts are merged into one
candidate whose sources are every sample that produced it (config, sample index); candidates are grouped into classes
by javac AST (BatchMethodFingerprint; text fallback), as in the frozen contract.
G-E0 (no execution): a class is correct if any member's AST (or stripped text) equals the developer fix; no-op classes
(AST equal to the buggy method) are handled by the contract's N-a rule; everything else is unknown.
Policies (s.4): challenger_frozen (the Defects4J challenger refit on all 488 bugs, applied unchanged), occurrence,
uniform, sample_order, codet5_similarity and naturalness (only if their G1 score files exist).
Execution selection (s.6.2): unknown classes that are decision-relevant in P1 (tier P, executed first) or only in a
secondary comparison (tier S); one representative per class = the member with the lowest sample index.
--build-package tier  writes a census package (same format and checks as prepare_v4_rerun_package.py, v3 image).
"""
import argparse
import base64
import hashlib
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import v4core as V  # noqa: E402
import topk as T  # noqa: E402
from validation_policy_contract import CandidateView, SourcePosition, candidate_id  # noqa: E402

G1 = ROOT / "results/g1"
GEN = G1 / "generations.jsonl"
REF = ROOT / "llm_apr_dataset/llm_apr_defects4j_candidates_v2_reference_fixes.jsonl"
JAVA = ROOT / "execution_tools/BatchMethodFingerprint.java"
CONFIG = "qwen2.5-coder-7b-instruct-nf4-t0.8"
P1 = ("challenger_frozen", "occurrence")
SECONDARY = [("occurrence", "uniform"), ("challenger_frozen", "uniform"), ("codet5_similarity", "uniform"),
             ("naturalness", "uniform")]
IMAGE_V3 = "sha256:9d43d93cc76845e19fb314247714f4015f0c5fd99277e6e90208069024e5d05e"
CENSUS_CODE = ["execution_tools/census_runner.py", "execution_tools/census_evidence.py",
               "execution_tools/official_defects4j_runner.py", "execution_tools/run_census.py",
               "PROTOCOL_G1_FRESH_CAMPAIGN.md"]


def tid(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def fingerprints(texts):
    """AST digests for texts; cached by text id in results/g1/parser_cache.tsv (only new texts are parsed)."""
    cache = G1 / "parser_cache.tsv"
    fp = {}
    if cache.exists():
        for line in cache.read_text(encoding="utf-8").splitlines():
            k, st, h = line.split("\t")
            fp[k] = h if st == "ok" else None
    todo = {k: t for k, t in texts.items() if k not in fp}
    if todo:
        req = G1 / "parser_input.tsv"
        with req.open("w", encoding="utf-8", newline="\n") as f:
            for k, t in sorted(todo.items()):
                f.write(k + "\t" + base64.b64encode(t.encode()).decode() + "\n")
        with req.open(encoding="utf-8") as i:
            out = subprocess.run(["java", "-Xmx1g", str(JAVA)], stdin=i, capture_output=True, text=True,
                                 check=True, timeout=3600).stdout
        with cache.open("a", encoding="utf-8", newline="\n") as c:
            for line in out.splitlines():
                k, st, h = line.split("\t")
                fp[k] = h if st == "ok" else None
                c.write(line + "\n")
    missing = set(texts) - set(fp)
    assert not missing, f"parser did not cover {len(missing)} texts"
    return fp


def load_generations():
    rows = []
    for line in GEN.read_bytes().split(b"\n"):
        if line.strip():
            try:
                rows.append(json.loads(line))
            except ValueError:
                break  # an incomplete last record while generation is still running
    return rows


def build(rows):
    ref = {}
    for line in open(REF, encoding="utf-8"):
        r = json.loads(line)
        ref[(r["bug_id"], r["anchor"].strip())] = r["human_fix"]
    cands = {}  # candidate id -> dict
    for r in rows:
        bug, anchor = r["bug_id"], r["anchor"].strip()
        if not anchor:  # Chart-23, Collections-27: no buggy method in the dataset (empty in the D4J pool too)
            continue
        for s in r["samples"]:
            p = s["patch"].strip()
            cid = candidate_id(bug, anchor, p)
            c = cands.setdefault(cid, {"cid": cid, "bug": bug, "ctx": r["context_id"], "anchor": anchor, "patch": p,
                                       "sources": [], "fix": ref.get((bug, anchor))})
            c["sources"].append((CONFIG, int(s["index"])))
    texts = {}
    for c in cands.values():
        for t in (c["patch"], c["anchor"], c["fix"] or ""):
            if t:
                texts[tid(t)] = t
    fp = fingerprints(texts)
    occ, ctx_members, ctx_bug, e0 = {}, defaultdict(list), {}, {}
    for n, c in enumerate(sorted(cands.values(), key=lambda c: (c["bug"], min(i for _, i in c["sources"])))):
        pa = fp.get(tid(c["patch"])) if c["patch"] else None
        an = fp.get(tid(c["anchor"]))
        fx = fp.get(tid(c["fix"])) if c["fix"] else None
        if pa and an and pa == an:
            structure = "exact_noop" if c["patch"] == c["anchor"] else "normalized_noop"
        else:
            structure = "different_parse" if (pa and an) else "parse_unresolved"
        o = V.Occ(cid=c["cid"], ctx=c["ctx"], bug=c["bug"], patch=c["patch"], sources=sorted(c["sources"]),
                  ctx_order=0, pos_in_ctx=n, structure=structure, ast=pa)
        occ[o.cid] = o
        ctx_members[c["ctx"]].append(o.cid)
        ctx_bug[c["ctx"]] = c["bug"]
        ref_match = bool(c["fix"]) and ((pa is not None and pa == fx) or c["patch"] == c["fix"].strip())
        e0[o.cid] = 1 if ref_match else None
    contexts = [{"context_id": k, "bug_id": ctx_bug[k], "candidate_ids": v} for k, v in sorted(ctx_members.items())]
    data = V.Data(occ=occ, contexts=contexts, bugs=sorted({r["bug_id"] for r in rows}), ctx_bug=ctx_bug, ctx_fold={},
                  e0=e0, witnesses=set(), census={})
    data.ctx_anchor = {c["ctx"]: c["anchor"] for c in cands.values()}
    return data, cands


def register(data):
    from repairbench_v4 import frozen_challenger
    # The challenger's features use provenance only (sources/positions), never the code text; CandidateView just
    # refuses empty text, so an empty generation gets a placeholder here (its class label and identity are unaffected).
    views = [CandidateView(o.cid, o.ctx, data.ctx_anchor[o.ctx], o.patch or "<empty generation>",
                           tuple(sorted(SourcePosition(s, i) for s, i in o.sources))) for o in data.occ.values()]
    scores, audit = frozen_challenger(views)
    for v, s in zip(views, scores):
        data.occ[v.candidate_id].score = float(s)
    V.POLICIES["challenger_frozen"] = V.pol_challenger
    V.POLICIES["sample_order"] = V.pol_mra
    for name in ("codet5_similarity", "naturalness"):
        p = G1 / f"{name}.jsonl"
        V.POLICIES.pop(name, None)
        if p.exists():
            sc = {r["candidate_id"]: r["score"] for r in V.jsonl(p)}
            if set(sc) >= set(data.occ):
                V.POLICIES[name] = (lambda table: (lambda d, kl: max(table[m] for m in kl.members)))(sc)
    return audit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-package", choices=("P", "S"))
    args = ap.parse_args()
    rows = load_generations()
    data, cands = build(rows)
    audit = register(data)
    pools = V.build_pools(data, "bug", "ast")
    ev = data.e0
    comps = [P1] + [c for c in SECONDARY if c[0] in V.POLICIES and c[1] in V.POLICIES]
    res = {"bugs_generated": len(rows), "candidates": len(data.occ), "classes": sum(len(c) for _, c in pools.values()),
           "reference_match_classes": sum(1 for _, cl in pools.values() for kl in cl
                                          if any(ev[m] == 1 for m in kl.members)),
           "noop_classes": sum(1 for _, cl in pools.values() for kl in cl if any(data.occ[m].noop for m in kl.members)),
           "parse_unresolved_candidates": sum(o.structure == "parse_unresolved" for o in data.occ.values()),
           "challenger_frozen": audit, "missing_policies": [c for c in ("codet5_similarity", "naturalness")
                                                             if c not in V.POLICIES], "comparisons": []}
    relevant = {}
    for a, b in comps:
        units, _ = V.evaluate_pair(data, pools, ev, a, b)
        agg = V.aggregate(units, "bug", len(data.bugs))
        tk = T.run(data, pools, ev, a, b) if (a, b) in (P1, ("occurrence", "uniform")) else None
        res["comparisons"].append({"a": a, "b": b, "G-E0_pp": [V.pp(agg["lo"]), V.pp(agg["hi"])],
                                   "identified": agg["lo"] > 0 or agg["hi"] < 0,
                                   "relevant_unknown_classes": V.relevant_unknowns(units), "topk_pp": tk})
        for u, (bug, classes) in zip(units, pools.values()):
            for d, y, i in u.coeffs:
                if y is None:
                    rep = min(classes[i].members, key=lambda m: min(ix for _, ix in data.occ[m].sources))
                    relevant.setdefault(rep, set()).add(f"{a}-{b}")
    p1 = f"{P1[0]}-{P1[1]}"
    tier_p = sorted(k for k, v in relevant.items() if p1 in v)
    tier_s = sorted(k for k, v in relevant.items() if p1 not in v)
    res["execution_selection"] = {"tier_P": len(tier_p), "tier_P_bugs": len({data.occ[k].bug for k in tier_p}),
                                  "tier_S": len(tier_s), "tier_S_bugs": len({data.occ[k].bug for k in tier_s})}
    G1.mkdir(parents=True, exist_ok=True)
    (G1 / "g1_pools_summary.json").write_text(json.dumps(res, indent=1, default=str))
    for name, ids in (("P", tier_p), ("S", tier_s)):
        rows_out = [{"candidate_id": k, "bug_id": data.occ[k].bug, "context_id": data.occ[k].ctx,
                     "anchor": data.ctx_anchor[data.occ[k].ctx], "patch": data.occ[k].patch,
                     "comparisons": sorted(relevant[k])} for k in ids]
        sel = G1 / f"exec_tier{name}_candidates.json"
        if (G1 / f"exec_tier{name}_package_v1").exists():
            # The frozen package hash-checks this selection file: never overwrite it. Only confirm the recomputed
            # selection has exactly the same representatives, and record any difference.
            frozen = {r["candidate_id"] for r in json.loads(sel.read_text())}
            res["execution_selection"][f"tier_{name}_matches_frozen_package"] = (frozen == set(ids))
            if frozen != set(ids):
                (G1 / f"exec_tier{name}_candidates.recomputed.json").write_text(json.dumps(rows_out, indent=1))
            continue
        sel.write_text(json.dumps(rows_out, indent=1))
    (G1 / "g1_pools_summary.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps({k: v for k, v in res.items() if k != "challenger_frozen"}, indent=1, default=str))
    if args.build_package:
        build_package(args.build_package)


def build_package(tier):
    from prepare_multibug_execution import digest, write_json
    sel = G1 / f"exec_tier{tier}_candidates.json"
    rows = json.loads(sel.read_text())
    out = G1 / f"exec_tier{tier}_package_v1"
    if out.exists():
        raise FileExistsError(out)
    (out / "cases").mkdir(parents=True)
    (out / "jobs").mkdir()
    by_bug = defaultdict(list)
    for r in rows:
        write_json(out / "cases" / (r["candidate_id"] + ".json"),
                   {k: r[k] for k in ("candidate_id", "bug_id", "anchor", "patch", "context_id")})
        by_bug[r["bug_id"]].append({"candidate_id": r["candidate_id"], "compile_only": False})
    jobs = [{"job_id": "full_" + b, "phase": "full", "bug_id": b, "cases": sorted(v, key=lambda e: e["candidate_id"])}
            for b, v in sorted(by_bug.items())]
    for j in jobs:
        write_json(out / "jobs" / (j["job_id"] + ".json"), j)
    write_json(out / "jobs.json", jobs)
    write_json(out / "summary.json", {"candidates": len(rows), "jobs": len(jobs), "image_name": "v3_jdk11",
                                      "image": IMAGE_V3, "tier": tier})
    inputs = {p: digest(ROOT / p) for p in CENSUS_CODE}
    inputs[sel.relative_to(ROOT).as_posix()] = digest(sel)
    write_json(out / "manifest.json", {"image": IMAGE_V3, "inputs": inputs,
                                      "outputs": {p.relative_to(out).as_posix(): digest(p)
                                                  for p in sorted(out.rglob("*")) if p.is_file()}})
    print(f"package {out.name}: {len(rows)} candidates, {len(jobs)} bug jobs")


if __name__ == "__main__":
    main()
