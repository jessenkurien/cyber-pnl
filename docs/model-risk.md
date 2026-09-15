# Model Risk and Limitations

A model that overstates its own precision is more dangerous than a heat map, because it will be trusted. This page is the leader's answer to "how could this be wrong," written before anyone asks.

## What the model is for

Comparing decisions under uncertainty: which control to keep, which proposal to fund, whether we are inside the board's appetite, what the insurance retention is worth. It is not a forecast of next year's loss, and it should never be presented as one.

## Known limitations

**The ranges are judgment.** Public benchmarks are context, not proof of a company-specific frequency
or loss range. The endpoint tornado shows which judgments deserve review first; it is not global
sensitivity analysis.

**Two kinds of uncertainty share one layer.** The current engine samples uncertain parameters and
year-to-year event variability together. Annual-loss p95 and p99 are distribution percentiles, not
confidence intervals around EAL. Second-order uncertainty analysis is a roadmap item.

**Scenarios are independent.** A real bad year is correlated: the same credential theft leads to ransomware *and* a data breach *and* a regulatory action. The model treats scenarios as independent Poisson processes, which understates the far tail (p99). Treat p99 as indicative, not planning-grade. Correlated scenario clusters are on the roadmap.

**Attribution is one-at-a-time.** Two independent controls that overlap on the same risk will each be credited with most of the reduction. Declared dependencies handle the prerequisite case (sensor → response) but not the substitute case. Shapley attribution fixes this and is planned; until then, do not sum control values.

**Control multipliers stack multiplicatively** and are floored at 5% combined. The floor is a guard against absurd claims, not a measurement.

**KPI curves are shaped, not fitted.** The logistic containment curve and the credential grade map are reasonable, monotonic, and documented, but they are not estimated from your data. Their parameters are assumptions and are in the register.

**Loss magnitudes use benchmark sources that are themselves biased.** Published incident cost studies over-represent large, reported, insured events. Your own history is the better calibration where it exists.

**The proposed-investment effects are estimates before the fact.** After implementation, replace the
estimate with measured evidence where possible and refresh the digest attestations.

**Counterfactual value is not causal proof.** Stable input streams reduce resampling noise, while the
result still depends on modeled effects, tags, dependencies, and replacement declarations.

**Recovery offsets are simplified.** An offset is sampled independently from gross loss and the event
total is floored at zero. Conditional recovery models would be more realistic when sufficient data
exists.

**Unpriced consequences are real.** The list is on the statement so that no one mistakes the dollar figure for the whole story.

## Controls on the model itself

Version control on every input; strict schema and reference validation; a digest-bound CFO/CISO
attestation workflow; an organization-ready publication gate; a seeded, reproducible simulation;
non-negative-loss and monotonic-control tests; a methodology page an auditor can check; and a
calibration log that compares estimates with actual incidents.

A digest attestation detects that inputs changed after review. It does not authenticate the reviewer's
identity. Use an authenticated corporate approval or cryptographic signing system when that assurance
is required.

## How to say it in the boardroom

"This is our best structured estimate, with its uncertainty shown, of a risk we already own. The value is in the comparisons it enables and the assumptions it forces us to write down, not in the exact figure. Here are the three assumptions that would change the answer, and here is who owns each."
