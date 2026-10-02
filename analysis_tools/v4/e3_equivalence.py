"""E3 equivalence (ADDENDUM_V4_E3_HUMANEVAL.md, C1): a candidate is equivalent to the developer fix when
(a) its javac AST fingerprint equals the fix's, or (b) its comment/whitespace-free token sequence equals the fix's up
to a one-to-one renaming of names that both methods declare as a parameter or local variable. Text only; reads no
execution outcome. Writes results/v4/humaneval/equivalence.jsonl."""
import base64
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/v4/humaneval"
JAVA = ROOT / "execution_tools/BatchMethodFingerprint.java"

TOKEN = re.compile(r"""
    (?P<ws>\s+) | (?P<lc>//[^\n]*) | (?P<bc>/\*.*?\*/) |
    (?P<str>"(?:\\.|[^"\\])*") | (?P<chr>'(?:\\.|[^'\\])*') |
    (?P<num>\.?[0-9][0-9A-Za-z_.]*) | (?P<id>[A-Za-z_$][A-Za-z0-9_$]*) |
    (?P<op>>>>=|<<=|>>=|>>>|\+\+|--|&&|\|\||==|!=|<=|>=|\+=|-=|\*=|/=|%=|&=|\|=|\^=|<<|>>|->|::|[{}()\[\];,.@=<>!~?:+\-*/&|^%])
""", re.S | re.X)
NOT_TYPE = {"return", "throw", "new", "case", "else", "assert", "instanceof", "do", "try", "finally", "break",
            "continue", "this", "super", "null", "true", "false", "package", "import", "goto", "yield"}
DECL_END = {"=", ";", ",", ")", ":"}
TYPE_TOKENS = {",", ".", "?", "[", "]", "<", ">", ">>", ">>>", "extends", "super", "&"}


def tokens(text):
    out, pos = [], 0
    while pos < len(text):
        m = TOKEN.match(text, pos)
        if not m:
            raise ValueError(f"untokenizable text at {pos}: {text[pos:pos + 20]!r}")
        pos = m.end()
        kind = m.lastgroup
        if kind not in ("ws", "lc", "bc"):
            out.append((kind, m.group()))
    return out


def closes_generic(toks, i):
    """toks[i] is '>' (or '>>'): true if it closes a generic type argument list that follows an identifier."""
    depth = 0
    for j in range(i, -1, -1):
        k, t = toks[j]
        if t in (">", ">>", ">>>"):
            depth += len(t)
        elif t == "<":
            depth -= 1
            if depth == 0:
                return j > 0 and toks[j - 1][0] == "id"
        elif not (k == "id" or t in TYPE_TOKENS):
            return False
    return False


def declared(toks):
    names = set()
    for i in range(1, len(toks) - 1):
        k, t = toks[i]
        if k != "id" or t in NOT_TYPE or toks[i + 1][1] not in DECL_END:
            continue
        pk, pt = toks[i - 1]
        if (pk == "id" and pt not in NOT_TYPE) or pt == "]" or (pt in (">", ">>", ">>>") and closes_generic(toks, i - 1)):
            names.add(t)
    return names


def alpha_equal(patch, fix):
    a, b = tokens(patch), tokens(fix)
    if len(a) != len(b):
        return False
    fwd, back = {}, {}
    for (ka, ta), (kb, tb) in zip(a, b):
        if ka != kb:
            return False
        if ka != "id":
            if ta != tb:
                return False
            continue
        if fwd.setdefault(ta, tb) != tb or back.setdefault(tb, ta) != ta:
            return False
    renamed = {(p, f) for p, f in fwd.items() if p != f}
    if not renamed:
        return True
    da, db = declared(a), declared(b)
    return all(p in da and f in db for p, f in renamed)


def tid(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def fingerprints(texts):
    req = OUT / "equivalence_parser_input.tsv"
    with req.open("w", encoding="utf-8", newline="\n") as f:
        for k, t in sorted(texts.items()):
            f.write(k + "\t" + base64.b64encode(t.encode()).decode() + "\n")
    with req.open(encoding="utf-8") as i:
        out = subprocess.run(["java", "-Xmx1g", str(JAVA)], stdin=i, capture_output=True, text=True, check=True).stdout
    fp = {}
    for line in out.splitlines():
        k, st, h = line.split("\t")
        fp[k] = h if st == "ok" else None
    if set(fp) != set(texts):
        raise ValueError("parser did not cover every method")
    return fp


def main():
    recs = [json.loads(l) for name in ("e3_targets.jsonl", "e3_tierB.jsonl") for l in open(OUT / name, encoding="utf-8") if l.strip()]
    fp = fingerprints({tid(t): t for r in recs for t in (r["patch"], r["human_fix"])})
    n_ast = n_alpha = n_eq = 0
    with open(OUT / "equivalence.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for r in recs:
            pa, fx = fp[tid(r["patch"])], fp[tid(r["human_fix"])]
            ast = pa is not None and pa == fx
            try:
                alpha = alpha_equal(r["patch"], r["human_fix"])
            except ValueError:
                alpha = False
            n_ast += ast; n_alpha += alpha; n_eq += ast or alpha
            f.write(json.dumps({"candidate_id": r["candidate_id"], "bug_id": r["bug_id"], "ast_equal": ast,
                                "alpha_equal": alpha, "equivalent": ast or alpha,
                                "patch_parsed": pa is not None, "fix_parsed": fx is not None}) + "\n")
    print(f"records {len(recs)}: AST-equal {n_ast}, alpha-equal {n_alpha}, equivalent {n_eq}")


if __name__ == "__main__":
    main()
