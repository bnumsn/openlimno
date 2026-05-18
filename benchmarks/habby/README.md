# HABBY equivalence — composite method matrix

> 3.x research route. v2.2.0 ships the contract; actual HABBY-Python
> cross-runs land in v3.x.

## Goal

Reproduce HABBY's three combination methods (product / geometric
mean / arithmetic mean — Le Coarer et al., INRAE Lyon) on a shared
test case and assert OpenLimno's `apply_overlay_per_cell` matches
each within **1e-6** relative error per cell.

The v1.6.0 — v2.1.0 composite-overlay surface explicitly modelled its
combination-rule menu on HABBY's. This benchmark exists to prove
that OpenLimno's per-cell engine is bit-for-bit equivalent on the
common subset.

## Reference platform

* **HABBY 0.6+** — Python; LGPL; redistributable. Source:
  [habby.gitlab.io](https://habby.gitlab.io/).
* HABBY is the *most* tractable of the three external comparison
  targets — pure Python, MIT-friendly ecosystem, no Wine. Expected
  to be the first reference platform actually wired in for v3.x.

## Adapter status

* `benchmarks/habby/adapter.py` — v2.2.0 stub. ``is_available()``
  attempts ``import habby`` and returns ``True`` if the package
  is importable; otherwise ``False``. ``run`` raises
  ``NotImplementedError`` (real bridge is v3.x).

## Acceptance threshold

`acceptance.yaml`:

```yaml
threshold:
  max_abs_m2: 1e-6
  max_rel: 1e-6
```

Tight because both engines should compute the same closed-form
formula. Any drift > 1e-6 indicates a math discrepancy worth
investigating.

## What v3.x adds

* `benchmarks/habby/bridge.py` — translates an OpenLimno case YAML
  into HABBY's project XML, runs HABBY headless, and reads the
  produced WUA-Q table back through the
  :class:`benchmarks._compare.ReferenceResult` interface.
* Pinned HABBY version in `benchmarks/habby/requirements.txt` for
  CI reproducibility.
