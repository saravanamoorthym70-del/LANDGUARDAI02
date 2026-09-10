# LANDGUARD AI — Improved SIH26001 Prototype

AI-based early warning and landslide risk monitoring for the North Eastern Region, built around SIH Problem Statement 26001.

## What is improved in this version

- Calibrated Random Forest model artifact with model metadata.
- Recall-oriented alert threshold selected from out-of-fold training probabilities.
- Stable LOW/MEDIUM/HIGH UI risk bands.
- Data-quality audit script for missing values, duplicates, ranges and rainfall consistency.
- Polygon-constrained background sampler — no unsafe bounding-box fallback.
- Historical-date matching for background environmental samples to reduce temporal leakage.
- Backend coordinate validation and safer live elevation handling.
- Live weather requests use seven past days without adding a forecast day to the 1/3/7-day rainfall windows.
- Model card and data-upgrade guide documenting limitations honestly.

## Current shipped data

`ml/dataset/LANDGUARD_FINAL_DATASET.csv` contains 1,143 rows:

- 494 historical landslide observations (`risk=1`)
- 649 background/pseudo-absence observations (`risk=0`)
- 6 model features

The shipped dataset is a prototype dataset. It has **not** been spatially cross-validated and the background class is not confirmed landslide absence.

## Quick start

### Backend

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
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
python -m ml.scripts.get_background_slope
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
        calibrated Random Forest
                    |
             risk probability
                    |
       LOW / MEDIUM / HIGH + alert
                    |
              FastAPI backend
                    |
          React + Leaflet GIS UI
```

## Honest limitation

This is a research/prototype system, not a safety-certified warning service. Before operational deployment, use larger verified inventories, exact administrative polygons, spatial/temporal validation, calibrated thresholds, independent event-based testing, and domain-expert review.
