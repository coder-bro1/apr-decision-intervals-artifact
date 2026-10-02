"""Level-1 reproduction: verify the package, regenerate every table and figure of the paper from the stored results,
and check the principal numbers. Needs only Python 3.10+ (standard library); runs in about a minute.

    python reproduce.py

1. Every file listed in SHA256SUMS.json is checked.
2. manuscript/tools/make_v4_figures.py regenerates the paper's generated tables and figures into reproduced/;
   each is compared byte for byte with the version in paper/.
3. Each entry of claims.json is checked against the result file it names.
Exit status 0 means all checks passed.
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def check_sums():
    sums = json.loads((HERE / "SHA256SUMS.json").read_text(encoding="utf-8"))
    bad = [rel for rel, h in sums.items() if hashlib.sha256((HERE / rel).read_bytes()).hexdigest() != h]
    print(f"[1] checksums: {len(sums) - len(bad)}/{len(sums)} files match")
    return not bad


def regenerate():
    spec = importlib.util.spec_from_file_location("make_v4_figures", HERE / "manuscript/tools/make_v4_figures.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = HERE / "reproduced"
    mod.FIG, mod.TAB = out / "figures", out / "tables"
    mod.main()
    ok, total = True, 0
    for sub in ("tables", "figures"):
        for p in sorted((out / sub).glob("*.tex")):
            ref = HERE / "paper" / sub / p.name
            total += 1
            same = ref.exists() and ref.read_bytes() == p.read_bytes()
            ok &= same
            if not same:
                print(f"    differs: {sub}/{p.name}")
    print(f"[2] tables and figures regenerated: {total} files, {'all identical' if ok else 'differences above'}")
    return ok


def resolve(obj, path):
    for step in path:
        if isinstance(step, dict):
            obj = next(x for x in obj if all(x.get(k) == v for k, v in step.items()))
        else:
            obj = obj[step]
    return obj


def check_claims():
    claims = json.loads((HERE / "claims.json").read_text(encoding="utf-8"))
    ok = True
    for c in claims:
        val = resolve(json.loads((HERE / c["file"]).read_text(encoding="utf-8")), c["path"])
        if "len" in c:
            good = len(val) == c["len"]
        elif "expect_subset" in c:
            good = all(val.get(k) == v for k, v in c["expect_subset"].items())
        elif isinstance(c["expect"], list):
            good = all(abs(a - b) <= c.get("tol", 0) for a, b in zip(val, c["expect"]))
        else:
            good = val == c["expect"]
        ok &= good
        print(f"    {'ok ' if good else 'BAD'} {c['where']}: {c['claim']}")
    print(f"[3] claims: {'all hold' if ok else 'some do not hold'}")
    return ok


if __name__ == "__main__":
    results = [check_sums(), regenerate(), check_claims()]
    sys.exit(0 if all(results) else 1)
