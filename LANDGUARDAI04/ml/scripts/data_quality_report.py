"""LANDGUARD data quality audit.

Audits the final ML dataset and, when available, the historical/background
source files. Writes a machine-readable JSON report and a human-readable CSV
summary. This does not silently delete rows; it reports anomalies for review.
"""
import json, os
import numpy as np
import pandas as pd
from ml.scripts.common import DATASET_DIR, MODEL_FEATURES, TARGET_COLUMN

FINAL = os.path.join(DATASET_DIR, 'LANDGUARD_FINAL_DATASET.csv')
REPORT = os.path.join(DATASET_DIR, 'LANDGUARD_DATA_QUALITY_REPORT.json')

RANGES = {
    'rainfall_1d_mm': (0, 2000),
    'rainfall_3d_mm': (0, 3000),
    'rainfall_7d_mm': (0, 4000),
    'soil_moisture_0_7cm': (0, 1),
    'elevation_m': (-500, 9000),
}

def main():
    if not os.path.exists(FINAL):
        raise SystemExit(f'Missing {FINAL}')
    df = pd.read_csv(FINAL)
    report = {'file': FINAL, 'rows': int(len(df)), 'columns': list(df.columns), 'checks': {}}
    report['checks']['missing_values'] = {k: int(v) for k,v in df.isna().sum().items()}
    required_columns = list(MODEL_FEATURES) + [TARGET_COLUMN]
    report['checks']['required_missing_values'] = {
        column: int(df[column].isna().sum()) for column in required_columns
    }
    if 'slope_deg' in df:
        optional_slope = pd.to_numeric(df['slope_deg'], errors='coerce')
        report['checks']['optional_slope_coverage'] = {
            'available_rows': int(optional_slope.notna().sum()),
            'missing_rows': int(optional_slope.isna().sum()),
            'source_note': 'Approximate 3x3 Open-Meteo elevation-grid gradient; not a 30 m DEM product.',
        }
    if 'location_accuracy_km' in df:
        event_accuracy = pd.to_numeric(
            df.loc[df[TARGET_COLUMN] == 1, 'location_accuracy_km'], errors='coerce'
        )
        report['checks']['event_location_accuracy'] = {
            'max_accuracy_km': 1.0,
            'positive_rows': int((df[TARGET_COLUMN] == 1).sum()),
            'measured_positive_rows': int(event_accuracy.notna().sum()),
            'outside_threshold_rows': int((event_accuracy > 1.0).sum()),
            'source_field': 'NASA Global Landslide Catalog location_accuracy',
        }
        accuracy_ok = (
            event_accuracy.notna().all()
            and event_accuracy.le(1.0).all()
        )
    else:
        report['checks']['event_location_accuracy'] = {
            'available': False,
            'reason': 'location_accuracy_km is absent from the combined dataset.',
        }
        accuracy_ok = False
    temporal_negatives = int(
        df.get('sample_type', pd.Series(dtype=str)).eq('temporal_negative').sum()
    )
    report['checks']['temporal_negative_rows'] = {
        'count': temporal_negatives,
        'available': temporal_negatives > 0,
    }
    requested_features = (
        'aspect_deg', 'curvature', 'twi', 'rainfall_14d_mm', 'rainfall_30d_mm',
        'antecedent_precipitation_index', 'rainfall_intensity', 'ndvi',
        'landcover_class', 'lithology', 'distance_to_river_km',
        'distance_to_fault_km', 'distance_to_road_km',
        'distance_to_settlement_km',
    )
    report['checks']['requested_feature_availability'] = {
        column: {
            'available_rows': int(df[column].notna().sum()) if column in df else 0,
            'present': column in df,
        }
        for column in requested_features
    }
    report['checks']['spatial_reporting_proximity'] = {}
    for column in ('distance_to_road_km', 'distance_to_settlement_km'):
        if column not in df:
            report['checks']['spatial_reporting_proximity'][column] = {
                'available': False,
                'reason': 'OSM proximity enrichment has not been run.',
            }
            continue
        numeric = pd.to_numeric(df[column], errors='coerce')
        report['checks']['spatial_reporting_proximity'][column] = {
            'available_rows': int(numeric.notna().sum()),
            'event_median_km': (
                float(numeric[df[TARGET_COLUMN] == 1].median())
                if numeric[df[TARGET_COLUMN] == 1].notna().any() else None
            ),
            'background_median_km': (
                float(numeric[df[TARGET_COLUMN] == 0].median())
                if numeric[df[TARGET_COLUMN] == 0].notna().any() else None
            ),
            'source': 'OpenStreetMap regional PBF extracts; <=20 km nearest-feature search.',
        }
    report['checks']['duplicates'] = int(df.duplicated().sum())
    report['checks']['class_counts'] = {str(k): int(v) for k,v in df['risk'].value_counts().sort_index().items()}
    coverage_columns = ['region', 'state', 'sample_type', TARGET_COLUMN]
    if all(column in df.columns for column in coverage_columns):
        coverage = (
            df.groupby(coverage_columns, dropna=False)
            .size()
            .reset_index(name='rows')
        )
        report['checks']['coverage_by_region_state'] = [
            {
                'region': None if pd.isna(row.region) else str(row.region),
                'state': None if pd.isna(row.state) else str(row.state),
                'sample_type': None if pd.isna(row.sample_type) else str(row.sample_type),
                'risk': int(row.risk),
                'rows': int(row.rows),
            }
            for row in coverage.itertuples(index=False)
        ]
    report['checks']['feature_ranges'] = {}
    for col,(lo,hi) in RANGES.items():
        s = pd.to_numeric(df[col], errors='coerce')
        bad = ((s < lo) | (s > hi)).sum()
        report['checks']['feature_ranges'][col] = {
            'min': float(s.min()), 'max': float(s.max()), 'mean': float(s.mean()),
            'out_of_range_count': int(bad), 'expected_min': lo, 'expected_max': hi
        }
    report['checks']['rainfall_consistency'] = {
        'r1_gt_r3_count': int((df.rainfall_1d_mm > df.rainfall_3d_mm + 1e-9).sum()),
        'r3_gt_r7_count': int((df.rainfall_3d_mm > df.rainfall_7d_mm + 1e-9).sum()),
    }
    report['checks']['quality_status'] = 'PASS' if all(
        x == 0 for x in report['checks']['required_missing_values'].values()
    ) and report['checks']['duplicates'] == 0 and all(
        v['out_of_range_count'] == 0 for v in report['checks']['feature_ranges'].values()
    ) and report['checks']['rainfall_consistency']['r1_gt_r3_count'] == 0 and report['checks']['rainfall_consistency']['r3_gt_r7_count'] == 0 else 'REVIEW'
    if not accuracy_ok or temporal_negatives == 0:
        report['checks']['quality_status'] = 'REVIEW'
    with open(REPORT, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))
    print(f'\nWrote {REPORT}')

if __name__ == '__main__':
    main()
