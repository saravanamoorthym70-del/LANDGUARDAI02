"""Measure OSM road and settlement proximity for Northeast training rows."""

import argparse
import os

import pandas as pd

from ml.scripts.common import DATASET_DIR

INPUT_CSV = os.path.join(DATASET_DIR, "LANDGUARD_FINAL_DATASET.csv")
OUTPUT_CSV = os.path.join(DATASET_DIR, "OSM_DISTANCE_FEATURES.csv")
NER_STATES = {
    "Arunachal Pradesh",
    "Assam",
    "Manipur",
    "Meghalaya",
    "Mizoram",
    "Nagaland",
    "Sikkim",
    "Tripura",
}
DISTANCE_CRS = "+proj=aeqd +lat_0=25 +lon_0=92 +datum=WGS84 +units=m +no_defs"
MAX_SEARCH_DISTANCE_KM = 20.0
BOUNDING_BOX_BUFFER_DEG = 0.25
DISTANCE_COLUMNS = ("distance_to_road_km", "distance_to_settlement_km")


def _tag_present(values):
    return values.fillna("").astype(str).str.strip().ne("")


def nearest_distance_km(samples, features, max_distance_km=MAX_SEARCH_DISTANCE_KM):
    import geopandas as gpd

    if features.empty:
        return pd.Series(float("nan"), index=samples["sample_id"], dtype=float)

    projected_samples = samples.to_crs(DISTANCE_CRS)
    projected_features = features.to_crs(DISTANCE_CRS)
    joined = gpd.sjoin_nearest(
        projected_samples,
        projected_features[["geometry"]],
        how="left",
        max_distance=max_distance_km * 1000,
        distance_col="distance_m",
    )
    return (
        joined.groupby("sample_id")["distance_m"]
        .min()
        .reindex(samples["sample_id"])
        .div(1000)
    )


def _read_osm_features(pbf_paths, bounds):
    import geopandas as gpd
    import pyogrio

    roads = []
    settlement_areas = []
    settlement_points = []
    for path in pbf_paths:
        road_frame = pyogrio.read_dataframe(
            path,
            layer="lines",
            columns=["osm_id", "highway"],
            where="highway IS NOT NULL",
            bbox=bounds,
        )
        road_frame = road_frame.loc[_tag_present(road_frame["highway"])]
        if not road_frame.empty:
            road_frame["osm_id"] = road_frame["osm_id"].astype(str)
            roads.append(road_frame[["osm_id", "geometry"]])

        area_frame = pyogrio.read_dataframe(
            path,
            layer="multipolygons",
            columns=["osm_id", "place", "landuse"],
            where="place IS NOT NULL OR landuse='residential'",
            bbox=bounds,
        )
        area_mask = _tag_present(area_frame["place"]) | area_frame[
            "landuse"
        ].fillna("").eq("residential")
        area_frame = area_frame.loc[area_mask]
        if not area_frame.empty:
            area_frame["osm_id"] = area_frame["osm_id"].astype(str)
            settlement_areas.append(area_frame[["osm_id", "geometry"]])

        place_frame = pyogrio.read_dataframe(
            path,
            layer="points",
            columns=["osm_id", "place"],
            where="place IS NOT NULL",
            bbox=bounds,
        )
        place_frame = place_frame.loc[_tag_present(place_frame["place"])]
        if not place_frame.empty:
            place_frame["osm_id"] = place_frame["osm_id"].astype(str)
            settlement_points.append(place_frame[["osm_id", "geometry"]])

        print(
            f"{os.path.basename(path)}: roads={len(road_frame)}, "
            f"settlement_areas={len(area_frame)}, place_points={len(place_frame)}"
        )

    def combine(frames, layer_name):
        if not frames:
            return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
        result = gpd.GeoDataFrame(
            pd.concat(frames, ignore_index=True), geometry="geometry", crs="EPSG:4326"
        )
        result = result.drop_duplicates("osm_id").drop(columns="osm_id")
        if layer_name == "settlement":
            result["geometry"] = result.geometry.make_valid()
        return result.loc[result.geometry.notna() & ~result.geometry.is_empty]

    roads_frame = combine(roads, "road")
    settlements_frame = combine(
        settlement_areas + settlement_points, "settlement"
    )
    return roads_frame, settlements_frame


def enrich_dataset(pbf_paths):
    import geopandas as gpd

    if not os.path.exists(INPUT_CSV):
        raise SystemExit(f"Missing {INPUT_CSV}; build the combined dataset first.")
    missing_paths = [path for path in pbf_paths if not os.path.exists(path)]
    if missing_paths:
        raise SystemExit("Missing OSM PBF files: " + ", ".join(missing_paths))

    data = pd.read_csv(INPUT_CSV)
    target_rows = data.loc[data["state"].isin(NER_STATES)]
    samples = target_rows[["latitude", "longitude", "state"]].drop_duplicates()
    samples = samples.reset_index(drop=True)
    if samples.empty:
        raise SystemExit("No Northeast sample locations are present in the dataset.")
    samples["sample_id"] = range(len(samples))

    bounds = (
        float(samples["longitude"].min()) - BOUNDING_BOX_BUFFER_DEG,
        float(samples["latitude"].min()) - BOUNDING_BOX_BUFFER_DEG,
        float(samples["longitude"].max()) + BOUNDING_BOX_BUFFER_DEG,
        float(samples["latitude"].max()) + BOUNDING_BOX_BUFFER_DEG,
    )
    points = gpd.GeoDataFrame(
        samples,
        geometry=gpd.points_from_xy(samples["longitude"], samples["latitude"]),
        crs="EPSG:4326",
    )
    roads, settlements = _read_osm_features(pbf_paths, bounds)

    distances = samples[["latitude", "longitude", "state"]].copy()
    distances["distance_to_road_km"] = nearest_distance_km(points, roads).to_numpy()
    distances["distance_to_settlement_km"] = nearest_distance_km(
        points, settlements
    ).to_numpy()
    distances.to_csv(OUTPUT_CSV, index=False)

    base = data.drop(columns=list(DISTANCE_COLUMNS), errors="ignore")
    enriched = base.merge(
        distances,
        on=["latitude", "longitude", "state"],
        how="left",
        validate="many_to_one",
    )
    enriched.to_csv(INPUT_CSV, index=False)
    for column in DISTANCE_COLUMNS:
        valid = enriched.loc[enriched.state.isin(NER_STATES), column].notna().sum()
        print(f"{column}: {valid}/{len(target_rows)} Northeast rows covered")
    print(f"Wrote {OUTPUT_CSV} and updated {INPUT_CSV}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pbf",
        action="append",
        required=True,
        help="Path to an OSM PBF regional extract; repeat for multiple zones.",
    )
    args = parser.parse_args()
    enrich_dataset(args.pbf)


if __name__ == "__main__":
    main()