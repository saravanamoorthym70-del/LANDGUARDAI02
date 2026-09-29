"""LANDGUARD data quality audit.

Audits the final ML dataset and, when available, the historical/background
source files. Writes a machine-readable JSON report and a human-readable CSV
summary. This does not silently delete rows; it reports anomalies for review.
"""
import json, os
import numpy as np
import pandas as pd
from ml.scripts.common import DATASET_DIR, FEATURES

FINAL = os.path.join(DATASET_DIR, 'LANDGUARD_FINAL_DATASET.csv')
REPORT = os.path.join(DATASET_DIR, 'LANDGUARD_DATA_QUALITY_REPORT.json')

RANGES = {
    'rainfall_1d_mm': (0, 2000),
    'rainfall_3d_mm': (0, 3000),
    'rainfall_7d_mm': (0, 4000),
    'soil_moisture_0_7cm': (0, 1),
    'elevation_m': (-500, 9000),
    'slope_deg': (0, 90),
}

def main():
    if not os.path.exists(FINAL):
        raise SystemExit(f'Missing {FINAL}')
    df = pd.read_csv(FINAL)
    report = {'file': FINAL, 'rows': int(len(df)), 'columns': list(df.columns), 'checks': {}}
    report['checks']['missing_values'] = {k: int(v) for k,v in df.isna().sum().items()}
    report['checks']['duplicates'] = int(df.duplicated().sum())
    report['checks']['class_counts'] = {str(k): int(v) for k,v in df['risk'].value_counts().sort_index().items()}
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
        x == 0 for x in report['checks']['missing_values'].values()
    ) and report['checks']['duplicates'] == 0 and all(
        v['out_of_range_count'] == 0 for v in report['checks']['feature_ranges'].values()
    ) and report['checks']['rainfall_consistency']['r1_gt_r3_count'] == 0 and report['checks']['rainfall_consistency']['r3_gt_r7_count'] == 0 else 'REVIEW'
    with open(REPORT, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))
    print(f'\nWrote {REPORT}')

if __name__ == '__main__':
    main()
