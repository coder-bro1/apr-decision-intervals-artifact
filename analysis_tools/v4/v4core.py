"""Protocol v4 core: bug-level pools, identity classes, policies, exact shared-label bounds.

All arithmetic uses fractions.Fraction. Nothing here writes into frozen artifacts.
Definitions follow PROTOCOL_V4_BUG_LEVEL.md (sections 2-5).
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "results"
PROTOCOL = ROOT / "PROTOCOL_V4_BUG_LEVEL.md"
LABEL = {"correct": 1, "incorrect": 0, "unknown": None}
NOOP_STRUCTURES = {"normalized_noop", "exact_noop"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def jsonl(path: Path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


INPUTS = {
    "contexts": RES / "contract_step1" / "contexts.jsonl",
    "decision_candidates": RES / "contract_step1" / "decision_candidates.jsonl",
    "evaluation_evidence": RES / "contract_step1" / "evaluation_evidence.jsonl",
    "predictions": RES / "pilot_step2" / "predictions.jsonl",
    "noop_structure": RES / "noop_filter" / "v1" / "candidate_structure.jsonl",
    "parser_output": RES / "noop_filter" / "v1" / "parser_output.tsv",
    "census": RES / "conflict_census" / "summary_v1" / "candidate_evidence.json",
}


@dataclass
class Occ:
    cid: str
    ctx: str
    bug: str
    patch: str
    sources: list  # list of (config, index)
    ctx_order: int
    pos_in_ctx: int
    score: float = 0.0
    compile_p: float = 0.0
    test_p: float = 0.0
    correct_p: float = 0.0
    rotation: int | None = None
    structure: str = ""
    ast: str | None = None

    @property
    def min_index(self) -> int:
        return min(i for _, i in self.sources)

    @property
    def noop(self) -> bool:
        return self.structure in NOOP_STRUCTURES


@dataclass
class Data:
    occ: dict
    contexts: list
    bugs: list
    ctx_bug: dict
    ctx_fold: dict
    e0: dict
    witnesses: set
    census: dict
    input_hashes: dict = field(default_factory=dict)

    def evidence(self, name: str) -> dict:
        if name == "E0":
            return self.e0
        if name == "E1":
            ev = dict(self.e0)
            for k in self.witnesses:
                assert ev[k] is None, k
                ev[k] = 0
            return ev
        raise KeyError(name)


def load(hash_inputs: bool = True) -> Data:
    contexts = list(jsonl(INPUTS["contexts"]))
    ctx_bug = {c["context_id"]: c["bug_id"] for c in contexts}
    ctx_fold = {c["context_id"]: c.get("fold") for c in contexts}
    order = {}
    for ci, c in enumerate(contexts):
        for pi, k in enumerate(c["candidate_ids"]):
            order[k] = (ci, pi)
    occ = {}
    for r in jsonl(INPUTS["decision_candidates"]):
        ci, pi = order[r["candidate_id"]]
        occ[r["candidate_id"]] = Occ(
            cid=r["candidate_id"], ctx=r["context_id"], bug=ctx_bug[r["context_id"]], patch=r["patch"],
            sources=[(s["source_config"], s["candidate_index"]) for s in r["sources"]],
            ctx_order=ci, pos_in_ctx=pi)
    n_scored = 0
    for p in jsonl(INPUTS["predictions"]):
        if p["role"] != "test":
            continue
        o = occ[p["candidate_id"]]
        o.score, o.compile_p, o.test_p, o.correct_p = p["score"], p["compile"], p["test_given_compile"], p["correct_given_test"]
        o.rotation = p["rotation"]
        n_scored += 1
    assert n_scored == len(occ), (n_scored, len(occ))
    for r in jsonl(INPUTS["noop_structure"]):
        occ[r["candidate_id"]].structure = r["structure"]
    fp = {}
    with open(INPUTS["parser_output"], encoding="utf-8") as f:
        for line in f:
            k, st, h = line.rstrip("\n").split("\t")
            fp[k] = h if st == "ok" else None
    missing = 0
    for o in occ.values():
        key = sha256_text(o.patch)
        if key not in fp:
            missing += 1
        o.ast = fp.get(key)
    assert missing == 0, f"{missing} patches missing from parser output"
    e0 = {r["candidate_id"]: LABEL[r["label"]] for r in jsonl(INPUTS["evaluation_evidence"])}
    assert set(e0) == set(occ)
    census_rows = json.loads(INPUTS["census"].read_text(encoding="utf-8"))
    census = {c["candidate_id"]: c for c in census_rows}
    witnesses = {k for k, c in census.items() if c["evidence_status"] == "controlled_trigger_failure"}
    assert len(witnesses) == 185
    bugs = sorted({c["bug_id"] for c in contexts})
    hashes = {name: sha256_file(p) for name, p in INPUTS.items()} if hash_inputs else {}
    hashes["protocol"] = sha256_file(PROTOCOL)
    data = Data(occ=occ, contexts=contexts, bugs=bugs, ctx_bug=ctx_bug, ctx_fold=ctx_fold, e0=e0,
                witnesses=witnesses, census=census, input_hashes=hashes)
    data.ctx_anchor = {c["context_id"]: c.get("anchor") for c in contexts}
    norm_path = RES / "v4" / "normalize" / "normalized.tsv"
    data.norm = {}
    if norm_path.exists():
        with open(norm_path, encoding="utf-8") as f:
            for line in f:
                p = line.rstrip("\n").split("\t")
                data.norm[p[0]] = None if p[1] != "ok" else {"noann": p[2], "nothrows": p[3], "alpha": p[4]}
        if hash_inputs:
            hashes["normalized"] = sha256_file(norm_path)
    return data


# ---------------------------------------------------------------- text normalisation (fallback for unparsed code)

def strip_comments(s: str) -> str:
    out, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c in "\"'":
            j = i + 1
            while j < n:
                if s[j] == "\\":
                    j += 2
                    continue
                if s[j] == c:
                    j += 1
                    break
                if s[j] == "\n":
                    break
                j += 1
            out.append(s[i:j])
            i = j
            continue
        if s.startswith("//", i):
            j = s.find("\n", i)
            i = n if j < 0 else j
            continue
        if s.startswith("/*", i):
            j = s.find("*/", i + 2)
            i = n if j < 0 else j + 2
            out.append(" ")
            continue
        out.append(c)
        i += 1
    return "".join(out)


def text_norm(s: str) -> str:
    return "".join(strip_comments(s).split())


def norm_of(data, text: str):
    return data.norm.get(sha256_text(text)) if getattr(data, "norm", None) else None


# ---------------------------------------------------------------- identity and pools

def identity_key(o: Occ, mode: str, data=None) -> str:
    if mode == "occ":  # context-level exact identity of the reviewed draft
        return o.cid
    if mode == "exact":
        return "txt:" + o.patch.strip()
    if mode == "ast":
        return ("ast:" + o.ast) if o.ast else ("txt:" + o.patch.strip())
    if mode in ("ast_noann", "alpha"):
        n = norm_of(data, o.patch)
        if n:
            return ("noann:" + n["noann"]) if mode == "ast_noann" else ("alpha:" + n["alpha"])
        return "txt:" + o.patch.strip()
    raise KeyError(mode)


def noop_variant(data, variant: str = "base"):
    """Class-level no-op predicate. base: the frozen AST structure flags. strong: base, or equal to the buggy
    method after removing annotations and throws clauses, or (if either side is unparsed) equal after removing
    comments and whitespace (covers the parse-unresolved fragments, R1 E1)."""
    if variant == "base":
        return lambda kl: any(data.occ[m].noop for m in kl.members)
    cache = {}

    def occ_is_noop(m):
        if m in cache:
            return cache[m]
        o = data.occ[m]
        anchor = data.ctx_anchor.get(o.ctx)
        res = o.noop
        if not res and anchor:
            nc, na = norm_of(data, o.patch), norm_of(data, anchor)
            if nc and na:
                res = nc["nothrows"] == na["nothrows"]
            else:
                res = text_norm(o.patch) == text_norm(anchor)
        cache[m] = res
        return res

    if variant == "strong":
        return lambda kl: any(occ_is_noop(m) for m in kl.members)
    raise KeyError(variant)


@dataclass
class Klass:
    key: str
    members: list  # occurrence ids

    def hash_key(self) -> str:
        return sha256_text(self.key)


def build_pools(data: Data, unit: str, identity: str, key_fn=None) -> dict:
    """unit in {'context','bug'} -> {unit_id: (bug_id, [Klass,...])} (every context/bug kept, even empty)."""
    key_fn = key_fn or (lambda o: identity_key(o, identity, data))
    pools = {}
    if unit == "context":
        for c in data.contexts:
            groups = {}
            for k in c["candidate_ids"]:
                groups.setdefault(key_fn(data.occ[k]), []).append(k)
            pools[c["context_id"]] = (c["bug_id"], [Klass(g, m) for g, m in groups.items()])
    elif unit == "bug":
        by_bug = defaultdict(list)
        for c in data.contexts:
            by_bug[c["bug_id"]].extend(c["candidate_ids"])
        for b in data.bugs:
            groups = {}
            for k in by_bug.get(b, []):
                groups.setdefault(key_fn(data.occ[k]), []).append(k)
            pools[b] = (b, [Klass(g, m) for g, m in groups.items()])
    else:
        raise KeyError(unit)
    return pools


def class_label(members, ev: dict, rule: str):
    """Returns (label, conflict_flag). rule: 'known_wins' | 'strict'."""
    vals = [ev[m] for m in members]
    known = {v for v in vals if v is not None}
    if len(known) > 1:
        return None, True
    if not known:
        return None, False
    if rule == "strict" and any(v is None for v in vals):
        return None, False
    return next(iter(known)), False


# ---------------------------------------------------------------- policies

def pol_challenger(data, kl):
    return max(data.occ[m].score for m in kl.members)


def pol_mra(data, kl):
    return -min(data.occ[m].min_index for m in kl.members)


def pol_testability(data, kl):
    return max(data.occ[m].compile_p * data.occ[m].test_p for m in kl.members)


def pol_occurrence(data, kl):
    return sum(len(data.occ[m].sources) for m in kl.members)


def pol_mra_then_occ(data, kl):
    """The draft's 'native then occurrence': minimum rank first, occurrence count as lexicographic tie-breaker."""
    return (pol_mra(data, kl), pol_occurrence(data, kl))


def pol_uniform(data, kl):
    return 0


POLICIES = {
    "challenger": pol_challenger,
    "mra": pol_mra,
    "testability": pol_testability,
    "occurrence": pol_occurrence,
    "mra_then_occurrence": pol_mra_then_occ,
    "uniform": pol_uniform,
}
# Optional per-policy eligibility predicates: (data, klass) -> bool. A policy abstains when nothing is eligible.
POLICY_ELIG = {}


def file_order_key(data, kl):
    return min((data.occ[m].ctx_order, data.occ[m].pos_in_ctx) for m in kl.members)


def select(data, classes, score_fn, eligible, ties="uniform"):
    """Return {class_index: Fraction probability} over eligible classes (empty -> abstain)."""
    elig = [i for i in range(len(classes)) if i in eligible]
    if not elig:
        return {}
    vals = {i: score_fn(data, classes[i]) for i in elig}
    best = max(vals.values())
    top = [i for i in elig if vals[i] == best]
    if ties == "uniform" or len(top) == 1:
        return {i: Fraction(1, len(top)) for i in top}
    if ties == "file_order":
        return {min(top, key=lambda i: file_order_key(data, classes[i])): Fraction(1)}
    if ties == "hash":
        return {min(top, key=lambda i: classes[i].hash_key()): Fraction(1)}
    raise KeyError(ties)


# ---------------------------------------------------------------- evaluation

@dataclass
class UnitResult:
    bug: str
    lo: Fraction
    hi: Fraction
    all0: Fraction
    all1: Fraction
    coeffs: list  # list of (d, label, class_index)


def evaluate_pair(data, pools, ev, pol_a, pol_b, rule="known_wins", noop="N-a", ties="uniform",
                  noop_fn=None):
    """Paired shared-label bounds of success(A) - success(B) per unit.

    noop: 'N-a' (no-op classes labelled incorrect unless known correct), 'N-b' (filtered), 'N-c' (neither).
    Returns (list[UnitResult], stats dict).
    """
    fa, fb = POLICIES[pol_a] if isinstance(pol_a, str) else pol_a, POLICIES[pol_b] if isinstance(pol_b, str) else pol_b
    ea = POLICY_ELIG.get(pol_a) if isinstance(pol_a, str) else None
    eb = POLICY_ELIG.get(pol_b) if isinstance(pol_b, str) else None
    noop_fn = noop_fn or (lambda kl: any(data.occ[m].noop for m in kl.members))
    out, conflicts, contradictions = [], 0, 0
    for unit_id, (bug, classes) in pools.items():
        labels, is_noop = [], []
        for kl in classes:
            y, conflict = class_label(kl.members, ev, rule)
            conflicts += conflict
            nf = noop_fn(kl)
            if noop == "N-a" and nf:
                if y == 1:
                    contradictions += 1
                elif y is None:
                    y = 0
            labels.append(y)
            is_noop.append(nf)
        eligible = {i for i in range(len(classes)) if not (noop == "N-b" and is_noop[i])}
        el_a = {i for i in eligible if ea is None or ea(data, classes[i])}
        el_b = {i for i in eligible if eb is None or eb(data, classes[i])}
        pa = select(data, classes, fa, el_a, ties)
        pb = select(data, classes, fb, el_b, ties)
        lo = hi = a0 = a1 = Fraction(0)
        coeffs = []
        for i in set(pa) | set(pb):
            d = pa.get(i, Fraction(0)) - pb.get(i, Fraction(0))
            if d == 0:
                continue
            y = labels[i]
            coeffs.append((d, y, i))
            if y is None:
                lo += min(Fraction(0), d)
                hi += max(Fraction(0), d)
                a1 += d
            else:
                lo += d * y
                hi += d * y
                a0 += d * y
                a1 += d * y
        out.append(UnitResult(bug, lo, hi, a0, a1, coeffs))
    return out, {"class_label_conflicts": conflicts, "noop_correct_contradictions": contradictions}


def aggregate(units, weighting="bug", n_bugs=None):
    """Equal-bug mean (units averaged within bug first) or equal-unit mean. Returns dict of Fractions."""
    if weighting == "unit":
        n = len(units)
        return {k: sum(getattr(u, k) for u in units) / n for k in ("lo", "hi", "all0", "all1")}
    per_bug = defaultdict(list)
    for u in units:
        per_bug[u.bug].append(u)
    n = n_bugs or len(per_bug)
    res = {}
    for k in ("lo", "hi", "all0", "all1"):
        res[k] = sum(sum(getattr(u, k) for u in us) / len(us) for us in per_bug.values()) / n
    return res


def relevant_unknowns(units):
    return sum(1 for u in units for d, y, _ in u.coeffs if y is None)


def pp(x: Fraction) -> float:
    return round(float(100 * x), 6)
