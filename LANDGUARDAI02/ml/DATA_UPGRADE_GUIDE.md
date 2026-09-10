# LANDGUARD AI — Data Upgrade Pipeline

The original prototype used random background samples and a bootstrap model. This upgrade removes the two biggest data-quality weaknesses:

1. background points must be inside real state polygons; and
2. background environmental dates are sampled from historical event dates in the same state where possible.

## Improved order

```text
NASA raw catalog
  -> inspect_nasa_data.py
  -> historical environmental data
  -> terrain/slope

Official target-state GeoJSON
  -> create_real_background_locations.py
  -> match_background_dates.py
  -> get_background_environmental_data.py
  -> get_background_elevation.py
  -> get_background_slope.py
  -> combine_ml_dataset.py
  -> data_quality_report.py
  -> train_real_model.py
```

## Boundary file

Place an authoritative WGS84 GeoJSON at:

`ml/dataset/target_states.geojson`

The file must contain polygons for the 13 target states and one of these state-name fields:
`state`, `ST_NM`, `NAME_1`, `name`, or `NAME`.

The sampling script intentionally does **not** fall back to bounding boxes.

## Recommended future features

- 14-day and 30-day antecedent rainfall
- maximum 1h/3h/6h rainfall intensity
- soil-moisture change over 24h/7d
- aspect, curvature, roughness, TWI/TPI
- distance/count of previous landslides before the prediction date
- district and land-cover features
- satellite change indicators

These should be added only when the same feature can be generated consistently for both training data and live inference.
