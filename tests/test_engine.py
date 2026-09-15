import copy

import numpy as np
import pytest

from cyberpnl.engine import (
    MAX_EVENT_SAMPLES,
    MAX_SEED,
    MAX_SIMULATED_YEARS,
    appetite_check,
    control_values,
    investment_cases,
    sensitivity,
    simulate,
)
from cyberpnl.kpis import CURVES, contain_before_exfil, credential_exposure_grade, evaluate
from cyberpnl.models import KpiSpec, Range


def test_reproducible_with_seed(model):
    first = simulate(model, 5000, 11)
    second = simulate(model, 5000, 11)
    assert np.array_equal(first.total, second.total)
    assert not np.array_equal(first.total, simulate(model, 5000, 12).total)


def test_simulation_resource_and_seed_limits_fail_before_allocation(model):
    for years in (0, MAX_SIMULATED_YEARS + 1, 1.5, True):
        with pytest.raises((TypeError, ValueError)):
            simulate(model, years, 7)
    for seed in (-1, MAX_SEED + 1, 1.5, True):
        with pytest.raises((TypeError, ValueError)):
            simulate(model, 100, seed)

    oversized = copy.deepcopy(model)
    oversized.scenarios[0].frequency = oversized.scenarios[0].frequency.model_copy(
        update={"value": MAX_EVENT_SAMPLES + 1, "min": None, "mode": None, "max": None}
    )
    with np.testing.assert_raises(ValueError):
        simulate(oversized, 1, 7)


def test_converges(model):
    eal_one = simulate(model, 20_000, 1).eal
    eal_two = simulate(model, 20_000, 2).eal
    assert abs(eal_one - eal_two) / eal_one < 0.08


def test_losses_are_never_negative(model):
    run = simulate(model, 30_000, 7)
    assert np.all(run.total >= 0)
    assert all(np.all(scenario.annual >= 0) for scenario in run.scenarios)


def test_percentiles_and_exceedance_are_ordered(model):
    result = simulate(model, 10_000, 3)
    assert result.pct(50) <= result.pct(90) <= result.pct(95) <= result.pct(99)
    thresholds = np.linspace(0, result.pct(99), 50)
    probabilities = result.exceedance(thresholds)
    assert np.all(np.diff(probabilities) <= 1e-12)
    assert probabilities[0] >= 0.99


def test_removing_controls_and_adding_proposals_are_monotone(model):
    base = simulate(model, 10_000, 5).eal
    for control in model.existing_controls():
        assert simulate(model, 10_000, 5, exclude={control.id}).eal >= base - 1e-6, control.id
    for control in model.proposed_controls():
        assert simulate(model, 10_000, 5, include_proposed={control.id}).eal <= base + 1e-6, control.id


def test_unrelated_counterfactual_does_not_reshuffle_other_scenarios(model):
    base = simulate(model, 8000, 5)
    without_ddos = simulate(model, 8000, 5, exclude={"ddos-protection"})
    for before, after in zip(base.scenarios, without_ddos.scenarios):
        if before.id != "ddos-portal":
            assert np.array_equal(before.annual, after.annual), before.id


def test_control_values_are_positive_and_dependency_is_credited(model):
    values = {value.control.id: value for value in control_values(model, 10_000, 5)}
    assert all(value.value >= 0 for value in values.values())
    assert values["edr-fleet"].value > values["containment-72md"].value


def test_proposed_replacement_does_not_stack_with_existing_control(model):
    proper = simulate(model, 10_000, 5, include_proposed={"prop-phishing-resistant-mfa"})
    assert "mfa-workforce" in proper.excluded
    stacked_model = copy.deepcopy(model)
    proposal = next(c for c in stacked_model.controls if c.id == "prop-phishing-resistant-mfa")
    proposal.replaces = []
    stacked = simulate(stacked_model, 10_000, 5, include_proposed={proposal.id})
    assert stacked.eal < proper.eal


def test_benefit_cost_and_net_rosi_are_distinct(model):
    cases = investment_cases(model, 10_000, 5)
    assert cases[0].benefit_cost_ratio >= cases[-1].benefit_cost_ratio
    for case in cases:
        assert np.isclose(case.net_rosi, case.benefit_cost_ratio - 1)
        annual_net = case.avoided - case.control.annual_cost
        expected_payback = None if annual_net <= 0 else 12 * case.control.one_time_cost / annual_net
        assert case.payback_months == expected_payback
    cheap_process = next(case for case in cases if case.control.id == "prop-payment-dual-control")
    siem = next(case for case in cases if case.control.id == "prop-siem-replacement")
    assert cheap_process.benefit_cost_ratio > siem.benefit_cost_ratio


def test_kpi_drives_control_value(model):
    slow = copy.deepcopy(model)
    slow.kpis["time_to_contain_minutes"] = slow.kpis["time_to_contain_minutes"].model_copy(
        update={"value": 150}
    )
    fast = copy.deepcopy(model)
    fast.kpis["time_to_contain_minutes"] = fast.kpis["time_to_contain_minutes"].model_copy(
        update={"value": 20}
    )
    assert simulate(fast, 10_000, 5).eal < simulate(slow, 10_000, 5).eal


def test_kpi_curves_are_monotone_and_bounded():
    previous = 0
    for minutes in (10, 30, 50, 72, 100, 150):
        value = contain_before_exfil(minutes, {})
        assert 0 <= value <= 1 and value >= previous
        previous = value
    assert abs(contain_before_exfil(72, {"residual": 0}) - 0.5) < 1e-9
    assert credential_exposure_grade("A", {}) < credential_exposure_grade("D", {})
    assert credential_exposure_grade("D", {}) < credential_exposure_grade("F", {})
    assert credential_exposure_grade(34.0, {}) == credential_exposure_grade("B", {})
    for name, curve in CURVES.items():
        assert 0 <= curve(50, {}) <= 1.3, name


def test_kpi_default_used_when_unmeasured():
    spec = KpiSpec(curve="contain_before_exfil", key="ttc", default=120)
    multiplier, explanation = evaluate(spec, {})
    assert multiplier > 0.9 and "DEFAULT" in explanation


def test_stacking_floor_applies():
    from cyberpnl.models import Business, Component, Control, Effect, Model, Scenario, Service

    business = Business(
        organization="test",
        fiscal_year=2026,
        annual_revenue=1e6,
        services=[Service(id="service", revenue_per_hour=100)],
    )
    scenario = Scenario(
        id="scenario",
        name="scenario",
        service="service",
        threat="threat",
        frequency=Range(value=1.0),
        components=[Component(name="cost", kind="dollars", amount=Range(value=1000))],
    )
    controls = [
        Control(
            id=f"control-{index}",
            name="control",
            effects=[Effect(magnitude_multiplier=Range(value=0.1))],
        )
        for index in range(5)
    ]
    test_model = Model(business=business, scenarios=[scenario], controls=controls, min_multiplier=0.05)
    result = simulate(test_model, 5000, 1)
    assert 40 < result.eal < 60


def test_sensitivity_ranks_by_endpoint_swing(model):
    rows = sensitivity(model, 3000, 5, top=5)
    assert len(rows) == 5 and rows[0].swing >= rows[-1].swing


def test_every_appetite_limit_is_enforced(model):
    result = simulate(model, 5000, 5)
    appetite = appetite_check(model, result)
    assert appetite["within"] and {check["metric"] for check in appetite["checks"]} == {"eal", "p95"}
    tight = copy.deepcopy(model)
    eal_limit = next(limit for limit in tight.appetite.limits if limit.metric == "eal")
    eal_limit.max_pct_revenue = 0.001
    assert not appetite_check(tight, result)["within"]
