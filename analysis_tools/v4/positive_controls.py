"""C5: built-in positive controls in released LLM-APR archives (exploratory, post hoc; see
manuscript/fse_revision/NOVELTY_PANEL_2026-10-01.md item C5).

A generated candidate that is a copy of the developer fix must pass the benchmark tests (for a bug whose fix is
contained in the one method the candidate replaces). Its archived failure rate therefore estimates how often the
archived harness wrongly rejected a patch, without running anything.

Identity levels (cumulative: each level contains the previous one):
  L1 text   token sequence equal after removing comments and whitespace; string/char literals kept verbatim;
  L2 AST    L1, or equal javac AST fingerprint (execution_tools/BatchMethodFingerprint.java; keeps annotations);
  L3 rename L2, or equal BatchMethodNormalize h_noann_alpha (annotations removed, locals/parameters renamed).

Artifacts: RepairLLaMA Defects4J / HumanEval-Java / GitBug-Java (raw per-configuration files in
repairllama/results/3_martin, one occurrence = one archived evaluation entry) and RepairBench GitBug-Java
(curated occurrence file). Defects4J positive controls are restricted to the bugs that
results/v4/single_function_audit marks single_method_consistent.

Validation is read from disk only (no execution): the Defects4J fix re-run (results/v4/c1_fixrerun*), the Defects4J
conflict census, and the HumanEval-Java E3 re-execution (results/v4/humaneval/e3_statuses.jsonl).

Published-count effect: the RepairLLaMA paper's union logic (as re-implemented in
analysis_tools/certification_screen_v2.stage_counts) applied to the same raw files; corrected counts add, per
configuration, the in-scope bugs whose only obstacle is an archived failure of a fix copy.

Writes results/v4/positive_controls/{positive_controls.json, POSITIVE_CONTROLS.md, flagged_occurrences.jsonl}
and tool caches under results/v4/positive_controls/cache/. Reads no new outcome and runs no container."""
import base64
import glob
import hashlib
import json
import os
import pickle
import re
import subprocess
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

from scipy.stats import beta, chi2

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analysis_tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import v4core as V  # noqa: E402
import certification_screen_v2 as CS2  # noqa: E402
import certification_screen as CS1  # noqa: E402
from validation_policy_contract import candidate_id, project_candidate  # noqa: E402

OUT = ROOT / "results/v4/positive_controls"
CACHE = OUT / "cache"
RAW = ROOT / "repairllama/results/3_martin"
CURATED = {
    "defects4j": [ROOT / f"llm_apr_dataset/llm_apr_defects4j_candidates_v2_candidates_{k}.jsonl" for k in ("all", "excluded")],
    "humanevaljava": [ROOT / f"llm_apr_dataset/external/llm_apr_humanevaljava_candidates_v2_candidates_{k}.jsonl"
                      for k in ("all", "excluded")],
    "gitbugjava": [ROOT / f"llm_apr_dataset/external/llm_apr_gitbugjava_candidates_v2_candidates_{k}.jsonl"
                   for k in ("all", "excluded")],
}
RB_OCC = ROOT / ("llm_apr_dataset/external/repairbench_gitbugjava_2025_v1/"
                 "repairbench_gitbugjava_v1_candidate_occurrences_all.jsonl")
SF_AUDIT = ROOT / "results/v4/single_function_audit/single_function_audit.json"
FIXRERUN_SEL = ROOT / "results/v4/c1_fixrerun/candidates.json"
FIXRERUN_RES = ROOT / "results/v4/c1_fixrerun/c1_fixrerun_results.json"
FIXRERUN_RUN = ROOT / "results/v4/c1_fixrerun_run_v1"
CENSUS = ROOT / "results/conflict_census/summary_v1/candidate_evidence.json"
E3_STATUS = ROOT / "results/v4/humaneval/e3_statuses.jsonl"
CLAIMS = ROOT / "results/certification_screen_v2/claims_repairllama_corrected.csv"
NORM_JAVA = ROOT / "execution_tools/BatchMethodNormalize.java"
FP_JAVA = ROOT / "execution_tools/BatchMethodFingerprint.java"
EXPORTS = [f"--add-exports=jdk.compiler/com.sun.tools.javac.{p}=ALL-UNNAMED" for p in ("tree", "util", "api")]
BENCHES = ("defects4j", "humanevaljava", "gitbugjava")
LEVELS = ("L1_text", "L2_ast", "L3_rename")
CFG_KEY = {v["config"]: k for k, v in CS2.PUBLISHED.items()}
TABLES = {"II": set(CS1.RQ1_KEYS), "III": {k for fam in CS1.RQ2_FAMILIES for k in fam}, "IV": set(CS1.RQ3_KEYS)}
TOK = re.compile(r'"(?:\\.|[^"\\])*"' + r"|'(?:\\.|[^'\\])*'" + r"|\w+|[^\s\w]")


# ---------------------------------------------------------------------------------------------------- helpers

def tid(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def tokens(s):
    return tuple(TOK.findall(V.strip_comments(s)))


def cp(k, n, a=0.05):
    if n == 0:
        return [None, None]
    lo = 0.0 if k == 0 else float(beta.ppf(a / 2, k, n - k + 1))
    hi = 1.0 if k == n else float(beta.ppf(1 - a / 2, k + 1, n - k))
    return [round(lo, 4), round(hi, 4)]


def rate(k, n):
    return {"k": k, "n": n, "rate": round(k / n, 4) if n else None, "cp95": cp(k, n)}


def pct(r):
    if r["n"] == 0:
        return "-"
    lo, hi = r["cp95"]
    return f"{r['k']}/{r['n']} ({100 * r['rate']:.1f}%; {100 * lo:.1f}-{100 * hi:.1f})"


def run_tool(cmd, texts, name):
    """texts: {key: text}. Returns {key: [status, *fields]}, cached on disk by input hash (CACHE only)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    inp, out, stamp = CACHE / f"{name}_input.tsv", CACHE / f"{name}_output.tsv", CACHE / f"{name}_input.sha256"
    body = "".join(k + "\t" + base64.b64encode(t.encode()).decode() + "\n" for k, t in sorted(texts.items()))
    h = hashlib.sha256(body.encode()).hexdigest()
    if not (out.exists() and stamp.exists() and stamp.read_text() == h):
        inp.write_text(body, encoding="utf-8", newline="\n")
        with inp.open(encoding="utf-8") as i, out.open("w", encoding="utf-8", newline="\n") as o:
            subprocess.run(cmd, stdin=i, stdout=o, stderr=subprocess.DEVNULL, check=True, timeout=4 * 3600)
        stamp.write_text(h)
    res = {}
    for line in out.read_text(encoding="utf-8").splitlines():
        p = line.split("\t")
        res[p[0]] = p[1:]
    if set(res) != set(texts):
        raise ValueError(f"{name}: tool did not cover every input")
    return res


# ---------------------------------------------------------------------------------------------------- loading

def load_raw():
    """One record per archived evaluation entry of the RepairLLaMA raw files, plus the paper's per-configuration
    bug sets (same union logic as certification_screen_v2.stage_counts). Cached in CACHE/raw.pkl."""
    files = sorted(glob.glob(str(RAW / "evaluation_*_martin.jsonl")))
    sig = [(os.path.basename(p), os.path.getsize(p), int(os.path.getmtime(p))) for p in files]
    cache = CACHE / "raw.pkl"
    if cache.exists():
        with cache.open("rb") as f:
            c = pickle.load(f)
        if c["sig"] == sig:
            return c
    occ, texts, counts = [], {}, {}
    for p in files:
        base = os.path.basename(p)
        bench = next(b for b in BENCHES if base.startswith(f"evaluation_{b}_"))
        cfg = base[len(f"evaluation_{bench}_"):-len("_martin.jsonl")]
        scope = CS2.excluded_bug_set(bench)
        sets = {m: set() for m in CS1.METRICS}
        with open(p, encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                d = json.loads(line)
                bug = d.get("identifier")
                fix = (d.get("fixed_code") or "").strip()
                anchor = (d.get("buggy_code") or "").strip()
                for idx, ev in enumerate(d.get("evaluation") or []):
                    if not isinstance(ev, dict):
                        continue
                    positive = any(ev.get(k) is True for k in ("exact_match", "ast_match", "semantical_match"))
                    if bug in scope:  # certification_screen_v2.stage_counts, verbatim logic
                        if ev.get("test") is True or positive:
                            sets["plausible"].add(bug)
                        if ev.get("exact_match") is True:
                            sets["exact"].add(bug)
                        if ev.get("exact_match") is True or ev.get("ast_match") is True:
                            sets["ast"].add(bug)
                        if positive:
                            sets["semantic"].add(bug)
                    raw_gen = ev.get("generation") or ""
                    gen = raw_gen.strip()
                    if not gen or not fix:
                        continue
                    t, ft = tid(gen), tid(fix)
                    texts.setdefault(t, gen)
                    texts.setdefault(ft, fix)
                    occ.append({"bench": bench, "cfg": cfg, "bug": bug, "line": line_no, "idx": idx,
                                "raw_sha": tid(raw_gen), "t": t, "ft": ft, "anchor_t": tid(anchor),
                                "cid": candidate_id(bug, anchor, gen),
                                "compile": ev.get("compile"), "test": ev.get("test"),
                                "exact": ev.get("exact_match"), "ast": ev.get("ast_match"),
                                "sem": ev.get("semantical_match")})
        counts[(bench, cfg)] = sets
        print(f"  read {base}: {sum(1 for o in occ if o['bench'] == bench and o['cfg'] == cfg)} occurrences", flush=True)
    c = {"sig": sig, "occ": occ, "texts": texts, "counts": counts}
    CACHE.mkdir(parents=True, exist_ok=True)
    with cache.open("wb") as f:
        pickle.dump(c, f)
    return c


def load_repairbench(texts):
    occ = []
    for line in open(RB_OCC, encoding="utf-8"):
        r = json.loads(line)
        gen, fix = (r.get("patch") or "").strip(), (r.get("human_fix") or "").strip()
        if not gen or not fix:
            continue
        t, ft = tid(gen), tid(fix)
        texts.setdefault(t, gen)
        texts.setdefault(ft, fix)
        occ.append({"bench": "repairbench_gitbugjava", "cfg": r["source_config"], "bug": r["bug_id"],
                    "line": r.get("source_line"), "idx": r.get("candidate_index"), "raw_sha": tid(r.get("patch") or ""),
                    "t": t, "ft": ft, "cid": r.get("candidate_id"), "compile": r.get("patch_compiles"),
                    "test": r.get("test_passed"), "exact": r.get("exact_match"), "ast": r.get("ast_match"), "sem": None})
    return occ


def curated_ids():
    """(source_file, source_line, candidate_index) -> projected obscand id, from the curated all+excluded files."""
    m = {}
    for bench, paths in CURATED.items():
        for p in paths:
            for line in open(p, encoding="utf-8"):
                if not line.strip():
                    continue
                r = json.loads(line)
                cid = project_candidate(r).candidate_id
                for s in r["sources"]:
                    m[(s["source_file"], s["source_line"], s["candidate_index"])] = cid
    return m


# ---------------------------------------------------------------------------------------------------- analysis

def verdict(o):
    if o["test"] is True:
        return "pass"
    if o["compile"] is False:
        return "fail_compile"
    if o["test"] is False:
        return "fail_test"
    return "unknown"


def cmh(strata):
    """Cochran-Mantel-Haenszel over 2x2 strata (a=cfg fail, b=cfg pass, c=other fail, d=other pass)."""
    sa = se = sv = rn = rd = 0.0
    used = 0
    for a, b, c, d in strata:
        n = a + b + c + d
        if n < 2 or (a + b) == 0 or (c + d) == 0 or (a + c) == 0 or (b + d) == 0:
            continue
        used += 1
        sa += a
        se += (a + b) * (a + c) / n
        sv += (a + b) * (c + d) * (a + c) * (b + d) / (n * n * (n - 1))
        rn += a * d / n
        rd += b * c / n
    if not used or sv == 0:
        return {"informative_bugs": used, "mh_odds_ratio": None, "chi2": None, "p": None}
    x2 = (abs(sa - se) - 0.5) ** 2 / sv
    return {"informative_bugs": used, "mh_odds_ratio": (round(rn / rd, 3) if rd else "inf"),
            "observed_cfg_failures": int(sa), "expected_cfg_failures": round(se, 2),
            "chi2": round(x2, 3), "p": float(f"{chi2.sf(x2, 1):.3g}")}


def summarise(copies, all_occ_by_cfg):
    """copies: occurrences that are fix copies at the chosen level (already scope-filtered)."""
    per_cfg = defaultdict(list)
    for o in copies:
        per_cfg[o["cfg"]].append(o)

    def block(rows):
        known = [o for o in rows if verdict(o) != "unknown"]
        fails = [o for o in known if verdict(o) != "pass"]
        uniq = defaultdict(list)
        for o in known:
            uniq[(o["bug"], o["t"])].append(verdict(o) != "pass")
        u_any = sum(1 for v in uniq.values() if any(v))
        u_all = sum(1 for v in uniq.values() if all(v))
        return {"occurrences": rate(len(fails), len(known)),
                "fail_compile": sum(1 for o in fails if verdict(o) == "fail_compile"),
                "fail_test": sum(1 for o in fails if verdict(o) == "fail_test"),
                "unknown_verdict": len(rows) - len(known),
                "bugs_with_copies": len({o["bug"] for o in known}),
                "bugs_with_failing_copies": len({o["bug"] for o in fails}),
                "unique_candidates": rate(u_any, len(uniq)),
                "unique_all_occurrences_fail": u_all, "unique_mixed_verdicts": u_any - u_all,
                "failing_copies_with_exact_or_ast_flag": sum(1 for o in fails if o["exact"] or o["ast"]),
                "passing_copies_with_exact_or_ast_flag": sum(1 for o in known if verdict(o) == "pass"
                                                              and (o["exact"] or o["ast"])),
                "passing_copies": len(known) - len(fails)}

    out = {"all": block(copies), "per_config": {c: block(rows) for c, rows in sorted(per_cfg.items())}}
    # differential test: each config vs all other configs, stratified by bug
    for c in out["per_config"]:
        strata = []
        for bug in {o["bug"] for o in per_cfg[c]}:
            mine = [verdict(o) != "pass" for o in per_cfg[c] if o["bug"] == bug and verdict(o) != "unknown"]
            other = [verdict(o) != "pass" for o in copies if o["bug"] == bug and o["cfg"] != c and verdict(o) != "unknown"]
            strata.append((sum(mine), len(mine) - sum(mine), sum(other), len(other) - sum(other)))
        shared = [s for s in strata if s[2] + s[3] > 0]
        out["per_config"][c]["vs_other_configs_same_bugs"] = {
            "shared_bugs": len(shared),
            "cfg_rate_on_shared_bugs": rate(sum(s[0] for s in shared), sum(s[0] + s[1] for s in shared)),
            "others_rate_on_shared_bugs": rate(sum(s[2] for s in shared), sum(s[2] + s[3] for s in shared)),
            "cmh": cmh(shared)}
    return out


def pair_within_bugs(copies, a, b):
    """Failure rates of configs a and b restricted to bugs where both produced fix copies."""
    ba = {o["bug"] for o in copies if o["cfg"] == a and verdict(o) != "unknown"}
    bb = {o["bug"] for o in copies if o["cfg"] == b and verdict(o) != "unknown"}
    shared = ba & bb
    res = {"shared_bugs": len(shared)}
    strata = []
    for bug in sorted(shared):
        x = [verdict(o) != "pass" for o in copies if o["cfg"] == a and o["bug"] == bug and verdict(o) != "unknown"]
        y = [verdict(o) != "pass" for o in copies if o["cfg"] == b and o["bug"] == bug and verdict(o) != "unknown"]
        strata.append((sum(x), len(x) - sum(x), sum(y), len(y) - sum(y)))
    res[a] = rate(sum(s[0] for s in strata), sum(s[0] + s[1] for s in strata))
    res[b] = rate(sum(s[2] for s in strata), sum(s[2] + s[3] for s in strata))
    res["bugs_where_only_" + a + "_fails"] = sum(1 for s in strata if s[0] and not s[2])
    res["bugs_where_only_" + b + "_fails"] = sum(1 for s in strata if s[2] and not s[0])
    res["cmh"] = cmh(strata)
    return res


def contradictions(occ, key="raw_sha"):
    """Identical outputs (key raw_sha: byte-identical raw string; key t: identical after strip()) with opposite
    verdicts within one configuration and bug."""
    groups = defaultdict(list)
    for o in occ:
        if verdict(o) != "unknown":
            groups[(o["cfg"], o["bug"], o[key])].append(o)
    res = defaultdict(lambda: Counter())
    for (cfg, _, _), rows in groups.items():
        if len(rows) < 2:
            continue
        v = {verdict(o) == "pass" for o in rows}
        comp = {o["compile"] for o in rows if o["compile"] is not None}
        res[cfg]["repeated_strings"] += 1
        if len(v) == 2:
            res[cfg]["pass_fail_strings"] += 1
            res[cfg]["pass_fail_occurrences"] += len(rows)
            if rows[0]["level"]:
                res[cfg]["pass_fail_strings_fix_copies"] += 1
        if len(comp) == 2:
            res[cfg]["compile_true_false_strings"] += 1
    return {c: dict(v) for c, v in sorted(res.items())}


def level_of(o, fp, al):
    """1/2/3 for the first identity level at which the occurrence equals the developer fix, else 0."""
    if o["tok"] == o["ftok"]:
        return 1
    a, b = fp.get(o["t"]), fp.get(o["ft"])
    if a and a == b:
        return 2
    a, b = al.get(o["t"]), al.get(o["ft"])
    if a and a == b:
        return 3
    return 0


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    print("loading raw RepairLLaMA files", flush=True)
    raw = load_raw()
    occ, texts, counts = raw["occ"], raw["texts"], raw["counts"]
    rb = load_repairbench(texts)
    print(f"occurrences: RepairLLaMA {len(occ)}, RepairBench {len(rb)}; unique texts {len(texts)}", flush=True)

    # identity keys
    tokc = {t: tokens(s) for t, s in texts.items()}
    print("javac fingerprint ...", flush=True)
    fpr = run_tool(["java", "-Xmx2g", str(FP_JAVA)], texts, "fingerprint")
    fp = {k: (v[1] if v[0] == "ok" else None) for k, v in fpr.items()}
    print("rename-aware normaliser ...", flush=True)
    nr = run_tool(["java", "-Xmx3g", *EXPORTS, str(NORM_JAVA)], texts, "normalise")
    al = {k: (v[3] if v[0] == "ok" else None) for k, v in nr.items()}
    allocc = occ + rb
    for o in allocc:
        o["tok"], o["ftok"] = tokc[o["t"]], tokc[o["ft"]]
        o["level"] = level_of(o, fp, al)
    for o in allocc:
        del o["tok"], o["ftok"]

    # map RepairLLaMA occurrences to curated obscand ids (check against the direct computation)
    cur = curated_ids()
    agree = Counter()
    for o in occ:
        c = cur.get((f"evaluation_{o['bench']}_{o['cfg']}_martin.jsonl", o["line"], o["idx"]))
        agree["joined" if c else "not_in_curated"] += 1
        if c:
            agree["same_id" if c == o["cid"] else "different_id"] += 1
            o["cid"] = c

    sf = json.loads(SF_AUDIT.read_text())
    sf_ok = {r["bug"] for r in sf["rows"] if r["status"] == "single_method_consistent"}
    sf_bad = {r["bug"]: r["status"] for r in sf["rows"] if r["status"] != "single_method_consistent"}

    def in_scope(o):
        return o["bench"] != "defects4j" or o["bug"] in sf_ok

    artifacts = {"repairllama_defects4j": [o for o in occ if o["bench"] == "defects4j"],
                 "repairllama_humanevaljava": [o for o in occ if o["bench"] == "humanevaljava"],
                 "repairllama_gitbugjava": [o for o in occ if o["bench"] == "gitbugjava"],
                 "repairbench_gitbugjava": rb}
    res = {"description": __doc__.split("\n\n")[0], "provenance": "exploratory, post hoc; no execution; reads archived "
           "labels and existing re-execution results only",
           "identity_levels": {"L1_text": "token sequence equal after removing comments/whitespace (literals kept)",
                               "L2_ast": "L1 or equal javac AST fingerprint (annotations kept)",
                               "L3_rename": "L2 or equal h_noann_alpha (annotations removed, locals renamed)"},
           "failure_definition": "archived test is not True and (compile is False or test is False); entries with "
                                 "neither value are 'unknown' and excluded from denominators",
           "curated_join": dict(agree),
           "tool_status": {"fingerprint_ok": sum(1 for v in fp.values() if v), "normalise_ok": sum(1 for v in al.values() if v),
                           "texts": len(texts)},
           "defects4j_scope": {"single_method_consistent_bugs": len(sf_ok), "excluded_bugs": sf_bad},
           "artifacts": {}}

    flagged_rows = []
    for name, rows in artifacts.items():
        a = {"occurrences": len(rows), "occurrences_with_known_verdict": sum(1 for o in rows if verdict(o) != "unknown"),
             "bugs": len({o["bug"] for o in rows}), "configs": len({o["cfg"] for o in rows}), "levels": {}}
        for li, lv in enumerate(LEVELS, 1):
            copies = [o for o in rows if 0 < o["level"] <= li and in_scope(o)]
            a["levels"][lv] = summarise(copies, None)
            if name == "repairllama_defects4j":
                unrestricted = [o for o in rows if 0 < o["level"] <= li]
                a["levels"][lv]["all_bugs_unrestricted"] = summarise(unrestricted, None)["all"]
        a["level_counts_failing"] = dict(Counter(o["level"] for o in rows if o["level"] and verdict(o) not in ("pass", "unknown")))
        a["contradictions_all_outputs"] = contradictions(rows)
        a["contradictions_all_outputs_stripped_text"] = contradictions(rows, "t")
        res["artifacts"][name] = a
        for o in rows:
            if o["level"] and verdict(o) not in ("pass", "unknown"):
                flagged_rows.append({k: o[k] for k in ("bench", "cfg", "bug", "line", "idx", "cid", "compile", "test",
                                                       "exact", "ast", "level")} | {"in_scope": in_scope(o)})
        print(f"{name}: L1 {pct(a['levels']['L1_text']['all']['occurrences'])}  "
              f"L3 {pct(a['levels']['L3_rename']['all']['occurrences'])}", flush=True)

    # headline within-bug pairs (published Table IV comparisons and the probe's contrasts)
    pairs = [("gpt4_gpt-zero-shot", "repairllama_ir4_or2"), ("gpt35_gpt-zero-shot", "repairllama_ir4_or2"),
             ("gpt4_gpt-zero-shot", "deepseek_lora"), ("gpt35_gpt-zero-shot", "deepseek_lora"),
             ("gpt4_gpt-zero-shot", "gpt35_gpt-zero-shot")]
    res["within_bug_pairs"] = {}
    for bench in ("defects4j", "humanevaljava"):
        rows = [o for o in occ if o["bench"] == bench and 0 < o["level"] <= 1 and in_scope(o)]
        res["within_bug_pairs"][bench] = {f"{a} vs {b}": pair_within_bugs(rows, a, b) for a, b in pairs}

    # ---------------------------------------------------------------- validation from existing re-execution
    sel = {r["candidate_id"] for r in json.loads(FIXRERUN_SEL.read_text())}
    rstat = {}
    for t in glob.glob(str(FIXRERUN_RUN / "*/terminal.json")):
        for f in json.loads(Path(t).read_text()).get("findings", []):
            rstat[f["candidate_id"]] = f["evidence_status"]
    census = {c["candidate_id"]: c["evidence_status"] for c in json.loads(CENSUS.read_text())}
    e3 = {json.loads(l)["candidate_id"]: json.loads(l)["status"] for l in open(E3_STATUS, encoding="utf-8") if l.strip()}
    d4 = [o for o in occ if o["bench"] == "defects4j"]
    by_cid = defaultdict(list)
    for o in d4:
        by_cid[o["cid"]].append(o)
    rerun_rows = []
    for c in sorted(sel):
        os_ = by_cid.get(c, [])
        bug = os_[0]["bug"] if os_ else None
        lv = min((o["level"] for o in os_ if o["level"]), default=0)
        rerun_rows.append({"candidate_id": c, "bug": bug, "status": rstat.get(c), "direct_level": lv,
                           "in_scope": bug in sf_ok, "occurrences": len(os_),
                           "failing_occurrences": sum(1 for o in os_ if verdict(o) not in ("pass", "unknown")),
                           "configs": sorted({o["cfg"] for o in os_})})
    NOTREP, REP = "admissible_triggers_pass_semantics_unknown", "controlled_trigger_failure"

    def rerun_summary(rows):
        st = Counter(r["status"] for r in rows)
        resolved = st[NOTREP] + st[REP] + st["compile_command_failed_twice"]
        return {"candidates": len(rows), "bugs": len({r["bug"] for r in rows}), "statuses": dict(st),
                "failing_occurrences": sum(r["failing_occurrences"] for r in rows),
                "not_reproduced_of_resolved": rate(st[NOTREP], resolved),
                "not_reproduced_of_all_rerun": rate(st[NOTREP], len(rows))}

    val = {"defects4j_fixrerun": {
        "source": "results/v4/c1_fixrerun (selection: archived-incorrect members of rename-aware classes holding a "
                  "fix-equivalent member) and results/v4/c1_fixrerun_run_v1/*/terminal.json",
        "recorded_summary": {k: v for k, v in json.loads(FIXRERUN_RES.read_text()).items() if k != "comparisons"},
        "all_80": rerun_summary(rerun_rows),
        "by_direct_level": {str(l): rerun_summary([r for r in rerun_rows if r["direct_level"] == l])
                            for l in sorted({r["direct_level"] for r in rerun_rows})},
        "positive_control_scope_L2": rerun_summary([r for r in rerun_rows if r["in_scope"] and 0 < r["direct_level"] <= 2]),
        "positive_control_scope_L3": rerun_summary([r for r in rerun_rows if r["in_scope"] and 0 < r["direct_level"] <= 3]),
        "non_not_reproduced": [r for r in rerun_rows if r["status"] != NOTREP],
        "by_config_failing_occurrences": {}}}
    cfg_cov = defaultdict(Counter)
    for r in rerun_rows:
        for o in by_cid.get(r["candidate_id"], []):
            if verdict(o) not in ("pass", "unknown"):
                cfg_cov[o["cfg"]][r["status"]] += 1
    val["defects4j_fixrerun"]["by_config_failing_occurrences"] = {c: dict(v) for c, v in sorted(cfg_cov.items())}

    # coverage of every in-scope failing fix copy (L3) by R or census, exact text
    def coverage(rows, lookup):
        cov = Counter()
        texts_bug = defaultdict(Counter)
        for o in rows:
            s = lookup(o["cid"])
            if s:
                texts_bug[(o["bug"], o["level"] > 0)][s] += 1
        for o in rows:
            if not o["level"] or verdict(o) in ("pass", "unknown") or not in_scope(o):
                continue
            s = lookup(o["cid"])
            if s:
                cov["exact_text:" + s] += 1
            elif texts_bug.get((o["bug"], True)):
                cov["only_other_copy_text_in_bug:" + "+".join(sorted(texts_bug[(o["bug"], True)]))] += 1
            else:
                cov["no_reexecution"] += 1
        return dict(cov)

    val["defects4j_failing_copy_occurrence_coverage_L3"] = coverage(
        d4, lambda c: rstat.get(c) or (("census:" + census[c]) if c in census else None))
    he = [o for o in occ if o["bench"] == "humanevaljava"]
    val["humanevaljava_e3_failing_copy_occurrence_coverage_L3"] = coverage(he, lambda c: e3.get(c))
    # unique-candidate view of HE E3
    he_u = defaultdict(list)
    for o in he:
        if o["level"] and verdict(o) not in ("pass", "unknown"):
            he_u[o["cid"]].append(o)
    he_copy_ids_bug = defaultdict(set)
    for o in he:
        if o["level"]:
            he_copy_ids_bug[o["bug"]].add(o["cid"])
    u = Counter()
    for c, os_ in he_u.items():
        if c in e3:
            u["exact_text_executed:" + e3[c]] += 1
        else:
            others = {e3[x] for x in he_copy_ids_bug[os_[0]["bug"]] if x in e3}
            u["only_other_copy_text_in_bug:" + "+".join(sorted(others)) if others else "no_e3_evidence"] += 1
    ex_pass = sum(v for k, v in u.items() if k == "exact_text_executed:admissible_all_tests_pass")
    ex_all = sum(v for k, v in u.items() if k.startswith("exact_text_executed:"))
    val["humanevaljava_e3_unique_failing_copies"] = {
        "unique_failing_copy_candidates": len(he_u), "breakdown": dict(u),
        "exact_text_executed_passed": rate(ex_pass, ex_all),
        "note": "retrospective: E3 executed archived-unknown records chosen for the selector comparison, before and "
                "independently of this analysis; it is not a prediction test"}
    res["validation"] = val

    # ---------------------------------------------------------------- effect on published per-configuration counts
    passed_ids = {c for c, s in rstat.items() if s == NOTREP} | {c for c, s in census.items() if s == NOTREP} | \
                 {c for c, s in e3.items() if s == "admissible_all_tests_pass"}
    PASS = {NOTREP, "admissible_all_tests_pass"}

    def status_of(o):
        if o["bench"] == "defects4j":
            return rstat.get(o["cid"]) or census.get(o["cid"])
        if o["bench"] == "humanevaljava":
            return e3.get(o["cid"])
        return None

    bug_status = defaultdict(set)
    for o in occ:
        if o["level"] and in_scope(o):
            s = status_of(o)
            if s:
                bug_status[(o["bench"], o["bug"])].add(s)

    def validated_equiv(o):
        """Exact text re-executed and passed; or exact text not re-executed and every re-executed copy text of the
        same bug passed."""
        s = status_of(o)
        if s:
            return s in PASS
        st = bug_status.get((o["bench"], o["bug"]))
        return bool(st) and st <= PASS

    pub = {}
    flags = {}
    for bench in BENCHES:
        scope = CS2.excluded_bug_set(bench)
        for cfg in sorted({c for b, c in counts if b == bench}):
            sets = counts[(bench, cfg)]
            rows = [o for o in occ if o["bench"] == bench and o["cfg"] == cfg and o["bug"] in scope and in_scope(o)
                    and o["level"] and verdict(o) not in ("pass", "unknown")]
            f = {lv: {o["bug"] for o in rows if o["level"] <= i} for i, lv in enumerate(LEVELS, 1)}
            f["validated"] = {o["bug"] for o in rows if o["cid"] in passed_ids}
            f["validated_or_equivalent"] = {o["bug"] for o in rows if validated_equiv(o)}
            flags[(bench, cfg)] = f
            key = CFG_KEY.get(cfg)
            published = CS2.PUBLISHED[key][bench] if key else None
            row = {"published": {"plausible": published[0], "semantic": published[3]} if published else None,
                   "computed": {m: len(sets[m]) for m in ("plausible", "semantic")}, "gain": {}}
            for sc, bugs in f.items():
                row["gain"][sc] = {"plausible": len(bugs - sets["plausible"]), "semantic": len(bugs - sets["semantic"]),
                                   "flagged_bugs": len(bugs), "semantic_bugs_added": sorted(bugs - sets["semantic"]),
                                   "plausible_bugs_added": sorted(bugs - sets["plausible"])}
            failing_cands = {(o["bug"], o["t"]) for o in rows if o["level"] <= 1}
            row["failing_fix_copy_candidates_L1"] = len(failing_cands)
            pub.setdefault(bench, {})[key or cfg] = row
    res["published_counts"] = pub

    # orderings: all pairs, computed counts vs corrected
    order = {}
    for bench in BENCHES:
        keys = [k for k in CS2.PUBLISHED if k in pub[bench]]
        bo = {}
        for metric in ("semantic", "plausible"):
            base = {k: pub[bench][k]["computed"][metric] for k in keys}
            for sc in ("L1_text", "L2_ast", "L3_rename", "validated", "validated_or_equivalent"):
                corr = {k: base[k] + pub[bench][k]["gain"][sc][metric] for k in keys}
                changes = []
                for a, b in combinations(keys, 2):
                    s0 = (base[a] > base[b]) - (base[a] < base[b])
                    s1 = (corr[a] > corr[b]) - (corr[a] < corr[b])
                    if s0 != s1:
                        kind = "reversal" if s0 * s1 == -1 else "tie_created" if s1 == 0 else "tie_broken"
                        same_table = [t for t, ks in TABLES.items() if a in ks and b in ks]
                        changes.append({"a": a, "b": b, "base": [base[a], base[b]], "corrected": [corr[a], corr[b]],
                                        "kind": kind, "same_published_table": same_table})
                bo[f"{metric}:{sc}"] = changes
        order[bench] = bo
    res["ordering_changes_all_pairs"] = order

    claims = []
    import csv
    with open(CLAIMS, encoding="utf-8", newline="") as f:
        for c in csv.DictReader(f):
            bench, a, b = c["benchmark"], CFG_KEY[c["config_a"]], CFG_KEY[c["config_b"]]
            ba, bb = pub[bench][a]["computed"]["semantic"], pub[bench][b]["computed"]["semantic"]
            row = {"claim_id": c["claim_id"], "benchmark": bench, "higher": a, "lower": b,
                   "reported": [int(c["reported_a"]), int(c["reported_b"])], "computed": [ba, bb]}
            for sc in ("L1_text", "L3_rename", "validated", "validated_or_equivalent"):
                ga, gb = pub[bench][a]["gain"][sc]["semantic"], pub[bench][b]["gain"][sc]["semantic"]
                row[sc] = {"corrected": [ba + ga, bb + gb], "margin": (ba + ga) - (bb + gb),
                           "margin_if_only_lower_corrected": ba - (bb + gb)}
            row["base_margin"] = ba - bb
            claims.append(row)
    res["stated_claims"] = claims
    res["stated_claims_summary"] = {sc: {"reversed": sum(1 for r in claims if r[sc]["margin"] < 0),
                                         "tied": sum(1 for r in claims if r[sc]["margin"] == 0),
                                         "reversed_or_tied_if_only_lower_corrected":
                                             sum(1 for r in claims if r[sc]["margin_if_only_lower_corrected"] <= 0)}
                                    for sc in ("L1_text", "L3_rename", "validated", "validated_or_equivalent")}

    (OUT / "positive_controls.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    with open(OUT / "flagged_occurrences.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for r in flagged_rows:
            f.write(json.dumps(r) + "\n")
    print("wrote", OUT / "positive_controls.json", flush=True)
    write_md(res)


# ---------------------------------------------------------------------------------------------------- report

PROBE = {"repairllama_defects4j": "197/1,867 (10.6%) occurrences, all D4J bugs, curated file, token identity",
         "repairllama_humanevaljava": "438/2,847 (15.4%)", "repairllama_gitbugjava": "0/583",
         "repairbench_gitbugjava": "56 failing copies in 6 bugs (check report); 'clean' in the candidate text"}
SHORT = {"gpt4_gpt-zero-shot": "GPT-4", "gpt35_gpt-zero-shot": "GPT-3.5", "repairllama_ir4_or2": "RepairLLaMA IR4xOR2",
         "repairllama_ir1_or1": "IR1xOR1", "repairllama_ir1_or3": "IR1xOR3", "repairllama_ir1_or4": "IR1xOR4",
         "repairllama_ir2_or2": "IR2xOR2", "repairllama_ir3_or2": "IR3xOR2", "deepseek_base": "DeepSeek base",
         "deepseek_fft": "DeepSeek full FT", "deepseek_lora": "DeepSeek LoRA",
         "zero-shot-cloze_codellama": "CodeLlama zero-shot IR3", "zero-shot-cloze_codellama-ir4": "CodeLlama zero-shot IR4",
         "zero-shot-cloze_repairllama-fft": "CodeLlama full FT"}
KEY_SHORT = {k: SHORT[v["config"]] for k, v in CS2.PUBLISHED.items()}


def write_md(res):
    L = []
    w = L.append
    w("# C5: built-in positive controls in released LLM-APR archives")
    w("")
    w("Exploratory and post hoc. Nothing was executed for this analysis. Script: "
      "`analysis_tools/v4/positive_controls.py`; data: `positive_controls.json`, `flagged_occurrences.jsonl`.")
    w("")
    A = res["artifacts"]
    d1 = A["repairllama_defects4j"]["levels"]["L1_text"]
    h1 = A["repairllama_humanevaljava"]["levels"]["L1_text"]
    g1 = A["repairllama_gitbugjava"]["levels"]["L1_text"]["all"]
    b1 = A["repairbench_gitbugjava"]["levels"]["L1_text"]["all"]
    wb = res["within_bug_pairs"]
    fr = res["validation"]["defects4j_fixrerun"]
    hev = res["validation"]["humanevaljava_e3_unique_failing_copies"]
    cl = {r["claim_id"]: r for r in res["stated_claims"]}
    g4 = cl.get("RL2-humanevaljava-gpt4-vs-repairllama")
    zero_he = [c for c, s in h1["per_config"].items() if s["occurrences"]["k"] == 0]
    zero_n = sum(h1["per_config"][c]["occurrences"]["n"] for c in zero_he)

    def pc(art, c):
        return pct(art["per_config"][c]["occurrences"])

    w("## Headline (L1 text identity unless stated)")
    w("")
    w(f"- Fix copies archived as failing: RepairLLaMA Defects4J {pct(d1['all']['occurrences'])} in "
      f"{d1['all']['bugs_with_failing_copies']} bugs; HumanEval-Java {pct(h1['all']['occurrences'])} in "
      f"{h1['all']['bugs_with_failing_copies']} bugs; RepairLLaMA GitBug-Java {pct(g1['occurrences'])}; RepairBench "
      f"GitBug-Java {pct(b1['occurrences'])} in {b1['bugs_with_failing_copies']} bugs (not clean).")
    w(f"- Defects4J by configuration: GPT-4 {pc(d1, 'gpt4_gpt-zero-shot')}, GPT-3.5 {pc(d1, 'gpt35_gpt-zero-shot')}, "
      f"IR1xOR3 {pc(d1, 'repairllama_ir1_or3')}; RepairLLaMA IR4xOR2 {pc(d1, 'repairllama_ir4_or2')}, DeepSeek LoRA "
      f"{pc(d1, 'deepseek_lora')}. Most GPT failures are compile failures (GPT-4 "
      f"{d1['per_config']['gpt4_gpt-zero-shot']['fail_compile']} of {d1['per_config']['gpt4_gpt-zero-shot']['occurrences']['k']}).")
    p = wb["defects4j"]["gpt4_gpt-zero-shot vs repairllama_ir4_or2"]
    w(f"- The Defects4J gap is not bug mix: on the {p['shared_bugs']} bugs where both produced copies, GPT-4 "
      f"{pct(p['gpt4_gpt-zero-shot'])} vs RepairLLaMA {pct(p['repairllama_ir4_or2'])} (MH odds ratio "
      f"{p['cmh']['mh_odds_ratio']}, p = {p['cmh']['p']}).")
    p = wb["humanevaljava"]["gpt4_gpt-zero-shot vs repairllama_ir4_or2"]
    w(f"- HumanEval-Java: GPT-3.5 {pc(h1, 'gpt35_gpt-zero-shot')}, IR1xOR3 {pc(h1, 'repairllama_ir1_or3')}, "
      f"IR2xOR2/IR3xOR2/IR4xOR2 24-27%, GPT-4 {pc(h1, 'gpt4_gpt-zero-shot')}; the {len(zero_he)} DeepSeek and "
      f"zero-shot/full-fine-tuning CodeLlama configurations 0/{zero_n}. Here GPT-4 and RepairLLaMA do not differ on "
      f"shared bugs ({pct(p['gpt4_gpt-zero-shot'])} vs {pct(p['repairllama_ir4_or2'])}, p = {p['cmh']['p']}); the split "
      "is between two groups of configurations.")
    w(f"- Validation already on disk: R did not reproduce {pct(fr['all_80']['not_reproduced_of_resolved'])} of the "
      f"resolved re-runs (68 of 80 overall, 9 unresolved placement); inside the positive-control scope at L1-L2 "
      f"{pct(fr['positive_control_scope_L2']['not_reproduced_of_resolved'])}. Every HumanEval-Java failing copy whose "
      f"exact text E3 executed passed: {pct(hev['exact_text_executed_passed'])}.")
    if g4:
        w(f"- Published counts: the 23 stated directions never reverse. The conceded HumanEval-Java GPT-4 > RepairLLaMA "
          f"margin ({g4['computed'][0]} vs {g4['computed'][1]}) shrinks to {g4['L1_text']['margin']:+d} if every flag "
          f"is spurious, {g4['validated_or_equivalent']['margin']:+d} with the validated-or-equivalent flags, and "
          f"would only reverse ({g4['L1_text']['margin_if_only_lower_corrected']:+d}) if RepairLLaMA's flags were all "
          "spurious and GPT-4's all genuine. Orderings inside a published table that change are listed in section 5.")
    w("")
    w("## Discrepancies with the panel probe")
    w("")
    w(f"- Defects4J total: probe 197/1,867 (curated `all` file, all bugs, v4core.text_norm); here "
      f"{pct(d1['all_bugs_unrestricted']['occurrences'])} from the raw files over all bugs and "
      f"{pct(d1['all']['occurrences'])} in the single-method scope. The raw files hold "
      f"{res['curated_join'].get('not_in_curated', 0)} evaluated outputs that the curated files do not.")
    w(f"- RepairLLaMA IR4xOR2 on Defects4J: probe 5/176 (2.8%); here {pc(d1, 'repairllama_ir4_or2')}. The fifth "
      "failure is JxPath-14, which is outside the positive-control scope (its fix spans 3 methods).")
    w(f"- GPT-4 on Defects4J: probe 87/272; here {pc(d1, 'gpt4_gpt-zero-shot')}, which matches the judge's raw-file count.")
    w(f"- HumanEval-Java: probe 438/2,847; here {pct(h1['all']['occurrences'])}. GitBug-Java: probe 0/583; here "
      f"{pct(g1['occurrences'])}. RepairBench: 56 failing copies in 6 bugs, as in the check report.")
    con_d, con_h = A["repairllama_defects4j"]["contradictions_all_outputs"], A["repairllama_humanevaljava"]["contradictions_all_outputs"]
    w(f"- Opposite verdicts on byte-identical outputs: Defects4J GPT-4 {con_d['gpt4_gpt-zero-shot'].get('pass_fail_strings_fix_copies', 0)} "
      f"and GPT-3.5 {con_d['gpt35_gpt-zero-shot'].get('pass_fail_strings_fix_copies', 0)} strings among fix copies, as in "
      f"the probe (all outputs: {con_d['gpt4_gpt-zero-shot'].get('pass_fail_strings', 0)} and "
      f"{con_d['gpt35_gpt-zero-shot'].get('pass_fail_strings', 0)}). HumanEval-Java does not match the probe's 54 and 42: "
      f"GPT-4 {con_h['gpt4_gpt-zero-shot'].get('pass_fail_strings_fix_copies', 0)} and GPT-3.5 "
      f"{con_h['gpt35_gpt-zero-shot'].get('pass_fail_strings_fix_copies', 0)} among fix copies, "
      f"{con_h['gpt4_gpt-zero-shot'].get('pass_fail_strings', 0)} and {con_h['gpt35_gpt-zero-shot'].get('pass_fail_strings', 0)} "
      "over all outputs.")
    w(f"- Byte-identical outputs that both compiled and failed to compile in the same bug (compilation should be "
      f"deterministic): Defects4J GPT-3.5 {con_d['gpt35_gpt-zero-shot'].get('compile_true_false_strings', 0)}, GPT-4 "
      f"{con_d['gpt4_gpt-zero-shot'].get('compile_true_false_strings', 0)}, IR1xOR4 "
      f"{con_d.get('repairllama_ir1_or4', {}).get('compile_true_false_strings', 0)}, IR1xOR3 "
      f"{con_d.get('repairllama_ir1_or3', {}).get('compile_true_false_strings', 0)}; HumanEval-Java GPT-3.5 "
      f"{con_h['gpt35_gpt-zero-shot'].get('compile_true_false_strings', 0)}, GPT-4 "
      f"{con_h['gpt4_gpt-zero-shot'].get('compile_true_false_strings', 0)}. The probe did not report this. Only "
      "configurations that repeat outputs can show it, so it cannot be compared across all configurations.")
    pd = res["published_counts"]["defects4j"]
    w("- Defects4J count deltas (semantic, L1): " + ", ".join(
        f"{KEY_SHORT[k]} +{pd[k]['gain']['L1_text']['semantic']}" for k in
        ("gpt4", "ir1_or3", "baseline_ir3", "gpt35", "codellama_fft", "repairllama", "ir2_or2")) +
      "; the check report had +8, +7, +6, +5, +5, +4, +4. IR1xOR3's extra bug there is Codec-17, a text_norm false "
      "positive (`new String` vs `newString`). Re-running the check script's own logic (curated file, single-method "
      "bugs) gives RepairLLaMA +3 and IR2xOR2 +2, so its +4 values could not be reproduced; the per-bug lists used "
      "here are in positive_controls.json. The HumanEval-Java deltas match the check report.")
    w(f"- HumanEval-Java E3 overlap: the check report found 110 of 131 flagged records with an equivalent text in E3. "
      f"Here, of {hev['unique_failing_copy_candidates']} unique failing copy candidates (L3, any label), "
      + ", ".join(f"{v} {k}" for k, v in sorted(hev["breakdown"].items(), key=lambda x: -x[1])) + ".")
    w("")
    w("## What is measured")
    w("")
    w("- **Positive control:** an archived generated candidate that is a copy of the developer fix for its bug. "
      "If the fix lies wholly inside the method that the candidate replaces, the copy must pass the tests.")
    w("- **Occurrence:** one archived evaluation entry (one of the up to 10 outputs per bug and configuration). "
      "**Unique candidate:** one distinct text per bug and configuration (or per bug, for the artifact total).")
    w("- **Archived failure:** compile is False or test is False. RepairBench and RepairLLaMA GitBug-Java do not "
      "record compile results, so there every failure is listed as a test failure.")
    w("- **Identity levels** (cumulative):")
    w("  - L1 text: the same token sequence once comments and whitespace are removed; string literals are kept verbatim;")
    w("  - L2 AST: L1, or the same javac AST fingerprint (`BatchMethodFingerprint`, which keeps annotations);")
    w("  - L3 rename: L2, or the same `BatchMethodNormalize` h_noann_alpha (annotations removed, locals and parameters renamed).")
    w("- **Scope:** Defects4J positive controls are restricted to the "
      f"{res['defects4j_scope']['single_method_consistent_bugs']} bugs that `results/v4/single_function_audit` marks "
      "single_method_consistent. Excluded: " + ", ".join(f"{b} ({s})" for b, s in
                                                          sorted(res['defects4j_scope']['excluded_bugs'].items())) + ".")
    w("- **95% intervals** are Clopper-Pearson on occurrences. Occurrences of the same text in the same bug are not "
      "independent, so the intervals are too narrow; the bug and unique-candidate counts are given for that reason.")
    w("- The failure rate of fix copies is an upper bound on harness false rejection for this kind of patch. It is not "
      "a rate for all candidates, because fix copies are not a random sample.")
    w("")
    w("## 1. Artifact totals")
    w("")
    w("| Artifact | Level | Fix-copy occurrences archived failing (95% CI) | Compile / test failures | Bugs with copies / with failing copies | Unique candidates with a failing occurrence | of which every occurrence fails |")
    w("|---|---|---|---|---|---|---|")
    for name, a in res["artifacts"].items():
        for lv in LEVELS:
            s = a["levels"][lv]["all"]
            w(f"| {name} | {lv} | {pct(s['occurrences'])} | {s['fail_compile']} / {s['fail_test']} | "
              f"{s['bugs_with_copies']} / {s['bugs_with_failing_copies']} | {s['unique_candidates']['k']}/{s['unique_candidates']['n']} | "
              f"{s['unique_all_occurrences_fail']} |")
    d = res["artifacts"]["repairllama_defects4j"]["levels"]
    w("")
    w("Defects4J without the single-method restriction (for comparison with the probe): " + "; ".join(
        f"{lv} {pct(d[lv]['all_bugs_unrestricted']['occurrences'])}" for lv in LEVELS) + ".")
    w("")
    w("RepairLLaMA's own flags on the failing copies: " + "; ".join(
        f"{n} {a['levels']['L1_text']['all']['failing_copies_with_exact_or_ast_flag']} of "
        f"{a['levels']['L1_text']['all']['occurrences']['k']} failing L1 copies carry exact_match or ast_match = True "
        f"(passing copies: {a['levels']['L1_text']['all']['passing_copies_with_exact_or_ast_flag']} of "
        f"{a['levels']['L1_text']['all']['passing_copies']})" for n, a in res["artifacts"].items()) + ".")
    w("")
    w("## 2. Per configuration (L1 text identity; L3 in the last column)")
    w("")
    for name, a in res["artifacts"].items():
        p1, p3 = a["levels"]["L1_text"]["per_config"], a["levels"]["L3_rename"]["per_config"]
        con = a["contradictions_all_outputs"]
        w(f"### {name}")
        w("")
        w("| Configuration | Fix-copy occurrences failing (95% CI) | Compile / test | Bugs with failing copies | Unique failing / unique copies | Byte-identical outputs with pass and fail verdicts in one bug (all outputs; fix copies) | Byte-identical outputs that both compiled and failed to compile | L3: failing (95% CI) |")
        w("|---|---|---|---|---|---|---|---|")
        cfgs = sorted(set(p1) | set(p3) | set(con), key=lambda c: -(p1.get(c, {}).get("occurrences", {}).get("rate") or 0))
        for c in cfgs:
            s1, s3, k = p1.get(c), p3.get(c), con.get(c, {})
            first = (f"{pct(s1['occurrences'])} | {s1['fail_compile']} / {s1['fail_test']} | {s1['bugs_with_failing_copies']} | "
                     f"{s1['unique_candidates']['k']}/{s1['unique_candidates']['n']}") if s1 else "no copies | - | - | -"
            w(f"| {SHORT.get(c, c)} | {first} | {k.get('pass_fail_strings', 0)}; {k.get('pass_fail_strings_fix_copies', 0)} | "
              f"{k.get('compile_true_false_strings', 0)} | {pct(s3['occurrences']) if s3 else '-'} |")
        w("")
        cs = a.get("contradictions_all_outputs_stripped_text", {})
        w("Contradiction columns cover all bugs (no scope filter). With leading/trailing whitespace ignored the "
          "pass/fail counts are: " + (", ".join(f"{SHORT.get(c, c)} {v.get('pass_fail_strings', 0)} "
                                                 f"({v.get('pass_fail_strings_fix_copies', 0)} fix copies)"
                                                 for c, v in cs.items() if v.get("pass_fail_strings")) or "none") + ".")
        w("")
    w("## 3. Is the error differential between configurations?")
    w("")
    w("Each configuration against all other configurations, restricted to the bugs where both produced fix copies "
      "(L1), with a Cochran-Mantel-Haenszel test stratified by bug. This removes differences in bug mix.")
    w("")
    for name in ("repairllama_defects4j", "repairllama_humanevaljava", "repairbench_gitbugjava"):
        pc = res["artifacts"][name]["levels"]["L1_text"]["per_config"]
        rows = [(c, s["vs_other_configs_same_bugs"]) for c, s in pc.items() if s["occurrences"]["k"]]
        if not rows:
            continue
        w(f"### {name}")
        w("")
        w("| Configuration | Shared bugs | Its failure rate on shared bugs | Other configurations on the same bugs | MH odds ratio | p |")
        w("|---|---|---|---|---|---|")
        for c, v in sorted(rows, key=lambda x: -(x[1]["cfg_rate_on_shared_bugs"]["rate"] or 0)):
            w(f"| {SHORT.get(c, c)} | {v['shared_bugs']} | {pct(v['cfg_rate_on_shared_bugs'])} | "
              f"{pct(v['others_rate_on_shared_bugs'])} | {v['cmh'].get('mh_odds_ratio')} | {v['cmh'].get('p')} |")
        w("")
    w("Pairs compared directly (bugs where both configurations produced an L1 fix copy):")
    w("")
    w("| Benchmark | Pair | Shared bugs | First config failing | Second config failing | MH odds ratio | p |")
    w("|---|---|---|---|---|---|---|")
    for bench, pairs in res["within_bug_pairs"].items():
        for pname, v in pairs.items():
            a, b = pname.split(" vs ")
            w(f"| {bench} | {SHORT.get(a, a)} vs {SHORT.get(b, b)} | {v['shared_bugs']} | {pct(v[a])} | {pct(v[b])} | "
              f"{v['cmh'].get('mh_odds_ratio')} | {v['cmh'].get('p')} |")
    w("")
    w("## 4. Validation by existing re-execution (retrospective)")
    w("")
    fr = res["validation"]["defects4j_fixrerun"]
    w("### Defects4J fix re-run (R)")
    w("")
    w("R re-executed the 80 archived-incorrect candidates that sit in a rename-aware class with a fix-equivalent "
      "member (two repetitions, controls).")
    w("")
    w("| Subset | Candidates | Bugs | Not reproduced | Reproduced | Compile failure | Unresolved placement | Not reproduced / resolved (95% CI) |")
    w("|---|---|---|---|---|---|---|---|")
    for lab, s in [("all 80", fr["all_80"])] + [(f"direct identity level {k}", v) for k, v in fr["by_direct_level"].items()] + \
            [("in positive-control scope, L1-L2", fr["positive_control_scope_L2"]),
             ("in positive-control scope, L1-L3", fr["positive_control_scope_L3"])]:
        st = s["statuses"]
        w(f"| {lab} | {s['candidates']} | {s['bugs']} | {st.get('admissible_triggers_pass_semantics_unknown', 0)} | "
          f"{st.get('controlled_trigger_failure', 0)} | {st.get('compile_command_failed_twice', 0)} | "
          f"{st.get('unresolved_placement_or_repetition', 0)} | {pct(s['not_reproduced_of_resolved'])} |")
    w("")
    w("Candidates that were not 'not reproduced': " + "; ".join(
        f"{r['bug']} {r['status']} (level {r['direct_level']}, {', '.join(SHORT.get(c, c) for c in r['configs'])})"
        for r in fr["non_not_reproduced"]) + ".")
    w("")
    w("Failing occurrences behind the 80 re-run candidates, by configuration and R status: " + "; ".join(
        f"{SHORT.get(c, c)} {dict(v)}" for c, v in fr["by_config_failing_occurrences"].items()) + ".")
    w("")
    w("Re-execution coverage of every in-scope failing Defects4J fix copy (L3, occurrences; exact text means the "
      "same obscand id was re-run by R or by the conflict census):")
    w("")
    for k, v in sorted(res["validation"]["defects4j_failing_copy_occurrence_coverage_L3"].items(), key=lambda x: -x[1]):
        w(f"- {k}: {v}")
    w("")
    he = res["validation"]["humanevaljava_e3_unique_failing_copies"]
    w("### HumanEval-Java E3 (retrospective, not a prediction)")
    w("")
    w(f"Unique failing fix-copy candidates (L3): {he['unique_failing_copy_candidates']}. "
      f"Exact text executed in E3 and passed every test: {pct(he['exact_text_executed_passed'])}.")
    w("")
    for k, v in sorted(he["breakdown"].items(), key=lambda x: -x[1]):
        w(f"- {k}: {v}")
    w("")
    w("Occurrence-level coverage (L3):")
    w("")
    for k, v in sorted(res["validation"]["humanevaljava_e3_failing_copy_occurrence_coverage_L3"].items(), key=lambda x: -x[1]):
        w(f"- {k}: {v}")
    w("")
    w("## 5. Effect on the published RepairLLaMA counts")
    w("")
    w("Counts are bugs, inside the paper's scope (single-function bugs minus Math-28, Math-44, JacksonDatabind-82; "
      "Defects4J additionally needs a single_method_consistent fix for a copy to count). 'Computed' applies the "
      "paper's union logic to the raw files. A bug is added when the configuration has an archived failing fix copy "
      "for it and no plausible (or semantic) candidate. 'Validated' adds only bugs whose failing copy text was "
      "re-executed and passed (R, census or E3). 'Validated or equivalent' also adds a bug when the failing copy's "
      "own text was not re-executed but every re-executed copy text of that bug passed. The L1-L3 columns are upper "
      "bounds: they assume every flagged failure is spurious. The validated columns are lower bounds, and because "
      "re-execution covered configurations unevenly (E3 and the census only ran archived-unknown records), orderings "
      "under the validated columns can move for reasons of coverage alone.")
    w("")
    for bench in BENCHES:
        w(f"### {bench}")
        w("")
        w("| Configuration | Semantic: published / computed | + L1 | + L2 | + L3 | + validated | + validated or equivalent | Plausible: published / computed | + L1 | + L3 | + validated | + validated or equivalent | Failing fix-copy candidates (L1) |")
        w("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for k, r in res["published_counts"][bench].items():
            g = r["gain"]
            pubv = r["published"] or {"semantic": "-", "plausible": "-"}
            w(f"| {KEY_SHORT.get(k, k)} | {pubv['semantic']} / {r['computed']['semantic']} | {g['L1_text']['semantic']} | "
              f"{g['L2_ast']['semantic']} | {g['L3_rename']['semantic']} | {g['validated']['semantic']} | "
              f"{g['validated_or_equivalent']['semantic']} | "
              f"{pubv['plausible']} / {r['computed']['plausible']} | {g['L1_text']['plausible']} | {g['L3_rename']['plausible']} | "
              f"{g['validated']['plausible']} | {g['validated_or_equivalent']['plausible']} | {r['failing_fix_copy_candidates_L1']} |")
        w("")
    w("### Pairwise orderings that change (all 91 pairs per benchmark; computed counts)")
    w("")
    w("| Benchmark | Metric : scenario | Pair | Before | After | Change | Same published table |")
    w("|---|---|---|---|---|---|---|")
    n_changes = 0
    for bench, bo in res["ordering_changes_all_pairs"].items():
        for key, ch in bo.items():
            for c in ch:
                n_changes += 1
                w(f"| {bench} | {key} | {KEY_SHORT[c['a']]} vs {KEY_SHORT[c['b']]} | {c['base'][0]} vs {c['base'][1]} | "
                  f"{c['corrected'][0]} vs {c['corrected'][1]} | {c['kind']} | {', '.join(c['same_published_table']) or 'none'} |")
    if not n_changes:
        w("| - | - | none | - | - | - | - |")
    w("")
    w("### The 23 directions stated in the paper (semantic-match bugs)")
    w("")
    w("| Claim | Reported | Computed | L1 corrected (margin) | L3 corrected (margin) | Validated (margin) | Validated or equivalent (margin) | Margin if only the lower config is corrected (L3) |")
    w("|---|---|---|---|---|---|---|---|")
    for r in res["stated_claims"]:
        ve = r["validated_or_equivalent"]
        w(f"| {r['benchmark']}: {KEY_SHORT[r['higher']]} > {KEY_SHORT[r['lower']]} | {r['reported'][0]} vs {r['reported'][1]} | "
          f"{r['computed'][0]} vs {r['computed'][1]} | {r['L1_text']['corrected'][0]} vs {r['L1_text']['corrected'][1]} ({r['L1_text']['margin']:+d}) | "
          f"{r['L3_rename']['corrected'][0]} vs {r['L3_rename']['corrected'][1]} ({r['L3_rename']['margin']:+d}) | "
          f"{r['validated']['corrected'][0]} vs {r['validated']['corrected'][1]} ({r['validated']['margin']:+d}) | "
          f"{ve['corrected'][0]} vs {ve['corrected'][1]} ({ve['margin']:+d}) | "
          f"{r['L3_rename']['margin_if_only_lower_corrected']:+d} |")
    w("")
    w("Summary: " + "; ".join(f"{sc}: {v['reversed']} reversed, {v['tied']} tied, "
                              f"{v['reversed_or_tied_if_only_lower_corrected']} reversed or tied if only the lower "
                              f"configuration were corrected" for sc, v in res["stated_claims_summary"].items()) + ".")
    w("")
    w("## 6. Caveats")
    w("")
    w("- A fix copy can legitimately fail when the official fix touches code outside the replaced method. JxPath-14 "
      "(fix spans 3 methods) is the known case; its copies reproduced their failure under R. Such bugs are excluded "
      "here, but the audit only checks the patch footprint, so the measured rates are upper bounds on harness noise "
      "unless confirmed by re-execution.")
    w("- The rename-aware normaliser removes annotations. Collections-26 is an L3-only match whose candidate adds an "
      "`@Override`; it fails to compile under R. L1 and L2 keep annotations; prefer them for headline numbers.")
    w("- L1 treats adjacent operator characters as separate tokens (`a + +b` equals `a ++b`). L2 does not.")
    w("- R ran the trigger tests; 'not reproduced' means the archived failure did not recur, not that the full "
      "suite passed. The cause of the archived failures is not established; call them non-reproducing archived failures.")
    w("- The recount assumes that a passing copy would have been flagged as an exact/AST/semantic match. Published "
      "counts with the corrections are upper bounds unless the 'validated' column is used.")
    w("- Everything here is post hoc, designed after the C1 sensitivity and the R results.")
    w("")
    (OUT / "POSITIVE_CONTROLS.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("wrote", OUT / "POSITIVE_CONTROLS.md", flush=True)


if __name__ == "__main__":
    if "--md-only" in sys.argv:
        write_md(json.loads((OUT / "positive_controls.json").read_text(encoding="utf-8")))
    else:
        main()
