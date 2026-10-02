"""Single-function audit: does each Defects4J pool bug's official source patch change only the method that the
RepairLLaMA context gives (buggy anchor -> human_fix)? Triggered by the C1 fix re-run, where JxPath-14 copies of the
method-level developer fix failed the trigger test (the official patch also changes functionCeiling/functionRound).

Rule: compare the multiset of changed lines (whitespace removed; comment-only and empty lines ignored; a line both
removed and added cancels) in the official patch with the same multiset for anchor -> human_fix over the bug's
contexts. A bug is flagged if the official patch changes lines the method-level fix does not account for, or touches
more than one file. Patches: results/v4/single_function_audit/d4j_src_patches.tar (exported from the v3 image).
Writes results/v4/single_function_audit/single_function_audit.json."""
import difflib
import json
import re
import sys
import tarfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import v4core as V  # noqa: E402
from validation_policy_contract import context_id  # noqa: E402

OUT = ROOT / "results/v4/single_function_audit"
LEGACY = [ROOT / f"llm_apr_dataset/llm_apr_defects4j_candidates_v2_candidates_{k}.jsonl" for k in ("all", "excluded")]
COMMENT = re.compile(r"^(//|/\*|\*|\*/)")


def norm(line):
    s = "".join(line.split())
    return None if not s or COMMENT.match(s) else s


def changed(minus, plus):
    m, p = Counter(x for x in map(norm, minus) if x), Counter(x for x in map(norm, plus) if x)
    common = m & p
    return (m - common) + (p - common)


def patch_changes(text):
    minus, plus, files = [], [], 0
    for line in text.splitlines():
        if line.startswith("diff --git"):
            files += 1
        elif line.startswith("---") or line.startswith("+++"):
            continue
        elif line.startswith("-"):
            minus.append(line[1:])
        elif line.startswith("+"):
            plus.append(line[1:])
    return changed(minus, plus), files


def method_changes(anchor, fix):
    minus, plus = [], []
    for d in difflib.ndiff(anchor.splitlines(), fix.splitlines()):
        if d.startswith("- "):
            minus.append(d[2:])
        elif d.startswith("+ "):
            plus.append(d[2:])
    return changed(minus, plus)


def main():
    data = V.load()
    patches = {}
    with tarfile.open(OUT / "d4j_src_patches.tar") as tf:
        for m in tf.getmembers():
            p = Path(m.name)
            if m.isfile() and p.parent.name == "patches":
                patches[f"{p.parts[0]}-{p.name.split('.')[0]}"] = tf.extractfile(m).read().decode("utf-8", "replace")
    ctx = defaultdict(set)
    for path in LEGACY:
        for line in open(path, encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                ctx[r["bug_id"]].add((r["anchor"], r["human_fix"]))
    e0 = data.evidence("E0")
    correct_by_bug = Counter(o.bug for k, o in data.occ.items() if e0[k] == 1)
    rows, flagged = [], []
    for bug in sorted(data.bugs):
        if bug not in patches:
            rows.append({"bug": bug, "status": "no_official_patch_found"})
            continue
        pc, files = patch_changes(patches[bug])
        mc = Counter()
        for anchor, fix in ctx.get(bug, ()):
            mc |= method_changes(anchor, fix)
        extra = pc - mc
        status = ("no_context" if not ctx.get(bug) else
                  "multi_file" if files > 1 else
                  "changes_outside_method" if sum(extra.values()) else "single_method_consistent")
        row = {"bug": bug, "status": status, "files": files, "patch_changed_lines": sum(pc.values()),
               "method_changed_lines": sum(mc.values()), "unexplained_lines": sum(extra.values()),
               "archived_correct_candidates": correct_by_bug.get(bug, 0),
               "unexplained_examples": [k for k, _ in extra.most_common(3)]}
        rows.append(row)
        if status in ("multi_file", "changes_outside_method"):
            flagged.append(row)
    res = {"bugs": len(rows), "status_counts": dict(Counter(r["status"] for r in rows)),
           "flagged": flagged, "rows": rows}
    (OUT / "single_function_audit.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res["status_counts"], indent=1))
    for r in flagged:
        print(f"{r['bug']:22s} {r['status']:24s} files {r['files']} patch {r['patch_changed_lines']} method {r['method_changed_lines']} "
              f"unexplained {r['unexplained_lines']} archived-correct {r['archived_correct_candidates']} e.g. {r['unexplained_examples'][:2]}")


if __name__ == "__main__":
    main()
