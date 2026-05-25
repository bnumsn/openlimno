from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import openlimno.ibm.instream7 as instream7
from openlimno.ibm import (
    build_population_from_official_adult_arrivals,
    build_population_from_official_initial,
    compare_instream7_native_to_brief,
    parse_instream7_case,
    read_instream7_brief_population,
    read_official_adult_arrivals,
    read_official_initial_population,
    read_official_time_series,
    species_profile_from_official_case,
    summarize_instream7_brief_population,
    summarize_instream7_parity,
    write_instream7_parity_report,
)
from openlimno.ibm.instream7 import _interpolate_hydraulic_table


def _write_minimal_official_case(root: Path) -> Path:
    project = root / "Example-Project-A_1Reach-1Species"
    project.mkdir()
    (project / "parameters-ExampleA.nls").write_text(
        """
to set-parameters
  set start-date "10/1/2001"
  set end-date "9/30/2011"
  set GIS-file-name "Example-Project-A_1Reach-1Species/Shapefile/ExampleA.shp"
  set initial-population-file "Example-Project-A_1Reach-1Species/ExampleA-InitialPopulations.csv"
  set GIS-property-for-cell-ID "ID_TEXT"
  set GIS-property-for-cell-reach-name "REACH_NAME"
  set GIS-property-for-cell-area "AREA"
  set GIS-property-for-cell-num-hiding-places "NUM_HIDING"
  set GIS-property-for-cell-frac-vel-shelter "FRACVSHL"
  set GIS-property-for-cell-frac-spawn "FRACSPWN"
  set reach-names (list "ExampleA")
  set time-series-input-files (list "Example-Project-A_1Reach-1Species/ExampleA-TimeSeriesInputs.csv")
  set depth-file-names (list "Example-Project-A_1Reach-1Species/ExampleA-Depths.csv")
  set velocity-file-names (list "Example-Project-A_1Reach-1Species/ExampleA-Vels.csv")
  set species-list (list "Rainbow")
  set trout-spawn-start-day (list time:create "4/1")
  set trout-spawn-end-day (list time:create "6/30")
  set trout-spawn-fecund-mult (list 0.18)
  set trout-spawn-fecund-exp (list 2.51)
  set trout-spawn-egg-viability (list 0.8)
  set trout-spawn-min-length (list 12)
  set trout-emerge-length-mode (list 2.8)
  set trout-weight-A (list 0.0185)
  set trout-weight-B (list 2.90)
  set trout-cmax-A (list 0.628)
  set trout-cmax-B (list 0.7)
  set trout-resp-A (list 36)
  set trout-resp-B (list 0.783)
  set trout-resp-C (list 0.0020)
  set trout-resp-D (list 1.4)
  set mort-redd-dewater-surv (list 0.9)
  set mort-redd-scour-depth (list 5.0)
  set mort-high-temp-T1 (list 30.0)
  set mort-high-temp-T9 (list 25.8)
  let Rainbow-cmax-table table:make
  table:put Rainbow-cmax-table 0.0 0.05
  table:put Rainbow-cmax-table 22.0 1.0
  table:put Rainbow-cmax-table 30.0 0.0
end
""".strip(),
        encoding="utf-8",
    )
    (project / "ExampleA-InitialPopulations.csv").write_text(
        "; Trout initialization input for InSTREAM-7,,,,,,\n"
        "; Species,Reach,Age,Number,Length min,Length mode,Length max\n"
        "Rainbow,ExampleA,0,3,4,6,7\n"
        "Rainbow,ExampleA,1,2,9,12,15\n",
        encoding="utf-8",
    )
    (project / "ExampleA-TimeSeriesInputs.csv").write_text(
        "; Time series inputs for Example Project A\n"
        "Date,temperature,flow,turbidity\n"
        "10/1/2001 12:00,13.1,6.37,2\n",
        encoding="utf-8",
    )
    return project / "parameters-ExampleA.nls"


def test_parse_instream7_case_parameter_file(tmp_path: Path) -> None:
    param = _write_minimal_official_case(tmp_path)
    case = parse_instream7_case(tmp_path, param)

    assert case.case_id == "ExampleA"
    assert case.species == ("Rainbow",)
    assert case.start_date == "10/1/2001"
    assert case.adult_arrival_file is None
    assert case.reaches[0].reach_id == "ExampleA"
    assert case.reaches[0].depth_file.name == "ExampleA-Depths.csv"



def _write_minimal_netlogo_model(root: Path, case_id: str = "ExampleA") -> Path:
    model = root / f"InSTREAM7.4_2026-02-06_{case_id}.nlogox"
    model.write_text(
        """
<model>
  <experiments>
    <experiment name="experiment" repetitions="5" sequentialRunOrder="true" runMetricsEveryStep="true">
      <setup>setup</setup>
      <go>go</go>
      <metrics>
        <metric>formatted-sim-time</metric>
        <metric>light-phase</metric>
        <metric>RT-age-0-abund</metric>
      </metrics>
      <constants>
        <enumeratedValueSet variable="brief-pop-output?"><value value="false" /></enumeratedValueSet>
      </constants>
    </experiment>
  </experiments>
</model>
""".strip(),
        encoding="utf-8",
    )
    return model



def test_write_instream7_netlogo_setup_file_uses_model_metrics(tmp_path: Path) -> None:
    model = _write_minimal_netlogo_model(tmp_path)
    setup = instream7.write_instream7_netlogo_setup_file(
        model,
        tmp_path / "openlimno-reference.xml",
        seed=17,
    )

    text = setup.read_text(encoding="utf-8")
    assert '<experiment name="openlimno-reference" repetitions="1"' in text
    assert "<metric>formatted-sim-time</metric>" in text
    assert "<metric>RT-age-0-abund</metric>" in text
    assert 'variable="brief-pop-output?"' in text
    assert 'value="true"' in text
    assert 'variable="random-number-seed"' in text
    assert 'value="17"' in text


def test_prepare_instream7_netlogo_reference_case_copies_and_shortens_case(tmp_path: Path) -> None:
    _write_minimal_official_case(tmp_path)
    _write_minimal_netlogo_model(tmp_path)

    result = instream7.prepare_instream7_netlogo_reference_case(
        tmp_path,
        tmp_path.parent / f"{tmp_path.name}-netlogo-run",
        case_id="ExampleA",
        days=3,
        seed=19,
    )

    copied_param = result.case_root / "Example-Project-A_1Reach-1Species" / "parameters-ExampleA.nls"
    copied_param_text = copied_param.read_text(encoding="utf-8")
    assert 'set end-date   "10/3/2001"' in copied_param_text
    assert 'set file-output-units "days"' in copied_param_text
    assert "set file-output-frequency  1" in copied_param_text
    assert result.model_file.exists()
    assert result.setup_file.exists()
    assert result.table_path.name == "openlimno_netlogo_table.csv"
    assert result.spreadsheet_path.name == "openlimno_netlogo_spreadsheet.csv"
    assert result.brief_population_files == ()
    assert 'value="19"' in result.setup_file.read_text(encoding="utf-8")


def test_prepare_instream7_netlogo_reference_case_rejects_output_inside_source(tmp_path: Path) -> None:
    _write_minimal_official_case(tmp_path)
    _write_minimal_netlogo_model(tmp_path)

    with pytest.raises(ValueError, match="output_dir must not be inside"):
        instream7.prepare_instream7_netlogo_reference_case(
            tmp_path,
            tmp_path / "nested-output",
            case_id="ExampleA",
            days=2,
        )


def test_read_official_initial_population_and_expand(tmp_path: Path) -> None:
    param = _write_minimal_official_case(tmp_path)
    case = parse_instream7_case(tmp_path, param)
    initial = read_official_initial_population(case.initial_population_file)
    pop = build_population_from_official_initial(
        initial,
        reach_id="ExampleA",
        species="Rainbow",
        seed=1,
    )

    assert int(initial["Number"].sum()) == 5
    assert len(pop) == 5
    assert set(pop["species"]) == {"Rainbow"}
    assert pop["length_mm"].between(40.0, 150.0).all()


def test_read_official_adult_arrivals_and_build_schedule(tmp_path: Path) -> None:
    arrivals_path = tmp_path / "AdultArrivals.csv"
    arrivals_path.write_text(
        "; Adult arrival input for InSALMO-7,,,,,,,,,,\n"
        "; Year,Species,Reach,Number,Fraction female,Arrival start,Arrival peak,Arrival end,Length min,Length mode,Length max\n"
        "2011,Chinook-Spring,ExampleA,5,0.6,4/1/2011,4/3/2011,4/5/2011,40,60,70\n",
        encoding="utf-8",
    )
    arrivals = read_official_adult_arrivals(arrivals_path)
    scheduled = build_population_from_official_adult_arrivals(
        arrivals,
        reach_id="ExampleA",
        species="Chinook-Spring",
        start_date="4/1/2011",
        days=5,
        seed=3,
        first_fish_id=10,
    )

    assert int(arrivals["Number"].sum()) == 5
    assert len(scheduled) == 5
    assert scheduled["fish_id"].min() == 10
    assert scheduled["arrival_day"].between(1, 5).all()
    assert scheduled["length_mm"].between(400.0, 700.0).all()


def test_read_official_time_series_normalises_columns(tmp_path: Path) -> None:
    param = _write_minimal_official_case(tmp_path)
    case = parse_instream7_case(tmp_path, param)
    forcing = read_official_time_series(case.reaches[0].time_series_file)

    assert list(forcing.columns) == ["date", "temperature_c", "flow_m3s", "turbidity_ntu"]
    assert forcing["flow_m3s"].iloc[0] == 6.37
    assert isinstance(forcing["date"].iloc[0], pd.Timestamp)


def test_species_profile_from_official_case_maps_spawn_parameters(tmp_path: Path) -> None:
    param = _write_minimal_official_case(tmp_path)
    case = parse_instream7_case(tmp_path, param)
    profile = species_profile_from_official_case(case, "Rainbow")

    assert profile.species == "Rainbow"
    assert profile.maturity_length_mm == 120.0
    assert profile.spawn_start_day == 91
    assert profile.spawn_end_day == 181
    assert profile.fry_length_mm == 28.0
    assert profile.fecundity_length_exponent == pytest.approx(2.51)
    assert profile.fecundity_reference_length_mm == 120.0
    assert profile.weight_a_g_per_cm_b == pytest.approx(0.0185)
    assert profile.weight_b == pytest.approx(2.90)
    assert profile.thermal_optimum_c == pytest.approx(22.0)
    assert profile.redd_dewatering_mortality == pytest.approx(0.1)
    assert profile.redd_min_depth_m == pytest.approx(0.05)
    assert profile.base_daily_survival == pytest.approx(0.999)
    assert profile.predation_base_risk == pytest.approx(0.001)
    assert profile.predation_csi_risk == pytest.approx(0.002)
    assert profile.thermal_stress_mortality == pytest.approx(0.005)


def test_compare_instream7_native_to_brief_flags_tolerance_exceedances() -> None:
    native = pd.DataFrame(
        {
            "scenario_id": ["ExampleA", "ExampleA"],
            "reach_id": ["ExampleA", "ExampleA"],
            "species": ["Rainbow", "Rainbow"],
            "day": [0, 1],
            "official_date": ["2001-10-01", "2001-10-02"],
            "abundance": [360, 350],
            "biomass_g": [2400.0, 2510.0],
            "mean_length_mm": [61.1, 63.0],
        }
    )
    brief_summary = pd.DataFrame(
        {
            "behaviorspace_run": [1, 1],
            "end_time": ["10/1/2001 00:00", "10/2/2001 00:00"],
            "end_timestamp": pd.to_datetime(["2001-10-01", "2001-10-02"]),
            "reach_id": ["ExampleA", "ExampleA"],
            "species": ["Rainbow", "Rainbow"],
            "abundance": [360, 355],
            "biomass_g": [2400.0, 2600.0],
            "mean_length_mm": [61.0, 66.0],
        }
    )

    comparison = compare_instream7_native_to_brief(
        native,
        brief_summary,
        abundance_tolerance=2,
        biomass_relative_tolerance=0.05,
        mean_length_tolerance_mm=1.0,
    ).set_index("comparison_day")

    assert bool(comparison.loc[0, "passed"])
    assert not bool(comparison.loc[1, "passed"])
    assert comparison.loc[1, "comparison_note"] == "outside_tolerance"
    assert comparison.loc[1, "abundance_abs_delta"] == pytest.approx(5.0)

    parity = summarize_instream7_parity(comparison.reset_index())
    assert int(parity["failed_rows"].sum()) == 1


def test_write_instream7_parity_report_writes_detail_and_summary(tmp_path: Path) -> None:
    comparison = pd.DataFrame(
        {
            "scenario_id": ["s1"],
            "reach_id": ["r1"],
            "species": ["Rainbow"],
            "comparison_day": [0],
            "abundance_abs_delta": [0.0],
            "biomass_relative_delta": [0.0],
            "mean_length_abs_delta_mm": [0.0],
            "matched": [True],
            "passed": [True],
        }
    )

    paths = write_instream7_parity_report(comparison, tmp_path / "parity.csv")

    assert Path(paths["instream7_parity_detail"]).exists()
    assert Path(paths["instream7_parity_summary"]).exists()


def test_next_global_fish_id_after_handles_empty_frame() -> None:
    assert instream7._next_global_fish_id_after(pd.DataFrame(columns=["fish_id"]), 7) == 7
    assert instream7._next_global_fish_id_after(pd.DataFrame({"fish_id": [2, 5]}), 7) == 7
    assert instream7._next_global_fish_id_after(pd.DataFrame({"fish_id": [8]}), 7) == 9


def test_hydraulic_interpolation_rejects_out_of_range_flow() -> None:
    wide = pd.DataFrame(
        {
            "cell_id": ["a", "b"],
            1.0: [0.2, 0.4],
            2.0: [0.3, 0.5],
        }
    )

    with pytest.raises(ValueError, match="outside depth_m lookup range"):
        _interpolate_hydraulic_table(wide, "depth_m", 0.5)


def test_official_benchmark_preserves_redds_across_days(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reach = instream7.Instream7Reach(
        case_id="Synthetic",
        reach_id="Reach",
        time_series_file=Path("time.csv"),
        depth_file=Path("depth.csv"),
        velocity_file=Path("velocity.csv"),
        shapefile=Path("cells.shp"),
        cell_id_field="ID_TEXT",
        reach_field="REACH_NAME",
        area_field="AREA",
        hiding_places_field="NUM_HIDING",
        velocity_shelter_field="FRACVSHL",
        spawning_fraction_field="FRACSPWN",
    )
    case = instream7.Instream7Case(
        case_id="Synthetic",
        root=tmp_path,
        parameter_file=tmp_path / "parameters-Synthetic.nls",
        initial_population_file=tmp_path / "initial.csv",
        start_date="1/1/2001",
        end_date="1/3/2001",
        species=("Rainbow",),
        reaches=(reach,),
        parameters={
            "trout-spawn-start-day": ("1/1",),
            "trout-spawn-end-day": ("1/1",),
            "trout-spawn-fecund-mult": (4.0,),
            "trout-spawn-fecund-exp": (0.0,),
            "trout-spawn-egg-viability": (1.0,),
            "trout-spawn-min-length": (12.0,),
            "trout-emerge-length-mode": (2.8,),
        },
    )
    initial = pd.DataFrame(
        {
            "Species": ["Rainbow"],
            "Reach": ["Reach"],
            "Age": [2],
            "Number": [2],
            "Length min": [17.0],
            "Length mode": [18.0],
            "Length max": [19.0],
        }
    )
    forcing = pd.DataFrame(
        {
            "date": pd.to_datetime(["2001-01-01", "2001-01-02", "2001-01-03"]),
            "flow_m3s": [1.0, 1.0, 1.0],
            "temperature_c": [12.0, 12.0, 12.0],
            "turbidity_ntu": [0.0, 0.0, 0.0],
        }
    )
    static = pd.DataFrame(
        {
            "cell_id": ["cell-1"],
            "reach_id": ["Reach"],
            "area_m2": [100.0],
            "hiding_cover": [1.0],
            "feeding_cover": [1.0],
            "spawning_cover": [1.0],
        }
    )
    depth = pd.DataFrame({"cell_id": ["cell-1"], 1.0: [0.5]})
    velocity = pd.DataFrame({"cell_id": ["cell-1"], 1.0: [0.2]})

    monkeypatch.setattr(instream7, "discover_instream7_cases", lambda root: (case,))
    monkeypatch.setattr(instream7, "read_official_initial_population", lambda path: initial.copy())
    monkeypatch.setattr(instream7, "read_official_time_series", lambda path: forcing.copy())
    monkeypatch.setattr(instream7, "read_reach_static_cells", lambda reach: static.copy())
    monkeypatch.setattr(
        instream7,
        "_hydraulic_wide",
        lambda path, role: depth.copy() if role == "depth_m" else velocity.copy(),
    )
    monkeypatch.setattr(
        instream7,
        "_case_inventory_rows",
        lambda case, initial: [{"case_id": case.case_id, "reach_id": "Reach"}],
    )

    result = instream7.run_instream7_official_benchmark(
        tmp_path,
        tmp_path / "out",
        days=3,
        seed=3,
        stochastic=False,
    )

    summary = result.population_summary.set_index("day")
    assert int(summary.loc[1, "n_active_redds"]) > 0
    assert int(summary.loc[2, "n_active_redds"]) > 0
    assert not result.redds.empty
    assert int(result.redds["age_days"].max()) >= 2



def test_official_benchmark_uses_ordered_multi_reach_movement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reaches = (
        instream7.Instream7Reach(
            case_id="SyntheticMulti",
            reach_id="Upper",
            time_series_file=Path("upper-time.csv"),
            depth_file=Path("upper-depth.csv"),
            velocity_file=Path("upper-velocity.csv"),
            shapefile=Path("cells.shp"),
            cell_id_field="ID_TEXT",
            reach_field="REACH_NAME",
            area_field="AREA",
            hiding_places_field="NUM_HIDING",
            velocity_shelter_field="FRACVSHL",
            spawning_fraction_field="FRACSPWN",
        ),
        instream7.Instream7Reach(
            case_id="SyntheticMulti",
            reach_id="Lower",
            time_series_file=Path("lower-time.csv"),
            depth_file=Path("lower-depth.csv"),
            velocity_file=Path("lower-velocity.csv"),
            shapefile=Path("cells.shp"),
            cell_id_field="ID_TEXT",
            reach_field="REACH_NAME",
            area_field="AREA",
            hiding_places_field="NUM_HIDING",
            velocity_shelter_field="FRACVSHL",
            spawning_fraction_field="FRACSPWN",
        ),
    )
    case = instream7.Instream7Case(
        case_id="SyntheticMulti",
        root=tmp_path,
        parameter_file=tmp_path / "parameters-SyntheticMulti.nls",
        initial_population_file=tmp_path / "initial.csv",
        start_date="1/1/2001",
        end_date="1/1/2001",
        species=("Rainbow",),
        reaches=reaches,
        parameters={},
    )
    initial = pd.DataFrame(
        {
            "Species": ["Rainbow", "Rainbow"],
            "Reach": ["Upper", "Lower"],
            "Age": [1, 1],
            "Number": [1, 1],
            "Length min": [14.0, 14.0],
            "Length mode": [15.0, 15.0],
            "Length max": [16.0, 16.0],
        }
    )
    forcing = pd.DataFrame(
        {
            "date": pd.to_datetime(["2001-01-01"]),
            "flow_m3s": [1.0],
            "temperature_c": [12.0],
            "turbidity_ntu": [0.0],
        }
    )

    def static_cells(reach: instream7.Instream7Reach) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "cell_id": [f"{reach.reach_id}-cell"],
                "reach_id": [reach.reach_id],
                "area_m2": [100.0],
                "hiding_cover": [1.0],
                "feeding_cover": [1.0],
                "spawning_cover": [1.0],
            }
        )

    def hydraulic(path: Path, role: str) -> pd.DataFrame:
        reach_name = "Upper" if "upper" in str(path) else "Lower"
        value = 0.7 if role == "depth_m" else 0.35
        return pd.DataFrame({"cell_id": [f"{reach_name}-cell"], 1.0: [value]})

    monkeypatch.setattr(instream7, "discover_instream7_cases", lambda root: (case,))
    monkeypatch.setattr(instream7, "read_official_initial_population", lambda path: initial.copy())
    monkeypatch.setattr(instream7, "read_official_time_series", lambda path: forcing.copy())
    monkeypatch.setattr(instream7, "read_reach_static_cells", static_cells)
    monkeypatch.setattr(instream7, "_hydraulic_wide", hydraulic)
    monkeypatch.setattr(
        instream7,
        "_case_inventory_rows",
        lambda case, initial: [{"case_id": case.case_id, "reach_id": "Upper"}],
    )

    result = instream7.run_instream7_official_benchmark(
        tmp_path,
        tmp_path / "out",
        days=1,
        seed=3,
        stochastic=False,
    )

    day1 = result.population_summary[result.population_summary["day"] == 1].set_index("reach_id")
    assert int(day1.loc["Upper", "abundance"]) == 2
    assert int(day1.loc["Lower", "abundance"]) == 0
    movement = result.events[result.events["event"] == "movement"]
    assert int(movement["n"].sum()) == 1


def test_read_and_summarize_instream7_brief_population(tmp_path: Path) -> None:
    brief = tmp_path / "BriefPopOut-r1.csv"
    brief.write_text(
        "InSTREAM-7 brief population output file, Created 10:39:01 AM\n"
        "BehavSp-Run,End of time step,IsCensus?,Light phase,Reach,Flow,Temperature,Turbidity,Species,Age class,Count,Mean length,Mean weight,Mean condition,FractionDriftFeeding,FractionSearchFeeding,FractionHiding\n"
        "1,10/1/2001 00:00,false,At setup,ExampleA,3.65,-999,0,Rainbow,Age-0,300,5.0,2.0,1,0,0,1\n"
        "1,10/1/2001 00:00,false,At setup,ExampleA,3.65,-999,0,Rainbow,Age-1,50,10.0,20.0,1,0,0,1\n"
        "1,10/1/2001 00:00,false,At setup,ExampleA,3.65,-999,0,Rainbow,Age-2+,10,20.0,80.0,1,0,0,1\n",
        encoding="utf-8",
    )

    raw = read_instream7_brief_population(brief)
    summary = summarize_instream7_brief_population(raw)

    assert len(raw) == 3
    assert raw["mean_length_mm"].iloc[0] == 50.0
    assert len(summary) == 1
    row = summary.iloc[0]
    assert row["reach_id"] == "ExampleA"
    assert row["abundance"] == 360
    assert row["biomass_g"] == pytest.approx(2400.0)
    assert row["mean_length_mm"] == pytest.approx((300 * 50 + 50 * 100 + 10 * 200) / 360)
    assert row["age_classes"] == "Age-0|Age-1|Age-2+"
