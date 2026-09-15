"""The board statement: one page, HTML + Markdown + JSON. SVG charts drawn inline, no dependencies."""

from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Any

import numpy as np

from . import DISCLAIMER, __version__
from .engine import ControlValue, InvestmentCase, RunResult, Sensitivity
from .models import Model

# palette (light surface): status + one categorical hue; text never in series color
SURFACE, INK, INK2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9"
BLUE, GOOD, CRIT, GOODTXT, ORANGE = "#2a78d6", "#0ca30c", "#d03b3b", "#006300", "#eb6834"
FONT = 'font-family="system-ui,-apple-system,Segoe UI,Helvetica,Arial,sans-serif"'
PROJECT_CREATOR = "Jessen Kurien"
PROJECT_URL = "https://github.com/jessenkurien/cyber-pnl"


_CURRENCY_PREFIXES = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
    "INR": "₹",
    "CAD": "C$",
    "AUD": "A$",
    "NZD": "NZ$",
    "SGD": "S$",
    "HKD": "HK$",
    "CHF": "CHF ",
    "AED": "AED ",
}


def money(x: float | None, currency: str = "USD", digits: int = 0) -> str:
    if x is None:
        return "—"
    sign = "-" if x < 0 else ""
    x = abs(x)
    prefix = _CURRENCY_PREFIXES.get(currency, f"{currency} ")
    if x >= 1e9:
        return f"{sign}{prefix}{x / 1e9:.2f}B"
    if x >= 1e6:
        return f"{sign}{prefix}{x / 1e6:.2f}M"
    if x >= 1e3:
        return f"{sign}{prefix}{x / 1e3:.0f}K"
    return f"{sign}{prefix}{x:,.{digits}f}"


# ---------------------------------------------------------------- charts
def exceedance_svg(
    run: RunResult,
    appetite: dict | None,
    width: int = 760,
    height: int = 300,
    currency: str = "USD",
) -> str:
    x_max = max(run.pct(99.5), 1.0)
    xs = np.linspace(0, x_max, 160)
    ys = run.exceedance(xs)
    L, R, T, B = 70, width - 20, 24, height - 44
    sx = lambda v: L + (v / x_max) * (R - L)
    sy = lambda p: T + (1 - p) * (B - T)
    s = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Loss exceedance curve">',
        f'<rect width="{width}" height="{height}" fill="{SURFACE}"/>',
    ]
    for p in (0.0, 0.25, 0.5, 0.75, 1.0):
        s.append(f'<line x1="{L}" y1="{sy(p):.1f}" x2="{R}" y2="{sy(p):.1f}" stroke="{GRID}"/>')
        s.append(
            f'<text x="{L - 8}" y="{sy(p) + 4:.1f}" {FONT} font-size="11" fill="{MUTED}" text-anchor="end">{int(p * 100)}%</text>'
        )
    for i in range(6):
        v = x_max * i / 5
        s.append(
            f'<text x="{sx(v):.1f}" y="{B + 16}" {FONT} font-size="11" fill="{MUTED}" text-anchor="middle">{money(v, currency)}</text>'
        )
    s.append(
        f'<text x="{(L + R) / 2:.0f}" y="{height - 6}" {FONT} font-size="11" fill="{MUTED}" text-anchor="middle">annual loss</text>'
    )
    s.append(
        f'<text x="{L}" y="14" {FONT} font-size="12" font-weight="600" fill="{INK}">Probability that annual loss exceeds X</text>'
    )
    pts = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in zip(xs, ys))
    s.append(f'<polyline points="{pts}" fill="none" stroke="{BLUE}" stroke-width="2"/>')
    for q, lab in ((50, "median"), (95, "1-in-20 year")):
        v = run.pct(q)
        if v <= x_max:
            s.append(
                f'<line x1="{sx(v):.1f}" y1="{T}" x2="{sx(v):.1f}" y2="{B}" stroke="{MUTED}" stroke-dasharray="4 4"/>'
            )
            s.append(
                f'<text x="{sx(v) + 4:.1f}" y="{T + 12}" {FONT} font-size="11" fill="{INK2}">{lab} {money(v, currency)}</text>'
            )
    p95_check = (
        next((check for check in appetite["checks"] if check["metric"] == "p95"), None) if appetite else None
    )
    if p95_check and p95_check["limit"] <= x_max:
        v = p95_check["limit"]
        s.append(
            f'<line x1="{sx(v):.1f}" y1="{T}" x2="{sx(v):.1f}" y2="{B}" stroke="{CRIT}" stroke-width="2" stroke-dasharray="6 4"/>'
        )
        near_edge = sx(v) > R - 110
        s.append(
            f'<text x="{sx(v) + (-4 if near_edge else 4):.1f}" y="{B - 6}" {FONT} font-size="11" font-weight="700" fill="{CRIT}" '
            f'text-anchor="{"end" if near_edge else "start"}">appetite {money(v, currency)}</text>'
        )
    s.append("</svg>")
    return "\n".join(s)


def hbar_svg(
    rows: list[tuple[str, float, str]],
    title: str,
    width: int = 760,
    fmt=None,
    currency: str = "USD",
) -> str:
    """rows: (label, value, color). Thin bars, direct labels, one axis."""
    rows = rows[:12]
    fmt = fmt or (lambda value: money(value, currency))
    h = 34 + 26 * len(rows) + 10
    vmax = max((abs(v) for _, v, _ in rows), default=1) or 1
    L, R = 300, width - 90
    s = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{h}" viewBox="0 0 {width} {h}" role="img" aria-label="{html.escape(title)}">',
        f'<rect width="{width}" height="{h}" fill="{SURFACE}"/>',
        f'<text x="12" y="18" {FONT} font-size="12" font-weight="600" fill="{INK}">{html.escape(title)}</text>',
    ]
    for i, (label, v, color) in enumerate(rows):
        y = 34 + i * 26
        w = max(2, abs(v) / vmax * (R - L))
        s.append(
            f'<text x="{L - 10}" y="{y + 13}" {FONT} font-size="12" fill="{INK2}" text-anchor="end">{html.escape(label[:44])}</text>'
        )
        s.append(f'<rect x="{L}" y="{y + 2}" width="{w:.1f}" height="16" rx="3" fill="{color}"/>')
        s.append(f'<text x="{L + w + 6:.1f}" y="{y + 14}" {FONT} font-size="12" fill="{INK}">{fmt(v)}</text>')
    s.append("</svg>")
    return "\n".join(s)


def tornado_svg(sens: list[Sensitivity], width: int = 760, currency: str = "USD") -> str:
    rows = sens[:10]
    h = 34 + 26 * len(rows) + 30
    base = rows[0].base_eal if rows else 0
    span = max((max(abs(r.low_eal - base), abs(r.high_eal - base)) for r in rows), default=1) or 1
    L, R = 300, width - 90
    mid = (L + R) / 2
    sc = (R - L) / 2 / span
    s = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{h}" viewBox="0 0 {width} {h}" role="img" aria-label="Sensitivity of expected annual loss to model assumptions">',
        f'<rect width="{width}" height="{h}" fill="{SURFACE}"/>',
        f'<text x="12" y="18" {FONT} font-size="12" font-weight="600" fill="{INK}">Which assumptions move expected loss most (input at its low vs high end)</text>',
        f'<line x1="{mid:.1f}" y1="28" x2="{mid:.1f}" y2="{h - 26}" stroke="{MUTED}"/>',
    ]
    for i, r in enumerate(rows):
        y = 34 + i * 26
        lo, hi = r.low_eal - base, r.high_eal - base
        for v, col in ((lo, BLUE), (hi, ORANGE)):
            x0 = mid + min(0, v) * sc
            s.append(
                f'<rect x="{x0:.1f}" y="{y + 2}" width="{abs(v) * sc:.1f}" height="16" rx="3" fill="{col}" opacity="0.85"/>'
            )
        s.append(
            f'<text x="{L - 10}" y="{y + 13}" {FONT} font-size="11" fill="{INK2}" text-anchor="end">{html.escape(r.path[:48])}</text>'
        )
        s.append(
            f'<text x="{mid + max(lo, hi) * sc + 6:.1f}" y="{y + 14}" {FONT} font-size="11" fill="{INK}">±{money(r.swing / 2, currency)}</text>'
        )
    s.append(
        f'<text x="{mid:.1f}" y="{h - 8}" {FONT} font-size="11" fill="{MUTED}" text-anchor="middle">baseline {money(base, currency)} · blue = input at low end · orange = at high end</text>'
    )
    s.append("</svg>")
    return "\n".join(s)


# ---------------------------------------------------------------- statement
def statement_data(
    model: Model,
    run: RunResult,
    cvs: list[ControlValue],
    ics: list[InvestmentCase],
    sens: list[Sensitivity],
    appetite: dict | None,
) -> dict[str, Any]:
    rev = model.business.annual_revenue
    ok, problems = model.verify()
    return {
        "cyber_pnl_version": __version__,
        "project": {"name": "Cyber P&L", "creator": PROJECT_CREATOR, "url": PROJECT_URL},
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "organization": model.business.organization,
        "fiscal_year": model.business.fiscal_year,
        "currency": model.business.currency,
        "template": model.business.template,
        "annual_revenue": rev,
        "security_spend_annual": model.business.security_spend_annual,
        "simulation": {"years": run.n, "seed": run.seed},
        "expected_annual_loss": run.eal,
        "eal_pct_revenue": run.eal / rev,
        "median": run.pct(50),
        "p90": run.pct(90),
        "p95": run.pct(95),
        "p99": run.pct(99),
        "p95_pct_revenue": run.pct(95) / rev,
        "spend_to_eal_ratio": (model.business.security_spend_annual / run.eal) if run.eal else None,
        "appetite": appetite,
        "assumptions_attested": ok,
        "attestation_problems": problems,
        "assumptions_digest": model.digest(),
        "kpis": {key: value.model_dump(mode="json") for key, value in model.kpis.items()},
        "scenarios": run.summary()["scenarios"],
        "unpriced": {s.id: s.unpriced for s in model.scenarios if s.unpriced},
        "control_values": [
            {
                "id": v.control.id,
                "name": v.control.name,
                "annual_cost": v.control.annual_cost,
                "avoided_eal": v.value,
                "avoided_p95": v.p95_without - v.p95_with,
                "benefit_cost_ratio": v.benefit_cost_ratio,
                "net_rosi": v.net_rosi,
            }
            for v in cvs
        ],
        "investments": [
            {
                "id": c.control.id,
                "name": c.control.name,
                "annualized_cost": c.annualized_cost,
                "one_time_cost": c.control.one_time_cost,
                "avoided_eal": c.avoided,
                "avoided_p95": c.p95_before - c.p95_after,
                "benefit_cost_ratio": c.benefit_cost_ratio,
                "net_rosi": c.net_rosi,
                "payback_months": c.payback_months,
                "replaces": c.control.replaces,
            }
            for c in ics
        ],
        "sensitivity": [
            {"path": s.path, "low_eal": s.low_eal, "high_eal": s.high_eal, "swing": s.swing} for s in sens
        ],
        "disclaimer": DISCLAIMER,
    }


def statement_markdown(d: dict[str, Any]) -> str:
    a = d["appetite"]
    cash = lambda value: money(value, d["currency"])
    state = (
        "ILLUSTRATIVE TEMPLATE"
        if d["template"]
        else "ATTESTED"
        if d["assumptions_attested"]
        else "UNATTESTED"
    )
    lines = [
        f"# Cyber P&L — {d['organization']} FY{d['fiscal_year']}",
        "",
        "*Cyber-risk decision-support estimate; not an accounting or GAAP profit-and-loss statement.*",
        "",
        (
            f"*Generated {d['generated']} · {d['simulation']['years']:,} simulated years · "
            f"seed {d['simulation']['seed']} · status {state} · digest {d['assumptions_digest'][:12]}…*"
        ),
        "",
        "| | |",
        "|---|---|",
        f"| Expected annual loss | **{cash(d['expected_annual_loss'])}** ({d['eal_pct_revenue']:.2%} of revenue) |",
        f"| Bad year (1-in-20, p95) | **{cash(d['p95'])}** ({d['p95_pct_revenue']:.2%} of revenue) |",
        f"| Very bad year (1-in-100, p99) | {cash(d['p99'])} |",
        f"| Median year | {cash(d['median'])} |",
        f"| Security spend | {cash(d['security_spend_annual'])} ({(d['spend_to_eal_ratio'] or 0):.1f}× expected loss) |",
    ]
    if a:
        for check in a["checks"]:
            lines.append(
                f"| Risk appetite ({check['metric']}) | "
                f"{'WITHIN' if check['within'] else '**BREACHED**'} — "
                f"{cash(check['value'])} vs limit {cash(check['limit'])} |"
            )
    lines += [
        "",
        "## Where the loss comes from",
        "",
        "| Scenario | Expected loss | Share | Events/yr | Bad year (p95) |",
        "|---|---:|---:|---:|---:|",
    ]
    for s in d["scenarios"]:
        lines.append(
            f"| {s['name']} | {cash(s['eal'])} | {s['share']:.0%} | {s['events_per_year']:.2f} | {cash(s['p95'])} |"
        )
    lines += [
        "",
        "## What existing controls are worth (counterfactual: remove it, re-simulate)",
        "",
        "*Values are one-control-at-a-time counterfactuals and must not be summed.*",
        "",
        "| Control | Annual cost | Loss avoided / yr | Bad-year reduction | Benefit/cost | Net ROSI |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for c in d["control_values"]:
        lines.append(
            f"| {c['name']} | {cash(c['annual_cost'])} | {cash(c['avoided_eal'])} | "
            f"{cash(c['avoided_p95'])} | {c['benefit_cost_ratio']:.1f}x | {c['net_rosi']:.1f}x |"
            if c["benefit_cost_ratio"] is not None
            else f"| {c['name']} | — | {cash(c['avoided_eal'])} | {cash(c['avoided_p95'])} | — | — |"
        )
    lines += [
        "",
        "## Proposed investments, ranked by benefit-cost ratio",
        "",
        "| Investment | Annualized cost | Loss avoided / yr | Bad-year reduction | Benefit/cost | Net ROSI | Payback |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for c in d["investments"]:
        pb = f"{c['payback_months']:.0f} mo" if c["payback_months"] is not None else "—"
        lines.append(
            f"| {c['name']} | {cash(c['annualized_cost'])} | {cash(c['avoided_eal'])} | "
            f"{cash(c['avoided_p95'])} | {c['benefit_cost_ratio']:.1f}x | {c['net_rosi']:.1f}x | {pb} |"
        )
    lines += [
        "",
        "## Assumptions that matter most",
        "",
        "| Input | Expected loss at low end | at high end | Swing |",
        "|---|---:|---:|---:|",
    ]
    for s in d["sensitivity"][:8]:
        lines.append(f"| `{s['path']}` | {cash(s['low_eal'])} | {cash(s['high_eal'])} | {cash(s['swing'])} |")
    if d["unpriced"]:
        lines += ["", "## Consequences we do not price", ""]
        for sid, items in d["unpriced"].items():
            lines.append(f"- **{sid}**: " + "; ".join(items))
    lines += [
        "",
        f"_Cyber P&L was created by [{d['project']['creator']}]({d['project']['url']})._",
        "",
        f"_{d['disclaimer']}_",
        "",
    ]
    return "\n".join(lines)


def statement_html(
    model: Model,
    run: RunResult,
    d: dict[str, Any],
    cvs: list[ControlValue],
    ics: list[InvestmentCase],
    sens: list[Sensitivity],
) -> str:
    a = d["appetite"]
    cash = lambda value: money(value, d["currency"])
    tile = lambda big, small, col: (
        f'<div class="tile" style="border-left-color:{col}"><b>{html.escape(big)}</b><span>{html.escape(small)}</span></div>'
    )
    tiles = [
        tile(
            cash(d["expected_annual_loss"]),
            f"expected annual loss · {d['eal_pct_revenue']:.2%} of revenue",
            BLUE,
        ),
        tile(cash(d["p95"]), f"bad year (1-in-20) · {d['p95_pct_revenue']:.2%} of revenue", ORANGE),
        tile(
            cash(d["security_spend_annual"]),
            f"security spend · {(d['spend_to_eal_ratio'] or 0):.1f}× expected loss",
            INK2,
        ),
    ]
    if a:
        details = " · ".join(f"{check['metric']} ≤ {cash(check['limit'])}" for check in a["checks"])
        tiles.append(
            tile(
                "WITHIN" if a["within"] else "BREACHED",
                f"risk appetite · {details}",
                GOOD if a["within"] else CRIT,
            )
        )
    attestation_state = (
        "TEMPLATE" if d["template"] else "ATTESTED" if d["assumptions_attested"] else "UNATTESTED"
    )
    tiles.append(
        tile(
            attestation_state,
            "assumptions digest · " + d["assumptions_digest"][:12] + "…",
            MUTED if d["template"] else GOOD if d["assumptions_attested"] else CRIT,
        )
    )
    sc_rows = [(s["name"], s["eal"], BLUE) for s in d["scenarios"]]
    cv_rows = [(v.control.name, v.value, GOOD) for v in cvs]
    inv_rows = "".join(
        f"<tr><td>{html.escape(c.control.name)}</td><td>{cash(c.annualized_cost)}</td><td>{cash(c.avoided)}</td>"
        f"<td>{cash(c.p95_before - c.p95_after)}</td><td><b>{(c.benefit_cost_ratio or 0):.1f}x</b></td>"
        f"<td>{(c.net_rosi or 0):.1f}x</td><td>{(f'{c.payback_months:.0f} mo' if c.payback_months is not None else '—')}</td></tr>"
        for c in ics
    )
    cv_table = "".join(
        f"<tr><td>{html.escape(v.control.name)}</td><td>{cash(v.control.annual_cost)}</td><td>{cash(v.value)}</td><td>{cash(v.p95_without - v.p95_with)}</td>"
        f"<td>{(f'{v.benefit_cost_ratio:.1f}x' if v.benefit_cost_ratio is not None else '—')}</td>"
        f"<td>{(f'{v.net_rosi:.1f}x' if v.net_rosi is not None else '—')}</td></tr>"
        for v in cvs
    )
    unpriced = "".join(
        f"<li><b>{html.escape(k)}</b>: {html.escape('; '.join(v))}</li>" for k, v in d["unpriced"].items()
    )
    kpi_txt = (
        " · ".join(f"{key}={value['value']} ({value['status']})" for key, value in d["kpis"].items())
        or "none supplied (defaults in use)"
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Cyber P&L — {html.escape(d["organization"])}</title>
<style>
body{{margin:0;background:#f9f9f7;color:#0b0b0b;font-family:system-ui,-apple-system,'Segoe UI',sans-serif}}
main{{max-width:1240px;margin:0 auto;padding:32px 24px}} h1{{font-size:30px;margin:0 0 4px}} h2{{font-size:18px;margin:28px 0 10px}} .sub{{color:#52514e;margin:0 0 22px;font-size:14px}}
.tiles{{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px;margin-bottom:20px}}
.tile{{background:#fff;border:1px solid #e1e0d9;border-radius:10px;padding:14px 16px;border-left:6px solid #2a78d6}}
.tile b{{display:block;font-size:28px}} .tile span{{color:#52514e;font-size:12px}}
.card{{background:#fff;border:1px solid #e1e0d9;border-radius:10px;padding:10px;margin-bottom:16px;overflow-x:auto}}
.row{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
.card svg{{display:block;max-width:none}} .table-wrap{{max-width:100%;overflow-x:auto;border-radius:10px}}
table{{width:100%;min-width:720px;border-collapse:collapse;background:#fff;border:1px solid #e1e0d9}} th,td{{padding:9px 12px;text-align:left;border-bottom:1px solid #e1e0d9;font-size:13px}} td:not(:first-child),th:not(:first-child){{text-align:right}}
.foot{{color:#898781;font-size:12px;margin-top:22px}} ul{{margin:6px 0 0 18px;font-size:13px;color:#52514e}}
a:focus-visible,.table-wrap:focus-visible{{outline:3px solid #0b63ce;outline-offset:3px}}
@media (max-width:900px){{main{{padding:24px 16px}}.tiles{{grid-template-columns:repeat(2,minmax(0,1fr))}}.row{{grid-template-columns:1fr}}}}
@media (max-width:560px){{main{{padding:20px 12px}}h1{{font-size:26px}}.tiles{{grid-template-columns:1fr}}.tile b{{font-size:24px}}}}
@media print{{body{{background:#fff}}main{{max-width:none;padding:0}}.card,.table-wrap{{overflow:visible}}}}
</style></head><body><main>
<h1>Cyber P&amp;L</h1>
<p class="sub">{html.escape(d["organization"])} · FY{d["fiscal_year"]} · {d["simulation"]["years"]:,} simulated years · generated {d["generated"]} · KPI inputs: {html.escape(kpi_txt)}</p>
<div class="tiles">{"".join(tiles)}</div>
<div class="row">
  <section class="card">{exceedance_svg(run, a, width=580, currency=d["currency"])}</section>
  <section class="card">{hbar_svg(sc_rows, "Expected annual loss by scenario", width=580, currency=d["currency"])}</section>
</div>
<h2>What existing controls are worth <span style="font-weight:400;color:#52514e;font-size:13px">(remove it, re-simulate with stable matched streams, measure the difference; dependents removed with it)</span></h2>
<section class="card">{hbar_svg(cv_rows, "Expected loss avoided per year", width=1200, currency=d["currency"])}</section>
<div class="table-wrap" role="region" aria-label="Existing control value table" tabindex="0"><table><thead><tr><th>Control</th><th>Annual cost</th><th>Loss avoided / yr</th><th>Bad-year (p95) reduction</th><th>Benefit/cost</th><th>Net ROSI</th></tr></thead><tbody>{cv_table}</tbody></table></div>
<p class="sub">Control values are one-at-a-time counterfactuals. They overlap and must not be summed.</p>
<h2>Proposed investments, ranked by benefit-cost ratio</h2>
<div class="table-wrap" role="region" aria-label="Proposed investment ranking table" tabindex="0"><table><thead><tr><th>Investment</th><th>Annualized cost</th><th>Loss avoided / yr</th><th>Bad-year reduction</th><th>Benefit/cost</th><th>Net ROSI</th><th>Payback</th></tr></thead><tbody>{inv_rows}</tbody></table></div>
<h2>Assumptions that move the answer most <span style="font-weight:400;color:#52514e;font-size:13px">(spend calibration effort here)</span></h2>
<section class="card">{tornado_svg(sens, width=1200, currency=d["currency"])}</section>
<h2>Consequences we do not put a number on</h2>
<ul>{unpriced or "<li>none declared</li>"}</ul>
<p class="foot"><b>Cyber P&amp;L by <a href="{html.escape(d["project"]["url"])}">{html.escape(d["project"]["creator"])}</a>.</b> Cyber-risk decision-support estimate; not an accounting or GAAP P&amp;L. {html.escape(d["disclaimer"])} Method: loss-event frequency × loss magnitude, Monte Carlo, stable matched streams for counterfactual attribution; see docs/methodology.md. Assumptions digest {d["assumptions_digest"][:16]}…</p>
</main></body></html>"""
