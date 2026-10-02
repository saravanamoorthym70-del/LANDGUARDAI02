# LANDGUARD AI data dictionary

| Field | Unit | Meaning | Model use |
|---|---|---|---|
| latitude | degrees | Geographic latitude | spatial context |
| longitude | degrees | Geographic longitude | spatial context |
| event_date / sample_date | date | Observation/event date | temporal matching |
| state | text | Canonical Indian state | grouping/QA |
| location_accuracy | text | NASA catalog location-accuracy category | event filter/provenance only |
| location_accuracy_km | km | Parsed event-location uncertainty; exact locations are 0 | event filter/provenance only |
| rainfall_1d_mm | mm | Rainfall over previous 24 h | model feature |
| rainfall_3d_mm | mm | Rainfall over previous 72 h | model feature |
| rainfall_7d_mm | mm | Rainfall over previous 168 h | model feature |
| soil_moisture_0_7cm | fraction | Surface soil moisture | model feature |
| elevation_m | m | Elevation | model feature |
| slope_deg | degrees | Approximate slope from a 3x3 Open-Meteo elevation grid | context only; not a 30 m DEM product |
| distance_to_road_km | km | Distance to nearest OSM highway line within 20 km | context/QA only; Northeast coverage |
| distance_to_settlement_km | km | Distance to nearest OSM place/residential feature within 20 km | context/QA only; Northeast coverage |
| risk | 0/1 | Positive historical event vs background sample | target |
| sample_type | text | historical/background provenance | QA only |
