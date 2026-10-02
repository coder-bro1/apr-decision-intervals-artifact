import math
from collections import defaultdict

from scipy.optimize import minimize, minimize_scalar
from scipy.special import betaln, expit


MIN_CONCENTRATION = 1e-3
MAX_CONCENTRATION = 1e6
EPSILON = 1e-9


def clamp_probability(value):
    return min(max(float(value), EPSILON), 1.0 - EPSILON)


def logit(value):
    value = clamp_probability(value)
    return math.log(value / (1.0 - value))


def beta_binomial_log_marginal(correct, total, mean, concentration):
    mean = clamp_probability(mean)
    concentration = min(max(float(concentration), MIN_CONCENTRATION), MAX_CONCENTRATION)
    alpha = mean * concentration
    beta = (1.0 - mean) * concentration
    return float(
        betaln(correct + alpha, total - correct + beta) - betaln(alpha, beta)
    )


def estimate_concentration(cells, means):
    cells = list(cells)
    means = list(means)
    if not cells or len(cells) != len(means):
        raise ValueError("Cells and prior means must be non-empty and aligned.")

    def objective(log_concentration):
        concentration = math.exp(float(log_concentration))
        return -sum(
            beta_binomial_log_marginal(correct, total, mean, concentration)
            for (total, correct), mean in zip(cells, means)
        )

    result = minimize_scalar(
        objective,
        bounds=(math.log(MIN_CONCENTRATION), math.log(MAX_CONCENTRATION)),
        method="bounded",
        options={"xatol": 1e-6, "maxiter": 1000},
    )
    concentration = math.exp(float(result.x))
    return concentration, {
        "success": bool(result.success),
        "objective": float(result.fun),
        "message": str(result.message),
        "cell_count": len(cells),
        "hit_lower_bound": concentration <= MIN_CONCENTRATION * 1.01,
        "hit_upper_bound": concentration >= MAX_CONCENTRATION / 1.01,
    }


def posterior_rate(correct, total, prior, concentration):
    return (correct + concentration * prior) / (total + concentration)


class EmpiricalBayesStreamCalibrator:
    def __init__(self):
        self.global_prior = 0.0
        self.index_rates = {}
        self.source_rates = {}
        self.stream_rates = {}
        self.index_counts = {}
        self.source_counts = {}
        self.stream_counts = {}
        self.index_concentration = None
        self.source_concentration = None
        self.stream_concentration = None
        self.source_mix_weight = None
        self.optimization = {}

    def fit(self, rows):
        global_total = 0
        global_correct = 0
        index_counts = defaultdict(lambda: [0, 0])
        source_counts = defaultdict(lambda: [0, 0])
        stream_counts = defaultdict(lambda: [0, 0])

        for row in rows:
            label = 1 if row.get("label") == "correct" else 0
            for occurrence in row.get("_stream_occurrences", []):
                source = occurrence["source_config"]
                bin_label = occurrence["index_bin"]
                global_total += 1
                global_correct += label
                index_counts[bin_label][0] += 1
                index_counts[bin_label][1] += label
                source_counts[source][0] += 1
                source_counts[source][1] += label
                stream_counts[(source, bin_label)][0] += 1
                stream_counts[(source, bin_label)][1] += label
        if global_total == 0:
            raise ValueError("Cannot fit empirical-Bayes calibration without occurrences.")

        self.global_prior = (global_correct + 0.5) / (global_total + 1.0)
        self.index_counts = {
            key: {"total": total, "correct": correct}
            for key, (total, correct) in index_counts.items()
        }
        self.source_counts = {
            key: {"total": total, "correct": correct}
            for key, (total, correct) in source_counts.items()
        }
        self.stream_counts = {
            f"{source}|{bin_label}": {"total": total, "correct": correct}
            for (source, bin_label), (total, correct) in stream_counts.items()
        }

        ordered_index = sorted(index_counts)
        self.index_concentration, index_metadata = estimate_concentration(
            [index_counts[key] for key in ordered_index],
            [self.global_prior] * len(ordered_index),
        )
        self.index_rates = {
            key: posterior_rate(
                correct, total, self.global_prior, self.index_concentration
            )
            for key, (total, correct) in index_counts.items()
        }

        ordered_sources = sorted(source_counts)
        self.source_concentration, source_metadata = estimate_concentration(
            [source_counts[key] for key in ordered_sources],
            [self.global_prior] * len(ordered_sources),
        )
        self.source_rates = {
            key: posterior_rate(
                correct, total, self.global_prior, self.source_concentration
            )
            for key, (total, correct) in source_counts.items()
        }

        ordered_streams = sorted(stream_counts)

        def stream_objective(parameters):
            source_weight = float(parameters[0])
            concentration = math.exp(float(parameters[1]))
            total = 0.0
            for source, bin_label in ordered_streams:
                cell_total, cell_correct = stream_counts[(source, bin_label)]
                prior = self._combined_prior(source, bin_label, source_weight)
                total -= beta_binomial_log_marginal(
                    cell_correct, cell_total, prior, concentration
                )
            return total

        stream_result = minimize(
            stream_objective,
            x0=[0.5, math.log(35.0)],
            method="L-BFGS-B",
            bounds=[(0.0, 1.0), (math.log(MIN_CONCENTRATION), math.log(MAX_CONCENTRATION))],
            options={"maxiter": 2000, "ftol": 1e-12},
        )
        fallback_optimizer_used = False
        if not stream_result.success:
            fallback_optimizer_used = True
            fallback_result = minimize(
                stream_objective,
                x0=[0.5, math.log(35.0)],
                method="Powell",
                bounds=[
                    (0.0, 1.0),
                    (math.log(MIN_CONCENTRATION), math.log(MAX_CONCENTRATION)),
                ],
                options={"maxiter": 4000, "xtol": 1e-8, "ftol": 1e-10},
            )
            if fallback_result.success or fallback_result.fun < stream_result.fun:
                stream_result = fallback_result
        if stream_result.success:
            self.source_mix_weight = float(stream_result.x[0])
            self.stream_concentration = math.exp(float(stream_result.x[1]))
        else:
            self.source_mix_weight = 0.5
            means = [
                self._combined_prior(source, bin_label, self.source_mix_weight)
                for source, bin_label in ordered_streams
            ]
            self.stream_concentration, _ = estimate_concentration(
                [stream_counts[key] for key in ordered_streams], means
            )

        self.stream_rates = {}
        for source, bin_label in ordered_streams:
            total, correct = stream_counts[(source, bin_label)]
            prior = self._combined_prior(
                source, bin_label, self.source_mix_weight
            )
            self.stream_rates[(source, bin_label)] = posterior_rate(
                correct, total, prior, self.stream_concentration
            )

        self.optimization = {
            "index": index_metadata,
            "source": source_metadata,
            "stream": {
                "success": bool(stream_result.success),
                "objective": float(stream_result.fun),
                "message": str(stream_result.message),
                "fallback_optimizer_used": fallback_optimizer_used,
                "cell_count": len(ordered_streams),
                "hit_source_mix_lower_bound": self.source_mix_weight <= 0.001,
                "hit_source_mix_upper_bound": self.source_mix_weight >= 0.999,
                "hit_concentration_lower_bound": self.stream_concentration
                <= MIN_CONCENTRATION * 1.01,
                "hit_concentration_upper_bound": self.stream_concentration
                >= MAX_CONCENTRATION / 1.01,
            },
        }
        return self

    def _combined_prior(self, source_config, bin_label, source_weight=None):
        if source_weight is None:
            source_weight = self.source_mix_weight if self.source_mix_weight is not None else 0.5
        source_probability = self.source_prob(source_config)
        index_probability = self.index_prob(bin_label)
        combined_logit = (
            source_weight * logit(source_probability)
            + (1.0 - source_weight) * logit(index_probability)
        )
        return float(expit(combined_logit))

    def index_prob(self, bin_label):
        return self.index_rates.get(bin_label, self.global_prior)

    def source_prob(self, source_config):
        return self.source_rates.get(source_config, self.global_prior)

    def stream_prob(self, source_config, bin_label):
        if (source_config, bin_label) in self.stream_rates:
            return self.stream_rates[(source_config, bin_label)]
        return self._combined_prior(source_config, bin_label)

    def candidate_probabilities(self, row):
        occurrences = row.get("_stream_occurrences", [])
        if not occurrences:
            return {
                "global_index_values": [self.global_prior],
                "source_prior_values": [self.global_prior],
                "stream_values": [self.global_prior],
            }
        return {
            "global_index_values": [
                self.index_prob(occurrence["index_bin"])
                for occurrence in occurrences
            ],
            "source_prior_values": [
                self.source_prob(occurrence["source_config"])
                for occurrence in occurrences
            ],
            "stream_values": [
                self.stream_prob(
                    occurrence["source_config"], occurrence["index_bin"]
                )
                for occurrence in occurrences
            ],
        }

    def metadata(self):
        return {
            "estimator": "hierarchical_beta_binomial_empirical_bayes",
            "global_prior": self.global_prior,
            "learned_hyperparameters": {
                "index_concentration": self.index_concentration,
                "source_concentration": self.source_concentration,
                "stream_concentration": self.stream_concentration,
                "source_mix_weight": self.source_mix_weight,
                "index_mix_weight": 1.0 - self.source_mix_weight,
            },
            "index_rates": self.index_rates,
            "source_rates": self.source_rates,
            "stream_rates": {
                f"{source}|{bin_label}": value
                for (source, bin_label), value in self.stream_rates.items()
            },
            "index_counts": self.index_counts,
            "source_counts": self.source_counts,
            "stream_counts": self.stream_counts,
            "optimization": self.optimization,
            "hyperparameter_policy": (
                "Concentrations and source/index log-odds mixing weight are "
                "estimated by training-only beta-binomial marginal likelihood."
            ),
        }
