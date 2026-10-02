"""F3 relevance review helper: prints, per candidate with counterexamples, the candidate-vs-developer-fix diff and every
counterexample (test source + failure head) so each can be read by hand. Writes nothing into results/.
Usage: f3_review_view.py [--bugs Lang-45 ...] [--exclude-bugs ...] [--full-failure]"""
import argparse
import difflib
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from validation_policy_contract import context_id  # noqa: E402

RR = ROOT / "results/v4/f3_difftest/relevance_review.json"
CASES = ROOT / "results/v4/f3_tier1_package_v1/cases"
LEGACY = [ROOT / f"llm_apr_dataset/llm_apr_defects4j_candidates_v2_candidates_{k}.jsonl" for k in ("all", "excluded")]


def fixes():
    out = defaultdict(set)
    for p in LEGACY:
        for line in open(p, encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                out[context_id(r["bug_id"], r["anchor"])].add(r["human_fix"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bugs", nargs="*")
    ap.add_argument("--exclude-bugs", nargs="*", default=[])
    ap.add_argument("--candidate")
    ap.add_argument("--full-failure", action="store_true")
    ap.add_argument("--no-diff", action="store_true")
    ap.add_argument("--review", type=Path, default=RR, help="relevance_review.json (default: Defects4J F3 tier 1)")
    ap.add_argument("--cases", type=Path, default=CASES, help="package cases folder")
    a = ap.parse_args()
    items = json.loads(a.review.read_text())
    fx = fixes()
    byc = defaultdict(list)
    for n, it in enumerate(items):
        byc[it["candidate_id"]].append((n, it))
    for cid, its in sorted(byc.items(), key=lambda kv: (kv[1][0][1]["bug"], kv[0])):
        bug = its[0][1]["bug"]
        if (a.bugs and bug not in a.bugs) or bug in a.exclude_bugs or (a.candidate and not cid.startswith(a.candidate)):
            continue
        case = json.loads((a.cases / f"{cid}.json").read_text())
        fix = fx.get(case["context_id"], set())
        print("=" * 100)
        print(f"{bug}  {cid[:20]}  counterexamples: {len(its)}  fixes known: {len(fix)}")
        if not a.no_diff:
            for f in sorted(fix):
                print("\n".join(difflib.unified_diff(f.splitlines(), case["patch"].splitlines(), "developer_fix", "candidate", lineterm="", n=2)))
        for n, it in its:
            print("-" * 60)
            print(f"[{n}] {it['suite']}  {it['test'].split('::')[-1]}")
            print(it["test_source"].strip())
            fail = it["failure"] or ""
            lines = fail.splitlines()
            print(">> " + ("\n>> ".join(lines) if a.full_failure else "\n>> ".join(lines[:3])))


if __name__ == "__main__":
    main()
