# LANDGUARD AI — Prototype

AI-based early warning and landslide risk monitoring for the North Eastern Region, built around SIH Problem Statement 26001.

## What is improved in this version

- Four-model comparison using leave-one-state-out validation, a 5-fold spatial-group check, and a chronological holdout; the selected estimator is saved with threshold-specific and per-state metrics.
- Prototype screening score with alerts aligned to the HIGH band; scores are not calibrated event probabilities.
- Stable LOW/MEDIUM/HIGH UI risk bands.
- Data-quality audit script for missing values, duplicates, ranges and rainfall consistency.
- NASA location-accuracy filter keeps event records labeled `exact` or <=1 km uncertainty.
- The final table now includes available slope estimates as context; these are from a 3x3 Open-Meteo elevation grid, not a 30 m DEM.
- OSM road and settlement proximity is measured for Northeast records as a reporting-bias diagnostic; these columns are not model inputs.
- Polygon-constrained background sampler — no unsafe bounding-box fallback.
- Historical-date matching for background environmental samples to reduce temporal leakage.
- Backend coordinate validation and safer live elevation handling.
- Live weather requests use seven past days without adding a forecast day to the 1/3/7-day rainfall windows.
- Completed live map assessments are stored in the backend SQLite record store with CSV and full JSON export.
- The current-location button uses browser GPS to center the map and assess the device location; selected locations also support manual refresh and optional 15-minute monitoring.
- Daylight cartography UI with responsive recent-record review and risk badges.
- Model card and data-upgrade guide documenting limitations honestly.

## Current shipped data

`ml/dataset/LANDGUARD_FINAL_DATASET.csv` currently contains 728 rows with location and sample provenance:

- 79 historical landslide observations (`risk=1`), after the <=1 km location-accuracy filter
- 649 background/pseudo-absence observations (`risk=0`)
- 5 model features: rainfall windows, soil moisture, and elevation
- OSM distance context is available for 638 rows to roads and 637 rows to mapped settlements; southern comparison rows are not covered.

Background samples are not confirmed absences. No temporal negatives have been added, and the spatial sampling is not matched to road/settlement reporting bias: median event/background distances are 0.027/1.181 km to roads and 0.630/3.608 km to mapped settlements. The 1 km event filter leaves only 79 positives. OSM distances and slope remain context-only, excluded from model inputs. Validation is informative but does not establish operational accuracy or a real-world landslide probability.

## Quick start

### Backend

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m ml.scripts.inspect_nasa_data
python -m ml.scripts.combine_ml_dataset
python -m ml.scripts.data_quality_report
python -m ml.scripts.train_real_model
uvicorn backend.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Tests

```bash
pytest backend/tests -v
```

### Regional risk grid

Run a complete 1 km regional update once:

```bash
python -m backend.run_grid_job
```

Keep it refreshed with the built-in scheduler. It runs once at startup, then every six hours; run it as a separate long-lived process:

```bash
python -m backend.grid_scheduler
```

The grid uses `ml/dataset/target_states.geojson` and `ml/dataset/district_boundaries.geojson`. The district file is GeoBoundaries India ADM2 (2021), downloaded 2026-10-02; source data updated 2023-01-19, ODbL 1.0 ([source](https://github.com/wmgeolab/geoBoundaries/raw/9469f09/releaseData/gbOpen/IND/ADM2/geoBoundaries-IND-ADM2.geojson)). Grid settings can be changed with `LANDGUARD_GRID_INTERVAL_HOURS` (6), `LANDGUARD_GRID_CELL_SIZE_M` (1000), `LANDGUARD_GRID_BATCH_SIZE` (200), `LANDGUARD_GRID_CACHE_HOURS` (4), and `LANDGUARD_GRID_REQUEST_INTERVAL_SECONDS` (2). A geometry scan found 262,910 cells at 1 km, or about 1,315 batched HTTP requests per full update before retries. The 2-second request delay alone is about 44 minutes. Open-Meteo documents multi-location requests and a non-commercial allowance below 10,000 daily calls; verify how provider accounting applies to batched locations and check commercial terms before deployment. Eligible non-commercial use does not require an API key.

For a live-data smoke check that does not persist a partial regional result:

```bash
python -m backend.run_grid_job --max-cells 3 --no-store
```

### Live record log

Click a map location or choose **Check my current location** to run a live assessment. Current-location assessment requires browser location permission and a secure context (HTTPS or localhost). After a successful assessment, the frontend sends the location, risk inputs, complete response, browser session ID, per-assessment correlation ID, and trigger (`map-click`, `current-location`, or `scheduled-refresh`) to the backend SQLite record store. The backend assigns a UUID and authoritative capture timestamp while retaining the client timestamp as metadata. Use `GET /records/{record_id}` to retrieve one assessment directly. The **Live records** panel shows the eight most recent entries and supports CSV export with trace metadata and JSON export for the complete raw records. A browser-local cache is used only when the backend is temporarily unavailable. The selected location can also be manually refreshed or monitored automatically every 15 minutes.

## Improved real-data pipeline

Install the optional GIS dependencies:

```bash
pip install -r requirements-data.txt
```

Then place an authoritative WGS84 target-state GeoJSON at:

`ml/dataset/target_states.geojson`

Run:

```bash
python -m ml.scripts.inspect_nasa_data
python -m ml.scripts.get_environmental_data
python -m ml.scripts.get_elevation_data
python -m ml.scripts.get_slope_data
python -m ml.scripts.create_real_background_locations
python -m ml.scripts.match_background_dates
python -m ml.scripts.get_background_environmental_data
python -m ml.scripts.get_background_elevation
python -m ml.scripts.combine_ml_dataset
python -m ml.scripts.data_quality_report
python -m ml.scripts.train_real_model
```

To add OSM proximity diagnostics for the Northeast rows, pass the downloaded regional extracts after building the combined dataset:

```bash
python -m ml.scripts.enrich_osm_context --pbf "C:/Users/Dell/Downloads/north-eastern-zone-261001.osm.pbf" --pbf "C:/Users/Dell/Downloads/eastern-zone-261001.osm.pbf"
python -m ml.scripts.combine_ml_dataset
python -m ml.scripts.data_quality_report
```

This extracts road lines and settlement/place geometries, searches for the nearest feature within 20 km, and updates `OSM_DISTANCE_FEATURES.csv` plus the combined dataset. Rows without a nearby mapped feature remain missing. A Southern Zone extract is required to extend these distances to the five South comparison states.

Do not use `build_placeholder_dataset.py` for reported project metrics. It remains only as an offline development fallback.

## API

- `GET /health`
- `POST /predict-risk`
- `GET /live-environment?latitude=...&longitude=...`
- `GET /live-risk?latitude=...&longitude=...`
- `GET /reverse-geocode?latitude=...&longitude=...`
- `GET /records?limit=50`
- `GET /records/{record_id}`
- `GET /risk-grid?bbox=min_lon,min_lat,max_lon,max_lat&limit=2000` (GeoJSON cells with last-updated, completeness, and top-district summary metadata)
- `POST /records`
- `DELETE /records`

## Architecture

```text
Historical landslides + weather + soil + terrain
                    |
              data quality
                    |
          feature engineering
                    |
             ML training
                    |
      held-out-state classifier
                    |
            screening score (not probability)
                    |
       LOW / MEDIUM / HIGH + alert
                    |
              FastAPI backend
                    |
          React + Leaflet GIS UI
```

## Honest limitation

This is a research/prototype system, not a safety-certified warning service. The current event filter retains 79 catalog events at <=1 km reported location uncertainty, but the resulting leave-one-state-out performance is weak and the existing 0.70 alert cutoff detects none of those held-out positives. Background locations are not verified absences, no temporal negatives exist, and the large road/settlement distance gap indicates unresolved reporting/sampling bias. OSM distances are diagnostics, not model inputs. Do not use the score as a probability or operational warning.

The regional grid's 1 km spacing is a sampling resolution, not 1 km weather-data resolution; Open-Meteo weather values may represent coarser model cells. Districts are assigned from the supplied boundary overlays, and cells that cannot be assigned unambiguously are excluded from district rankings and reported separately. The saved estimator warns that it was serialized with scikit-learn 1.5.1 while this workspace runtime is 1.9.1; match and validate these versions before relying on model scores.

The repository does not contain the inputs needed for the remaining task-1/2 features:

- For temporal negatives and 14/30-day antecedent rainfall, provide daily gridded history at the event locations in `ml/dataset/DAILY_WEATHER_HISTORY.csv` with `latitude,longitude,date,rainfall_mm,soil_moisture_0_7cm`. The weather provider must be the same source selected for live inference after task 3; that source has not been checked yet, so I have not generated or imputed these rows.
- For 30 m slope, aspect, curvature, and TWI, download Copernicus DEM GLO-30 GeoTIFF tiles covering the target-state polygons plus a buffer and place them under `ml/dataset/dem/`. Keep the raster CRS and nodata metadata intact. The current slope values are from the coarse Open-Meteo elevation-grid method and are not substitutes for these files.
- To extend OSM distance diagnostics beyond the Northeast, provide the missing Southern Zone extract; the five South comparison states are currently unmeasured.
- For optional land cover/NDVI, geology/lithology, rivers, and faults, place dated rasters and vector layers in `ml/dataset/context/`; those layers are not present in this workspace, so they have not been added as features.

Independent event-based validation, duplicate-safe splits, calibration, cost-based threshold selection, and domain-expert review are also still required before operational use.
