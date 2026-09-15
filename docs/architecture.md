# Architecture

```
  model/                          cyberpnl/
  ├─ business.yaml   (Finance)    ├─ models.py        pydantic schemas · Range · digest · verify
  ├─ scenarios.yaml  (owners)     ├─ distributions.py PERT · lognormal(90% CI) · fixed
  ├─ controls.yaml   (owners)     ├─ kpis.py          measured number → multiplier · importers (72md, wormprint)
  ├─ appetite.yaml   (Board)      ├─ engine.py        Monte Carlo · matched streams · investments · sensitivity · appetite
  ├─ kpis.yaml       (measured)   ├─ report.py        statement HTML/MD/JSON · exceedance · bars · tornado (inline SVG)
  ├─ sources.yaml                 ├─ calibrate.py     equivalent-bet wizard
  └─ register.yaml   (CFO, CISO)  └─ cli.py           validate · statement · invest · explain · register · attest · verify
```

Data flow: `load_model()` validates the seven YAML files into one `Model`. `simulate()` samples ranges through a seeded numpy Generator, applies control multipliers per scenario, draws Poisson event counts, sums component costs, and returns per-scenario and total annual-loss arrays. `control_values()` and `investment_cases()` call `simulate()` with controls excluded or included under the same seed. `sensitivity()` pins one input at a time. `statement_*()` render.

Design decisions: numpy only, so the engine stays inspectable; no runtime data downloads; strict YAML schemas; stable integer seed coordinates for every scenario, control effect, event process, and component; explicit recovery offsets with a zero-loss floor; replacement semantics for upgrade proposals; and inline SVG charts, so the HTML statement is self-contained.

The distribution bundled in `cyberpnl/default_model/` mirrors the editable top-level `model/` sample.
CI verifies that the two copies remain identical and smoke-tests the installed wheel from outside the
source tree.

Extending: a new component kind is one branch in `_component_cost`; a new KPI curve is one function registered in `CURVES`; a new importer is one function in `kpis.py` and one CLI option.
