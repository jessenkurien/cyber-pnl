# Methodology

Cyber P&L is a transparent, FAIR-style decision model. It is not an actuarially validated forecast,
an accounting P&L, or a claim of Open FAIR conformance. This page makes each formula and judgment
visible so Finance, Risk, Internal Audit, or an independent reviewer can challenge it.

## 1. Scenario structure

A scenario pairs a business service with a threat event and contains:

- loss-event frequency `λ`, expressed as events per year before controls;
- component-level loss magnitude;
- tags that allow control effects to target scenarios or components;
- a named owner and source for each ranged input; and
- unpriced consequences that remain visible without forcing a false dollar value.

A control applies a frequency multiplier, magnitude multiplier, or named KPI curve. Values from zero
to one reduce modeled risk. Controls can declare dependencies and proposed controls can declare which
existing controls they replace.

## 2. Input distributions

| Shape | Parameters | Sampling interpretation |
|---|---|---|
| PERT | `min`, `mode`, `max` | Beta-PERT with shape 4, scaled to the stated bounds |
| Lognormal | `p05`, `p95` | Lognormal whose 5th and 95th percentiles match the inputs |
| Fixed | `value` | Constant |

For PERT, the mean is `(min + 4 × mode + max) / 6`.

For lognormal inputs:

```text
mu    = (ln(p05) + ln(p95)) / 2
sigma = (ln(p95) - ln(p05)) / (2 × 1.6448536)
mean  = exp(mu + sigma² / 2)
```

The `p05`/`p95` values are a **90% input interval supplied by the model owner**. They are not a
statistical confidence interval unless the calibration process independently establishes that.

## 3. Simulation

For each simulated year and scenario:

```text
rate_y   = sampled_frequency_y × product(frequency_multipliers_y)
events_y ~ Poisson(rate_y)
event_loss = max(0, sum(component_cost × component_multiplier_y))
annual_y = sum(event_loss for each event)
portfolio_annual_y = sum(annual_y for each scenario)
```

Component formulas:

| Kind | Formula |
|---|---|
| `dollars` | `amount` |
| `offset` | negative `amount`, representing a recovery or credit |
| `downtime` | `hours × revenue_per_hour` |
| `ransom` | `demand × Bernoulli(p_pay)` |
| `per_record` | `records × cost_per_record` |
| `pct_revenue` | `pct × annual_revenue` |

Offsets must be non-positive; other loss inputs must be non-negative. Each event is floored at zero,
so an independently sampled recovery can never turn an incident into profit. Generic magnitude
effects do not alter offsets; a control must explicitly target an offset tag to do so.

Outputs include EAL (the sample mean), median, p90, p95, p99, zero-loss-year probability, and the
loss-exceedance curve `P(annual loss ≥ x)`. The percentiles are percentiles of simulated annual loss,
not confidence bounds around EAL.

## 4. Stable counterfactual streams

Every scenario, control effect, base frequency, event count, and component uses a stable stream derived
from integer seed coordinates. Removing one control cannot shift the random draws for an unrelated
scenario or control. This reduces counterfactual resampling noise and makes runs reproducible.

This is not a proof that the remaining difference is causal. Control effect sizes, dependencies, and
scenario structure remain assumptions.

## 5. Control stacking and offsets

Multipliers combine multiplicatively. The combined frequency multiplier and each component's combined
magnitude multiplier are floored at `min_multiplier` (5% in the sample). The floor prevents a long
control stack from implying nearly zero risk. It is a model-governance assumption with its own owner
and source, not an empirical constant.

## 6. KPI curves

KPI records contain a value, source, owner, measurement date, and evidence status. Named curves convert
the value to a multiplier:

- `contain_before_exfil(t)`: logistic relationship between time to contain and exfiltration-related
  residual loss;
- `contain_before_encrypt(t)`: equivalent curve for ransomware impact;
- `credential_exposure_grade(score)`: exposure score or grade to credential-event frequency;
- `coverage(pct)`: coverage to frequency reduction; and
- `restore_hours_ratio(h)`: measured restore time relative to an outage baseline.

These curves are monotonic and inspectable. They are judgment functions, not causal relationships fit
to outcome data. The sample's 72-minute clock is a transparent calibration point inspired by incident-
response reporting; it is not presented as a universal or fastest-observed attacker time. Curve
defaults and parameters are material assumptions in the register.

## 7. Existing-control counterfactual

For existing control `c`:

```text
value(c) = EAL(with all existing controls except exclusions)
         - EAL(with all existing controls)
```

Excluding a prerequisite also excludes its declared dependents. One-at-a-time values overlap and are
not additive; **never sum the control-value column**.

Metrics:

```text
benefit-cost ratio = annual loss avoided / annual control cost
net ROSI           = (annual loss avoided - annual control cost) / annual control cost
```

## 8. Proposed investments

For proposal `p`:

```text
avoided(p) = EAL(existing controls) - EAL(existing controls + p - replacements)
annualized_cost = annual_cost + one_time_cost / 3
benefit-cost ratio = avoided / annualized_cost
net ROSI = (avoided - annualized_cost) / annualized_cost
payback_months = 12 × one_time_cost / (avoided - recurring_annual_cost)
```

Payback is undefined when annual loss avoided does not exceed recurring annual cost. The sample uses a
three-year straight-line convention for ranking; an organization should align it to Finance policy.

## 9. Endpoint sensitivity

Each non-fixed scenario input is pinned once to its low endpoint and once to its high endpoint. The
model re-runs under both conditions and ranks `abs(EAL_high - EAL_low)`. This is an **one-at-a-time
endpoint sensitivity analysis**, not variance decomposition or global sensitivity analysis. It helps
prioritize calibration work; it does not allocate uncertainty shares.

## 10. Risk appetite

Each configured limit chooses `eal`, `p90`, `p95`, or `p99` and a maximum dollar value or percentage
of revenue. All limits are evaluated. Overall appetite passes only when every individual limit passes.

The public sample includes illustrative p95 and EAL limits but no fictional board approval.

## 11. Assumption digest and attestations

SHA-256 is calculated over canonical JSON containing the business profile, scenarios, controls,
appetite, KPIs, sources, and model settings. The attestation block is excluded so people can add an
attestation without changing the digest they are attesting to.

`cyberpnl attest` emits a named, dated digest assertion. `cyberpnl verify` checks:

- the digest matches the current model;
- every required role has one current attestation; and
- no attestation is future-dated.

This detects stale edits but **does not authenticate the person's identity**. For authenticated
approval, sign the digest using the organization's existing GPG, Sigstore, e-signature, or governance
system and retain that evidence outside this YAML file.

## 12. Validation and publication gates

Strict validation rejects extra fields, invalid distribution shapes, NaN/infinite values, negative
frequencies, invalid probabilities, duplicate IDs, dependency cycles, unknown selectors, component
tags that match nothing, and unknown source IDs.

`cyberpnl validate` accepts the clearly labeled illustrative template. `cyberpnl validate
--operational` additionally rejects template status, placeholder evidence, non-measured KPI values,
missing owners/sources, and missing or stale attestations.

## 13. Interpretation limits

The model samples input uncertainty and annual event variability in one layer. It does not provide a
second-order confidence interval around EAL. Scenarios are modeled as independent Poisson processes;
shared campaigns and cascading failures may make the far tail too low. See
[`model-risk.md`](model-risk.md) before using the output in a decision.
