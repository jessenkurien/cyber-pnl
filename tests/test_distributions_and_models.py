import copy
import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest
import yaml

from cyberpnl.distributions import lognormal_ci_mean, pert_mean, sample_lognormal_ci, sample_pert
from cyberpnl.models import Attestation, Business, Component, Model, Range, load_model
from cyberpnl.report import money

ROOT = Path(__file__).resolve().parent.parent


def test_release_version_is_consistent():
    from cyberpnl import __version__

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    project_version = re.search(r'^version = "([^"]+)"$', pyproject, re.MULTILINE)
    assert project_version is not None
    citation = yaml.safe_load((ROOT / "CITATION.cff").read_text(encoding="utf-8"))
    assert project_version.group(1) == __version__ == citation["version"]


def test_pert_bounds_and_mean():
    rng = np.random.default_rng(1)
    values = sample_pert(rng, 10, 30, 100, 200_000)
    assert values.min() >= 10 and values.max() <= 100
    assert abs(values.mean() - pert_mean(10, 30, 100)) < 0.5


def test_lognormal_input_interval_hits_quantiles():
    rng = np.random.default_rng(2)
    values = sample_lognormal_ci(rng, 100_000, 2_000_000, 400_000)
    p05, p95 = np.percentile(values, [5, 95])
    assert abs(p05 / 100_000 - 1) < 0.05
    assert abs(p95 / 2_000_000 - 1) < 0.05
    assert abs(values.mean() / lognormal_ci_mean(100_000, 2_000_000) - 1) < 0.03


def test_range_rejects_ambiguous_invalid_and_nonfinite_values():
    with pytest.raises(ValueError):
        Range(min=1, mode=2, max=3, value=5)
    with pytest.raises(ValueError):
        Range(min=5, mode=2, max=3)
    with pytest.raises(ValueError):
        Range(p05=10, p95=5)
    with pytest.raises(ValueError):
        Range(value=float("nan"))
    with pytest.raises(ValueError):
        Range(value=1, misspelled_source="x")
    assert Range(value=3).shape == "fixed"
    assert Range(p05=1, p95=2).shape == "lognormal"
    sampled = Range(min=1, mode=1, max=1).sample(np.random.default_rng(0), 5)
    assert sampled.tolist() == [1.0] * 5


def test_currency_codes_are_validated_and_money_is_currency_aware():
    assert money(1_250_000, "USD") == "$1.25M"
    assert money(1_250_000, "EUR") == "€1.25M"
    assert money(1_250_000, "AED") == "AED 1.25M"
    assert money(1_250_000, "ZAR") == "ZAR 1.25M"
    with pytest.raises(ValueError, match="currency"):
        Business(organization="test", fiscal_year=2026, annual_revenue=1, currency="usd")


def test_component_signs_and_probability_bounds_are_enforced():
    with pytest.raises(ValueError):
        Component(name="loss", kind="dollars", amount=Range(value=-1))
    with pytest.raises(ValueError):
        Component(name="offset", kind="offset", amount=Range(value=1))
    with pytest.raises(ValueError):
        Component(
            name="ransom",
            kind="ransom",
            demand=Range(value=1),
            p_pay=Range(value=1.1),
        )
    Component(name="offset", kind="offset", amount=Range(min=-10, mode=-2, max=0))


def test_sample_model_loads_and_every_material_input_has_source_and_owner(model):
    rows = model.assumptions()
    assert len(rows) > 100
    assert all(row["source"] for row in rows), [row["path"] for row in rows if not row["source"]]
    assert all(row["owner"] for row in rows), [row["path"] for row in rows if not row["owner"]]
    assert model.business.template
    assert not model.verify_attestations()[0]
    assert any("illustrative model" in problem for problem in model.operational_problems())


def test_digest_attestation_verifies_and_detects_edits(model):
    attested = copy.deepcopy(model)
    digest = attested.digest()
    attested.attestations.attestations = [
        Attestation(
            role="CFO", name="Finance Reviewer", date=datetime.now(timezone.utc).date(), digest=digest
        ),
        Attestation(
            role="CISO", name="Security Reviewer", date=datetime.now(timezone.utc).date(), digest=digest
        ),
    ]
    assert attested.verify_attestations()[0]
    attested.scenarios[0].frequency = Range(
        min=0.5,
        mode=0.9,
        max=1.5,
        source="iris2025",
        owner="Threat Intel Lead",
    )
    ok, problems = attested.verify_attestations()
    assert not ok and any("stale" in problem for problem in problems)


def test_future_attestation_is_rejected(model):
    changed = copy.deepcopy(model)
    changed.attestations.required_roles = ["CFO"]
    changed.attestations.attestations = [
        Attestation(
            role="CFO",
            name="Reviewer",
            date=datetime.now(timezone.utc).date() + timedelta(days=1),
            digest=changed.digest(),
        )
    ]
    assert not changed.verify_attestations()[0]


def test_kpi_change_changes_digest(model):
    changed = copy.deepcopy(model)
    measurement = changed.kpis["time_to_contain_minutes"].model_copy(update={"value": 90.0})
    changed.kpis["time_to_contain_minutes"] = measurement
    assert changed.digest() != model.digest()


def test_dependency_and_replacement_closures(model):
    assert "containment-72md" in model.with_dependents({"edr-fleet"})
    assert model.with_dependents({"containment-72md"}) == {"containment-72md"}
    assert model.replacement_exclusions({"prop-phishing-resistant-mfa"}) == {"mfa-workforce"}


def test_bad_control_references_and_cycles_are_rejected(model):
    data = model.model_dump(mode="json")
    data["controls"][0]["depends_on"] = ["nope"]
    with pytest.raises(ValueError, match="unknown control"):
        Model.model_validate(data)

    data = model.model_dump(mode="json")
    data["controls"][0]["depends_on"] = [data["controls"][1]["id"]]
    data["controls"][1]["depends_on"] = [data["controls"][0]["id"]]
    with pytest.raises(ValueError, match="cycle"):
        Model.model_validate(data)

    data = model.model_dump(mode="json")
    data["controls"][0]["effects"][0]["scenarios"] = ["#misspelled"]
    with pytest.raises(ValueError, match="unknown scenario tag"):
        Model.model_validate(data)


def test_unknown_source_reference_is_rejected(model):
    data = model.model_dump(mode="json")
    data["scenarios"][0]["frequency"]["source"] = "not-in-catalog"
    with pytest.raises(ValueError, match="unknown source"):
        Model.model_validate(data)


def test_editable_and_bundled_default_models_match():
    editable = {path.name: path.read_bytes() for path in (ROOT / "model").glob("*.yaml")}
    bundled = {path.name: path.read_bytes() for path in (ROOT / "cyberpnl" / "default_model").glob("*.yaml")}
    assert editable == bundled


def test_empty_required_roles_cannot_bypass_attestation(model):
    data = model.model_dump(mode="json")
    data["attestations"]["required_roles"] = []
    with pytest.raises(ValueError, match="at least 1 item"):
        Model.model_validate(data)


def test_yaml_aliases_are_rejected(tmp_path):
    shutil.copytree(ROOT / "model", tmp_path / "model")
    path = tmp_path / "model" / "business.yaml"
    path.write_text(
        path.read_text(encoding="utf-8") + "\nalias_one: &value 1\nalias_two: *value\n", encoding="utf-8"
    )
    with pytest.raises(yaml.YAMLError, match="aliases are not allowed"):
        load_model(tmp_path / "model")
