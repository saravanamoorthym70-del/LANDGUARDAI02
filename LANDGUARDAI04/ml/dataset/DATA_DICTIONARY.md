# LANDGUARD AI data dictionary

| Field | Unit | Meaning | Model use |
|---|---|---|---|
| latitude | degrees | Geographic latitude | spatial context |
| longitude | degrees | Geographic longitude | spatial context |
| event_date / sample_date | date | Observation/event date | temporal matching |
| state | text | Canonical Indian state | grouping/QA |
| rainfall_1d_mm | mm | Rainfall over previous 24 h | model feature |
| rainfall_3d_mm | mm | Rainfall over previous 72 h | model feature |
| rainfall_7d_mm | mm | Rainfall over previous 168 h | model feature |
| soil_moisture_0_7cm | fraction | Surface soil moisture | model feature |
| elevation_m | m | Elevation | model feature |
| slope_deg | degrees | Terrain slope estimate | context only; excluded while missing |
| risk | 0/1 | Positive historical event vs background sample | target |
| sample_type | text | historical/background provenance | QA only |
