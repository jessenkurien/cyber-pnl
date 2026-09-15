# GitHub Launch Checklist

## Before publishing

1. Keep the sample fictional: `business.template: true`, synthetic KPI statuses, no CFO/CISO
   attestations, and visible `[TEMPLATE]` source records.
2. Confirm the public references in `model/sources.yaml` point to the intended edition and exact page.
   A report may inform calibration without proving a scenario-specific range.
3. Complete [`RELEASE_REVIEW.md`](../RELEASE_REVIEW.md). Publication requires the named author's
   explicit approval; passing automated tests is necessary but not sufficient.
4. Run the complete release checks:

   ```bash
   python -m ruff format --check .
   python -m ruff check .
   python -m pytest --cov=cyberpnl --cov-fail-under=90
   cyberpnl validate
   cyberpnl statement --model model --out out --fail-on-appetite
   ```

5. Confirm `model/` and `cyberpnl/default_model/` contain identical YAML files.
6. Build and install the wheel in a clean environment, then run `cyberpnl validate` outside the
   repository.
7. Regenerate `docs/sample-statement.html` and `docs/statement.png` from the current model.
8. Inspect every generated page for **TEMPLATE**, not **ATTESTED**, and confirm both appetite checks
   appear.
9. Review your employment, invention-assignment, open-source, and confidentiality obligations. The
   repository must contain no employer data, client information, internal benchmarks, or proprietary
   methods.
10. Turn on GitHub private vulnerability reporting, Dependabot alerts, and branch protection after the
   first push.
11. Upload `docs/social-preview.png` under **Settings → Social preview**.
12. Confirm GitHub shows **Cite this repository** from the root `CITATION.cff` file.
13. Create the release from a protected commit, attach the source archive and checksums, and publish
    release notes that repeat the illustrative-template and non-advice limitations.

Repository settings:

- Name: `cyber-pnl`
- Description: `Open-source cyber risk quantification: Monte Carlo loss modeling, control valuation, security investment analysis, and governed assumptions.`
- Topics: `cyber-risk`, `risk-quantification`, `monte-carlo`, `ciso`, `cfo`, `grc`, `board-reporting`,
  `security-leadership`, `fair-risk-analysis`, `cybersecurity-roi`, `security-economics`,
  `control-effectiveness`, `risk-appetite`, `security-investment`

## Suggested LinkedIn launch post

I kept hearing the same board questions: “How much cyber risk do we carry in money?” and “What does
the next dollar of security spend buy?”

So I built **Cyber P&L**, an open, auditable, FAIR-style decision model for cyber risk.

It models loss-event frequency and business-recognizable loss components, runs a seeded Monte Carlo
simulation, compares every configured appetite limit, estimates existing-control value through
counterfactuals, and ranks proposed investments by benefit-cost ratio, net ROSI, payback, and bad-year
reduction.

The part I care most about is governance. The model uses strict schemas; every material input has a
source and owner; operational KPIs carry a measurement date and evidence status; and named reviewers
can attest to the exact SHA-256 digest. An edit makes the attestation stale. I’m explicit that this is
tamper evidence—not an authenticated digital signature.

The repository includes an **illustrative fictional company**, not a claim about a real organization.
Its current demonstration output is about $1.36M in expected annual loss and $4.31M at annual-loss p95.
The numbers are less important than the decisions the model exposes:

- a low-cost payment verification control outranks several technology purchases;
- phishing-resistant MFA replaces app-based MFA instead of being double-counted;
- EDR value includes the containment process that depends on its telemetry; and
- one-at-a-time control values overlap, so the tool warns leaders not to sum them.

Building it also exposed mistakes that a spreadsheet could hide: independently sampled recovery
credits could create negative losses, “ROSI” was being used for benefit-cost ratio, one appetite
sentence contained two limits while only one was enforced, and counterfactual runs could reshuffle
unrelated random inputs. Those issues are now modeled and tested explicitly.

This is not a forecast, accounting P&L, or compliance claim. It is a disciplined, reviewable way to
compare decisions under uncertainty.

GitHub: https://github.com/jessenkurien/cyber-pnl

#CyberRisk #SecurityLeadership #CISO #CFO #GRC #RiskQuantification #MonteCarlo

## Interview discussion points

- Why benefit-cost ratio and net ROSI answer different finance questions.
- Why a control upgrade must replace—not stack with—the old control.
- Why recovery offsets require a zero-loss floor.
- Why a digest attestation detects edits but cannot authenticate identity.
- Why annual-loss p95 is not a confidence interval for EAL.
- Why overlapping one-at-a-time control values must never be summed.
