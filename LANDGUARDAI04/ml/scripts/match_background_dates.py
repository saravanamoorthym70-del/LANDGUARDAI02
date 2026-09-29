"""Assign seasonally/year-matched dates to background locations.

For each background point, sample a date from historical landslide dates in the
same state when possible. This prevents a simple time-period difference between
positive and background classes from becoming a shortcut for the model.
"""
import os, sys
import numpy as np
import pandas as pd
from ml.scripts.common import DATASET_DIR

BG=os.path.join(DATASET_DIR,'BACKGROUND_LOCATIONS.csv')
HIST=os.path.join(DATASET_DIR,'INDIA_TARGET_REGIONS_landslides.csv')
OUT=os.path.join(DATASET_DIR,'BACKGROUND_LOCATIONS_DATED.csv')

def main():
    for p in (BG,HIST):
        if not os.path.exists(p): raise SystemExit(f'Missing {p}')
    bg=pd.read_csv(BG); hist=pd.read_csv(HIST)
    hist['event_date']=pd.to_datetime(hist['event_date'],errors='coerce')
    hist=hist.dropna(subset=['event_date']).copy()
    rng=np.random.default_rng(42)
    global_dates=hist.event_date.tolist()
    dates=[]
    for _,r in bg.iterrows():
        candidates=hist.loc[hist.state.astype(str).str.strip()==str(r.get('state','')).strip(),'event_date'].tolist()
        if not candidates: candidates=global_dates
        d=rng.choice(candidates)
        dates.append(pd.Timestamp(d).strftime('%Y-%m-%d'))
    bg['sample_date']=dates
    bg.to_csv(OUT,index=False)
    print(f'Wrote {OUT} ({len(bg)} rows)')

if __name__=='__main__': main()
