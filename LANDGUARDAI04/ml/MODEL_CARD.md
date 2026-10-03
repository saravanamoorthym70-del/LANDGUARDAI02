# LANDGUARD AI model card

## Current model

- Current estimator: Extra Trees, selected from Logistic Regression, Random Forest, Extra Trees, and HistGradientBoosting using mean state-level average precision, with balanced accuracy as a tie-breaker.
- Input features: rainfall 1d/3d/7d, surface soil moisture, and elevation.
- `slope_deg` is retained as context only and is not used by the estimator. Values are approximate gradients from a 3x3 Open-Meteo elevation grid, not a 30 m DEM product.
- OSM distance-to-road and distance-to-settlement columns are diagnostics only, not estimator inputs; coverage is limited to Northeast rows.
- Current training table: 728 rows, comprising 79 NASA catalog events reported as `exact` or <=1 km uncertainty and 649 background/pseudo-absence rows.
- Background rows are not verified non-landslide observations. No temporal-negative samples have been added.

## Validation

The training script compares four classifiers with leave-one-state-out validation. Every row from the held-out state is excluded from that fold's training set. It also reports 5-fold spatial-group validation using 0.5-degree coordinate blocks and a chronological 80/20 holdout. Candidate selection for the chronological holdout uses only the earlier training period. State folds without both classes are excluded from state-level discrimination averages.

The following compares the committed pre-filter run (390 positives / 649 backgrounds) with the current accuracy-filtered run (79 positives / 649 backgrounds). These runs use different label populations, so this is not a controlled model-only comparison.

| Validation | Metric | Before | After |
|---|---|---:|---:|
| Leave-one-state-out | ROC-AUC | 0.682 | 0.551 |
| Leave-one-state-out | Average precision | 0.537 | 0.176 |
| Leave-one-state-out | Brier score | 0.224 | 0.098 |
| Spatial grouped | ROC-AUC | 0.723 | 0.581 |
| Spatial grouped | Average precision | 0.612 | 0.229 |
| Spatial grouped | Brier score | 0.209 | 0.094 |
| Chronological holdout | ROC-AUC | 0.792 | 0.764 |
| Chronological holdout | Average precision | 0.720 | 0.581 |
| Chronological holdout | Brier score | 0.176 | 0.179 |

The positive fraction fell from 37.5% to 10.9%, affecting average precision and Brier score; neither estimates operational performance. On pooled leave-one-state-out predictions, the current model emits no alerts at the existing 0.70 threshold and detects 0 of 79 positives. This threshold is not operationally usable.

OSM proximity diagnostics show median event/background distances of 0.027/1.181 km to roads and 0.630/3.608 km to mapped settlements. This large gap is consistent with reporting or sampling bias and can make validation appear to measure accessibility/reporting patterns rather than landslide susceptibility. Distances use the nearest OSM highway line or mapped place/residential feature within 20 km; 638/640 Northeast rows have road distances and 637/640 have settlement distances. These diagnostics do not correct the bias.

The labels distinguish catalog events with reported location uncertainty <=1 km from sampled background locations; they are not matched temporal negatives. The output is a **screening score, not a calibrated probability of a landslide at a specific place and time**. State-held-out, spatial-group, and chronological checks do not establish operational performance or safety. Before operational use, obtain verified event/non-event observations, temporally matched negatives, independent event-based testing, and domain-expert review.

## Risk bands

- LOW: screening score < 0.40
- MEDIUM: screening score 0.40–<0.70
- HIGH: screening score >= 0.70

The warning threshold remains fixed at 0.70 to match the UI HIGH-risk band. It was not selected by an explicit cost function and currently detects none of the pooled leave-one-state-out positives. It is not an emergency-warning standard.

## Regional risk grid

The regional job uses the same saved Extra Trees estimator and five model features. It scores 1 km cells clipped to the eight target-state polygons using batched Open-Meteo rainfall, soil moisture, and returned elevation; slope remains excluded. The hourly weather values can represent coarser model cells, so 1 km describes the sample grid, not the source-data resolution. Results, inputs, clipped geometry, district attribution, risk band, and update time are stored in the backend SQLite database. Fresh cells are reused for four hours by default; the separate scheduler runs immediately and then every six hours.

District boundaries come from the GeoBoundaries India ADM2 2021 GeoJSON (`ml/dataset/district_boundaries.geojson`), retrieved on 2026-10-02 (ODbL 1.0; source data updated 2023-01-19). When a cell representative point falls outside the district polygons because of boundary-source mismatch, the job assigns a district only if one district covers at least half of the clipped cell. Unassigned cells are excluded from district rankings and exposed in API metadata.

The current pickle emits an `InconsistentVersionWarning`: it was saved with scikit-learn 1.5.1 and the workspace runtime is 1.9.1. This compatibility warning is unresolved; validate the estimator under its training version or retrain and revalidate under the target runtime before relying on scores.

## Exposure overlay

The optional exposure view intersects stored HIGH grid cells with roads, mapped bridges, settlements, schools, hospitals, and railways from the local Geofabrik OSM extracts. Processed layers are clipped to the target-state polygons and stored in `ml/dataset/exposure_layers.gpkg`; the accompanying metadata JSON records input filenames, local file timestamps, processing time, license, and CRS. OSM feature completeness varies, so these are mapped-feature counts, not verified infrastructure inventories or population estimates.

## Historical replay

The `/replay` endpoint requests historical rainfall and 0–7 cm soil moisture from Open-Meteo's archive and uses Open-Meteo elevation for the model's fifth input. It scores each day before the selected event date with the saved estimator and the deployed LOW/MEDIUM/HIGH thresholds. `ml/scripts/replay_heldout_events.py` recomputes the training script's chronological 80/20 cutoff over the dated table, replays only positive rows in the test split, and reports request failures, events reaching HIGH, lead days, and pre-event HIGH-score days. Those pre-event days are not verified negatives; the report labels the false-alarm count as a proxy, not a measured operational false-positive rate.

The current chronological replay used cutoff 2015-08-27 and fetched all 32 held-out positives successfully. None reached HIGH during the preceding seven days; 0 pre-event HIGH-score days and 0 request failures were reported. The event dataset does not contain independently verified negative days, so this is not an operational false-alarm estimate.
