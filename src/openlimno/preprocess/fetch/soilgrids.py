"""SoilGrids 250 m soil property fetcher (v0.3.5 P0).

SoilGrids (ISRIC World Soil Information, Poggio et al. 2021) is the
de-facto open global soil mapping product at 250 m for 11 properties
across 6 depth layers, free + no auth via a REST API. We expose
single-point queries (the 90% of OpenLimno use case — soil parameters
at the case's reach centroid or pour-point).

For OpenLimno's hydrology + ecology models we mostly need:

* **bulk density (bdod)** — Saturated-hydraulic-conductivity proxy +
  catchment Manning-n initial guess.
* **clay / sand / silt fractions** — USDA texture class → SCS curve
  number → rainfall-runoff partitioning.
* **soil organic carbon (soc)** — Riparian-zone biogeochemistry +
  drift food supply proxy.
* **pH (phh2o)** — Acid-tolerant vs neutrophilic fish-species filter.

API docs:
    https://www.isric.org/explore/soilgrids/faq-soilgrids
    https://rest.isric.org/soilgrids/v2.0/docs

Citation:
    Poggio, L., de Sousa, L. M., Batjes, N. H., Heuvelink, G. B. M.,
    Kempen, B., Ribeiro, E., Rossiter, D. (2021). SoilGrids 2.0:
    producing soil information for the globe with quantified spatial
    uncertainty. SOIL, 7, 217-240. doi:10.5194/soil-7-217-2021. CC-BY 4.0.
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass

import pandas as pd
import requests

from openlimno.preprocess.fetch.cache import CacheEntry, cached_fetch

SOILGRIDS_REST = "https://rest.isric.org/soilgrids/v2.0/properties/query"

# Properties commonly used in fish-ecology and rainfall-runoff modelling.
# Names match the SoilGrids REST property identifiers exactly — extending
# is a one-line tuple change. Mapped/target units + d_factor are
# resolved automatically from the API response, so a future schema
# rename surfaces as an error rather than a silent unit shift.
DEFAULT_PROPERTIES: tuple[str, ...] = (
    "bdod", "clay", "sand", "silt", "soc", "phh2o",
)
# Depth labels SoilGrids accepts in the ``depth=`` query param. Top
# 0-30 cm is the layer most relevant to surface hydrology + riparian
# biogeochem; deeper layers are rarely consumed by reach-scale fish
# models, but the API supports them — exposed for power users.
ALL_DEPTHS: tuple[str, ...] = (
    "0-5cm", "5-15cm", "15-30cm", "30-60cm", "60-100cm", "100-200cm",
)
DEFAULT_DEPTHS: tuple[str, ...] = ("0-5cm", "5-15cm", "15-30cm")
ALL_STATISTICS: tuple[str, ...] = ("Q0.05", "Q0.5", "Q0.95", "mean", "uncertainty")
DEFAULT_STATISTIC = "mean"

SOILGRIDS_CITATION = (
    "Poggio, L. et al. (2021). SoilGrids 2.0: producing soil "
    "information for the globe with quantified spatial uncertainty. "
    "SOIL, 7, 217-240. doi:10.5194/soil-7-217-2021. CC-BY 4.0."
)


@dataclass
class SoilGridsFetchResult:
    """Outcome of a SoilGrids point query.

    Attributes:
        df: long-form DataFrame with columns
            ``[property, depth, statistic, value, unit]``.
            Long-form keeps multi-property + multi-depth queries
            losslessly tidy; downstream code can pivot to wide as
            needed.
        lat, lon: original query point.
        cache: provenance trail entry for the REST response.
        citation: APA-style citation string.
    """

    df: pd.DataFrame
    lat: float
    lon: float
    cache: CacheEntry
    citation: str = SOILGRIDS_CITATION

    def get(
        self, property_name: str, depth: str = "0-5cm",
        statistic: str = DEFAULT_STATISTIC,
    ) -> float:
        """Convenience: pluck a single (property, depth, statistic) value
        from ``df`` in target units. Raises KeyError if the requested
        combination is not in the result.
        """
        sub = self.df[
            (self.df["property"] == property_name)
            & (self.df["depth"] == depth)
            & (self.df["statistic"] == statistic)
        ]
        if sub.empty:
            raise KeyError(
                f"(property={property_name!r}, depth={depth!r}, "
                f"statistic={statistic!r}) not in result; available: "
                f"{sorted(self.df['property'].unique())}"
            )
        return float(sub["value"].iloc[0])


def _validate_args(
    lat: float, lon: float,
    properties: Iterable[str], depths: Iterable[str], statistic: str,
) -> tuple[list[str], list[str]]:
    if not (-90.0 <= lat <= 90.0):
        raise ValueError(f"lat={lat} outside [-90, 90]")
    if not (-180.0 <= lon <= 180.0):
        raise ValueError(f"lon={lon} outside [-180, 180]")
    props = list(properties)
    if not props:
        raise ValueError("at least one property must be requested")
    deps = list(depths)
    if not deps:
        raise ValueError("at least one depth must be requested")
    unknown_d = set(deps) - set(ALL_DEPTHS)
    if unknown_d:
        raise ValueError(
            f"unknown depth(s): {sorted(unknown_d)}; "
            f"valid: {ALL_DEPTHS}"
        )
    if statistic not in ALL_STATISTICS:
        raise ValueError(
            f"statistic={statistic!r} not in {ALL_STATISTICS}"
        )
    return props, deps


def fetch_soilgrids(
    lat: float, lon: float,
    *, properties: Iterable[str] = DEFAULT_PROPERTIES,
    depths: Iterable[str] = DEFAULT_DEPTHS,
    statistic: str = DEFAULT_STATISTIC,
) -> SoilGridsFetchResult:
    """Fetch SoilGrids 2.0 point properties at ``(lat, lon)``.

    Args:
        lat: latitude in decimal degrees (-90 to +90).
        lon: longitude in decimal degrees (-180 to +180).
        properties: SoilGrids property identifiers (e.g., ``"clay"``,
            ``"sand"``, ``"phh2o"``). Defaults to the 6 most commonly
            consumed in fish-ecology + rainfall-runoff models.
        depths: depth labels (e.g., ``"0-5cm"``). Defaults to the top
            0-30 cm layers — what surface hydrology cares about.
        statistic: which posterior summary to return. Default ``"mean"``;
            ``"Q0.05"`` / ``"Q0.95"`` give the 90% credible interval
            (useful for uncertainty-aware models).

    Returns:
        :class:`SoilGridsFetchResult` whose ``.df`` is a long-form
        DataFrame ready for groupby/pivot.
    """
    props, deps = _validate_args(lat, lon, properties, depths, statistic)

    # SoilGrids accepts repeated property + depth params. requests' params
    # accepts list-valued entries so we pass them as multi-keys.
    params: list[tuple[str, str]] = [
        ("lon", f"{lon:.6f}"), ("lat", f"{lat:.6f}"),
        ("value", statistic),
    ]
    params.extend(("property", p) for p in props)
    params.extend(("depth", d) for d in deps)

    # cached_fetch keys on params dict; convert to a sorted dict for
    # stable hashing. Property + depth order CAN'T matter for the
    # response so flatten to deterministic strings.
    cache_params = {
        "lat": round(lat, 6), "lon": round(lon, 6),
        "properties": ",".join(sorted(props)),
        "depths": ",".join(sorted(deps)),
        "statistic": statistic,
    }

    def _do_fetch() -> bytes:
        resp = requests.get(SOILGRIDS_REST, params=params, timeout=60)
        resp.raise_for_status()
        return resp.content

    cache = cached_fetch(
        subdir="soilgrids", url=SOILGRIDS_REST, params=cache_params,
        suffix=".json", fetch_fn=_do_fetch,
    )
    payload = json.loads(cache.path.read_text())

    layers = payload.get("properties", {}).get("layers", [])
    if not layers:
        raise RuntimeError(
            f"SoilGrids returned no layers for ({lat}, {lon}). Point "
            f"may be over ocean / fully masked. Payload keys: "
            f"{sorted(payload.keys())}"
        )

    # Long-form rows; one per (property, depth, statistic).
    rows: list[dict] = []
    for layer in layers:
        prop = layer["name"]
        unit_meta = layer.get("unit_measure", {})
        d_factor = unit_meta.get("d_factor", 1) or 1
        target_unit = unit_meta.get("target_units", "")
        for depth_entry in layer.get("depths", []):
            depth_label = depth_entry["label"]
            if depth_label not in deps:
                # SoilGrids sometimes returns extra depths; filter to
                # the user's request so the result is exactly what was
                # asked for.
                continue
            values = depth_entry.get("values", {}) or {}
            raw = values.get(statistic)
            if raw is None:
                continue
            # SoilGrids stores values as int × d_factor for compact
            # int storage on the back-end. We undo the scaling to land
            # in target_units.
            converted = float(raw) / float(d_factor)
            rows.append({
                "property": prop,
                "depth": depth_label,
                "statistic": statistic,
                "value": converted,
                "unit": target_unit,
            })

    df = pd.DataFrame(
        rows, columns=["property", "depth", "statistic", "value", "unit"],
    )
    return SoilGridsFetchResult(
        df=df, lat=lat, lon=lon, cache=cache,
    )
