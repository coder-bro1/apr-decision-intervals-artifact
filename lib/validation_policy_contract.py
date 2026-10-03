"""Outcome-blind policy interface for the September protocol amendment.

This module does not fit rankers, calibrate risk, or adjudicate correctness.
"""

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence


def content_id(prefix: str, *parts: str) -> str:
    payload = json.dumps(parts, ensure_ascii=True, separators=(",", ":"))
    return prefix + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def context_id(bug_id: str, anchor: str) -> str:
    return content_id("obsctx_", bug_id, anchor.strip())


def candidate_id(bug_id: str, anchor: str, patch: str) -> str:
    return content_id("obscand_", bug_id, anchor.strip(), patch.strip())


@dataclass(frozen=True, order=True)
class SourcePosition:
    source_config: str
    candidate_index: int

    def __post_init__(self):
        if not self.source_config or type(self.candidate_index) is not int or self.candidate_index < 0:
            raise ValueError("Source configuration and nonnegative integer index required.")


@dataclass(frozen=True)
class CandidateView:
    candidate_id: str
    context_id: str
    anchor: str
    patch: str
    sources: tuple[SourcePosition, ...]

    def __post_init__(self):
        if not self.anchor.strip() or not self.patch.strip() or not self.sources:
            raise ValueError("Nonempty buggy code, generated code, and provenance required.")


def project_candidate(row: Mapping) -> CandidateView:
    """Allowlist fields; never pass the raw archive record to a ranker."""
    bug, anchor, patch = row["bug_id"], row["anchor"].strip(), row["patch"].strip()
    positions = tuple(sorted(SourcePosition(s["source_config"], s["candidate_index"])
                             for s in row["sources"]))
    return CandidateView(candidate_id(bug, anchor, patch), context_id(bug, anchor),
                         anchor, patch, positions)


@dataclass(frozen=True)
class PolicyDecision:
    # Include every pool candidate, including zero selection probabilities.
    probabilities: tuple[tuple[str, float], ...]

    def __post_init__(self):
        ids = [key for key, _ in self.probabilities]
        values = [value for _, value in self.probabilities]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate policy candidate ID.")
        if any(not math.isfinite(value) or value < 0 for value in values):
            raise ValueError("Policy probabilities must be finite and nonnegative.")
        if values and not math.isclose(sum(values), 1.0, abs_tol=1e-12, rel_tol=0):
            raise ValueError("Nonempty policy probabilities must sum to one.")


Ranker = Callable[[Sequence[CandidateView]], Mapping[str, float]]


def decision_from_scores(pool: Sequence[CandidateView], scores: Mapping[str, float]) -> PolicyDecision:
    ids = [row.candidate_id for row in pool]
    if len(ids) != len(set(ids)) or len({row.context_id for row in pool}) > 1:
        raise ValueError("A policy call requires one context and unique candidates.")
    if set(scores) != set(ids):
        raise ValueError("Scores must cover exactly the full pool; no silent dropping/backfill.")
    if any(not math.isfinite(value) for value in scores.values()):
        raise ValueError("Scores must be finite.")
    if not pool:
        return PolicyDecision(())
    best = max(scores.values())
    top = {key for key, score in scores.items() if score == best}
    return PolicyDecision(tuple((key, 1.0 / len(top) if key in top else 0.0) for key in sorted(ids)))


def apply_ranker(pool: Sequence[CandidateView], ranker: Ranker) -> PolicyDecision:
    return decision_from_scores(pool, ranker(tuple(pool)))


def native_scores(pool: Sequence[CandidateView]) -> dict[str, float]:
    return {row.candidate_id: -min(source.candidate_index for source in row.sources) for row in pool}


def support_only_action(out_of_support: bool, top_sets_identical: bool) -> str:
    if out_of_support:
        return "defer"
    return "agreement" if top_sets_identical else "override"


def apply_support_only(baseline: PolicyDecision, challenger: PolicyDecision,
                       out_of_support: bool) -> tuple[str, PolicyDecision]:
    if {key for key, _ in baseline.probabilities} != {key for key, _ in challenger.probabilities}:
        raise ValueError("Policies must operate on the same full candidate pool.")
    # Compare distributions, not just the most probable candidate's identity.
    agreement = dict(baseline.probabilities) == dict(challenger.probabilities)
    action = support_only_action(out_of_support, agreement)
    return action, challenger if action == "override" else baseline


def label_blind_fold(bug_id: str) -> str:
    digest = content_id("", "validation-contract-2026-09-13-v1", bug_id)
    return f"fold_{int(digest, 16) % 5}"
