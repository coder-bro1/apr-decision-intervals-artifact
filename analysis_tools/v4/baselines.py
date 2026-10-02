"""D1: matched baselines under the v4 contract (PROTOCOL_V4 section 4).

Gate A2: at the draft's cell (context unit, per-context identity, filter N-b, evidence E1, equal-bug weighting) the
challenger-minus-baseline bounds must reproduce results/matched_baselines/v1 exactly for all seven draft rows.
Then: every baseline at the primary bug-level specification (E0 and E1), absolute success bounds, pairwise matrix.
"""
import json
import re
import sys
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v4core as V  # noqa: E402

TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z_0-9]*|\d+|[^\sA-Za-z_0-9]")


def jaccard(a, b):
    left, right = set(TOKEN_RE.findall(a or "")), set(TOKEN_RE.findall(b or ""))
    u = left | right
    return Fraction(len(left & right), len(u)) if u else Fraction(1)


def register(data):
    """Register data-dependent policies into V.POLICIES / V.POLICY_ELIG."""
    configs = sorted({s for o in data.occ.values() for s, _ in o.sources})
    cfg_rank = {c: i for i, c in enumerate(configs)}
    # per bug, per config: number of source entries (for Borda / normalised position)
    n_bc = defaultdict(Counter)
    for o in data.occ.values():
        for s, _ in o.sources:
            n_bc[o.bug][s] += 1

    def sources(kl):
        return [(data.occ[m].bug, s, i) for m in kl.members for s, i in data.occ[m].sources]

    V.POLICIES["token_similarity"] = lambda d, kl: max(jaccard(d.ctx_anchor[d.occ[m].ctx], d.occ[m].patch) for m in kl.members)
    V.POLICIES["first_global"] = lambda d, kl: tuple(-x for x in min((cfg_rank[s], i) for _, s, i in sources(kl)))
    V.POLICIES["borda"] = lambda d, kl: sum(1 - Fraction(i, n_bc[b][s]) for b, s, i in sources(kl))
    V.POLICIES["rrf"] = lambda d, kl: sum(Fraction(1, 60 + i) for _, _, i in sources(kl))
    V.POLICIES["mean_norm_position"] = lambda d, kl: -(sum(Fraction(i, n_bc[b][s]) for b, s, i in sources(kl)) / len(sources(kl)))
    # best single configuration: chosen per rotation on that rotation's refit (training + tuning) bugs only
    bug_rot = {}
    for o in data.occ.values():
        bug_rot[o.bug] = o.rotation
    fold_of_bug = {data.ctx_bug[c]: f for c, f in data.ctx_fold.items()}
    chosen = {}
    for j in range(5):
        test_fold = f"fold_{j}"
        sel_bugs = sorted({b for b, f in fold_of_bug.items() if f in {f"fold_{(j + k) % 5}" for k in (2, 3, 4)}})
        per_bug_cfg = defaultdict(dict)  # bug -> config -> list of (index, occurrence)
        for o in data.occ.values():
            if o.bug in sel_bugs:
                for s, i in o.sources:
                    per_bug_cfg[o.bug].setdefault(s, []).append((i, o.cid))
        score = {}
        for c in configs:
            total = Fraction(0)
            for b in sel_bugs:
                cands = per_bug_cfg[b].get(c, [])
                if not cands:
                    continue
                lo = min(i for i, _ in cands)
                top = [k for i, k in cands if i == lo]
                total += Fraction(sum(1 for k in top if data.e0[k] == 1), len(top))
            score[c] = total / len(sel_bugs)
        chosen[j] = max(configs, key=lambda c: (score[c], [-ord(ch) for ch in c]))
        chosen[f"{j}_scores"] = {c: float(v) for c, v in score.items()}
        assert test_fold not in {f"fold_{(j + k) % 5}" for k in (2, 3, 4)}

    def best_cfg_score(d, kl):
        c = chosen[bug_rot[d.occ[kl.members[0]].bug]]
        return -min(i for m in kl.members for s, i in d.occ[m].sources if s == c)

    def best_cfg_elig(d, kl):
        c = chosen[bug_rot[d.occ[kl.members[0]].bug]]
        return any(s == c for m in kl.members for s, _ in d.occ[m].sources)

    V.POLICIES["best_config_top1"] = best_cfg_score
    V.POLICY_ELIG["best_config_top1"] = best_cfg_elig
    # learned alternatives (held-out scores from learners.py)
    for name in ("one_stage", "source_agnostic"):
        p = V.RES / "v4" / "learners" / f"{name}.jsonl"
        if p.exists():
            sc = {r["candidate_id"]: r["score"] for r in V.jsonl(p)}
            V.POLICIES[name] = (lambda table: (lambda d, kl: max(table[m] for m in kl.members)))(sc)
    # content-aware scores produced on GPU (score = higher is better), if present
    for name in ("codet5_similarity", "naturalness", "entropy_delta"):
        p = V.RES / "v4" / "content_scores" / f"{name}.jsonl"
        if p.exists():
            sc = {r["candidate_id"]: r["score"] for r in V.jsonl(p)}
            V.POLICIES[name] = (lambda table: (lambda d, kl: max(table[m] for m in kl.members)))(sc)
    return chosen


DRAFT_ROWS = {"uniform": "uniform_random", "token_similarity": "token_similarity", "occurrence": "occurrence_count",
              "mra": "native_position", "mra_then_occurrence": "native_then_occurrence",
              "testability": "testability_product"}


def main():
    data = V.load()
    chosen = register(data)
    ref = json.loads((V.RES / "matched_baselines/v1/summary.json").read_text())["results"]["challenger_minus"]
    # Gate A2
    pools_ctx = V.build_pools(data, "context", "occ")
    ev1 = data.evidence("E1")
    gate = {}
    for mine, theirs in DRAFT_ROWS.items():
        units, _ = V.evaluate_pair(data, pools_ctx, ev1, "challenger", mine, noop="N-b")
        agg = V.aggregate(units, "bug", len(data.bugs))
        exp = ref[theirs]["equal_bug_bounds"]
        err = max(abs(float(agg["lo"]) - exp[0]), abs(float(agg["hi"]) - exp[1]))
        gate[mine] = err
    ok = all(e < 1e-12 for e in gate.values())
    print(json.dumps({"gate_A2_max_abs_errors": gate, "passed": ok}), flush=True)
    if not ok:
        raise SystemExit("Gate A2 failed")
    # bug-level matrix at the primary specification
    pools = V.build_pools(data, "bug", "ast")
    policies = [p for p in ("challenger", "mra", "best_config_top1", "first_global", "borda", "rrf",
                            "mean_norm_position", "occurrence", "mra_then_occurrence", "testability",
                            "one_stage", "source_agnostic", "token_similarity", "codet5_similarity",
                            "naturalness", "entropy_delta", "uniform") if p in V.POLICIES]
    out_rows = []
    for ev_name in ("E0", "E1"):
        ev = data.evidence(ev_name)
        for a in ("challenger", "mra"):
            for b in policies:
                if a == b:
                    continue
                units, _ = V.evaluate_pair(data, pools, ev, a, b, noop="N-a")
                agg = V.aggregate(units, "bug", len(data.bugs))
                same = sum(1 for u in units if not u.coeffs)
                out_rows.append({"evidence": ev_name, "a": a, "b": b, "lo_pp": V.pp(agg["lo"]), "hi_pp": V.pp(agg["hi"]),
                                 "sign": "+" if agg["lo"] > 0 else "-" if agg["hi"] < 0 else "open",
                                 "relevant_unknown_classes": V.relevant_unknowns(units),
                                 "bugs_identical_distribution": same})
                print(f"{ev_name} {a:10s} - {b:20s} [{out_rows[-1]['lo_pp']:+.3f},{out_rows[-1]['hi_pp']:+.3f}] "
                      f"{out_rows[-1]['sign']:4s} identical_bugs={same}", flush=True)
    # absolute success bounds per policy (uniform baseline difference trick: success = policy - 'nothing')
    absolute = []
    for ev_name in ("E0", "E1"):
        ev = data.evidence(ev_name)
        for p in policies:
            V.POLICIES["_abstain"] = lambda d, kl: 0
            V.POLICY_ELIG["_abstain"] = lambda d, kl: False
            units, _ = V.evaluate_pair(data, pools, ev, p, "_abstain", noop="N-a")
            agg = V.aggregate(units, "bug", len(data.bugs))
            absolute.append({"evidence": ev_name, "policy": p, "lo_pp": V.pp(agg["lo"]), "hi_pp": V.pp(agg["hi"])})
    out = V.RES / "v4" / "baselines"
    out.mkdir(parents=True, exist_ok=True)
    (out / "baselines_bug_level.json").write_text(json.dumps({
        "protocol_sha256": data.input_hashes["protocol"], "gate_A2": gate,
        "best_config_choice": {k: v for k, v in chosen.items() if not str(k).endswith("_scores")},
        "best_config_training_scores": {k: v for k, v in chosen.items() if str(k).endswith("_scores")},
        "pairs": out_rows, "absolute_success": absolute}, indent=1))
    for r in absolute:
        print(f"success {r['evidence']} {r['policy']:20s} [{r['lo_pp']:.3f},{r['hi_pp']:.3f}]")


if __name__ == "__main__":
    main()
