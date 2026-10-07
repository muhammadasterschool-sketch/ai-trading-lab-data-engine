"""Phase 7 — Statistical validation (blueprint 5.25).

Deterministic statistics WITHOUT scipy: the Student-t CDF is computed
via the regularized incomplete beta function (continued-fraction
expansion, Lentz's method). Identical inputs produce bit-identical
p-values in any process — no environment-dependent numerics.

- ``t_test``: two-sided one-sample t-test over a return series.
- ``confidence_interval``: t-quantile by deterministic bisection on
  the CDF.
- ``bonferroni`` / ``benjamini_hochberg``: multiple-testing control.

All p-values are valid (0..1); degenerate inputs (n < 2, zero
variance) raise — an invalid test must never produce a silently
wrong p-value (blueprint 5.25 failure mode: 'invalid statistical
tests, p-hacking').
"""

import math
from typing import Sequence

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.pit.hashing import deterministic_hash

#: Phase 7 contract version.
PHASE_7_CONTRACT_VERSION = "1.0.0"


def _betacf(a: float, b: float, x: float, max_iter: int = 200,
            eps: float = 3e-12) -> float:
    """Continued fraction for the incomplete beta function (Lentz)."""
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def regularized_incomplete_beta(a: float, b: float, x: float) -> float:
    """I_x(a, b) — the regularized incomplete beta function."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    ln_beta = (
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
        + a * math.log(x) + b * math.log(1.0 - x)
    )
    front = math.exp(ln_beta)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def t_distribution_cdf(t: float, df: int) -> float:
    """CDF of Student's t distribution with ``df`` degrees of freedom."""
    if df <= 0:
        raise ValueError("degrees of freedom must be positive")
    x = df / (df + t * t)
    p_one_sided = 0.5 * regularized_incomplete_beta(df / 2.0, 0.5, x)
    if t > 0:
        return 1.0 - p_one_sided
    if t < 0:
        return p_one_sided
    return 0.5


def t_quantile(prob: float, df: int) -> float:
    """Inverse CDF by deterministic bisection (prob in open (0, 1))."""
    if not 0.0 < prob < 1.0:
        raise ValueError("prob must be in the open interval (0, 1)")
    lo, hi = -100.0, 100.0
    for _ in range(300):  # bisection converges to 1e-60 range well before
        mid = 0.5 * (lo + hi)
        if t_distribution_cdf(mid, df) < prob:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


class TTestResult(BaseModel):
    """One-sample two-sided t-test result."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    n: int
    mean: float
    stdev: float
    t_statistic: float
    degrees_of_freedom: int
    p_value: float

    @field_validator("p_value")
    @classmethod
    def _validate_p(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("p-value outside [0, 1] — invalid test")
        return v

    @property
    def significant_at_5pct(self) -> bool:
        return self.p_value < 0.05

    @property
    def result_hash(self) -> str:
        return deterministic_hash(
            {
                "contract_version": PHASE_7_CONTRACT_VERSION,
                "n": self.n,
                "mean": self.mean,
                "stdev": self.stdev,
                "t_statistic": self.t_statistic,
                "degrees_of_freedom": self.degrees_of_freedom,
                "p_value": self.p_value,
            }
        )


def t_test(values: Sequence[float]) -> TTestResult:
    """Two-sided one-sample t-test of mean == 0.

    Raises on degenerate inputs (n < 2 or zero variance): a test that
    cannot be performed must fail loudly, not emit a fake p-value.
    """
    n = len(values)
    if n < 2:
        raise ValueError("t-test requires at least 2 observations")
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    if variance <= 0.0:
        raise ValueError(
            "zero variance: t-statistic undefined (degenerate sample)"
        )
    stdev = math.sqrt(variance)
    t_stat = mean / (stdev / math.sqrt(n))
    df = n - 1
    x = df / (df + t_stat * t_stat)
    p = regularized_incomplete_beta(df / 2.0, 0.5, x)
    return TTestResult(
        n=n,
        mean=mean,
        stdev=stdev,
        t_statistic=t_stat,
        degrees_of_freedom=df,
        p_value=min(1.0, max(0.0, p)),
    )


def confidence_interval(
    values: Sequence[float], confidence: float = 0.95
) -> tuple[float, float]:
    """t-based confidence interval for the mean.

    ``confidence`` in the open interval (0, 1); degenerate samples
    raise (fail closed).
    """
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")
    n = len(values)
    if n < 2:
        raise ValueError("confidence interval requires at least 2 observations")
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    if variance <= 0.0:
        raise ValueError("zero variance: interval undefined")
    stdev = math.sqrt(variance)
    critical = t_quantile(0.5 + confidence / 2.0, n - 1)
    half_width = critical * stdev / math.sqrt(n)
    return mean - half_width, mean + half_width


def bonferroni(p_values: Sequence[float]) -> list[float]:
    """Bonferroni-adjusted p-values (FWER control): p_i * m, capped at 1."""
    m = len(p_values)
    if m == 0:
        return []
    for p in p_values:
        if not 0.0 <= p <= 1.0:
            raise ValueError("all p-values must be in [0, 1]")
    return [min(1.0, p * m) for p in p_values]


def benjamini_hochberg(
    p_values: Sequence[float], q: float = 0.05
) -> list[bool]:
    """Benjamini-Hochberg FDR procedure at level ``q``.

    Returns a list of booleans (same order as input): True where the
    hypothesis is rejected (discovery) under the BH step-up rule.
    """
    m = len(p_values)
    if m == 0:
        return []
    if not 0.0 < q <= 1.0:
        raise ValueError("q must be in (0, 1]")
    for p in p_values:
        if not 0.0 <= p <= 1.0:
            raise ValueError("all p-values must be in [0, 1]")
    order = sorted(range(m), key=lambda i: p_values[i])
    rejected = [False] * m
    # Step-up: k* = max{k : p(k) <= (k/m) * q}; reject the k* smallest.
    running_max = 0
    for rank, idx in enumerate(order, start=1):
        if p_values[idx] <= (rank / m) * q:
            running_max = max(running_max, rank)
    for rank in range(1, running_max + 1):
        rejected[order[rank - 1]] = True
    return rejected


class StatisticalValidator:
    """Facade implementing blueprint 5.25's interface."""

    def validate_returns(self, returns: Sequence[float]) -> TTestResult:
        return t_test(returns)

    def validate_many(
        self, p_values: Sequence[float], method: str = "bh", q: float = 0.05
    ) -> list[bool]:
        if method == "bh":
            return benjamini_hochberg(p_values, q)
        if method == "bonferroni":
            adjusted = bonferroni(p_values)
            return [p < 0.05 for p in adjusted]
        raise ValueError(f"unknown multiple-testing method {method!r}")


__all__ = [
    "TTestResult",
    "t_test",
    "confidence_interval",
    "bonferroni",
    "benjamini_hochberg",
    "t_distribution_cdf",
    "t_quantile",
    "regularized_incomplete_beta",
    "StatisticalValidator",
    "PHASE_7_CONTRACT_VERSION",
]
