# CFO Brief — Cyber P&L

*A cyber-risk decision-support model, not an accounting or GAAP profit-and-loss statement.*

## What this is

Cyber P&L estimates annual cyber loss as a distribution and compares alternative security decisions on
the same dollar axis. Finance-recognizable loss components—downtime, incident response, legal cost,
fraud, recovery, contract credits, and customer loss—remain visible rather than being hidden behind a
single vendor score.

Every material input has an accountable owner and source record. Digest attestations show whether the
model changed after review. They are tamper evidence, not cryptographic authentication or a claim that
the estimates are correct.

## Illustrative output only

The included $180M SaaS company, KPIs, costs, appetite, and results are fictional:

| Metric | Demonstration result |
|---|---:|
| Expected annual loss | **$1.36M** (0.76% of revenue) |
| Annual-loss p95 (“1-in-20” simulated year) | **$4.31M** (2.40% of revenue) |
| Annual-loss p99 | $7.89M |
| Security spend | $5.40M |
| Illustrative appetite | Within both p95 and EAL limits |

These are annual-loss distribution percentiles, not confidence intervals for the expected-loss
estimate. They must not be used as benchmark facts about a real company.

## Questions for Finance

1. Which decisions should this model inform: security budget, insurance retention, risk acceptance, or
   another capital-allocation question?
2. Can Finance defend revenue per hour, contract exposure, control costs, and the annualization policy?
3. Which loss threshold can the organization absorb, and which percentile should govern the decision?
4. Which assumptions dominate the endpoint sensitivity analysis and deserve stronger evidence?
5. Which consequences should remain explicitly unpriced?

## Decision metrics

- **Benefit-cost ratio:** annual loss avoided divided by annualized cost.
- **Net ROSI:** annual loss avoided minus annualized cost, divided by annualized cost.
- **Payback:** one-time cost divided by annual loss avoided after recurring annual cost.
- **Bad-year reduction:** change in annual-loss p95.

Control values are one-at-a-time counterfactuals and overlap. They must not be summed. A decision pack
should show the underlying assumptions and at least one adverse sensitivity case, not only the ranking.

## Approval workflow

After the fictional inputs have been replaced:

1. Finance and Security review their owned assumptions and source evidence.
2. The model passes `cyberpnl validate --operational`.
3. Required roles attest to the exact SHA-256 digest.
4. If authenticated approval is required, the digest is signed in the organization's existing GPG,
   Sigstore, e-signature, GRC, or document-approval system.
5. Any model edit invalidates the digest attestations and triggers review again.

## What this is not

It is not a forecast, valuation, accounting statement, insurance submission, materiality decision, or
actuarial opinion. Scenario correlation, second-order uncertainty, and additive allocation of
overlapping control value are outside the current model. The value is disciplined comparison and
governed assumptions—not the third significant figure.

*Prepared by Jessen Kurien · model version: use the first 12 characters of the current digest · date:
insert review date*
