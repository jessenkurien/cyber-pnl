## Decision and scope

- What decision or user problem does this change improve?
- What is intentionally outside scope?

## Evidence and model risk

- What evidence supports the change?
- What assumptions, uncertainty, or failure modes remain?

## Verification

- [ ] I used only fictional or redacted test data.
- [ ] I added or updated tests for model/engine/curve behavior.
- [ ] Existing monotonicity and counterfactual-integrity tests remain green.
- [ ] `model/*.yaml` and `cyberpnl/default_model/*.yaml` remain identical.
- [ ] Formatting, lint, tests, and the illustrative sample-model gate pass.
- [ ] Documentation, changelog, and citations are updated where needed.
- [ ] No runtime dependency was added without a documented reason.
