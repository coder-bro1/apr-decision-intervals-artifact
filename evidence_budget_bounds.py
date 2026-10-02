"""Shared-outcome identification and fixed-rule bounded-loss calibration."""

import math
from fractions import Fraction

from validation_policy_contract import PolicyDecision


def exact_distribution(decision: PolicyDecision):
    values = dict(decision.probabilities)
    positive = [v for v in values.values() if v]
    if not positive:
        return {}
    if len(set(positive)) == 1:
        return {k: Fraction(1, len(positive)) if v else Fraction(0) for k, v in values.items()}
    total = sum((Fraction(v) for v in positive), Fraction(0))
    return {k: Fraction(v) / total for k, v in values.items()}


def difference_coefficients(proposed, baseline):
    p, b = exact_distribution(proposed), exact_distribution(baseline)
    if set(p) != set(b):
        raise ValueError("Comparison requires the same complete candidate pool.")
    return {k: p[k] - b[k] for k in p if p[k] != b[k]}


def comparison_bounds(coefficients, observed):
    lower = upper = Fraction(0)
    for key, coefficient in coefficients.items():
        value = observed.get(key)
        if value not in (None, 0, 1):
            raise ValueError("Evidence must be binary or unresolved.")
        coefficient = Fraction(coefficient)
        if value is None:
            lower += min(0, coefficient)
            upper += max(0, coefficient)
        else:
            lower += coefficient * value
            upper += coefficient * value
    return lower, upper


def resolved(lower, upper):
    return lower >= 0 or upper < 0


def bernoulli_kl(mean, upper):
    if not 0 <= mean <= upper <= 1:
        raise ValueError("Require 0 <= mean <= upper <= 1.")
    if mean == upper:
        return 0.0
    if upper == 1:
        return math.inf
    if mean == 0:
        return -math.log1p(-upper)
    return mean * math.log(mean / upper) + (1 - mean) * math.log((1 - mean) / (1 - upper))


def risk_upper(losses, method="kl", failure_probability=.01 / 42):
    if method not in {"kl", "hoeffding"} or not 0 < failure_probability < 1:
        raise ValueError("Invalid bound or failure probability.")
    if any(not math.isfinite(x) or not 0 <= x <= 1 for x in losses):
        raise ValueError("Losses must lie in [0,1].")
    if not len(losses):
        return None
    mean = math.fsum(losses) / len(losses)
    radius = -math.log(failure_probability) / len(losses)
    if method == "hoeffding":
        return min(1.0, mean + math.sqrt(radius / 2))
    if mean == 0:
        return -math.expm1(-radius)
    low, high = mean, 1.0
    for _ in range(70):
        middle = (low + high) / 2
        if bernoulli_kl(mean, middle) <= radius:
            low = middle
        else:
            high = middle
    return high


def select_query(method, coefficients, observed, scores, priorities, attempted):
    """Only observed evidence is accepted; no oracle/truth argument exists."""
    eligible = [k for k in scores if observed.get(k) is None and k not in attempted]
    if method != "random_all":
        eligible = [k for k in eligible if coefficients.get(k, 0)]
    if not eligible:
        return None
    if method in {"random_all", "random_disagreement"}:
        return min(eligible, key=lambda k: priorities[k])
    if method == "uncertainty":
        return min(eligible, key=lambda k: (abs(scores[k] - .5), priorities[k]))
    if method == "disagreement_first":
        return min(eligible, key=lambda k: (-abs(coefficients[k]), priorities[k]))
    if method != "decision_focused":
        raise ValueError(f"Unknown acquisition method: {method}")
    lower, upper = comparison_bounds(coefficients, observed)

    def key(k):
        d = coefficients[k]
        low0, high0 = lower - min(0, d), upper - max(0, d)
        gain = (1 - scores[k]) * resolved(low0, high0) + scores[k] * resolved(low0 + d, high0 + d)
        return -gain, -abs(d), priorities[k]

    return min(eligible, key=key)
