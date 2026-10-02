"""Read-only V8 control audit. No Java, Docker, training, or evidence updates."""
import collections
import json
import pickle
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import v4core as V

TOK = re.compile(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|\w+|[^\s\w]')
OPERATORS = re.compile(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|\w+|>>>=|>>>|>>=|<<=|>>|<<|\+\+|--|&&|\|\||==|!=|<=|>=|\+=|-=|\*=|/=|%=|&=|\|=|\^=|->|::|\.\.\.|[^\s\w]')


def main():
    with (ROOT / "results/v4/positive_controls/cache/raw.pkl").open("rb") as f:
        raw = pickle.load(f)
    audit = json.loads((ROOT / "results/v4/single_function_audit/single_function_audit.json").read_text())
    rows = audit["rows"]
    if isinstance(rows, dict):
        allowed = {k for k, r in rows.items() if r["status"] == "single_method_consistent"}
    else:
        allowed = {r["bug"] for r in rows if r["status"] == "single_method_consistent"}
    fingerprint = {}
    for line in (ROOT / "results/v4/positive_controls/cache/fingerprint_output.tsv").read_text().splitlines():
        key, *value = line.split("\t")
        fingerprint[key] = value
    tokens = {}
    lexical = {}
    copies = []
    mismatches = []
    operator_mismatches = []
    for row in raw["occ"]:
        if row["bench"] == "defects4j" and row["bug"] not in allowed:
            continue
        for key in (row["t"], row["ft"]):
            if key not in tokens:
                text = V.strip_comments(raw["texts"][key])
                tokens[key] = tuple(TOK.findall(text))
                lexical[key] = tuple(OPERATORS.findall(text))
        if tokens[row["t"]] != tokens[row["ft"]]:
            continue
        copies.append(row)
        a, b = fingerprint.get(row["t"]), fingerprint.get(row["ft"])
        if a != b:
            mismatches.append({k: row[k] for k in ("bench", "bug", "cfg", "idx", "t", "ft")})
        if lexical[row["t"]] != lexical[row["ft"]]:
            operator_mismatches.append({k: row[k] for k in ("bench", "bug", "cfg", "idx", "t", "ft")})
    print("Copies by benchmark:", dict(collections.Counter(r["bench"] for r in copies)))
    print("L1 copy pairs with different cached AST results:", len(mismatches))
    print("L1 copy pairs with different maximal-munch operator tokens:", len(operator_mismatches))
    print("Operator mismatch examples:", json.dumps(operator_mismatches[:10]))
    print("AST mismatch examples:", json.dumps(mismatches[:10]))
    configs = ("gpt4_gpt-zero-shot", "repairllama_ir4_or2")
    per_bug = {cfg: collections.defaultdict(lambda: [0, 0]) for cfg in configs}
    for row in copies:
        if row["bench"] != "defects4j" or row["cfg"] not in configs:
            continue
        y = 0 if row["test"] is True else (1 if row["compile"] is False or row["test"] is False else None)
        if y is None:
            continue
        pair = per_bug[row["cfg"]][row["bug"]]
        pair[0] += y
        pair[1] += 1
    common = sorted(set(per_bug[configs[0]]) & set(per_bug[configs[1]]))
    values = np.array([[*per_bug[configs[0]][bug], *per_bug[configs[1]][bug]] for bug in common], dtype=float)
    rates = values[:, 0] / values[:, 1] - values[:, 2] / values[:, 3]
    rng = np.random.default_rng(20261001)
    sample = rng.integers(0, len(common), (20000, len(common)))
    pooled = values[sample].sum(axis=1)
    pooled_delta = pooled[:, 0] / pooled[:, 1] - pooled[:, 2] / pooled[:, 3]
    print("Shared bugs:", len(common), "[GPT4 fail,total; RepairLLaMA fail,total]:", values.sum(axis=0).tolist())
    print("Equal-bug failure-rate gap pp:", rates.mean() * 100)
    print("Paired bug bootstrap equal-bug 95% percentile CI pp:", (100 * np.quantile(rates[sample].mean(axis=1), [0.025, 0.975])).tolist())
    print("Paired bug bootstrap occurrence-weighted gap 95% percentile CI pp:", (100 * np.quantile(pooled_delta, [0.025, 0.975])).tolist())
    print("Bug-rate differences positive/zero/negative:", int((rates > 0).sum()), int((rates == 0).sum()), int((rates < 0).sum()))


if __name__ == "__main__":
    main()
