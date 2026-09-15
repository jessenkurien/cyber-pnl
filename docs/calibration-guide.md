# Calibration Guide

The model is only as good as its ranges. This guide is how to produce ranges that named people will defend in front of a board.

## Who estimates what

| Input | Best estimator | Source to bring |
|---|---|---|
| Event frequency | Threat intel lead + IR lead | Your incident history (24 months), IRIS-style industry base rates, phishing/MFA telemetry |
| Incident response / forensics cost | IR lead | Retainer rate card, last two engagements |
| Downtime hours | IT director / platform head | Outage history, last restore drill |
| Revenue per hour by service | Finance | BIA, revenue attribution |
| Ransom demand and probability of paying | CISO + Legal + insurer | Public 2026 figures; your policy's stance |
| Records and cost per record | DPO + Legal | Data inventory; per-record benchmarks |
| Fines and settlements | Legal | Enforcement decisions and settlements in comparable cases |
| Churn / lost deals | CRO / sales leadership | Post-breach churn studies; your renewal cohort data |
| Control effectiveness | Control owner + CISO | Published studies where they exist; otherwise the workshop |

## The equivalent-bet method (`cyberpnl calibrate`)

Ask for an absolute lowest and highest plausible value. Then offer the choice: bet on the true value landing inside the range, or spin a wheel that pays 90% of the time. If they'd rather bet on the range, it's too wide; narrow it. If they'd rather spin, it's too narrow; widen it. Stop at indifference; record that as the owner's calibrated 90% input interval—not a statistically estimated confidence interval. Then ask for the most likely value, the owner, and the source. The wizard prints the YAML.

Two rules. Never let the loudest person set the range; run it individually first, then reconcile. And write the source down at the moment of estimation, because nobody remembers a month later.

## Workshop plan (two half-days)

**Session 1: frequency and response costs.** IR, threat intel, IT, platform. Walk the ten scenarios; produce frequency ranges and the operational cost components (IR, downtime, rebuild, recovery).

**Session 2: financial and legal consequences.** Finance, Legal, DPO, sales leadership. Records, per-record costs, fines, settlements, churn, lost deals, contract terms. Confirm revenue per hour.

After both, run `cyberpnl statement` and look only at the tornado. Spend one more hour on the top three inputs with their owners. Everything else can stay as estimated.

## Common mistakes

Arguing about the mode instead of the range; the range is what matters. Using a vendor's effectiveness claim as a control multiplier without a source you'd cite to a board. Mixing frequency of *attempts* with frequency of *loss events*: the model wants loss events (attempts that succeed), and controls that stop attempts reduce that frequency. Forgetting recoveries: insurance, bank clawbacks, contract remedies are negative components. Pricing what can't be priced; use the unpriced list.

## After an incident

Replace the estimate for that scenario's components with the actual costs, keep the range for the others, and record the comparison in `docs/calibration-log.md`. A model that is corrected after every real event is worth more each year; that log is also the evidence an auditor wants that the model is maintained.
