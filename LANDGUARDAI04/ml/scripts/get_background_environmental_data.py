"""Fetch historical environmental conditions for dated background samples.

Input: BACKGROUND_LOCATIONS_DATED.csv (latitude, longitude, sample_date)
Output: BACKGROUND_ENVIRONMENTAL_DATA.csv
Uses the same ERA5 hourly variables as the historical positive pipeline.
"""
import os, sys, time
import pandas as pd
import requests
from ml.scripts.common import DATASET_DIR, OPEN_METEO_ARCHIVE_URL, REQUEST_TIMEOUT_SECONDS

INPUT=os.path.join(DATASET_DIR,'BACKGROUND_LOCATIONS_DATED.csv')
OUTPUT=os.path.join(DATASET_DIR,'BACKGROUND_ENVIRONMENTAL_DATA.csv')
CHECKPOINT=os.path.join(DATASET_DIR,'BACKGROUND_ENVIRONMENTAL_DATA.checkpoint.csv')
PAUSE=float(os.environ.get('OPEN_METEO_PAUSE','0.2'))

def fetch(lat,lon,date):
    end=pd.Timestamp(date); start=end-pd.Timedelta(days=6)
    params={'latitude':float(lat),'longitude':float(lon),'start_date':start.strftime('%Y-%m-%d'),'end_date':end.strftime('%Y-%m-%d'),'hourly':'precipitation,soil_moisture_0_to_7cm','timezone':'UTC','models':'era5'}
    r=requests.get(OPEN_METEO_ARCHIVE_URL,params=params,timeout=REQUEST_TIMEOUT_SECONDS); r.raise_for_status(); h=r.json().get('hourly',{})
    p=h.get('precipitation',[]); s=h.get('soil_moisture_0_to_7cm',[])
    vals=lambda x,n: [v for v in x[-n:] if v is not None]
    p1,p3,p7=vals(p,24),vals(p,72),vals(p,168); sv=vals(s,168)
    return {'rainfall_1d_mm':sum(p1),'rainfall_3d_mm':sum(p3),'rainfall_7d_mm':sum(p7),'soil_moisture_0_7cm':(sum(sv)/len(sv) if sv else None)}

def main():
    if not os.path.exists(INPUT): raise SystemExit(f'Missing {INPUT}; run match_background_dates.py first.')
    df=pd.read_csv(INPUT)
    rows=[]
    for i,r in df.iterrows():
        try: env=fetch(r.latitude,r.longitude,r.sample_date)
        except Exception as exc: print(f'[{i}] failed: {exc}'); env={k:None for k in ['rainfall_1d_mm','rainfall_3d_mm','rainfall_7d_mm','soil_moisture_0_7cm']}
        row=r.to_dict(); row.update(env); rows.append(row)
        if (i+1)%25==0: pd.DataFrame(rows).to_csv(CHECKPOINT,index=False)
        if (i+1)%25==0: print(f'{i+1}/{len(df)} processed')
        time.sleep(PAUSE)
    out=pd.DataFrame(rows); out.to_csv(OUTPUT,index=False)
    if os.path.exists(CHECKPOINT): os.remove(CHECKPOINT)
    print(f'Wrote {OUTPUT} ({len(out)} rows)')
if __name__=='__main__': main()
