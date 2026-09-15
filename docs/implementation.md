# Implementation — the ten-week program

The tool runs in seconds. The work is getting the right people to agree on the inputs and then govern them. This is how a CISO stands it up.

**Week 1 — Name the decisions.** Agree with the CFO and CEO which three decisions the model exists to inform: usually the security budget, the cyber insurance renewal, and the board's risk appetite statement. Get the CFO as co-sponsor. A quantification effort without a named decision becomes an academic exercise.

**Weeks 2–3 — Business profile with Finance.** Revenue per hour by service (from the BIA), record counts by data type, regimes, contract penalty exposure, insurance terms, security spend by control. Reuse the service list from the containment program's business context so the projects line up. Only what Finance can defend goes in.

**Week 4 — Pick the scenarios.** Eight to ten, each a service paired with a threat, each with an owner. The shipped ten are the starting list; swap for your industry (clinical systems and patient safety for a hospital, payment fraud and capital effects for a bank, OT downtime and safety for a manufacturer).

**Weeks 5–6 — Calibrate.** Two half-day workshops (`docs/calibration-guide.md`). Every range gets a source and an owner at the moment of estimation. Replace or consciously keep each shipped placeholder.

**Week 7 — Connect the evidence.** `cyberpnl kpis import` from the containment rehearsals, the credential audit, and the restore drills. Run the statement. Read only the tornado. Spend one hour with the owners of the top three assumptions.

**Week 8 — Set appetite and attest.** Take the exceedance curve to the CFO and CEO: what loss in a 1-in-20 year are we willing to carry, and what expected annual loss requires action? Put every approved threshold in `appetite.yaml`. Have the CFO and CISO attest to the reviewed digest, and use an authenticated enterprise approval or signing workflow if identity assurance is required.

**Weeks 9–10 — Validate, publish, and use.** Run `cyberpnl validate --operational`, then produce the first board statement. Use it on a live decision: compare proposals by benefit-cost ratio, net ROSI, payback, p95 reduction, and the assumptions behind each result.

**Rhythm.** Quarterly refresh with measured KPIs. After any real incident, replace estimates with actuals and log the comparison. Bring the curve to the insurance renewal. Use the same numbers when Legal asks about materiality. Treat the model as a control: versioned, CI-gated, reviewed annually by Internal Audit.

**Pitfalls.** Treating annual-loss percentiles as confidence intervals. Arguing about $2.1M versus $2.8M instead of the decision. Letting a vendor set effectiveness multipliers. Summing overlapping control values. Thirty scenarios. A point estimate without its assumptions. Attesting once and never reviewing again.
