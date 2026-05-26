# Open boundary forcing

`open_boundary_forcing.csv` maps directly to the open boundary order in `hgrid.gr3`.

- `boundary_id` is 1-based and matches the SCHISM open-boundary segment order.
- `discharge_m3s` is the positive HEC-RAS flow profile value for the reach.
- `signed_discharge_m3s` is positive into the domain for upstream inflow and negative at downstream stage boundaries.
- `stage_m`, `depth_m`, and `velocity_ms` come from the calibrated builtin-1d cell nearest to the boundary station.
- `time_seconds` follows the OpenLimno scenario index, one HEC-RAS profile per simulated day; `date` preserves the source profile label.
- `stage_m` remains the source vertical datum; `elev.th` subtracts the SCHISM depth/stage reference so boundary elevation and hgrid depth use one consistent datum.
- `bctides.in`, `elev.th`, and `flux.th` are generated as SCHISM Type-1 time-history inputs. SCHISM uses negative flux for inflow, so `flux.th` has the opposite sign of `discharge_m3s` for upstream inflow boundaries.
- The terminal SCHISM forcing row repeats the final source profile at the scenario end time so the numerical solver can complete the full requested duration without reading past the boundary files.
- Review the generated flags, time step, and any missing tidal, salinity, or temperature requirements before a production SCHISM run.
