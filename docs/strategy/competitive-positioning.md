# Competitive Positioning

OpenLimno's product position is an **open, reproducible ecological-flow and
fish-habitat decision platform**. It should not try to become a universal
hydraulic solver. It should make existing hydraulic and habitat tools useful in
a modern, auditable ecological workflow.

## Software Families

| Family | Examples | Why users rely on it | OpenLimno response |
|---|---|---|---|
| Traditional IFIM / WUA | PHABSIM, RHYHABSIM, RHABSIM, SEFA, EVHA | Regulatory familiarity and WUA-Q methods | Preserve PHABSIM-compatible WUA outputs, legacy import paths, and evidence-grade HSI metadata |
| 2D / 3D hydraulics | HEC-RAS, MIKE 21, Delft3D FM, TELEMAC, TUFLOW, BASEMENT, River2D, iRIC | Mature hydraulics, institutional acceptance, engineering workflows | Import or wrap results; use OpenLimno for habitat, passage, provenance, and reporting |
| Habitat-specific tools | HABBY, CASiMiR, MesoHABSIM, DHABSIM | Fish-habitat maps and suitability workflows | Compete on open formats, QGIS integration, species evidence, and reproducible reporting |
| Fish passage | FishXing, HEC-26 style workflows | Culvert/passability design | Keep `passage` focused, but connect it to reach-scale habitat and species evidence |
| Individual/population models | inSTREAM, InSALMO, HexSim | Growth, mortality, competition, persistence, and population response | Provide plugin/data bridges; keep IBM outside the core runtime until a validated engine exists |
| Water quality / sediment / eco-complexes | EFDC+, CE-QUAL-W2, MIKE ECO Lab, Delft3D WAQ, TUFLOW WQ | Temperature, nutrients, algae, sediment, morphodynamics | Read results and calculate ecological risk indicators before attempting native solvers |
| Data / workflow platforms | HydroMT, HydroShare, OpenDA, QGIS, Jupyter, STAC/Zarr ecosystems | Automated setup, provenance, sharing, batch runs | Make OpenLimno the ecological workflow layer on top of these standards |

## Strategic Rules

1. **Interop before replacement.** If users already have HEC-RAS, Delft3D,
   TELEMAC, MIKE, River2D, or HABBY outputs, OpenLimno should ingest them before
   asking users to rebuild a model.
2. **Ecology is the product surface.** OpenLimno's user-visible value is HSI,
   WUA, HMU, passage, species evidence, population-response exchange, and
   regulatory reporting.
3. **Evidence beats feature count.** Validation cases, benchmark deltas,
   provenance, uncertainty, and HSI transferability warnings are more important
   than adding a long list of half-supported solvers.
4. **Core stays small; integrations are optional.** Private/licensed or
   high-churn formats such as MIKE DFS are exposed through optional adapters.
   Core OpenLimno stays importable without those dependencies.

## Near-Term Implementation Tracks

| Track | First deliverable | Success criterion |
|---|---|---|
| HEC-RAS interop | HDF result importer MVP for depth, velocity, WSE, and cell geometry | Existing HEC-RAS 2D model can produce OpenLimno WUA/HMU/regulatory outputs without rerunning hydraulics |
| TELEMAC interop | Native Selafin result importer plus CF/UGRID fallback | TELEMAC users can enter the same WUA/HMU path as HEC-RAS, MIKE, and NetCDF users |
| CF/UGRID NetCDF interop | Generic NetCDF hydraulic-cell importer for Delft3D FM / D-Flow FM and converted TELEMAC outputs | Open NetCDF model outputs can enter the same WUA/HMU path as HEC-RAS and MIKE |
| MIKE interop | Optional `mikeio`/`mikeio1d` adapter for DFSU/DFS2/DFS0/RES1D/XNS11 | Existing MIKE 21/FM/1D projects can produce OpenLimno staging tables without changing the hydraulic workflow |
| Legacy migration | Unified `openlimno preprocess import-model` command | HEC-RAS `.g0X` and River2D `.cdg` users can stage data from one CLI |
| Habitat tool exchange | HABBY/CASiMiR/MesoHABSIM table exchange importer | Suitability/WUA outputs can be compared table-by-table |
| IBM bridge | inSTREAM/InSALMO/NetLogo CSV exchange bridge | OpenLimno can export hydraulic/habitat cells and import population-response summaries without owning the IBM runtime |
| Reporting | Word/PDF-ready regulatory report package | Consultants can submit a complete method/data/provenance appendix |
