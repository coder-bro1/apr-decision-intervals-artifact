"""C1 equivalence constraints on Defects4J (ADDENDUM_V4_C1_EQUIVALENCE.md).

Equivalence = same javac AST fingerprint (contract identity) OR same normalised AST (BatchMethodNormalize
h_noann_alpha: annotations removed, parameters/locals renamed v0, v1, ... in declaration order), closed transitively
within a bug. Settings: AST identity (contract) | C1-id (rename-aware classes) | C1-id + C1-fix (a class with no known
label and a member equivalent to the developer fix becomes correct). Evidence views from final_evidence.py.
Also checks the same normaliser against the frozen HumanEval-Java E3 fix-equivalence rule.
Writes results/v4/c1_equivalence/c1_equivalence.json."""
import sys as _sys  # release layout: shared helper modules live in lib/
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / "lib").is_dir()) / "lib"))
import base64
import hashlib
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import v4core as V  # noqa: E402
import baselines as B  # noqa: E402
import final_evidence as FE  # noqa: E402
from select_f2_topup import BASELINES  # noqa: E402
from validation_policy_contract import context_id  # noqa: E402

OUT = ROOT / "results/v4/c1_equivalence"
NORM_JAVA = ROOT / "execution_tools/BatchMethodNormalize.java"
FP_JAVA = ROOT / "execution_tools/BatchMethodFingerprint.java"
EXPORTS = [f"--add-exports=jdk.compiler/com.sun.tools.javac.{p}=ALL-UNNAMED" for p in ("tree", "util", "api")]
LEGACY = [ROOT / f"llm_apr_dataset/llm_apr_defects4j_candidates_v2_candidates_{k}.jsonl" for k in ("all", "excluded")]
HE = ROOT / "results/v4/humaneval"


def tid(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def run_tool(cmd, texts, name):
    """texts: {key: text}. Returns {key: [status, *fields]} (cached on disk by input hash)."""
    inp, out = OUT / f"{name}_input.tsv", OUT / f"{name}_output.tsv"
    body = "".join(k + "\t" + base64.b64encode(t.encode()).decode() + "\n" for k, t in sorted(texts.items()))
    stamp = OUT / f"{name}_input.sha256"
    h = hashlib.sha256(body.encode()).hexdigest()
    if not (out.exists() and stamp.exists() and stamp.read_text() == h):
        inp.write_text(body, encoding="utf-8", newline="\n")
        with inp.open(encoding="utf-8") as i, out.open("w", encoding="utf-8", newline="\n") as o:
            subprocess.run(cmd, stdin=i, stdout=o, stderr=subprocess.DEVNULL, check=True, timeout=3600)
        stamp.write_text(h)
    res = {}
    for line in out.read_text(encoding="utf-8").splitlines():
        p = line.split("\t")
        res[p[0]] = p[1:]
    if set(res) != set(texts):
        raise ValueError(f"{name}: tool did not cover every input")
    return res


def normalise(texts, name):
    raw = run_tool(["java", "-Xmx2g", *EXPORTS, str(NORM_JAVA)], texts, name)
    return {k: (v[3] if v[0] == "ok" else None) for k, v in raw.items()}


def fingerprint(texts, name):
    raw = run_tool(["java", "-Xmx1g", str(FP_JAVA)], texts, name)
    return {k: (v[1] if v[0] == "ok" else None) for k, v in raw.items()}


class UF:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def humaneval_check():
    recs = [json.loads(l) for n in ("e3_targets.jsonl", "e3_tierB.jsonl") for l in open(HE / n, encoding="utf-8") if l.strip()]
    eq = {json.loads(l)["candidate_id"]: json.loads(l) for l in open(HE / "equivalence.jsonl", encoding="utf-8")}
    alpha = normalise({tid(t): t for r in recs for t in (r["patch"], r["human_fix"])}, "humaneval_norm")
    agree = Counter()
    diffs = []
    for r in recs:
        a_p, a_f = alpha[tid(r["patch"])], alpha[tid(r["human_fix"])]
        norm_eq = a_p is not None and a_p == a_f
        c1_rule = norm_eq or eq[r["candidate_id"]]["ast_equal"]
        e3_rule = eq[r["candidate_id"]]["equivalent"]
        agree[(e3_rule, c1_rule)] += 1
        if e3_rule != c1_rule:
            diffs.append({"candidate_id": r["candidate_id"], "bug": r["bug_id"], "e3_rule": e3_rule, "c1_rule": c1_rule,
                          "normaliser_parsed_patch": a_p is not None, "normaliser_parsed_fix": a_f is not None})
    return {"records": len(recs), "both_equivalent": agree[(True, True)], "neither": agree[(False, False)],
            "e3_only": agree[(True, False)], "c1_only": agree[(False, True)], "differences": diffs}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    data = V.load()
    B.register(data)
    fixes = defaultdict(set)
    for p in LEGACY:
        for line in open(p, encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                fixes[context_id(r["bug_id"], r["anchor"])].add(r["human_fix"])
    patch_alpha = normalise({tid(o.patch): o.patch for o in data.occ.values()}, "d4j_candidates_norm")
    fix_texts = {tid(f): f for fs in fixes.values() for f in fs}
    fix_alpha, fix_fp = normalise(fix_texts, "d4j_fixes_norm"), fingerprint(fix_texts, "d4j_fixes_fp")
    ctx_fix_keys = {c: ({("alpha", fix_alpha[tid(f)]) for f in fs if fix_alpha[tid(f)]} |
                        {("ast", fix_fp[tid(f)]) for f in fs if fix_fp[tid(f)]}) for c, fs in fixes.items()}

    def keys(o):
        ks = {("ast", o.ast) if o.ast else ("txt", o.patch.strip())}
        a = patch_alpha[tid(o.patch)]
        if a:
            ks.add(("alpha", a))
        return ks

    uf = UF()
    by_key = {}
    for cid in sorted(data.occ):
        o = data.occ[cid]
        uf.find(cid)
        for k in keys(o):
            first = by_key.setdefault((o.bug, k), cid)
            uf.union(first, cid)
    comp = {cid: f"c1:{data.occ[cid].bug}:{uf.find(cid)}" for cid in data.occ}
    fix_eq = {cid for cid, o in data.occ.items() if keys(o) & ctx_fix_keys.get(o.ctx, set())}
    ast_pools = V.build_pools(data, "bug", "ast")
    c1_pools = V.build_pools(data, "bug", "c1", key_fn=lambda o: comp[o.cid])
    views, log = FE.build(data, ast_pools)

    def c1_fix_view(ev, override=False):
        """override=True is the post-hoc sensitivity (not in the addendum): fix-equivalent classes are set correct
        even when the archive labels them incorrect (those archived failures are the developer fix itself, up to
        formatting/comments/renaming, so the failure is a harness artifact)."""
        out, applied, contradicted = dict(ev), 0, []
        for _, (_, classes) in c1_pools.items():
            for kl in classes:
                if not any(m in fix_eq for m in kl.members):
                    continue
                known = {ev[m] for m in kl.members if ev[m] is not None}
                if not known or (override and 0 in known):
                    for m in kl.members:
                        out[m] = 1
                    applied += 1
                if known and 0 in known:
                    contradicted.append({"bug": data.occ[kl.members[0]].bug, "members": len(kl.members),
                                         "known": sorted(known),
                                         "fix_equivalent_members": sum(m in fix_eq for m in kl.members)})
        return out, applied, contradicted

    def conflicts(pools, ev):
        return sum(1 for _, (_, cl) in pools.items() for kl in cl if V.class_label(kl.members, ev, "known_wins")[1])

    res = {"texts_normalised": sum(1 for v in patch_alpha.values() if v), "texts_total": len(patch_alpha),
           "fixes": len(fix_texts), "fixes_normalised": sum(1 for v in fix_alpha.values() if v),
           "fixes_fingerprinted": sum(1 for v in fix_fp.values() if v),
           "classes_ast": sum(len(c) for _, c in ast_pools.values()),
           "classes_c1": sum(len(c) for _, c in c1_pools.values()),
           "fix_equivalent_candidates": len(fix_eq), "evidence_log": log, "views": {}}
    for name, ev in views.items():
        ev_fix, applied, contradicted = c1_fix_view(ev)
        ev_over, applied_over, _ = c1_fix_view(ev, override=True)
        block = {"class_label_conflicts": {"ast": conflicts(ast_pools, ev), "c1": conflicts(c1_pools, ev)},
                 "c1_fix_classes_set_correct": applied, "c1_fix_contradictions": contradicted,
                 "posthoc_override_classes_set_correct": applied_over, "comparisons": []}
        for b in BASELINES:
            if b not in V.POLICIES:
                continue
            row = {"b": b}
            for setting, pools, e in (("ast", ast_pools, ev), ("c1", c1_pools, ev), ("c1+fix", c1_pools, ev_fix),
                                      ("c1+fix+override(posthoc)", c1_pools, ev_over)):
                units, _ = V.evaluate_pair(data, pools, e, "challenger", b)
                agg = V.aggregate(units, "bug", len(data.bugs))
                lo, hi = V.pp(agg["lo"]), V.pp(agg["hi"])
                row[setting] = {"pp": [round(lo, 3), round(hi, 3)], "unknowns": V.relevant_unknowns(units),
                                "result": "identified +" if lo > 0 else "identified -" if hi < 0 else "open"}
            block["comparisons"].append(row)
        res["views"][name] = block
        print(f"\n== {name}: conflicts ast {block['class_label_conflicts']['ast']} c1 {block['class_label_conflicts']['c1']}; "
              f"C1-fix sets {applied} classes correct; {len(contradicted)} fix-equivalent classes with a known 0", flush=True)
        for r in block["comparisons"]:
            print(f"  challenger vs {r['b']:20s} " + "  ".join(
                f"{s} [{r[s]['pp'][0]:+.2f},{r[s]['pp'][1]:+.2f}] {r[s]['result'][:12]:12s}(unk {r[s]['unknowns']})"
                for s in ("ast", "c1", "c1+fix", "c1+fix+override(posthoc)")), flush=True)
    res["humaneval_consistency"] = humaneval_check()
    (OUT / "c1_equivalence.json").write_text(json.dumps(res, indent=1))
    print("\n", json.dumps({k: v for k, v in res.items() if k not in ("views", "evidence_log", "humaneval_consistency")}, indent=1))
    print("evidence log:", json.dumps({k: (v if k != "overwrites" else len(v)) for k, v in log.items()}))
    hc = res["humaneval_consistency"]
    print("HumanEval check:", {k: v for k, v in hc.items() if k != "differences"})


if __name__ == "__main__":
    main()
