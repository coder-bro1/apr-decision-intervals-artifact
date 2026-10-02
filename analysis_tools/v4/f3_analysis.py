"""F3 analysis (ADDENDUM_V4_F3_DIFFTEST.md): find candidate counterexamples and prepare the hand review.

Candidate counterexample: a generated test that is in no failing list of the fixed version (both repetitions, suite
ran with reports) and in the failing list of the candidate in both repetitions. For each one, the failure text and the
test method source are extracted into results/v4/f3_difftest/relevance_review.json with verdict = null; a human (and
Claude) fills in verdict ("witness" | "not_relevant:a|b|c|d") and reason. Existing verdicts are preserved on reruns.
"""
import argparse
import json
import re
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def failure_block(text, test):
    m = re.search(r"^--- " + re.escape(test) + r"\n(.*?)(?=^--- |\Z)", text, re.S | re.M)
    return (m.group(1) if m else "")[:3000]


def test_source(suite_tar, test):
    cls, _, meth = test.partition("::")
    try:
        with tarfile.open(suite_tar) as t:
            for mem in t.getmembers():
                if mem.name.endswith(cls.replace(".", "/") + ".java"):
                    src = t.extractfile(mem).read().decode("utf-8", "replace")
                    i = src.find(" " + meth + "(")
                    if i < 0:
                        return src[:3000]
                    start = src.rfind("@Test", 0, i)
                    depth, j, opened = 0, src.find("{", i), False
                    k = j
                    while k < len(src):
                        if src[k] == "{":
                            depth += 1
                            opened = True
                        elif src[k] == "}":
                            depth -= 1
                            if opened and depth == 0:
                                break
                        k += 1
                    return src[max(start, 0):k + 1][:6000]
    except (tarfile.TarError, OSError):
        return ""
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=ROOT / "results/v4/f3_difftest")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    review_path = args.out / "relevance_review.json"
    old = {}
    if review_path.exists():
        old = {(r["candidate_id"], r["suite"], r["test"]): r for r in json.loads(review_path.read_text())}
    items, per_job = [], []
    for run in args.runs:
        for job in sorted(p for p in run.iterdir() if p.is_dir()):
            rp = job / "evidence/result.json"
            if not rp.exists():
                continue
            r = json.loads(rp.read_text())
            fixed = [v for v in r["runs"] if v["variant"] == "fixed"]
            cands = sorted({v["variant"] for v in r["runs"]} - {"fixed", "buggy"})
            info = {"job": job.name, "status": r["status"], "suites": list(r.get("suites", {})), "candidates": {}}
            for s in r.get("suites", {}):
                fx = [v["suites"].get(s) for v in fixed]
                if len(fx) != 2 or not all(x and x["reports_present"] and not x["timeout"] for x in fx):
                    continue
                fixed_fail = set(fx[0]["failing"]) | set(fx[1]["failing"])
                for c in cands:
                    cv = [v["suites"].get(s) for v in r["runs"] if v["variant"] == c]
                    if len(cv) != 2 or not all(x and x["reports_present"] for x in cv):
                        info["candidates"].setdefault(c, {})[s] = "not_run"
                        continue
                    both = (set(cv[0]["failing"]) & set(cv[1]["failing"])) - fixed_fail
                    info["candidates"].setdefault(c, {})[s] = len(both)
                    for t in sorted(both):
                        key = f"{c[:24]}_r1_{Path(s).stem}"
                        ftxt = (job / "evidence" / f"{key}_failing_tests.txt")
                        rec = {"candidate_id": c, "bug": r["bug_id"], "suite": s, "test": t,
                               "failure": failure_block(ftxt.read_text(errors="replace"), t) if ftxt.exists() else "",
                               "test_source": test_source(job / "evidence/suites" / s, t),
                               "verdict": None, "reason": None}
                        prev = old.get((c, s, t))
                        if prev:
                            rec.update(verdict=prev["verdict"], reason=prev["reason"])
                        items.append(rec)
            per_job.append(info)
    review_path.write_text(json.dumps(items, indent=1))
    (args.out / "f3_summary.json").write_text(json.dumps({"jobs": per_job, "candidate_counterexamples": len(items),
                                                          "candidates_with_counterexample": len({i["candidate_id"] for i in items})}, indent=1))
    print(len(per_job), "jobs;", len(items), "candidate counterexamples;",
          len({i["candidate_id"] for i in items}), "candidates")


if __name__ == "__main__":
    main()
