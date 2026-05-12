"""Chinese hydrology adapter framework (v0.8.2 P0, INTERFACE ONLY).

China's gauge-discharge data is published exclusively through
provincial / basin-level government portals (MWR, the 7 basin
commissions, and 16 provincial water bureaus). Together they cover
~9,700 stations — see ``docs/fetch_system.md`` §7 for the inventory.
**None of them expose a public REST API**: every working pipeline
against them is a reverse-engineered HTML / font-decryption crawler,
which:

1. Violates the OpenLimno "subscription-free public APIs only" charter
   (the data is "public" only in the sense the portal is reachable;
   programmatic access defies the publisher's terms of service for
   automated retrieval).
2. Carries operational risk (Cookie / CSRF / custom font tables drift
   every few months — a crawler that ships in OpenLimno's wheel can
   break the next morning).
3. Has regional compliance implications we don't want OpenLimno's
   downstream users to inherit silently by `pip install openlimno`.

This module therefore ships **the adapter interface only** — no
crawler code. Third-party plugins (e.g. an `openlimno-cn` package
not endorsed or maintained by the OpenLimno project) can register a
concrete adapter against this interface; the OpenLimno wheel itself
remains compliant with the v0.4 fetch-system charter.

To enable Chinese discharge in your local environment:

1. Audit your jurisdiction's rules for automated retrieval of
   provincial-portal data.
2. Install a third-party plugin that implements
   :class:`ChinaHydroAdapter` (none are officially maintained;
   dibiaoshui's ``crawler.hydrologic.hydro_sources`` is a reference
   implementation but its reverse-engineering surface drifts).
3. Register the adapter at runtime via :func:`register_adapter`.

Without (3), :func:`fetch_china_discharge` raises
``ChinaHydroNotEnabledError`` instead of attempting any network call.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import ClassVar

import pandas as pd

CN_HYDRO_CHARTER_NOTE = (
    "Chinese gauge-discharge data is reachable only through provincial / "
    "basin-commission HTML portals (no public REST). OpenLimno's wheel "
    "ships the ADAPTER INTERFACE only — no crawler code — to keep within "
    "the v0.4 fetch-system charter (subscription-free public APIs only). "
    "Install a third-party `openlimno-cn`-style plugin + register it via "
    "register_adapter(...) to enable. See docs/fetch_system.md §7."
)


class ChinaHydroNotEnabledError(RuntimeError):
    """Raised when ``fetch_china_discharge`` is called without a
    registered :class:`ChinaHydroAdapter` implementation."""


@dataclass
class ChinaDischargeResult:
    """Outcome shape that all :class:`ChinaHydroAdapter` implementations
    must return. Mirrors :class:`NWISFetchResult` for symmetry.

    Attributes:
        df: DataFrame with columns
            ``[time, discharge_m3s, water_level_m, station_id]``.
            ``time`` is ISO ``YYYY-MM-DD HH:MM:SS`` (mainland Beijing
            time, UTC+8) — adapter implementations MUST emit times in
            that timezone for consistency across provincial sources.
        station_id: station identifier echoed for provenance.
        source_name: human label of the upstream source (e.g.
            ``"mwr_river"`` / ``"beijing_swj"``).
        citation: APA-style citation string the adapter chose.
    """

    df: pd.DataFrame
    station_id: str
    source_name: str
    citation: str


class ChinaHydroAdapter(abc.ABC):
    """Pluggable interface for a Chinese discharge data source.

    Concrete implementations live OUTSIDE the OpenLimno wheel (in a
    third-party plugin) and register themselves via
    :func:`register_adapter`. The OpenLimno wheel never imports
    crawler / decryption code.

    Subclasses must set :attr:`source_key` (unique identifier used in
    CLI strings like ``cn-hydro:<source_key>:<station_id>:...``) and
    implement :meth:`fetch_discharge`.
    """

    #: Unique source identifier. Must match what users pass on the
    #: ``--fetch-discharge cn-hydro:<source_key>:...`` CLI string.
    source_key: ClassVar[str] = ""

    @abc.abstractmethod
    def fetch_discharge(
        self, station_id: str, start: str, end: str,
    ) -> ChinaDischargeResult:
        """Retrieve daily discharge for ``station_id`` over [start, end].

        Args:
            station_id: source-native station identifier.
            start, end: ISO ``YYYY-MM-DD``.
        """


_REGISTRY: dict[str, ChinaHydroAdapter] = {}


def register_adapter(adapter: ChinaHydroAdapter) -> None:
    """Register a concrete adapter under its ``source_key``.

    Third-party plugins call this at import time (or via an
    ``openlimno.cn_hydro_adapter`` entry point) so subsequent
    :func:`fetch_china_discharge` calls find the implementation.
    """
    key = adapter.source_key
    if not key:
        raise ValueError(
            "adapter.source_key must be a non-empty string; got "
            f"{key!r} (subclass of ChinaHydroAdapter)"
        )
    _REGISTRY[key] = adapter


def list_registered_adapters() -> list[str]:
    """Return the ``source_key``s currently registered. Empty by
    default — OpenLimno itself never registers anything here."""
    return sorted(_REGISTRY)


def fetch_china_discharge(
    source_key: str, station_id: str, start: str, end: str,
) -> ChinaDischargeResult:
    """Dispatch to the adapter registered under ``source_key``.

    Raises:
        ChinaHydroNotEnabledError: if no adapter is registered.
    """
    if source_key not in _REGISTRY:
        registered = list_registered_adapters()
        raise ChinaHydroNotEnabledError(
            f"No ChinaHydroAdapter registered for source_key="
            f"{source_key!r}. Currently registered: {registered or '(none)'}. "
            f"{CN_HYDRO_CHARTER_NOTE}"
        )
    return _REGISTRY[source_key].fetch_discharge(station_id, start, end)
