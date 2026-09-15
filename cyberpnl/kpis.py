"""KPI curves: turn a *measured* operational number into a model multiplier.

In an operational model, control value can be driven by evidence the security program produces and
updates when that evidence changes. The bundled public model clearly labels synthetic inputs.

Each curve takes the measured value and optional parameters and returns a multiplier
(< 1 reduces risk). Curves are deliberately simple, documented, and monotonic so a CFO can
follow them; docs/methodology.md explains each with its rationale and its limits.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

Curve = Callable[[float, dict[str, Any]], float]
MAX_EVIDENCE_FILE_BYTES = 5 * 1024 * 1024


def _read_json_object(path: Path) -> dict[str, Any]:
    if path.stat().st_size > MAX_EVIDENCE_FILE_BYTES:
        raise ValueError(f"evidence file exceeds the {MAX_EVIDENCE_FILE_BYTES // (1024 * 1024)} MB limit")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError("evidence JSON must contain an object")
    return data


def contain_before_exfil(ttc_minutes: float, p: dict[str, Any]) -> float:
    """P(attacker completes exfiltration before containment), as a magnitude multiplier for
    exfil-driven loss components. Logistic around the attacker clock (default 72 min):
    with the default residual: at 28 → ~0.17; at 72 → ~0.58; at 120 → ~0.98. `residual` is the share of exfil-driven
    cost you still pay when contained in time (forensics, notification of partial access)."""
    clock = float(p.get("clock_minutes", 72))
    width = float(p.get("width_minutes", 12))
    residual = float(p.get("residual", 0.15))
    prob = 1.0 / (1.0 + math.exp(-(ttc_minutes - clock) / width))
    return max(0.0, min(1.0, residual + (1.0 - residual) * prob))


def contain_before_encrypt(ttc_minutes: float, p: dict[str, Any]) -> float:
    """Same shape for encryption/impact-driven components; default clock 95 min (encryption
    typically follows exfiltration)."""
    q = dict(p)
    q.setdefault("clock_minutes", 95)
    q.setdefault("residual", 0.25)
    return contain_before_exfil(ttc_minutes, q)


_GRADE = {"A": 0.5, "B": 0.65, "C": 0.8, "D": 1.0, "F": 1.25}


def credential_exposure_grade(score_or_grade: float | str, p: dict[str, Any]) -> float:
    """Frequency multiplier for credential-driven scenarios from the endpoint exposure grade
    (wormprint). The transparent sample mapping defines grade D as baseline 1.0."""
    if isinstance(score_or_grade, str):
        return _GRADE.get(score_or_grade.upper(), 1.0)
    s = float(score_or_grade)
    g = "A" if s < 15 else "B" if s < 35 else "C" if s < 60 else "D" if s < 80 else "F"
    return _GRADE[g]


def coverage(pct: float, p: dict[str, Any]) -> float:
    """Linear frequency multiplier from control coverage (0–100%): 1 - pct/100 * max_reduction."""
    max_red = float(p.get("max_reduction", 0.8))
    return 1.0 - max(0.0, min(100.0, pct)) / 100.0 * max_red


def restore_hours_ratio(measured_hours: float, p: dict[str, Any]) -> float:
    """Magnitude multiplier for downtime components: proven restore time vs the assumed
    baseline outage (default 72 h). Capped so a great drill can't claim zero downtime."""
    baseline = float(p.get("baseline_hours", 72))
    floor = float(p.get("floor", 0.1))
    return max(floor, min(1.0, measured_hours / baseline))


CURVES: dict[str, Curve] = {
    "contain_before_exfil": contain_before_exfil,
    "contain_before_encrypt": contain_before_encrypt,
    "credential_exposure_grade": credential_exposure_grade,
    "coverage": coverage,
    "restore_hours_ratio": restore_hours_ratio,
}


def evaluate(kpi_spec: Any, kpis: dict[str, Any]) -> tuple[float, str]:
    """Resolve a control effect's kpi block to a multiplier. Returns (multiplier, explanation)."""
    get = (
        kpi_spec.get
        if isinstance(kpi_spec, dict)
        else lambda key, default=None: getattr(kpi_spec, key, default)
    )
    curve_name = get("curve", "")
    curve = CURVES.get(curve_name)
    if curve is None:
        raise KeyError(f"unknown kpi curve '{curve_name}'; known: {', '.join(CURVES)}")
    key = get("key")
    if key in kpis:
        measurement = kpis[key]
        if hasattr(measurement, "value"):
            value = measurement.value
            origin = f"{measurement.status} {key}={value} ({measurement.measured_at})"
        else:
            value, origin = measurement, f"untyped {key}={measurement}"
    elif get("default") is not None:
        value = get("default")
        origin = f"DEFAULT {key}={value} (no measurement supplied)"
    else:
        raise KeyError(f"kpi '{key}' not measured and no default given")
    mult = curve(value, get("params", {}))
    return float(mult), f"{curve_name}({origin}) -> x{mult:.3f}"


# ---------------------------------------------------------------- importers
def import_72md(path: Path) -> dict[str, dict[str, Any]]:
    """Read one or more 72md rehearsal JSON files (out/*.json). Uses the worst-case contain time
    across scenarios that expected containment, which is the number a board should plan on."""
    paths = [path] if Path(path).is_file() else sorted(Path(path).glob("*.json"))
    worst = None
    for p in paths:
        try:
            d = _read_json_object(Path(p))
        except (OSError, TypeError, ValueError):
            continue
        if d.get("expected") == "contain" and d.get("time_to_contain_minutes") is not None:
            worst = max(worst or 0, float(d["time_to_contain_minutes"]))
    if worst is None:
        raise ValueError(f"no valid 72md containment result found at {path}")
    return {
        "time_to_contain_minutes": {
            "value": worst,
            "source": "72md-rehearsal",
            "owner": "IR Lead",
            "measured_at": datetime.now(timezone.utc).date().isoformat(),
            "status": "measured",
        }
    }


def import_wormprint(path: Path) -> dict[str, dict[str, Any]]:
    """Read a wormprint report.json → exposure score (0–100)."""
    d = _read_json_object(Path(path))
    if "exposure_score" not in d:
        raise ValueError("wormprint report has no exposure_score")
    value = float(d["exposure_score"])
    if not math.isfinite(value) or not 0 <= value <= 100:
        raise ValueError("wormprint exposure_score must be between 0 and 100")
    return {
        "credential_exposure_score": {
            "value": value,
            "source": "wormprint-report",
            "owner": "CISO",
            "measured_at": datetime.now(timezone.utc).date().isoformat(),
            "status": "measured",
        }
    }
