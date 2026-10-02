# LANDGUARD AI — Improved SIH26001 Prototype

AI-based early warning and landslide risk monitoring for the North Eastern Region, built around SIH Problem Statement 26001.

## What is improved in this version

- Four-model comparison using leave-one-state-out validation, a 5-fold spatial-group check, and a chronological holdout; the selected estimator is saved with threshold-specific and per-state metrics.
- Prototype screening score with alerts aligned to the HIGH band; scores are not calibrated event probabilities.
- Stable LOW/MEDIUM/HIGH UI risk bands.
- Data-quality audit script for missing values, duplicates, ranges and rainfall consistency.
- Polygon-constrained background sampler — no unsafe bounding-box fallback.
- Historical-date matching for background environmental samples to reduce temporal leakage.
- Backend coordinate validation and safer live elevation handling.
- Live weather requests use seven past days without adding a forecast day to the 1/3/7-day rainfall windows.
- Completed live map assessments are stored in the backend SQLite record store with CSV and full JSON export.
- The current-location button uses browser GPS to center the map and assess the device location; selected locations also support manual refresh and optional 15-minute monitoring.
- Daylight cartography UI with responsive recent-record review and risk badges.
- Model card and data-upgrade guide documenting limitations honestly.

## Current shipped data

`ml/dataset/LANDGUARD_FINAL_DATASET.csv` contains 1,039 rows with location and sample provenance:

- 390 historical landslide observations (`risk=1`)
- 649 background/pseudo-absence observations (`risk=0`)
- 5 model features: rainfall windows, soil moisture, and elevation

The dataset is a prototype. Background samples are not confirmed landslide absences, and slope is missing from all current rows so it is excluded from model features. Validation is informative but does not establish operational accuracy or a real-world landslide probability.

## Quick start

### Backend

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
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

Do not use `build_placeholder_dataset.py` for reported project metrics. It remains only as an offline development fallback.

## API

- `GET /health`
- `POST /predict-risk`
- `GET /live-environment?latitude=...&longitude=...`
- `GET /live-risk?latitude=...&longitude=...`
- `GET /reverse-geocode?latitude=...&longitude=...`
- `GET /records?limit=50`
- `GET /records/{record_id}`
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

This is a research/prototype system, not a safety-certified warning service. Before operational deployment, use larger verified inventories, exact administrative polygons, spatial/temporal validation, calibrated thresholds, independent event-based testing, and domain-expert review.
