"""Freeze an outcome-blind, bug-matched execution sample without running patches."""

import argparse
from collections import Counter, defaultdict
from fractions import Fraction
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = "multibug-execution-v1"
EXCLUDED = {"Closure-78": "previously inspected and executed"}


def rows(path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            yield json.loads(line)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def priority(salt, key):
    return hashlib.sha256(f"{SEED}|{salt}|{key}".encode()).hexdigest()


def build_frame(decisions, evidence):
    counts = Counter(r["bug_id"] for r in decisions)
    frame, seen = [], set()
    for row in decisions:
        a, b = (row["policies"][n] for n in ("challenger_filtered", "native_filtered"))
        if set(a) != set(b):
            raise ValueError("Policy universes differ")
        for key in sorted(a):
            if key in seen:
                raise ValueError("Candidate appears in multiple contexts")
            seen.add(key)
            coefficient = Fraction(a[key]) - Fraction(b[key])
            if evidence[key]["label"] != "unknown" or not coefficient or row["bug_id"] in EXCLUDED:
                continue
            frame.append({"candidate_id": key, "context_id": row["context_id"],
                          "bug_id": row["bug_id"], "fold": row["fold"],
                          "coefficient": str(coefficient),
                          "influence": str(abs(coefficient) / counts[row["bug_id"]]),
                          "bug_context_count": counts[row["bug_id"]]})
    return sorted(frame, key=lambda r: (r["bug_id"], r["candidate_id"]))


def select(frame, limit=12):
    if limit < 1:
        raise ValueError("Positive bug cap required")
    groups = defaultdict(list)
    for row in frame:
        groups[row["bug_id"]].append(row)
    result = []
    for bug in sorted(groups, key=lambda b: (priority("bugs", b), b))[:limit]:
        pool = groups[bug]
        target = min(pool, key=lambda r: (-Fraction(r["influence"]), priority("target-tie", r["candidate_id"])))
        random = min(pool, key=lambda r: (priority("random-" + bug, r["candidate_id"]), r["candidate_id"]))
        result.append({"bug_id": bug, "eligible_candidates": len(pool),
                       "target": target, "random": random,
                       "overlap": target["candidate_id"] == random["candidate_id"]})
    return result


def write_json(path, obj):
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.relative_to((ROOT / "results").resolve())
    if out.exists():
        raise FileExistsError("Use a fresh output directory")
    contract = ROOT / "results/contract_step1"
    paths = {"decisions": ROOT / "results/noop_filter/v1/decisions.jsonl",
             "evidence": contract / "evaluation_evidence.jsonl",
             "views": contract / "decision_candidates.jsonl",
             "prior_packet": ROOT / "results/review_step3/_coordinator_only/selection_key.jsonl",
             "protocol": ROOT / "MULTIBUG_EXECUTION_PROTOCOL.md", "script": Path(__file__)}
    before = {str(p.relative_to(ROOT)): digest(p) for p in paths.values()}
    evidence = {r["candidate_id"]: r for r in rows(paths["evidence"])}
    decisions = list(rows(paths["decisions"]))
    frame = build_frame(decisions, evidence)
    sample = select(frame)
    wanted = {r[arm]["candidate_id"] for r in sample for arm in ("target", "random")}
    views = {r["candidate_id"]: r for r in rows(paths["views"]) if r["candidate_id"] in wanted}
    if set(views) != wanted:
        raise ValueError("Missing candidate source")
    prior = {r["candidate_id"]: r["case_id"] for r in rows(paths["prior_packet"])}
    out.mkdir(parents=True)
    with (out / "eligible_frame.jsonl").open("w", encoding="utf-8") as stream:
        for row in frame:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    write_json(out / "sample.json", sample)
    for key, view in sorted(views.items()):
        metadata = next(r for r in frame if r["candidate_id"] == key)
        if metadata["context_id"] != view["context_id"]:
            raise ValueError("Context mismatch")
        case = {**metadata, "prior_evidence": evidence[key],
                "previous_packet_case_id": prior.get(key),
                "arms": [arm for pair in sample for arm in ("target", "random") if pair[arm]["candidate_id"] == key],
                "anchor": view["anchor"], "patch": view["patch"], "sources": view["sources"],
                "execution_status": "not_started"}
        (out / "cases").mkdir(exist_ok=True)
        write_json(out / "cases" / f"{key}.json", case)
    summary = {"seed": SEED, "excluded_bugs": EXCLUDED,
               "eligible_candidates": len(frame), "eligible_bugs": len({r['bug_id'] for r in frame}),
               "eligible_projects": dict(Counter(r["bug_id"].rsplit("-", 1)[0] for r in frame)),
               "selected_bugs": len(sample), "unique_candidates": len(wanted),
               "overlapping_pairs": sum(r["overlap"] for r in sample),
               "singleton_pairs": sum(r["eligible_candidates"] == 1 for r in sample),
               "selected_projects": dict(Counter(r["bug_id"].rsplit("-", 1)[0] for r in sample)),
               "previous_packet_members": sum(k in prior for k in wanted),
               "execution_started": False}
    write_json(out / "summary.json", summary)
    report = ["# Frozen Multi-Bug Execution Sample", "", "No new patches executed; no labels changed.", "",
              "| Bug | Eligible patches | Same pick in both arms? |", "|---|---:|---|"]
    report.extend(f"| {r['bug_id']} | {r['eligible_candidates']} | {r['overlap']} |" for r in sample)
    report += ["", "The complete candidate choices, coefficients and source code are in sample.json and cases/.",
               "Selection is exploratory; see MULTIBUG_EXECUTION_PROTOCOL.md for costs, controls and limitations."]
    (out / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    if before != {str(p.relative_to(ROOT)): digest(p) for p in paths.values()}:
        raise RuntimeError("Input changed during sample preparation")
    write_json(out / "manifest.json", {"inputs": before, "outputs": {
        str(p.relative_to(out)): digest(p) for p in sorted(out.rglob("*")) if p.is_file()}})
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
