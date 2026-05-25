"""Preprocess module: load real-world data into WEDM. SPEC §4.0.

M1 physical deliverables:
- ``read_cross_sections`` — CSV / Excel cross-section tables
- ``read_adcp_qrev`` — USGS QRev CSV ADCP transects
- ``read_dem`` — GeoTIFF DEM rasters

M2 biological deliverables (SPEC §3.1.4.2):
- ``read_fish_sampling``, ``read_redd_count``, ``read_pit_tag_event``,
  ``read_rst_count``, ``read_edna_sample``, ``read_macroinvertebrate_sample``
- ``validate_biological_table`` — schema-validate a biological-observation DataFrame

M3+: interoperability registry for HEC-RAS, River2D, TELEMAC, Delft3D,
MIKE, HABBY, and IBM exchange paths. Implemented core importers remain
best-effort where upstream formats are legacy/private.
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
from .habitat_exchange import (
    HabitatExchangeImportResult,
    HabitatExchangeImportSummary,
    HabitatExchangeInspection,
    inspect_habitat_exchange,
    read_habitat_exchange,
)
from .hecras_hdf import (
    HDFDatasetInfo,
    HECRASHDFImportResult,
    HECRASHDFImportSummary,
    HECRASHDFInspection,
    inspect_hecras_hdf,
    read_hecras_hdf,
)
from .hecras_mesh import HECRASMeshExportResult, write_hecras_gis_ugrid
from .instream_netlogo import (
    InstreamExchangeInspection,
    InstreamHabitatExportResult,
    InstreamImportResult,
    InstreamImportSummary,
    inspect_instream_exchange,
    prepare_instream_habitat_exchange,
    read_instream_exchange,
    write_instream_exchange,
)
from .interoperability import (
    EXTERNAL_MODEL_SUPPORT,
    ExternalModelImportResult,
    ExternalModelSupport,
    infer_external_model,
    list_external_model_support,
    read_external_model,
)
from .legacy import (
    read_hecras_geometry,
    read_river2d_cdg,
    read_river2d_elements,
    write_river2d_ugrid,
)
from .mesh import MeshValidationReport, validate_ugrid_mesh
from .mike import (
    MIKEImportResult,
    MIKEImportSummary,
    MIKEInspection,
    MIKERuntimeDiagnostic,
    diagnose_mike_environment,
    inspect_mike_file,
    read_mike_file,
)
from .netcdf_hydraulic import (
    NetCDFHydraulicImportResult,
    NetCDFHydraulicImportSummary,
    NetCDFHydraulicInspection,
    NetCDFVariableInfo,
    inspect_netcdf_hydraulic,
    read_netcdf_hydraulic,
)
from .telemac_slf import (
    SelafinVariableInfo,
    TelemacSelafinImportResult,
    TelemacSelafinImportSummary,
    TelemacSelafinInspection,
    inspect_telemac_selafin,
    read_telemac_selafin,
)

__all__ = [
    "EXTERNAL_MODEL_SUPPORT",
    "ExternalModelImportResult",
    "ExternalModelSupport",
    "HDFDatasetInfo",
    "HECRASHDFImportResult",
    "HECRASHDFImportSummary",
    "HECRASHDFInspection",
    "HECRASMeshExportResult",
    "HabitatExchangeImportResult",
    "HabitatExchangeImportSummary",
    "HabitatExchangeInspection",
    "InstreamExchangeInspection",
    "InstreamHabitatExportResult",
    "InstreamImportResult",
    "InstreamImportSummary",
    "MIKEImportResult",
    "MIKEImportSummary",
    "MIKEInspection",
    "MIKERuntimeDiagnostic",
    "MeshValidationReport",
    "NetCDFHydraulicImportResult",
    "NetCDFHydraulicImportSummary",
    "NetCDFHydraulicInspection",
    "NetCDFVariableInfo",
    "SelafinVariableInfo",
    "TelemacSelafinImportResult",
    "TelemacSelafinImportSummary",
    "TelemacSelafinInspection",
    "diagnose_mike_environment",
    "infer_external_model",
    "inspect_habitat_exchange",
    "inspect_hecras_hdf",
    "inspect_instream_exchange",
    "inspect_mike_file",
    "inspect_netcdf_hydraulic",
    "inspect_telemac_selafin",
    "list_external_model_support",
    "prepare_instream_habitat_exchange",
    "read_adcp_qrev",
    "read_cross_sections",
    "read_dem",
    "read_edna_sample",
    "read_external_model",
    "read_fish_sampling",
    "read_habitat_exchange",
    "read_hecras_geometry",
    "read_hecras_hdf",
    "read_instream_exchange",
    "read_macroinvertebrate_sample",
    "read_mike_file",
    "read_netcdf_hydraulic",
    "read_pit_tag_event",
    "read_redd_count",
    "read_river2d_cdg",
    "read_river2d_elements",
    "read_rst_count",
    "read_telemac_selafin",
    "validate_biological_table",
    "validate_ugrid_mesh",
    "write_cross_sections_to_parquet",
    "write_hecras_gis_ugrid",
    "write_instream_exchange",
    "write_river2d_ugrid",
]
