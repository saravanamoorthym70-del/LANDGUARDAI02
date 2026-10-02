import pandas as pd
import pytest

from ml.scripts.enrich_osm_context import nearest_distance_km
from ml.scripts.combine_ml_dataset import merge_osm_context
from ml.scripts.inspect_nasa_data import filter_accurate_events


def test_filter_accurate_events_keeps_exact_and_within_one_kilometer():
    events = pd.DataFrame(
        {
            "event_id": [1, 2, 3, 4],
            "location_accuracy": ["exact", "1km", "5km", "unknown"],
        }
    )

    filtered, summary = filter_accurate_events(events)

    assert filtered["event_id"].tolist() == [1, 2]
    assert filtered["location_accuracy_km"].tolist() == [0.0, 1.0]
    assert summary == {
        "available": True,
        "input_rows": 4,
        "retained_rows": 2,
        "excluded_rows": 2,
        "max_accuracy_km": 1.0,
    }


def test_filter_accurate_events_leaves_rows_when_accuracy_field_is_absent():
    events = pd.DataFrame({"event_id": [1, 2]})

    filtered, summary = filter_accurate_events(events)

    assert filtered.equals(events)
    assert summary["available"] is False
    assert summary["retained_rows"] == 2


def test_nearest_distance_km_returns_nearest_and_leaves_out_of_range_missing():
    geopandas = pytest.importorskip("geopandas")
    shapely = pytest.importorskip("shapely.geometry")

    samples = geopandas.GeoDataFrame(
        {"sample_id": [0, 1]},
        geometry=[shapely.Point(92.0, 25.0), shapely.Point(94.0, 26.0)],
        crs="EPSG:4326",
    )
    roads = geopandas.GeoDataFrame(
        geometry=[shapely.LineString([(92.001, 25.0), (92.001, 25.01)])],
        crs="EPSG:4326",
    )

    distances = nearest_distance_km(samples, roads, max_distance_km=5)

    assert distances.loc[0] == pytest.approx(0.1, abs=0.02)
    assert pd.isna(distances.loc[1])


def test_merge_osm_context_replaces_placeholder_columns():
    data = pd.DataFrame(
        {
            "latitude": [25.0],
            "longitude": [92.0],
            "state": ["Assam"],
            "distance_to_road_km": [pd.NA],
            "distance_to_settlement_km": [pd.NA],
        }
    )
    context = pd.DataFrame(
        {
            "latitude": [25.0],
            "longitude": [92.0],
            "state": ["Assam"],
            "distance_to_road_km": [0.5],
            "distance_to_settlement_km": [1.2],
        }
    )

    merged = merge_osm_context(data, context)

    assert merged.loc[0, "distance_to_road_km"] == 0.5
    assert merged.loc[0, "distance_to_settlement_km"] == 1.2
    assert not any(column.endswith(("_x", "_y")) for column in merged.columns)