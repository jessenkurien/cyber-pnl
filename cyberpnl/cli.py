"""`cyberpnl` command-line interface."""

from __future__ import annotations

import io
import json
import math
import sys
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path

import click
import yaml

from . import __version__
from .engine import (
    MAX_SEED,
    MAX_SIMULATED_YEARS,
    appetite_check,
    control_values,
    investment_cases,
    sensitivity,
    simulate,
)
from .kpis import CURVES, import_72md, import_wormprint
from .models import (
    MAX_MODEL_FILE_BYTES,
    Attestation,
    KpiMeasurement,
    Model,
    NoAliasSafeLoader,
    load_model,
)
from .report import money, statement_data, statement_html, statement_markdown

DEFAULT_MODEL = Path(str(files("cyberpnl").joinpath("default_model")))
YEARS = click.IntRange(min=1, max=MAX_SIMULATED_YEARS)
SEED = click.IntRange(min=0, max=MAX_SEED)


def _load(model_dir: Path) -> Model:
    try:
        return load_model(model_dir)
    except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError) as e:
        msg = [line.strip() for line in str(e).splitlines() if line.strip()]
        click.echo(f"model invalid ({model_dir}): " + " | ".join(msg)[:500], err=True)
        sys.exit(1)


@click.group()
@click.version_option(__version__, prog_name="cyberpnl")
def main() -> None:
    """Cyber P&L - auditable cyber-risk decision support in financial terms."""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper) and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


@main.command()
@click.option(
    "--model", "model_dir", type=click.Path(path_type=Path), default=DEFAULT_MODEL, show_default=True
)
@click.option("--operational", is_flag=True, help="Also enforce the organization-ready publication gates.")
def validate(model_dir, operational):
    """Validate schema, references, evidence fields and optional publication readiness."""
    model = _load(model_dir)
    rows = model.assumptions()
    problems = []
    if any(not row["source"] for row in rows):
        problems.append("one or more material inputs have no source")
    if any(not row["owner"] for row in rows):
        problems.append("one or more material inputs have no owner")
    if operational:
        problems.extend(model.operational_problems())
    if problems:
        for problem in dict.fromkeys(problems):
            click.echo(f"  ! {problem}", err=True)
        raise click.exceptions.Exit(4 if operational else 1)
    state = "illustrative template" if model.business.template else "operational model"
    click.echo(f"  VALID {state} | {len(rows)} material inputs | digest {model.digest()[:16]}...")


@main.command()
@click.option(
    "--model", "model_dir", type=click.Path(path_type=Path), default=DEFAULT_MODEL, show_default=True
)
@click.option("--years", "n", type=YEARS, default=20000, show_default=True, help="Simulated years.")
@click.option("--seed", type=SEED, default=7, show_default=True)
@click.option("--out", "out_dir", type=click.Path(path_type=Path), default=Path("out"), show_default=True)
@click.option("--no-sensitivity", is_flag=True, help="Skip the tornado analysis (faster).")
@click.option("--fail-on-appetite", is_flag=True, help="Exit 2 if the risk appetite is breached (CI gate).")
@click.option(
    "--require-attested",
    "--require-signed",
    "require_attested",
    is_flag=True,
    help="Exit 3 unless every required role attests to the current digest.",
)
@click.option("--require-operational", is_flag=True, help="Exit 4 unless all publication gates pass.")
def statement(
    model_dir, n, seed, out_dir, no_sensitivity, fail_on_appetite, require_attested, require_operational
):
    """Produce the board statement: HTML, Markdown and JSON."""
    m = _load(model_dir)
    cash = lambda value: money(value, m.business.currency)
    run = simulate(m, n, seed)
    cvs = control_values(m, n, seed)
    ics = investment_cases(m, n, seed)
    sens = [] if no_sensitivity else sensitivity(m, min(n, 8000), seed)
    app = appetite_check(m, run)
    d = statement_data(m, run, cvs, ics, sens, app)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "statement.html").write_text(statement_html(m, run, d, cvs, ics, sens), encoding="utf-8")
    (out_dir / "statement.md").write_text(statement_markdown(d), encoding="utf-8")
    (out_dir / "statement.json").write_text(json.dumps(d, indent=2, default=str), encoding="utf-8")

    rev = m.business.annual_revenue
    click.echo("")
    click.echo(
        f"  Cyber P&L | {m.business.organization} | FY{m.business.fiscal_year} | {n:,} simulated years"
    )
    click.echo("  " + "-" * 78)
    click.echo(f"  Expected annual loss   {cash(run.eal):>10}   ({run.eal / rev:.2%} of revenue)")
    click.echo(
        f"  Bad year (p95)         {cash(run.pct(95)):>10}   ({run.pct(95) / rev:.2%} of revenue)     p99 {cash(run.pct(99))}"
    )
    click.echo(
        f"  Security spend         {cash(m.business.security_spend_annual):>10}   ({(m.business.security_spend_annual / run.eal if run.eal else 0):.1f}× expected loss)"
    )
    if app:
        for check in app["checks"]:
            click.echo(
                f"  Risk appetite ({check['metric']})    "
                f"{'WITHIN' if check['within'] else 'BREACHED':>10}   "
                f"{cash(check['value'])} vs limit {cash(check['limit'])}"
            )
    ok, problems = m.verify()
    state = "TEMPLATE" if m.business.template else "ATTESTED" if ok else "UNATTESTED"
    click.echo(f"  Assumptions            {state:>10}   " + ("" if ok else problems[0]))
    click.echo("")
    click.echo("  Top loss drivers")
    for s in d["scenarios"][:5]:
        click.echo(f"    {cash(s['eal']):>9}  {s['share']:5.0%}  {s['name']}")
    click.echo("  Existing controls, by loss avoided")
    for c in d["control_values"][:5]:
        ratio = f"{c['benefit_cost_ratio']:.1f}x" if c["benefit_cost_ratio"] is not None else "-"
        click.echo(f"    {cash(c['avoided_eal']):>9}  {ratio:>6}  {c['name']}")
    click.echo("  Proposed investments, by benefit-cost ratio")
    for c in d["investments"][:5]:
        click.echo(
            f"    {cash(c['avoided_eal']):>9}  {c['benefit_cost_ratio']:.1f}x  "
            f"{c['name']}  (cost {cash(c['annualized_cost'])}/yr)"
        )
    click.echo(
        f"\n  statement -> {out_dir / 'statement.html'} | "
        f"{out_dir / 'statement.md'} | {out_dir / 'statement.json'}\n"
    )
    if require_attested and not ok:
        sys.exit(3)
    if fail_on_appetite and app and not app["within"]:
        sys.exit(2)
    if require_operational:
        operational = m.operational_problems()
        if operational:
            for problem in operational:
                click.echo(f"  publication gate: {problem}", err=True)
            sys.exit(4)


@main.command()
@click.option(
    "--model", "model_dir", type=click.Path(path_type=Path), default=DEFAULT_MODEL, show_default=True
)
@click.option("--years", "n", type=YEARS, default=20000, show_default=True)
@click.option("--seed", type=SEED, default=7, show_default=True)
def invest(model_dir, n, seed):
    """Rank proposed investments by expected loss avoided per unit of spend."""
    m = _load(model_dir)
    cash = lambda value: money(value, m.business.currency)
    for c in investment_cases(m, n, seed):
        pb = f"{c.payback_months:.0f} mo" if c.payback_months is not None else "-"
        click.echo(
            f"  {(c.benefit_cost_ratio or 0):5.1f}x  avoided {cash(c.avoided):>9}/yr  "
            f"cost {cash(c.annualized_cost):>8}/yr  payback {pb:>6}  {c.control.name}"
        )


@main.command()
@click.argument("scenario_id")
@click.option(
    "--model", "model_dir", type=click.Path(path_type=Path), default=DEFAULT_MODEL, show_default=True
)
@click.option("--years", "n", type=YEARS, default=20000, show_default=True)
@click.option("--seed", type=SEED, default=7, show_default=True)
def explain(scenario_id, model_dir, n, seed):
    """Show one scenario's inputs, applied control effects, and results."""
    m = _load(model_dir)
    cash = lambda value: money(value, m.business.currency)
    sc = next((s for s in m.scenarios if s.id == scenario_id), None)
    if sc is None:
        click.echo(
            f"unknown scenario '{scenario_id}'; known: {', '.join(s.id for s in m.scenarios)}", err=True
        )
        sys.exit(1)
    run = simulate(m, n, seed)
    r = next(x for x in run.scenarios if x.id == scenario_id)
    click.echo(f"\n  {sc.name}  [{sc.service} · {sc.threat}]  owner {sc.owner}")
    click.echo(
        f"  frequency (before controls): {sc.frequency.describe()} events/yr   source {sc.frequency.source}  owner {sc.frequency.owner}"
    )
    click.echo(f"  frequency (after controls):  {r.events_per_year:.3f} events/yr")
    click.echo("  magnitude components:")
    for c in sc.components:
        parts = []
        for f in ("amount", "hours", "demand", "p_pay", "records", "cost_per_record", "pct"):
            rr = getattr(c, f)
            if rr is not None:
                parts.append(f"{f}={rr.describe()} [{rr.source}]")
        click.echo(f"    {c.name:<28} {c.kind:<11} tags={','.join(c.tags):<16} " + "; ".join(parts))
    click.echo("  control effects applied:")
    for note in r.multipliers or ["(none)"]:
        click.echo(f"    · {note}")
    click.echo(
        f"  result: EAL {cash(r.eal)}  p50 {cash(r.pct(50))}  p95 {cash(r.pct(95))}  p99 {cash(r.pct(99))}"
    )
    if sc.unpriced:
        click.echo("  unpriced: " + "; ".join(sc.unpriced))
    click.echo("")


# ---------------------------------------------------------------- assumptions register
@main.command()
@click.option(
    "--model", "model_dir", type=click.Path(path_type=Path), default=DEFAULT_MODEL, show_default=True
)
@click.option("--csv", "csv_out", type=click.Path(path_type=Path), help="Write the register as CSV.")
def register(model_dir, csv_out):
    """List material assumptions, evidence owners and attestation status."""
    m = _load(model_dir)
    rows = m.assumptions()
    for a in rows:
        click.echo(
            f"  {a['path']:<62} {a['shape']:<9} {a['estimate']:<34} src={a['source'] or '?':<26} owner={a['owner'] or '?'}"
        )
    missing_src = [a for a in rows if not a["source"]]
    missing_own = [a for a in rows if not a["owner"]]
    click.echo(
        f"\n  {len(rows)} assumptions · {len(missing_src)} without source · {len(missing_own)} without owner"
    )
    ok, problems = m.verify()
    click.echo("  attestations: " + ("CURRENT" if ok else "NOT CURRENT - " + "; ".join(problems)))
    if csv_out:
        import csv

        with open(csv_out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        click.echo(f"  → {csv_out}")


@main.command("attest")
@click.option(
    "--model", "model_dir", type=click.Path(path_type=Path), default=DEFAULT_MODEL, show_default=True
)
@click.option("--role", required=True)
@click.option("--name", required=True)
def attest(model_dir, role, name):
    """Print a digest attestation for the current assumptions."""
    m = _load(model_dir)
    s = Attestation(role=role, name=name, date=datetime.now(timezone.utc).date(), digest=m.digest())
    click.echo(
        "  - " + json.dumps({"role": s.role, "name": s.name, "date": s.date.isoformat(), "digest": s.digest})
    )


@main.command()
@click.option(
    "--model", "model_dir", type=click.Path(path_type=Path), default=DEFAULT_MODEL, show_default=True
)
def verify(model_dir):
    """Check current digest attestations (identity is not cryptographically authenticated)."""
    m = _load(model_dir)
    ok, problems = m.verify()
    click.echo(f"  digest {m.digest()[:16]}...  " + ("ATTESTED by all required roles" if ok else "NOT VALID"))
    for p in problems:
        click.echo(f"    ! {p}")
    sys.exit(0 if ok else 1)


# ---------------------------------------------------------------- kpis
@main.group()
def kpis() -> None:
    """Measured KPIs that drive control effects."""


@kpis.command("import")
@click.option(
    "--model", "model_dir", type=click.Path(path_type=Path), default=DEFAULT_MODEL, show_default=True
)
@click.option(
    "--from-72md", "p72", type=click.Path(path_type=Path), help="72md out/ directory or one rehearsal JSON"
)
@click.option("--from-wormprint", "pwp", type=click.Path(path_type=Path), help="wormprint report.json")
@click.option("--set", "sets", multiple=True, help="KEY=VALUE (repeatable), e.g. proven_restore_hours=6")
@click.option(
    "--owner", default="Model Owner", show_default=True, help="Owner for values supplied with --set."
)
@click.option("--source", default="manual-kpi-entry", show_default=True, help="Source id for --set values.")
def kpis_import(model_dir, p72, pwp, sets, owner, source):
    """Update KPI evidence. Changing a KPI invalidates current digest attestations."""
    path = Path(model_dir) / "kpis.yaml"
    if path.exists():
        if path.stat().st_size > MAX_MODEL_FILE_BYTES:
            raise click.ClickException(
                f"KPI file exceeds the {MAX_MODEL_FILE_BYTES // (1024 * 1024)} MB safety limit"
            )
        data = yaml.load(path.read_text(encoding="utf-8"), Loader=NoAliasSafeLoader)
        if not isinstance(data, dict):
            raise click.ClickException("KPI file must contain a YAML mapping")
    else:
        data = {"kpis": {}}
    data.setdefault("kpis", {})
    if not isinstance(data["kpis"], dict):
        raise click.ClickException("KPI file field 'kpis' must contain a YAML mapping")
    if p72:
        data["kpis"].update(import_72md(Path(p72)))
    if pwp:
        data["kpis"].update(import_wormprint(Path(pwp)))
    for s in sets:
        if "=" not in s:
            raise click.ClickException(f"invalid --set value '{s}'; expected KEY=VALUE")
        k, v = s.split("=", 1)
        k = k.strip()
        if not k:
            raise click.ClickException("invalid --set value; KEY cannot be empty")
        try:
            number = float(v)
        except ValueError as exc:
            raise click.ClickException(f"invalid numeric value for '{k}': {v}") from exc
        if not math.isfinite(number):
            raise click.ClickException(f"invalid numeric value for '{k}': value must be finite")
        data["kpis"][k.strip()] = {
            "value": number,
            "source": source,
            "owner": owner,
            "measured_at": datetime.now(timezone.utc).date().isoformat(),
            "status": "manual_estimate",
        }
    try:
        data["kpis"] = {
            key: KpiMeasurement.model_validate(value).model_dump(mode="json")
            for key, value in data["kpis"].items()
        }
    except (TypeError, ValueError) as exc:
        raise click.ClickException(f"KPI evidence is invalid: {exc}") from exc
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    for k, v in data["kpis"].items():
        click.echo(f"  {k} = {v['value']} ({v['status']}, {v['measured_at']})")
    click.echo(f"  -> {path}   (digest changed: refresh required attestations with `cyberpnl attest`)")


@kpis.command("curves")
def kpis_curves():
    """List KPI curves and show their shape."""
    for name, fn in CURVES.items():
        click.echo(f"  {name}: {(fn.__doc__ or '').strip().splitlines()[0]}")
    click.echo("\n  contain_before_exfil(time_to_contain_minutes):")
    for t in (15, 28, 45, 60, 72, 90, 120):
        click.echo(f"    {t:>4} min -> x{CURVES['contain_before_exfil'](t, {}):.3f}")


# ---------------------------------------------------------------- calibrate
@main.command()
@click.argument("quantity")
@click.option("--unit", default="USD", show_default=True)
def calibrate(quantity, unit):
    """Equivalent-bet wizard: elicit a defensible 90% input interval."""
    from .calibrate import wizard

    wizard(quantity, unit)


if __name__ == "__main__":
    main()
