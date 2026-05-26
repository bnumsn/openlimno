"""Native individual-based population model.

This package is OpenLimno's non-NetLogo path for inSTREAM-style workflows.
It does not depend on NetLogo and is designed to consume OpenLimno
habitat-cell tables directly.

Public API surface (in ``__all__``, stable contract):
    - ``run_ibm_scenario``: top-level scenario runner; the user-facing entry.
    - ``validate_ibm_scenario`` / ``load_ibm_scenario``: scenario IO.
    - ``run_native_ibm``: alternative direct-config runner.
    - ``NativeIBMConfig`` / ``NativeIBMResult`` / ``SpeciesProfile``:
      core dataclasses (config and output shapes).
    - ``run_instream7_official_benchmark`` / ``Instream7BenchmarkResult``:
      inSTREAM 7 comparison entry + result type.
    - ``IBM_SCHEMA_VERSION``: schema-version constant.

Internal helpers (Studio handlers, parsers, submodel registry, GIS bridge,
NetLogo reference runner, calibration / ensemble drivers, acceptance
reporting) remain importable via their concrete submodule paths
(e.g. ``from openlimno.ibm.studio import run_ibm_studio``) but are NOT in
``__all__``. They are considered subject to refactor until the
R-IBM-GOD-OBJECT track lands.

2026-05-26 R-IBM-API-SHRINK: per ADR-0016 cleanup track and round-22
codex A2 + gemini A2, ``__all__`` was reduced from 68 symbols to 10
stable public contracts.
"""

# Keep the imports — internal cross-module usage relies on them, and
# the symbols ARE reachable; they just aren't re-exported as the
# package's public contract.
from .acceptance import (  # noqa: F401
    IBMAcceptanceItem,
    build_ibm_acceptance_report,
    write_ibm_acceptance_report,
)
from .events import (  # noqa: F401
    daily_event_summary,
    summarize_events,
    write_event_report,
)
from .experiments import (  # noqa: F401
    IBMCalibrationResult,
    IBMEnsembleResult,
    parse_parameter_grid,
    run_ibm_abc_calibration,
    run_ibm_calibration,
    run_ibm_ensemble,
)
from .instream7 import (  # noqa: F401
    Instream7BenchmarkResult,
    Instream7Case,
    Instream7NetLogoReferenceResult,
    Instream7Reach,
    build_population_from_official_adult_arrivals,
    build_population_from_official_initial,
    compare_instream7_native_to_brief,
    discover_instream7_cases,
    extract_instream7_archive,
    parse_instream7_case,
    prepare_instream7_netlogo_reference_case,
    read_instream7_brief_population,
    read_official_adult_arrivals,
    read_official_initial_population,
    read_official_time_series,
    run_instream7_netlogo_reference,
    run_instream7_official_benchmark,
    species_profile_from_official_case,
    summarize_instream7_brief_population,
    summarize_instream7_parity,
    write_instream7_netlogo_setup_file,
    write_instream7_parity_report,
)
from .native import (  # noqa: F401
    NativeIBMConfig,
    NativeIBMResult,
    SpeciesProfile,
    build_initial_population,
    run_native_ibm,
    write_native_ibm_result,
)
from .runtime_submodels import (  # noqa: F401
    BioenergeticGrowthModel,
    CalibratedReddPlacementModel,
    CrossReachMovementModel,
    GrowthRiskHabitatModel,
    NetworkMovementModel,
    ReddRecruitmentModel,
    SizePriorityCellChooser,
)
from .scenario import (  # noqa: F401
    IBM_SCHEMA_VERSION,
    load_ibm_scenario,
    load_ibm_schema,
    load_species_profile,
    run_ibm_scenario,
    validate_ibm_scenario,
    validate_species_profile,
    write_species_profile,
)
from .studio import (  # noqa: F401
    compare_instream7_for_studio,
    default_studio_scenario,
    import_gis_for_studio,
    run_ibm_studio,
    run_instream7_benchmark_for_studio,
    run_studio_calibration,
    run_studio_ensemble,
    run_studio_scenario,
    validate_studio_payload,
    write_studio_scenario_files,
)
from .submodels import (  # noqa: F401
    IBMSubmodel,
    default_submodel_selection,
    list_ibm_submodels,
    resolve_submodel_selection,
    validate_submodel_selection,
)

# Public API contract — keep this short and stable.
__all__ = [
    "IBM_SCHEMA_VERSION",
    "Instream7BenchmarkResult",
    "NativeIBMConfig",
    "NativeIBMResult",
    "SpeciesProfile",
    "load_ibm_scenario",
    "run_ibm_scenario",
    "run_instream7_official_benchmark",
    "run_native_ibm",
    "validate_ibm_scenario",
]
