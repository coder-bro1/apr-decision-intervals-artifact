"""F4 + F5: build blinded annotation packets (one self-contained HTML page per annotator) and a private key.

F4 items: identity classes (bug unit, AST identity, E1, known-wins, N-a) that are unknown, decision-relevant
(non-zero coefficient) in a pre-registered comparison whose E1 interval is still open or whose break-down depends
on them, and whose every member passed the archived tests unanimously. Comparisons: challenger vs MRA (primary),
best_config_top1, testability, one_stage, occurrence, source_agnostic.
F5 items: 60 accepted human-judged labels on test-passing occurrences (so the packet instruction "the candidate
passes the tests" holds for every item and cannot reveal the set) (30 accepted-correct, 30 accepted-incorrect; one occurrence per identity
class; seed 20260929), excluding classes already in F4.
Both sets are merged and shuffled (seed 20260929) so annotators cannot tell which items already carry a label.
The key file (results/v4/annotation_key/KEY_private.json) must NOT be given to annotators; it is kept outside
the folder that is shared.
"""
import difflib
import html
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_evidence_pilot_step2 as S  # noqa: E402
import v4core as V  # noqa: E402
import baselines as B  # noqa: E402
import provenance as P  # noqa: E402

OUT = ROOT / "results/v4/annotation"
REF = ROOT / "llm_apr_dataset/llm_apr_defects4j_candidates_v2_reference_fixes.jsonl"
COMPARISONS = ("mra", "best_config_top1", "testability", "one_stage", "occurrence", "source_agnostic")
SEED = 20260929


def udiff(a, b, la, lb):
    return "\n".join(difflib.unified_diff(a.splitlines(), b.splitlines(), la, lb, lineterm="", n=3))


def main():
    data = V.load()
    B.register(data)
    basis, _ = P.basis_map(data)
    _, _, _, training, _ = S.load_inputs()
    tpass = {r["candidate_id"]: (r["compile"] == 1 and r["test_given_compile"] == 1) for r in training}
    pools = V.build_pools(data, "bug", "ast")
    ev = data.evidence("E1")
    f4 = {}  # (bug, class_key) -> {"members":..., "comparisons": set()}
    counts = {}
    for other in COMPARISONS:
        units, _ = V.evaluate_pair(data, pools, ev, "challenger", other)
        n_rel = n_tp = 0
        for u, (bug, classes) in zip(units, pools.values()):
            for d, y, i in u.coeffs:
                if y is not None:
                    continue
                n_rel += 1
                kl = classes[i]
                if not all(tpass[m] for m in kl.members):
                    continue
                n_tp += 1
                item = f4.setdefault((bug, kl.key), {"bug": bug, "members": kl.members, "comparisons": set()})
                item["comparisons"].add(other)
        counts[other] = {"decision_relevant_unknown_classes": n_rel, "of_which_all_members_test_pass": n_tp}
    f4_keys = set(f4)
    # F5: accepted human-judged labels, one occurrence per class
    klass_of = {}
    for bug, classes in pools.values():
        for kl in classes:
            for m in kl.members:
                klass_of[m] = (bug, kl.key)
    by_label = {0: {}, 1: {}}
    for m, b in sorted(basis.items()):
        if b != "human" or ev[m] is None or not tpass[m]:
            continue
        k = klass_of[m]
        if k in f4_keys:
            continue
        by_label[ev[m]].setdefault(k, m)
    rng = random.Random(SEED)
    f5 = []
    for y in (1, 0):
        keys = sorted(by_label[y])
        for k in rng.sample(keys, 30):
            f5.append({"bug": k[0], "members": [by_label[y][k]], "existing_label": y, "class_key": k[1]})
    # reference fixes by (bug, anchor)
    ref = {}
    for r in V.jsonl(REF):
        ref[(r["bug_id"], r["anchor"].strip())] = r["human_fix"]
    items = []
    for (bug, key), it in sorted(f4.items()):
        items.append({"set": "F4", "bug": bug, "class_key": key, "members": it["members"],
                      "comparisons": sorted(it["comparisons"]), "existing_label": None})
    for it in f5:
        items.append({"set": "F5", "bug": it["bug"], "class_key": it["class_key"], "members": it["members"],
                      "comparisons": [], "existing_label": it["existing_label"]})
    rng.shuffle(items)
    packet, key_rows, missing_ref = [], [], 0
    for n, it in enumerate(items, 1):
        occ = data.occ[it["members"][0]]
        anchor = data.ctx_anchor[occ.ctx]
        fix = ref.get((it["bug"], anchor.strip()))
        if fix is None:
            missing_ref += 1
        iid = f"A{n:03d}"
        packet.append({"id": iid, "bug": it["bug"], "buggy": anchor, "fix": fix or "(developer fix not available)",
                       "candidate": occ.patch,
                       "fix_diff": udiff(anchor, fix, "buggy", "developer_fix") if fix else "",
                       "cand_diff": udiff(anchor, occ.patch, "buggy", "candidate"),
                       "cand_vs_fix": udiff(fix, occ.patch, "developer_fix", "candidate") if fix else ""})
        key_rows.append({"id": iid, "set": it["set"], "bug": it["bug"], "candidate_id": it["members"][0],
                         "class_members": it["members"], "comparisons": it["comparisons"],
                         "existing_label": it["existing_label"]})
    OUT.mkdir(parents=True, exist_ok=True)
    summary = {"f4_counts_by_comparison": counts, "f4_items": len(f4), "f5_items": len(f5), "total": len(items),
               "missing_reference_fix": missing_ref, "seed": SEED}
    KEYDIR = OUT.parent / "annotation_key"
    KEYDIR.mkdir(parents=True, exist_ok=True)
    (OUT / "KEY_private.json").unlink(missing_ok=True)  # never leave a key in the shared folder
    (KEYDIR / "KEY_private.json").write_text(json.dumps({"summary": summary, "items": key_rows}, indent=1))
    template = (Path(__file__).parent / "annotation_template.html").read_text(encoding="utf-8")
    for who in ("annotator_1", "annotator_2"):
        page = template.replace("__ITEMS_JSON__", json.dumps(packet).replace("</", "<\\/")).replace("__ANNOTATOR__", who)
        (OUT / f"packet_{who}.html").write_text(page, encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
