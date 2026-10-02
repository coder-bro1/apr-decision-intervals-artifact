"""F4 + F5 scoring: read the two returned answer files, report agreement, list disagreements for adjudication,
estimate the accepted-label error rate from the F5 audit, and write the resolved F4 labels.

Usage: score_annotations.py answers_annotator_1.json answers_annotator_2.json [adjudication.json]
- Agreement: raw agreement and Cohen's kappa over the three verdicts, and over items both marked non-unsure.
- F4 resolution rule (frozen here, before any answers exist): an F4 class becomes known only if both annotators give
  the same non-unsure verdict, or the adjudication file (a joint discussion after both exports) gives one;
  anything else stays unknown.
- F5: disagreement with the accepted label per direction (accepted-correct judged incorrect, and the reverse), with
  exact Clopper-Pearson 95% intervals; the upper limits feed the label-error frontier (C1).
"""
import json
import sys
from collections import Counter
from pathlib import Path

from scipy.stats import beta

ROOT = Path(__file__).resolve().parents[2]
KEY = ROOT / "results/v4/annotation_key/KEY_private.json"
OUT = ROOT / "results/v4/annotation_results"
V3 = ("correct", "incorrect", "unsure")


def kappa(a, b, cats):
    n = len(a)
    if not n:
        return None
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[c] * cb[c] for c in cats) / n / n
    return (po - pe) / (1 - pe) if pe < 1 else None


def cp(k, n):
    if not n:
        return [None, None]
    lo = 0.0 if k == 0 else beta.ppf(0.025, k, n - k + 1)
    hi = 1.0 if k == n else beta.ppf(0.975, k + 1, n - k)
    return [float(lo), float(hi)]


def main():
    key = {r["id"]: r for r in json.loads(KEY.read_text())["items"]}
    def read(p):
        p = Path(p)
        if p.suffix.lower() == ".csv":  # simple packet (results/v4/annotation_simple): id, bug, verdict, confidence, reason
            import csv
            out = {}
            with open(p, encoding="utf-8-sig", newline="") as f:
                for r in csv.DictReader(f):
                    v = (r.get("verdict") or "").strip().lower()
                    if v:
                        out[r["id"].strip()] = {"verdict": v, "confidence": (r.get("confidence") or "").strip().lower(),
                                                "notes": r.get("reason", "")}
            bad = {k: v["verdict"] for k, v in out.items() if v["verdict"] not in V3}
            if bad:
                raise SystemExit(f"{p.name}: unrecognised verdicts {bad}")
            return out
        return json.loads(p.read_text())["answers"]

    a1, a2 = read(sys.argv[1]), read(sys.argv[2])
    adj = json.loads(Path(sys.argv[3]).read_text()) if len(sys.argv) > 3 else {}
    both = [i for i in key if a1.get(i, {}).get("verdict") and a2.get(i, {}).get("verdict")]
    v1 = [a1[i]["verdict"] for i in both]
    v2 = [a2[i]["verdict"] for i in both]
    firm = [k for k, i in enumerate(both) if v1[k] != "unsure" and v2[k] != "unsure"]
    res = {"items": len(key), "answered_by_both": len(both),
           "raw_agreement": sum(x == y for x, y in zip(v1, v2)) / len(both) if both else None,
           "kappa_3way": kappa(v1, v2, V3),
           "kappa_firm_only": kappa([v1[k] for k in firm], [v2[k] for k in firm], V3[:2]),
           "ai_use_share": {"annotator_1": sum(bool(a1.get(i, {}).get("used_ai")) for i in key) / len(key),
                            "annotator_2": sum(bool(a2.get(i, {}).get("used_ai")) for i in key) / len(key)},
           "disagreements": [i for i, x, y in zip(both, v1, v2) if x != y]}
    resolved = {}
    for i, r in key.items():
        x, y = a1.get(i, {}).get("verdict"), a2.get(i, {}).get("verdict")
        final = x if x == y and x in ("correct", "incorrect") else adj.get(i)
        if final not in ("correct", "incorrect"):
            final = None
        resolved[i] = final
    f4 = [r for r in key.values() if r["set"] == "F4"]
    res["F4"] = {"items": len(f4), "resolved": Counter(resolved[r["id"]] or "unknown" for r in f4)}
    f5 = [r for r in key.values() if r["set"] == "F5"]
    out5 = {}
    for y, name in ((1, "accepted_correct"), (0, "accepted_incorrect")):
        rows = [r for r in f5 if r["existing_label"] == y and resolved[r["id"]] is not None]
        flips = sum((resolved[r["id"]] == "correct") != bool(y) for r in rows)
        out5[name] = {"sampled": sum(r["existing_label"] == y for r in f5), "resolved": len(rows),
                      "disagree_with_accepted": flips, "rate_ci95": cp(flips, len(rows))}
    res["F5"] = out5
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "agreement_and_audit.json").write_text(json.dumps(res, indent=1, default=dict))
    labels = {key[i]["candidate_id"]: {"label": v, "class_members": key[i]["class_members"]}
              for i, v in resolved.items() if key[i]["set"] == "F4" and v}
    (OUT / "f4_resolved_labels.json").write_text(json.dumps(labels, indent=1))
    print(json.dumps(res, indent=1, default=dict))


if __name__ == "__main__":
    main()
