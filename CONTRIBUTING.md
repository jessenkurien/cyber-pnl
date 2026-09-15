# Contributing

Thank you. Three kinds of contribution matter most, in this order: calibration ranges with citable sources, new KPI curves with documented rationale, and industry scenario packs (healthcare, banking, manufacturing).

## Ground rules

- Sign your commits off under the [Developer Certificate of Origin](https://developercertificate.org/) (`git commit -s`). By doing so you certify you have the right to contribute the code under the MIT license.
- Never include real identifiers, tenant names, hostnames, or audit logs. Scenarios use `example.com`-style names.
- Every engine or curve change needs a test; monotonicity tests (removing a control never lowers loss) must stay green.
- Every change to the public sample must keep `cyberpnl validate` and `cyberpnl statement --fail-on-appetite` green. Do not add fictional CFO/CISO attestations merely to make a demonstration gate pass.
- Keep `model/*.yaml` and the bundled `cyberpnl/default_model/*.yaml` identical.
- Do not add a runtime dependency without saying why in the PR; the small surface is deliberate.


## Reporting security issues

See `SECURITY.md`. Please do not open public issues for anything that could let the engine act without authority.
