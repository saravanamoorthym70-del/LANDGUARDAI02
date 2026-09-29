$ErrorActionPreference = 'Stop'

Write-Host '=== LANDGUARD AI improved data pipeline ===' -ForegroundColor Cyan

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

Write-Host '=== Pipeline complete ===' -ForegroundColor Green
