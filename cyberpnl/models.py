"""Validated model schemas and integrity checks for Cyber P&L."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal

import numpy as np
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator
from yaml.events import AliasEvent

from .distributions import lognormal_ci_mean, pert_mean, sample_lognormal_ci, sample_pert

MAX_MODEL_FILE_BYTES = 5 * 1024 * 1024


class NoAliasSafeLoader(yaml.SafeLoader):
    """Safe YAML loader that also rejects aliases to avoid amplification surprises."""

    def compose_node(self, parent, index):
        if self.check_event(AliasEvent):
            raise yaml.YAMLError("YAML aliases are not allowed in model files")
        return super().compose_node(parent, index)


class StrictModel(BaseModel):
    """Reject misspelled or undocumented model fields."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Range(StrictModel):
    """A calibrated estimate. Exactly one supported shape must be given."""

    min: float | None = None
    mode: float | None = None
    max: float | None = None
    p05: float | None = None
    p95: float | None = None
    value: float | None = None
    source: str = ""
    owner: str = ""

    @model_validator(mode="after")
    def _one_shape(self):
        values = [v for v in (self.min, self.mode, self.max, self.p05, self.p95, self.value) if v is not None]
        if any(not math.isfinite(v) for v in values):
            raise ValueError("range values must be finite")
        shapes = [
            self.value is not None,
            self.p05 is not None or self.p95 is not None,
            any(v is not None for v in (self.min, self.mode, self.max)),
        ]
        if sum(shapes) != 1:
            raise ValueError("Range needs exactly one of: value | p05+p95 | min+mode+max")
        if shapes[2]:
            if None in (self.min, self.mode, self.max):
                raise ValueError("PERT range needs min, mode and max")
            if not (self.min <= self.mode <= self.max):
                raise ValueError(
                    f"PERT range must satisfy min <= mode <= max ({self.min}, {self.mode}, {self.max})"
                )
        if shapes[1] and (self.p05 is None or self.p95 is None or self.p05 <= 0 or self.p05 > self.p95):
            raise ValueError("lognormal range needs 0 < p05 <= p95")
        return self

    @property
    def shape(self) -> str:
        return "fixed" if self.value is not None else "lognormal" if self.p05 is not None else "pert"

    def sample(self, rng: np.random.Generator, n: int) -> np.ndarray:
        if self.value is not None:
            return np.full(n, float(self.value))
        if self.p05 is not None:
            return sample_lognormal_ci(rng, self.p05, self.p95, n)
        return sample_pert(rng, self.min, self.mode, self.max, n)

    def mean(self) -> float:
        if self.value is not None:
            return float(self.value)
        if self.p05 is not None:
            return lognormal_ci_mean(self.p05, self.p95)
        return pert_mean(self.min, self.mode, self.max)

    def low(self) -> float:
        return self.value if self.value is not None else self.p05 if self.p05 is not None else self.min

    def high(self) -> float:
        return self.value if self.value is not None else self.p95 if self.p95 is not None else self.max

    def require_bounds(
        self, low: float | None = None, high: float | None = None, label: str = "range"
    ) -> None:
        if low is not None and self.low() < low:
            raise ValueError(f"{label} must be >= {low}")
        if high is not None and self.high() > high:
            raise ValueError(f"{label} must be <= {high}")

    def describe(self) -> str:
        if self.value is not None:
            return f"{self.value:,.4g}"
        if self.p05 is not None:
            return f"{self.p05:,.4g} - {self.p95:,.4g} (90% input interval)"
        return f"{self.min:,.4g} / {self.mode:,.4g} / {self.max:,.4g}"


class Service(StrictModel):
    id: str
    name: str = ""
    revenue_per_hour: float = Field(default=0.0, ge=0)
    criticality: str = "standard"
    owner: str = ""
    source: str = ""


class Business(StrictModel):
    organization: str
    fiscal_year: int = Field(ge=2000, le=2200)
    annual_revenue: float = Field(gt=0)
    ebitda: float | None = None
    employees: int | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    security_spend_annual: float = Field(default=0.0, ge=0)
    services: list[Service] = Field(default_factory=list)
    regimes: list[str] = Field(default_factory=list)
    owner: str = ""
    source: str = ""
    template: bool = True

    @model_validator(mode="after")
    def _unique_services(self):
        ids = [service.id for service in self.services]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate service ids")
        for value in (self.annual_revenue, self.ebitda, self.security_spend_annual):
            if value is not None and not math.isfinite(value):
                raise ValueError("business financial values must be finite")
        return self

    def service(self, sid: str) -> Service:
        for service in self.services:
            if service.id == sid:
                return service
        raise KeyError(f"unknown service '{sid}'")


ComponentKind = Literal["dollars", "offset", "downtime", "ransom", "per_record", "pct_revenue"]


class Component(StrictModel):
    """One line item of event loss. Offsets are explicit and event totals are floored at zero."""

    name: str
    kind: ComponentKind
    tags: list[str] = Field(default_factory=list)
    amount: Range | None = None
    hours: Range | None = None
    revenue_per_hour: float | None = Field(default=None, ge=0)
    demand: Range | None = None
    p_pay: Range | None = None
    records: Range | None = None
    cost_per_record: Range | None = None
    pct: Range | None = None

    @model_validator(mode="after")
    def _fields_for_kind(self):
        required = {
            "dollars": {"amount"},
            "offset": {"amount"},
            "downtime": {"hours"},
            "ransom": {"demand", "p_pay"},
            "per_record": {"records", "cost_per_record"},
            "pct_revenue": {"pct"},
        }[self.kind]
        range_fields = {"amount", "hours", "demand", "p_pay", "records", "cost_per_record", "pct"}
        populated = {field for field in range_fields if getattr(self, field) is not None}
        missing = required - populated
        if missing:
            raise ValueError(f"component '{self.name}' ({self.kind}) missing {sorted(missing)}")
        if populated - required:
            raise ValueError(
                f"component '{self.name}' ({self.kind}) has unused fields {sorted(populated - required)}"
            )
        if self.revenue_per_hour is not None and self.kind != "downtime":
            raise ValueError("revenue_per_hour is only valid for downtime components")
        if self.kind == "offset":
            self.amount.require_bounds(high=0, label=f"offset '{self.name}'")
        else:
            for field in required:
                getattr(self, field).require_bounds(low=0, label=f"{self.name}.{field}")
        if self.p_pay is not None:
            self.p_pay.require_bounds(0, 1, f"{self.name}.p_pay")
        if self.pct is not None:
            self.pct.require_bounds(0, 1, f"{self.name}.pct")
        return self


class Scenario(StrictModel):
    id: str
    name: str
    service: str
    threat: str
    owner: str = ""
    tags: list[str] = Field(default_factory=list)
    frequency: Range
    components: list[Component] = Field(min_length=1)
    unpriced: list[str] = Field(default_factory=list)
    notes: str = ""

    @model_validator(mode="after")
    def _valid_scenario(self):
        self.frequency.require_bounds(low=0, label=f"{self.id}.frequency")
        names = [component.name for component in self.components]
        if len(names) != len(set(names)):
            raise ValueError(f"scenario '{self.id}' has duplicate component names")
        return self


class KpiSpec(StrictModel):
    curve: Literal[
        "contain_before_exfil",
        "contain_before_encrypt",
        "credential_exposure_grade",
        "coverage",
        "restore_hours_ratio",
    ]
    key: str
    default: float | str | None = None
    applies: Literal["frequency", "magnitude"] = "magnitude"
    params: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _finite_params(self):
        for key, value in self.params.items():
            if not math.isfinite(value):
                raise ValueError(f"KPI parameter '{key}' must be finite")
        if isinstance(self.default, float) and not math.isfinite(self.default):
            raise ValueError("KPI default must be finite")
        if self.curve in {"contain_before_exfil", "contain_before_encrypt"}:
            if isinstance(self.default, (int, float)) and self.default < 0:
                raise ValueError("containment time default must be non-negative")
            if self.params.get("clock_minutes", 0) < 0:
                raise ValueError("clock_minutes must be non-negative")
            if self.params.get("width_minutes", 1) <= 0:
                raise ValueError("width_minutes must be positive")
            if not 0 <= self.params.get("residual", 0) <= 1:
                raise ValueError("residual must be between 0 and 1")
        if self.curve == "restore_hours_ratio":
            if isinstance(self.default, (int, float)) and self.default < 0:
                raise ValueError("restore-hours default must be non-negative")
            if self.params.get("baseline_hours", 1) <= 0:
                raise ValueError("baseline_hours must be positive")
            if not 0 <= self.params.get("floor", 0) <= 1:
                raise ValueError("restore floor must be between 0 and 1")
        if self.curve == "coverage":
            if isinstance(self.default, (int, float)) and not 0 <= self.default <= 100:
                raise ValueError("coverage default must be between 0 and 100")
            if not 0 <= self.params.get("max_reduction", 0.8) <= 1:
                raise ValueError("max_reduction must be between 0 and 1")
        if self.curve == "credential_exposure_grade":
            if isinstance(self.default, (int, float)) and not 0 <= self.default <= 100:
                raise ValueError("credential exposure default must be between 0 and 100")
            if isinstance(self.default, str) and self.default.upper() not in {"A", "B", "C", "D", "F"}:
                raise ValueError("credential exposure grade must be A, B, C, D or F")
        return self


class Effect(StrictModel):
    scenarios: list[str] = Field(default_factory=lambda: ["*"])
    frequency_multiplier: Range | None = None
    magnitude_multiplier: Range | None = None
    component_tags: list[str] = Field(default_factory=list)
    kpi: KpiSpec | None = None

    @model_validator(mode="after")
    def _valid_effect(self):
        if not any((self.frequency_multiplier, self.magnitude_multiplier, self.kpi)):
            raise ValueError("control effect must define a multiplier or KPI")
        for label, value in (
            ("frequency_multiplier", self.frequency_multiplier),
            ("magnitude_multiplier", self.magnitude_multiplier),
        ):
            if value is not None:
                value.require_bounds(0, 1, label)
        if not self.scenarios:
            raise ValueError("control effect needs at least one scenario selector")
        return self

    def applies_to(self, scenario: Scenario) -> bool:
        return any(
            selector == "*"
            or selector == scenario.id
            or (selector.startswith("#") and selector[1:] in scenario.tags)
            for selector in self.scenarios
        )


class Control(StrictModel):
    id: str
    name: str
    status: Literal["existing", "proposed"] = "existing"
    annual_cost: float = Field(default=0.0, ge=0)
    one_time_cost: float = Field(default=0.0, ge=0)
    owner: str = ""
    effects: list[Effect] = Field(min_length=1)
    depends_on: list[str] = Field(default_factory=list)
    replaces: list[str] = Field(default_factory=list)
    source: str = ""
    cost_source: str = ""
    notes: str = ""

    @model_validator(mode="after")
    def _finite_costs(self):
        if not math.isfinite(self.annual_cost) or not math.isfinite(self.one_time_cost):
            raise ValueError("control costs must be finite")
        return self


Metric = Literal["eal", "p90", "p95", "p99"]


class AppetiteLimit(StrictModel):
    metric: Metric
    max_pct_revenue: float | None = Field(default=None, gt=0)
    max_dollars: float | None = Field(default=None, gt=0)
    owner: str = ""
    source: str = ""

    @model_validator(mode="after")
    def _one_limit(self):
        if (self.max_pct_revenue is None) == (self.max_dollars is None):
            raise ValueError("appetite limit needs exactly one of max_pct_revenue | max_dollars")
        return self

    def threshold(self, revenue: float) -> float:
        return self.max_dollars if self.max_dollars is not None else self.max_pct_revenue * revenue


class Appetite(StrictModel):
    statement: str = ""
    approved_by: list[str] = Field(default_factory=list)
    limits: list[AppetiteLimit] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_metrics(self):
        metrics = [limit.metric for limit in self.limits]
        if len(metrics) != len(set(metrics)):
            raise ValueError("duplicate risk-appetite metrics")
        return self


class Attestation(StrictModel):
    """A named assertion over a digest, not a cryptographic identity signature."""

    role: str
    name: str
    date: date
    digest: str
    method: Literal["digest_attestation"] = "digest_attestation"

    @model_validator(mode="after")
    def _digest_format(self):
        if not re.fullmatch(r"[0-9a-f]{64}", self.digest):
            raise ValueError("attestation digest must be a lowercase SHA-256 hex value")
        return self


class Register(StrictModel):
    required_roles: list[str] = Field(default_factory=lambda: ["CFO", "CISO"], min_length=1)
    attestations: list[Attestation] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_roles(self):
        if len(self.required_roles) != len(set(self.required_roles)):
            raise ValueError("required attestation roles must be unique")
        roles = [attestation.role for attestation in self.attestations]
        if len(roles) != len(set(roles)):
            raise ValueError("only one current attestation is allowed per role")
        return self


KpiStatus = Literal["measured", "synthetic_template", "manual_estimate"]


class KpiMeasurement(StrictModel):
    value: float | str
    source: str
    owner: str
    measured_at: date
    status: KpiStatus = "measured"

    @model_validator(mode="after")
    def _finite_value(self):
        if isinstance(self.value, float) and not math.isfinite(self.value):
            raise ValueError("KPI value must be finite")
        return self


class Model(StrictModel):
    business: Business
    scenarios: list[Scenario]
    controls: list[Control] = Field(default_factory=list)
    appetite: Appetite | None = None
    attestations: Register = Field(default_factory=Register)
    min_multiplier: float = Field(default=0.05, gt=0, le=1)
    min_multiplier_source: str = ""
    min_multiplier_owner: str = ""
    kpis: dict[str, KpiMeasurement] = Field(default_factory=dict)
    sources: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _refs(self):
        scenario_ids = [scenario.id for scenario in self.scenarios]
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("duplicate scenario ids")
        for scenario in self.scenarios:
            self.business.service(scenario.service)

        control_ids = [control.id for control in self.controls]
        if len(control_ids) != len(set(control_ids)):
            raise ValueError("duplicate control ids")
        known_controls = set(control_ids)
        known_existing = {control.id for control in self.controls if control.status == "existing"}
        dependency_map = {control.id: control.depends_on for control in self.controls}
        for control in self.controls:
            for dependency in control.depends_on:
                if dependency not in known_controls:
                    raise ValueError(f"control '{control.id}' depends on unknown control '{dependency}'")
                if dependency == control.id:
                    raise ValueError(f"control '{control.id}' cannot depend on itself")
            for replacement in control.replaces:
                if replacement not in known_existing:
                    raise ValueError(
                        f"control '{control.id}' replaces unknown/non-existing control '{replacement}'"
                    )
                if control.status != "proposed":
                    raise ValueError(f"existing control '{control.id}' cannot declare replacements")
            if control.status == "existing" and any(
                next(item for item in self.controls if item.id == dependency).status == "proposed"
                for dependency in control.depends_on
            ):
                raise ValueError(f"existing control '{control.id}' cannot depend on a proposed control")

        def visit(control_id: str, active: set[str], done: set[str]) -> None:
            if control_id in active:
                raise ValueError(f"control dependency cycle includes '{control_id}'")
            if control_id in done:
                return
            active.add(control_id)
            for dependency in dependency_map[control_id]:
                visit(dependency, active, done)
            active.remove(control_id)
            done.add(control_id)

        done: set[str] = set()
        for control_id in control_ids:
            visit(control_id, set(), done)

        tags = {tag for scenario in self.scenarios for tag in scenario.tags}
        scenario_id_set = set(scenario_ids)
        for control in self.controls:
            for effect in control.effects:
                for selector in effect.scenarios:
                    if selector == "*":
                        continue
                    if selector.startswith("#"):
                        if selector[1:] not in tags:
                            raise ValueError(f"control '{control.id}' uses unknown scenario tag '{selector}'")
                    elif selector not in scenario_id_set:
                        raise ValueError(f"control '{control.id}' uses unknown scenario '{selector}'")
                selected = [scenario for scenario in self.scenarios if effect.applies_to(scenario)]
                if effect.component_tags and not any(
                    set(effect.component_tags) & set(component.tags)
                    for scenario in selected
                    for component in scenario.components
                ):
                    raise ValueError(
                        f"control '{control.id}' component tags match no selected component: {effect.component_tags}"
                    )

                if effect.kpi and effect.kpi.key in self.kpis:
                    measurement = self.kpis[effect.kpi.key]
                    value = measurement.value
                    if effect.kpi.curve in {
                        "contain_before_exfil",
                        "contain_before_encrypt",
                        "restore_hours_ratio",
                    } and (not isinstance(value, (int, float)) or value < 0):
                        raise ValueError(f"KPI '{effect.kpi.key}' must be a non-negative number")
                    if effect.kpi.curve in {"coverage", "credential_exposure_grade"}:
                        valid_grade = isinstance(value, str) and value.upper() in {"A", "B", "C", "D", "F"}
                        valid_score = isinstance(value, (int, float)) and 0 <= value <= 100
                        if not (valid_grade or valid_score):
                            raise ValueError(f"KPI '{effect.kpi.key}' must be a 0-100 score or valid grade")

        referenced_sources = {row["source"] for row in self.assumptions() if row["source"]}
        referenced_sources.update(
            source
            for source in (
                self.business.source,
                self.min_multiplier_source,
                *(service.source for service in self.business.services),
                *(control.source for control in self.controls),
                *(control.cost_source for control in self.controls),
            )
            if source
        )
        unknown_sources = sorted(referenced_sources - set(self.sources))
        if unknown_sources:
            raise ValueError(f"unknown source ids: {', '.join(unknown_sources)}")
        empty_sources = sorted(source_id for source_id, text in self.sources.items() if not text.strip())
        if empty_sources:
            raise ValueError(f"source catalog entries are blank: {', '.join(empty_sources)}")
        return self

    def with_dependents(self, ids: set[str]) -> set[str]:
        out = set(ids)
        changed = True
        while changed:
            changed = False
            for control in self.controls:
                if control.id not in out and any(dependency in out for dependency in control.depends_on):
                    out.add(control.id)
                    changed = True
        return out

    def replacement_exclusions(self, proposed_ids: set[str]) -> set[str]:
        replaced = {
            replacement
            for control in self.controls
            if control.id in proposed_ids
            for replacement in control.replaces
        }
        return self.with_dependents(replaced)

    def with_dependencies(self, ids: set[str]) -> set[str]:
        """Include all transitive prerequisites for selected controls."""
        out = set(ids)
        changed = True
        while changed:
            changed = False
            for control in self.controls:
                if control.id in out:
                    for dependency in control.depends_on:
                        if dependency not in out:
                            out.add(dependency)
                            changed = True
        return out

    def existing_controls(self) -> list[Control]:
        return [control for control in self.controls if control.status == "existing"]

    def proposed_controls(self) -> list[Control]:
        return [control for control in self.controls if control.status == "proposed"]

    def assumptions(self) -> list[dict[str, Any]]:
        """Material model inputs with path, value, source and accountable owner."""

        out: list[dict[str, Any]] = []

        def add_range(path: str, value: Range | None, default_owner: str = "") -> None:
            if value is None:
                return
            out.append(
                {
                    "path": path,
                    "shape": value.shape,
                    "estimate": value.describe(),
                    "mean": round(value.mean(), 6),
                    "source": value.source,
                    "owner": value.owner or default_owner,
                }
            )

        def add_fixed(path: str, value: Any, source: str, owner: str) -> None:
            out.append(
                {
                    "path": path,
                    "shape": "fixed",
                    "estimate": str(value),
                    "mean": value if isinstance(value, (int, float)) else "",
                    "source": source,
                    "owner": owner,
                }
            )

        business = self.business
        for field in ("annual_revenue", "security_spend_annual", "ebitda", "employees"):
            value = getattr(business, field)
            if value is not None:
                add_fixed(f"business.{field}", value, business.source, business.owner)
        for service in business.services:
            add_fixed(
                f"business.service.{service.id}.revenue_per_hour",
                service.revenue_per_hour,
                service.source or business.source,
                service.owner or business.owner,
            )
        for scenario in self.scenarios:
            add_range(f"scenario.{scenario.id}.frequency", scenario.frequency, scenario.owner)
            for component in scenario.components:
                if component.revenue_per_hour is not None:
                    add_fixed(
                        f"scenario.{scenario.id}.{component.name}.revenue_per_hour",
                        component.revenue_per_hour,
                        scenario.frequency.source,
                        scenario.owner,
                    )
                for field in ("amount", "hours", "demand", "p_pay", "records", "cost_per_record", "pct"):
                    add_range(
                        f"scenario.{scenario.id}.{component.name}.{field}",
                        getattr(component, field),
                        scenario.owner,
                    )
        for control in self.controls:
            cost_source = control.cost_source or control.source
            add_fixed(f"control.{control.id}.annual_cost", control.annual_cost, cost_source, control.owner)
            add_fixed(
                f"control.{control.id}.one_time_cost", control.one_time_cost, cost_source, control.owner
            )
            for index, effect in enumerate(control.effects):
                add_range(
                    f"control.{control.id}.effect[{index}].frequency_multiplier",
                    effect.frequency_multiplier,
                    control.owner,
                )
                if effect.kpi:
                    if effect.kpi.default is not None:
                        add_fixed(
                            f"control.{control.id}.effect[{index}].kpi.default",
                            effect.kpi.default,
                            control.source,
                            control.owner,
                        )
                    for key, value in effect.kpi.params.items():
                        add_fixed(
                            f"control.{control.id}.effect[{index}].kpi.params.{key}",
                            value,
                            control.source,
                            control.owner,
                        )
                add_range(
                    f"control.{control.id}.effect[{index}].magnitude_multiplier",
                    effect.magnitude_multiplier,
                    control.owner,
                )
        if self.appetite:
            for limit in self.appetite.limits:
                value = limit.max_dollars if limit.max_dollars is not None else limit.max_pct_revenue
                add_fixed(f"appetite.{limit.metric}", value, limit.source, limit.owner)
        add_fixed(
            "model.min_multiplier", self.min_multiplier, self.min_multiplier_source, self.min_multiplier_owner
        )
        for key, measurement in self.kpis.items():
            add_fixed(f"kpi.{key}", measurement.value, measurement.source, measurement.owner)
        return out

    def canonical_body(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"attestations"})

    def digest(self) -> str:
        body = json.dumps(self.canonical_body(), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(body).hexdigest()

    def verify_attestations(self, today: date | None = None) -> tuple[bool, list[str]]:
        """Verify digest binding and required roles; this does not authenticate identity."""

        today = today or datetime.now(timezone.utc).date()
        digest = self.digest()
        problems: list[str] = []
        current_roles: set[str] = set()
        for attestation in self.attestations.attestations:
            if attestation.date > today:
                problems.append(f"attestation by {attestation.role} ({attestation.name}) is future-dated")
            if attestation.digest != digest:
                problems.append(
                    f"attestation by {attestation.role} ({attestation.name}) is stale or for different assumptions"
                )
            elif attestation.date <= today:
                current_roles.add(attestation.role)
        for role in self.attestations.required_roles:
            if role not in current_roles:
                problems.append(f"missing current digest attestation from required role: {role}")
        return not problems, problems

    def verify(self) -> tuple[bool, list[str]]:
        """Backward-compatible alias for digest-attestation verification."""

        return self.verify_attestations()

    def operational_problems(self) -> list[str]:
        problems: list[str] = []
        if self.business.template:
            problems.append("business.template is true; this is an illustrative model")
        ok, attestation_problems = self.verify_attestations()
        if not ok:
            problems.extend(attestation_problems)
        rows = self.assumptions()
        missing_sources = [row["path"] for row in rows if not row["source"]]
        missing_owners = [row["path"] for row in rows if not row["owner"]]
        if missing_sources:
            problems.append(f"{len(missing_sources)} material inputs have no source")
        if missing_owners:
            problems.append(f"{len(missing_owners)} material inputs have no owner")
        template_owners = [row["path"] for row in rows if "template" in row["owner"].lower()]
        if template_owners:
            problems.append(f"{len(template_owners)} material inputs still use template owners")
        placeholders = [
            source_id
            for source_id, text in self.sources.items()
            if "[PLACEHOLDER]" in text.upper() or "[TEMPLATE]" in text.upper()
        ]
        if placeholders:
            problems.append("placeholder source records remain: " + ", ".join(sorted(placeholders)))
        nonmeasured = [key for key, value in self.kpis.items() if value.status != "measured"]
        if nonmeasured:
            problems.append("KPI values are not measured evidence: " + ", ".join(sorted(nonmeasured)))
        future_kpis = [
            key for key, value in self.kpis.items() if value.measured_at > datetime.now(timezone.utc).date()
        ]
        if future_kpis:
            problems.append("KPI measurements are future-dated: " + ", ".join(sorted(future_kpis)))
        if self.appetite and not self.appetite.approved_by:
            problems.append("risk appetite has no recorded approval")
        return problems


FILES = {
    "business": "business.yaml",
    "scenarios": "scenarios.yaml",
    "controls": "controls.yaml",
    "appetite": "appetite.yaml",
    "register": "register.yaml",
    "kpis": "kpis.yaml",
    "sources": "sources.yaml",
}


def load_model(model_dir: Path) -> Model:
    model_dir = Path(model_dir)

    def read(name: str, required: bool = True):
        path = model_dir / FILES[name]
        if not path.exists():
            if required:
                raise FileNotFoundError(path)
            return None
        if path.stat().st_size > MAX_MODEL_FILE_BYTES:
            raise ValueError(f"model file exceeds {MAX_MODEL_FILE_BYTES} bytes: {path}")
        with open(path, encoding="utf-8") as stream:
            return yaml.load(stream, Loader=NoAliasSafeLoader)

    business = read("business")
    scenarios = read("scenarios")["scenarios"]
    controls = (read("controls", False) or {}).get("controls", [])
    appetite = read("appetite", False)
    register = read("register", False) or {}
    kpis = (read("kpis", False) or {}).get("kpis", {})
    source_data = read("sources", False) or {}
    sources = source_data.get("sources", {})
    settings = source_data.get("model_settings", {})
    return Model(
        business=business,
        scenarios=scenarios,
        controls=controls,
        appetite=appetite,
        attestations=register,
        kpis=kpis,
        sources=sources,
        **settings,
    )
