# LANDGUARD AI — ML pipeline

This mirrors the data pipeline described in the project workflow doc
(sections 2–14): historical landslide data → environmental enrichment
→ background sampling → combined dataset → model comparison and training.

## Directory layout

```
ml/
├── dataset/            raw + processed CSVs (git-ignored except .gitkeep)
├── models/
│   └── landslide_model.pkl   trained model, loaded by backend/ml_predictor.py
└── scripts/
    ├── common.py                          shared constants/helpers
    │
    │  ── real pipeline (needs internet access to NASA / Open-Meteo) ──
    ├── inspect_nasa_data.py                Stage 1 — filter NASA GLC to target states
    ├── get_environmental_data.py           Stage 2 — historical rainfall + soil moisture
    ├── get_elevation_data.py               Stage 3 — elevation
    ├── get_slope_data.py                   Stage 4 — slope from 3x3 elevation grid
    ├── create_real_background_locations.py Stage 5 — pseudo-absence sampling
    ├── get_background_environmental_data.py Stage 6
    ├── get_background_elevation.py         Stage 7
    ├── get_background_slope.py             Stage 8
    ├── combine_ml_dataset.py               Stage 9 — merge into LANDGUARD_FINAL_DATASET.csv
    ├── enrich_osm_context.py               Optional Northeast road/settlement distances
    │
    │  ── offline bootstrap (no internet required) ──
    ├── build_placeholder_dataset.py        alternative to stages 5–9
    │
    │  ── training (either path feeds this) ──
    └── train_real_model.py                 Stage 10 — train + save landslide_model.pkl
```

## Two ways to produce `landslide_model.pkl`

### Option A — the real pipeline (recommended for the actual SIH submission)

Requires outbound internet access to `data.nasa.gov`, `archive-api.open-meteo.com`,
and `api.open-meteo.com`. Run from the repo root:

```bash
# 1. Download the NASA Global Landslide Catalog export and save it to:
#    ml/dataset/NASA_Global_Landslide_Catalog.csv

python -m ml.scripts.inspect_nasa_data
python -m ml.scripts.get_environmental_data
python -m ml.scripts.get_elevation_data
python -m ml.scripts.get_slope_data
python -m ml.scripts.create_real_background_locations
python -m ml.scripts.get_background_environmental_data
python -m ml.scripts.get_background_elevation
python -m ml.scripts.get_background_slope
python -m ml.scripts.combine_ml_dataset
python -m ml.scripts.train_real_model
```

Each script picks up where the previous one left off and prints progress
and row counts. The current local catalog has 390 target-region events
before accuracy filtering; the inventory stage retains only events
reported as `exact` or <=1 km uncertainty. The current table has 79 such
events and 649 complete-feature background rows. Counts may change when
the source files are refreshed.

For optional Northeast reporting-bias diagnostics, after building the
combined table run `enrich_osm_context.py` with the downloaded Northeast and
Eastern OSM PBF extracts. It writes `OSM_DISTANCE_FEATURES.csv` and updates
the combined table. The distance columns are context-only and are not model
inputs. A Southern Zone extract is needed to cover the five South comparison
states.

### Option B — offline bootstrap (what this repo ships with)

No internet access needed. Uses the 494 historical records already
embedded in `frontend/src/landslideData.json` (positive class) plus
**synthetic** pseudo-absence samples (negative class) drawn from
distributions shifted lower than the historical positives:

```bash
python -m ml.scripts.build_placeholder_dataset
python -m ml.scripts.train_real_model
```

**This is a stand-in, not real background data.** The synthetic
samples were never actually measured at real locations — they exist
so the app has a working, loadable model to demo end-to-end. Metrics
from this bootstrap model (falls in the low-90s% for accuracy/ROC-AUC
on this repo's copy) are noticeably higher than the ~75%
accuracy / 81% ROC-AUC reported in the workflow doc for the real
pipeline, because the synthetic background is more separable from the
positives than real measured background locations would be. Treat
these numbers as "the wiring works," not as a result to cite.
**Before treating results as meaningful for the SIH submission, run
Option A on a machine with internet access.**

## If no model file is present at all

`backend/ml_predictor.py` doesn't crash if `ml/models/landslide_model.pkl`
is missing — it logs a warning and falls back to the rule-based scoring
in `backend/risk_engine.py`, and `/health` reports
`"model": "unavailable (rule-based fallback active)"`. Predictions in
that mode are tagged `"mode": "rule_based_fallback"` in the API
response so the frontend/judges can tell the difference from real ML
predictions (`"mode": "ml_model"`).
