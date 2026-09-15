"""Calibration wizard: the equivalent-bet method, so estimates are 90% calibrated input ranges an
expert will defend rather than numbers plucked from the air.

The technique (Hubbard-style): propose a range, then ask the expert whether they'd rather bet on
the true value landing inside it or spin a wheel that pays 90% of the time. If they prefer the
range, it's too wide (narrow it); if they prefer the wheel, it's too narrow (widen it). Stop when
they're indifferent: that's a 90% CI.
"""

from __future__ import annotations

import click


def wizard(
    quantity: str,
    unit: str = "USD",
    start_low: float | None = None,
    start_high: float | None = None,
    max_rounds: int = 8,
) -> dict:
    click.echo(f"\nCalibrating: {quantity} ({unit})")
    click.echo("We'll elicit a range you judge has a 90% chance of containing the value.\n")
    low = (
        start_low if start_low is not None else click.prompt("  Absolute lowest plausible value", type=float)
    )
    high = (
        start_high
        if start_high is not None
        else click.prompt("  Absolute highest plausible value", type=float)
    )
    if high < low:
        low, high = high, low
    for _ in range(max_rounds):
        click.echo(f"\n  Current range: {low:,.4g} – {high:,.4g} {unit}")
        ans = click.prompt(
            "  Would you rather bet on the true value being INSIDE this range (r), or on a wheel that pays 90% of the time (w)? "
            "Or are you indifferent (i)?",
            type=click.Choice(["r", "w", "i"]),
            default="i",
        )
        if ans == "i":
            break
        if ans == "r":  # too wide: narrow by 15% each side toward the middle
            span = high - low
            low, high = low + 0.15 * span, high - 0.15 * span
        else:  # too narrow: widen by 25% each side
            span = high - low
            low, high = low - 0.25 * span, high + 0.25 * span
            if low < 0 and unit == "USD":
                low = 0.0
    mode = click.prompt("  Most likely value within the range", type=float, default=(low + high) / 2)
    mode = min(max(mode, low), high)
    owner = click.prompt("  Who defends this number (role)", default="")
    source = click.prompt("  Source or workshop reference", default="workshop")
    out = {
        "min": round(low, 6),
        "mode": round(mode, 6),
        "max": round(high, 6),
        "source": source,
        "owner": owner,
    }
    click.echo("\n  YAML:")
    click.echo(
        "  {" + ", ".join(f"{k}: {v!r}" if isinstance(v, str) else f"{k}: {v}" for k, v in out.items()) + "}"
    )
    return out
