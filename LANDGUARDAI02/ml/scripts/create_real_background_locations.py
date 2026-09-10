"""Create spatially valid background/pseudo-absence samples.

Preferred workflow:
  1. Provide a GeoJSON with the 13 target-state polygons.
  2. Sample points strictly inside polygons.
  3. Keep points outside an exclusion radius from known landslides.
  4. Assign a matched historical sample date later with match_background_dates.py.

This replaces rectangle/bounding-box sampling. The script deliberately refuses
to fall back to bounding boxes because that can create points outside states.

Expected boundary file: ml/dataset/target_states.geojson
Properties should contain a state name under one of:
state, ST_NM, NAME_1, name, NAME.
"""
import os, sys
import numpy as np
import pandas as pd

DATASET_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'dataset'))
BOUNDARY = os.path.join(DATASET_DIR, 'target_states.geojson')
LANDSLIDES = os.path.join(DATASET_DIR, 'INDIA_TARGET_REGIONS_landslides.csv')
OUTPUT = os.path.join(DATASET_DIR, 'BACKGROUND_LOCATIONS.csv')
STATES = ['Assam','Arunachal Pradesh','Meghalaya','Manipur','Mizoram','Nagaland','Sikkim','Tripura','Tamil Nadu','Kerala','Karnataka','Andhra Pradesh','Telangana']
PER_STATE = int(os.environ.get('BACKGROUND_PER_STATE', '75'))
MIN_DISTANCE_KM = float(os.environ.get('BACKGROUND_MIN_DISTANCE_KM', '10'))
SEED = 42

def main():
    if not os.path.exists(BOUNDARY):
        raise SystemExit(f'Missing {BOUNDARY}. Add an official state-boundary GeoJSON before sampling; no bounding-box fallback is used.')
    try:
        import geopandas as gpd
        from shapely.geometry import Point
    except ImportError as exc:
        raise SystemExit('Install geopandas and shapely to generate polygon-constrained background samples.') from exc
    lands = pd.read_csv(LANDSLIDES)
    lands = lands.dropna(subset=['latitude','longitude'])
    # GeoJSON is assumed WGS84; reproject to a metric CRS for distance checks.
    g = gpd.read_file(BOUNDARY)
    if g.crs is None:
        g = g.set_crs('EPSG:4326')
    g = g.to_crs('EPSG:4326')
    name_col = next((c for c in ['state','ST_NM','NAME_1','name','NAME'] if c in g.columns), None)
    if not name_col:
        raise SystemExit('Boundary GeoJSON needs a state-name property: state/ST_NM/NAME_1/name/NAME.')
    g[name_col] = g[name_col].astype(str).str.strip()
    missing = [s for s in STATES if s not in set(g[name_col])]
    if missing:
        raise SystemExit('Boundary file is missing target states: ' + ', '.join(missing))
    # Use local metric projection for distance checks; UTM zones vary, so use an azimuthal
    # approximation through haversine for candidate-to-event filtering.
    lat1 = np.radians(lands.latitude.to_numpy()); lon1 = np.radians(lands.longitude.to_numpy())
    rng = np.random.default_rng(SEED)
    rows=[]
    for state in STATES:
        poly = g.loc[g[name_col] == state].geometry.unary_union
        minx,miny,maxx,maxy = poly.bounds
        accepted=[]; attempts=0; max_attempts=PER_STATE*500
        while len(accepted) < PER_STATE and attempts < max_attempts:
            attempts += 1
            lon=float(rng.uniform(minx,maxx)); lat=float(rng.uniform(miny,maxy))
            if not poly.contains(Point(lon,lat)):
                continue
            la=np.radians(lat); lo=np.radians(lon)
            dlat=lat1-la; dlon=lon1-lo
            a=np.sin(dlat/2)**2 + np.cos(la)*np.cos(lat1)*np.sin(dlon/2)**2
            km=6371.0088*2*np.arcsin(np.sqrt(a))
            if len(km) and float(km.min()) < MIN_DISTANCE_KM:
                continue
            accepted.append((lat,lon))
        if len(accepted) < PER_STATE:
            raise SystemExit(f'Could only create {len(accepted)}/{PER_STATE} points for {state}.')
        for lat,lon in accepted:
            rows.append({'latitude':lat,'longitude':lon,'state':state,'sample_type':'background','risk':0})
        print(f'{state}: {len(accepted)} background points')
    out=pd.DataFrame(rows)
    out.to_csv(OUTPUT,index=False)
    print(f'Wrote {OUTPUT} ({len(out)} rows), minimum exclusion distance={MIN_DISTANCE_KM} km')

if __name__=='__main__': main()
