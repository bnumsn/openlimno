"""Preprocess module: load real-world data into WEDM. SPEC §4.0.

M1 physical deliverables:
- ``read_cross_sections`` — CSV / Excel cross-section tables
- ``read_adcp_qrev`` — USGS QRev CSV ADCP transects
- ``read_dem`` — GeoTIFF DEM rasters

M2 biological deliverables (SPEC §3.1.4.2):
- ``read_fish_sampling``, ``read_redd_count``, ``read_pit_tag_event``,
  ``read_rst_count``, ``read_edna_sample``, ``read_macroinvertebrate_sample``
- ``validate_biological_table`` — schema-validate a biological-observation DataFrame

M3+: HEC-RAS .g0X (best-effort), River2D .cdg (best-effort), TRDI/SonTek native.
"""

from __future__ import annotations

from .adcp import read_adcp_qrev
from .biological import (
    read_edna_sample,
    read_fish_sampling,
    read_macroinvertebrate_sample,
    read_pit_tag_event,
    read_redd_count,
    read_rst_count,
    validate_biological_table,
)
from .cross_section import (
    read_cross_sections,
    write_cross_sections_to_parquet,
)
from .dem import read_dem
from .legacy import read_hecras_geometry, read_river2d_cdg
from .mesh import MeshValidationReport, validate_ugrid_mesh

__all__ = [
    "MeshValidationReport",
    "read_adcp_qrev",
    "read_cross_sections",
    "read_dem",
    "read_edna_sample",
    "read_fish_sampling",
    "read_hecras_geometry",
    "read_macroinvertebrate_sample",
    "read_pit_tag_event",
    "read_redd_count",
    "read_river2d_cdg",
    "read_rst_count",
    "validate_biological_table",
    "validate_ugrid_mesh",
    "write_cross_sections_to_parquet",
]
