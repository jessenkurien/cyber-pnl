"""Monte Carlo engine.

For each simulated year and each scenario:
  events      ~ Poisson(rate),  rate ~ frequency range × Π frequency multipliers
  loss        = Σ over events of Σ over components of sampled component cost × Π magnitude multipliers
annual loss   = Σ over scenarios

Control attribution uses stable, independent random streams for every scenario, control,
effect and loss component. Counterfactual runs therefore do not reshuffle unrelated inputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from . import kpis as kpimod
from .models import Component, Control, Model, Range, Scenario

PCTS = (50, 90, 95, 99)
MAX_SIMULATED_YEARS = 250_000
MAX_EVENT_SAMPLES = 10_000_000
MAX_SEED = 2**32 - 1


@dataclass
class ScenarioResult:
    id: str
    name: str
    annual: np.ndarray  # loss per simulated year
    events_per_year: float
    multipliers: list[str]  # human-readable explanation of applied control effects

    @property
    def eal(self) -> float:
        return float(self.annual.mean())

    def pct(self, q: float) -> float:
        return float(np.percentile(self.annual, q))


@dataclass
class RunResult:
    total: np.ndarray
    scenarios: list[ScenarioResult]
    n: int
    seed: int
    excluded: set[str] = field(default_factory=set)
    included_proposed: set[str] = field(default_factory=set)

    @property
    def eal(self) -> float:
        return float(self.total.mean())

    def pct(self, q: float) -> float:
        return float(np.percentile(self.total, q))

    def exceedance(self, thresholds: np.ndarray) -> np.ndarray:
        """P(annual loss >= threshold) for each threshold."""
        sorted_losses = np.sort(self.total)
        idx = np.searchsorted(sorted_losses, thresholds, side="left")
        return 1.0 - idx / len(sorted_losses)

    def p_exceed(self, x: float) -> float:
        return float((self.total >= x).mean())

    def summary(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "seed": self.seed,
            "eal": self.eal,
            **{f"p{q}": self.pct(q) for q in PCTS},
            "p_zero_loss_year": float((self.total == 0).mean()),
            "scenarios": [
                {
                    "id": s.id,
                    "name": s.name,
                    "eal": s.eal,
                    "p95": s.pct(95),
                    "events_per_year": s.events_per_year,
                    "share": (s.eal / self.eal if self.eal else 0.0),
                }
                for s in sorted(self.scenarios, key=lambda s: -s.eal)
            ],
        }


def _rng(seed: int, *parts: int) -> np.random.Generator:
    """Create a stable stream identified by integer coordinates."""
    return np.random.default_rng([seed, *parts])


def _component_cost(
    seed: int, stream: tuple[int, ...], c: Component, sc: Scenario, model: Model, n_events: int
) -> np.ndarray:
    if n_events == 0:
        return np.zeros(0)
    if c.kind in {"dollars", "offset"}:
        return c.amount.sample(_rng(seed, *stream, 1), n_events)
    if c.kind == "downtime":
        rph = (
            c.revenue_per_hour
            if c.revenue_per_hour is not None
            else model.business.service(sc.service).revenue_per_hour
        )
        return c.hours.sample(_rng(seed, *stream, 1), n_events) * rph
    if c.kind == "ransom":
        probability = c.p_pay.sample(_rng(seed, *stream, 1), n_events)
        pay = _rng(seed, *stream, 2).random(n_events) < probability
        return c.demand.sample(_rng(seed, *stream, 3), n_events) * pay
    if c.kind == "per_record":
        records = c.records.sample(_rng(seed, *stream, 1), n_events)
        cost = c.cost_per_record.sample(_rng(seed, *stream, 2), n_events)
        return records * cost
    if c.kind == "pct_revenue":
        return c.pct.sample(_rng(seed, *stream, 1), n_events) * model.business.annual_revenue
    raise ValueError(c.kind)


def _multipliers(
    sc: Scenario, active_ids: set[str], model: Model, seed: int, scenario_index: int, n: int
) -> tuple[np.ndarray, dict[str, np.ndarray], list[str]]:
    """Returns (frequency multiplier per year [n], magnitude multiplier per component-name [n], explanations)."""
    freq = np.ones(n)
    mag: dict[str, np.ndarray] = {c.name: np.ones(n) for c in sc.components}
    notes: list[str] = []
    for control_index, ctl in enumerate(model.controls):
        if ctl.id not in active_ids:
            continue
        for effect_index, e in enumerate(ctl.effects):
            if not e.applies_to(sc):
                continue
            if e.kpi:
                m, why = kpimod.evaluate(e.kpi, model.kpis)
                arr = np.full(n, m)
                target = e.kpi.applies
                if target == "frequency":
                    freq *= arr
                    notes.append(f"{ctl.id}: frequency {why}")
                else:
                    for c in sc.components:
                        target_matches = not e.component_tags or set(e.component_tags) & set(c.tags)
                        if target_matches and (c.kind != "offset" or bool(e.component_tags)):
                            mag[c.name] *= arr
                    notes.append(
                        f"{ctl.id}: magnitude{'[' + ','.join(e.component_tags) + ']' if e.component_tags else ''} {why}"
                    )
            if e.frequency_multiplier is not None:
                arr = e.frequency_multiplier.sample(
                    _rng(seed, scenario_index, 100, control_index, effect_index, 1), n
                )
                freq *= arr
                notes.append(f"{ctl.id}: frequency ×{e.frequency_multiplier.describe()}")
            if e.magnitude_multiplier is not None:
                arr = e.magnitude_multiplier.sample(
                    _rng(seed, scenario_index, 100, control_index, effect_index, 2), n
                )
                for c in sc.components:
                    target_matches = not e.component_tags or set(e.component_tags) & set(c.tags)
                    if target_matches and (c.kind != "offset" or bool(e.component_tags)):
                        mag[c.name] *= arr
                notes.append(
                    f"{ctl.id}: magnitude{'[' + ','.join(e.component_tags) + ']' if e.component_tags else ''} ×{e.magnitude_multiplier.describe()}"
                )
    floor = model.min_multiplier
    freq = np.maximum(freq, floor)
    for key, value in mag.items():
        mag[key] = np.maximum(value, floor)
    return freq, mag, notes


def simulate(
    model: Model,
    n: int = 20_000,
    seed: int = 7,
    exclude: set[str] | None = None,
    include_proposed: set[str] | None = None,
) -> RunResult:
    if not isinstance(n, (int, np.integer)) or isinstance(n, bool):
        raise TypeError("simulated years must be an integer")
    if not 1 <= int(n) <= MAX_SIMULATED_YEARS:
        raise ValueError(f"simulated years must be between 1 and {MAX_SIMULATED_YEARS:,}")
    if not isinstance(seed, (int, np.integer)) or isinstance(seed, bool):
        raise TypeError("seed must be an integer")
    if not 0 <= int(seed) <= MAX_SEED:
        raise ValueError(f"seed must be between 0 and {MAX_SEED:,}")
    n, seed = int(n), int(seed)
    for scenario in model.scenarios:
        upper_rate_budget = scenario.frequency.high() * n
        if upper_rate_budget > MAX_EVENT_SAMPLES:
            raise ValueError(
                f"scenario '{scenario.id}' can require up to {upper_rate_budget:,.0f} event samples; "
                f"limit is {MAX_EVENT_SAMPLES:,}. Reduce --years or the frequency range"
            )
    requested_proposed = include_proposed or set()
    unknown_proposed = requested_proposed - {control.id for control in model.proposed_controls()}
    if unknown_proposed:
        raise ValueError("unknown proposed controls: " + ", ".join(sorted(unknown_proposed)))
    unknown_excluded = (exclude or set()) - {control.id for control in model.existing_controls()}
    if unknown_excluded:
        raise ValueError("unknown existing controls: " + ", ".join(sorted(unknown_excluded)))
    included = model.with_dependencies(requested_proposed)
    include_proposed = {control.id for control in model.proposed_controls() if control.id in included}
    exclude = model.with_dependents((exclude or set()) | model.replacement_exclusions(include_proposed))
    active = [
        c
        for c in model.controls
        if (c.status == "existing" and c.id not in exclude) or c.id in include_proposed
    ]
    active_ids = {control.id for control in active}
    total = np.zeros(n)
    results: list[ScenarioResult] = []
    for i, sc in enumerate(model.scenarios):
        freq_mult, mag_mult, notes = _multipliers(sc, active_ids, model, seed, i, n)
        rate = sc.frequency.sample(_rng(seed, i, 1), n) * freq_mult
        events = _rng(seed, i, 2).poisson(rate)
        annual = np.zeros(n)
        total_events = int(events.sum())
        if total_events > MAX_EVENT_SAMPLES:
            raise ValueError(
                f"scenario '{sc.id}' generated {total_events:,} event samples; "
                f"limit is {MAX_EVENT_SAMPLES:,}. Reduce --years or the frequency range"
            )
        if total_events:
            year_idx = np.repeat(np.arange(n), events)
            per_event = np.zeros(total_events)
            for component_index, c in enumerate(sc.components):
                cost = _component_cost(seed, (i, 10, component_index), c, sc, model, total_events)
                per_event += cost * mag_mult[c.name][year_idx]
            # Recoveries and credits are offsets, but no event may create a negative loss.
            per_event = np.maximum(per_event, 0.0)
            np.add.at(annual, year_idx, per_event)
        total += annual
        results.append(ScenarioResult(sc.id, sc.name, annual, float(rate.mean()), notes))
    return RunResult(total, results, n, seed, set(exclude), set(include_proposed))


# ---------------------------------------------------------------- attribution & investments
@dataclass
class ControlValue:
    control: Control
    eal_with: float
    eal_without: float
    p95_with: float
    p95_without: float

    @property
    def value(self) -> float:  # expected annual loss avoided
        return self.eal_without - self.eal_with

    @property
    def benefit_cost_ratio(self) -> float | None:
        return (self.value / self.control.annual_cost) if self.control.annual_cost else None

    @property
    def net_rosi(self) -> float | None:
        return (
            (self.value - self.control.annual_cost) / self.control.annual_cost
            if self.control.annual_cost
            else None
        )


def control_values(model: Model, n: int = 20_000, seed: int = 7) -> list[ControlValue]:
    base = simulate(model, n, seed)
    out = []
    for c in model.existing_controls():
        without = simulate(model, n, seed, exclude={c.id})
        out.append(ControlValue(c, base.eal, without.eal, base.pct(95), without.pct(95)))
    return sorted(out, key=lambda v: -v.value)


@dataclass
class InvestmentCase:
    control: Control
    eal_before: float
    eal_after: float
    p95_before: float
    p95_after: float

    @property
    def avoided(self) -> float:
        return self.eal_before - self.eal_after

    @property
    def annualized_cost(self) -> float:
        # simple 3-year straight-line for one-time cost; documented in methodology
        return self.control.annual_cost + self.control.one_time_cost / 3.0

    @property
    def benefit_cost_ratio(self) -> float | None:
        return (self.avoided / self.annualized_cost) if self.annualized_cost else None

    @property
    def net_rosi(self) -> float | None:
        return (self.avoided - self.annualized_cost) / self.annualized_cost if self.annualized_cost else None

    @property
    def payback_months(self) -> float | None:
        annual_net_benefit = self.avoided - self.control.annual_cost
        if annual_net_benefit <= 0:
            return None
        return 12.0 * self.control.one_time_cost / annual_net_benefit if self.control.one_time_cost else 0.0


def investment_cases(model: Model, n: int = 20_000, seed: int = 7) -> list[InvestmentCase]:
    base = simulate(model, n, seed)
    out = []
    for c in model.proposed_controls():
        after = simulate(model, n, seed, include_proposed={c.id})
        out.append(InvestmentCase(c, base.eal, after.eal, base.pct(95), after.pct(95)))
    return sorted(out, key=lambda v: -(v.benefit_cost_ratio or -1))


# ---------------------------------------------------------------- sensitivity
@dataclass
class Sensitivity:
    path: str
    low_eal: float
    high_eal: float
    base_eal: float

    @property
    def swing(self) -> float:
        return abs(self.high_eal - self.low_eal)


def _set_range(r: Range, which: str) -> Range:
    v = r.low() if which == "low" else r.high()
    return Range(value=v, source=r.source, owner=r.owner)


def sensitivity(model: Model, n: int = 10_000, seed: int = 7, top: int = 10) -> list[Sensitivity]:
    """One-at-a-time: pin each scenario input to its low then high end, re-simulate, rank by swing."""
    base = simulate(model, n, seed).eal
    out = []
    for si, sc in enumerate(model.scenarios):
        targets: list[tuple[str, str, str | None]] = [(f"scenario.{sc.id}.frequency", "frequency", None)]
        for c in sc.components:
            for f in ("amount", "hours", "demand", "p_pay", "records", "cost_per_record", "pct"):
                if getattr(c, f) is not None and getattr(c, f).shape != "fixed":
                    targets.append((f"scenario.{sc.id}.{c.name}.{f}", f, c.name))
        for path, f, cname in targets:
            vals = {}
            for which in ("low", "high"):
                m = model.model_copy(deep=True)
                s2 = m.scenarios[si]
                if cname is None:
                    s2.frequency = _set_range(s2.frequency, which)
                else:
                    comp = next(x for x in s2.components if x.name == cname)
                    setattr(comp, f, _set_range(getattr(comp, f), which))
                vals[which] = simulate(m, n, seed).eal
            out.append(Sensitivity(path, vals["low"], vals["high"], base))
    return sorted(out, key=lambda s: -s.swing)[:top]


# ---------------------------------------------------------------- appetite
def appetite_check(model: Model, run: RunResult) -> dict[str, Any] | None:
    if model.appetite is None:
        return None
    appetite = model.appetite
    checks = []
    for item in appetite.limits:
        value = run.eal if item.metric == "eal" else run.pct(int(item.metric[1:]))
        threshold = item.threshold(model.business.annual_revenue)
        checks.append(
            {
                "metric": item.metric,
                "value": value,
                "limit": threshold,
                "within": value <= threshold,
                "headroom": threshold - value,
                "owner": item.owner,
                "source": item.source,
            }
        )
    return {
        "within": all(item["within"] for item in checks),
        "checks": checks,
        "statement": appetite.statement,
        "approved_by": appetite.approved_by,
    }
