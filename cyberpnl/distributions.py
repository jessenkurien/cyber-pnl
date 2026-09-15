"""Range → samples. Three shapes cover what experts can actually calibrate.

  pert:      {min, mode, max}      — the workhorse; a smoothed triangle (beta-PERT, lambda=4)
  lognormal: {p05, p95}            — heavy right tail for costs (a 90% calibrated input interval)
  fixed:     {value}               — a known quantity (record count, hourly revenue)

All sampling goes through a numpy Generator so runs are reproducible from a seed.
"""

from __future__ import annotations

import math

import numpy as np

_Z90 = 1.6448536269514722  # z for the 95th percentile (90% two-sided interval)


def sample_pert(
    rng: np.random.Generator, lo: float, mode: float, hi: float, n: int, lam: float = 4.0
) -> np.ndarray:
    if not (lo <= mode <= hi):
        raise ValueError(f"pert requires min <= mode <= max, got {lo}, {mode}, {hi}")
    if hi == lo:
        return np.full(n, float(lo))
    a = 1.0 + lam * (mode - lo) / (hi - lo)
    b = 1.0 + lam * (hi - mode) / (hi - lo)
    return lo + rng.beta(a, b, size=n) * (hi - lo)


def sample_lognormal_ci(rng: np.random.Generator, p05: float, p95: float, n: int) -> np.ndarray:
    if not (0 < p05 <= p95):
        raise ValueError(f"lognormal requires 0 < p05 <= p95, got {p05}, {p95}")
    if p05 == p95:
        return np.full(n, float(p05))
    mu = (math.log(p05) + math.log(p95)) / 2.0
    sigma = (math.log(p95) - math.log(p05)) / (2.0 * _Z90)
    return rng.lognormal(mu, sigma, size=n)


def pert_mean(lo: float, mode: float, hi: float, lam: float = 4.0) -> float:
    return (lo + lam * mode + hi) / (lam + 2.0)


def lognormal_ci_mean(p05: float, p95: float) -> float:
    mu = (math.log(p05) + math.log(p95)) / 2.0
    sigma = (math.log(p95) - math.log(p05)) / (2.0 * _Z90)
    return math.exp(mu + sigma * sigma / 2.0)
