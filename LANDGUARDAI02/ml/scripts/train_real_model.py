"""Train LANDGUARD's calibrated Random Forest model.

Uses out-of-fold probabilities to choose a warning threshold without tuning on
the held-out test set. The saved artifact is a bundle containing the estimator,
features, threshold, metrics and training metadata.
"""
import json, os, sys
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_predict
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score, precision_recall_curve
from ml.scripts.common import DATASET_DIR, MODELS_DIR, FEATURES, TARGET_COLUMN, RANDOM_STATE

INPUT=os.path.join(DATASET_DIR,'LANDGUARD_FINAL_DATASET.csv')
MODEL=os.path.join(MODELS_DIR,'landslide_model.pkl')
METRICS=os.path.join(MODELS_DIR,'model_metrics.json')

def best_f2(y,p):
    prec,rec,thr=precision_recall_curve(y,p)
    f2=(5*prec*rec)/(4*prec+rec+1e-12)
    i=int(np.nanargmax(f2[:-1]))
    return float(thr[i]), float(f2[i])

def main():
    if not os.path.exists(INPUT): raise SystemExit(f'Missing {INPUT}')
    df=pd.read_csv(INPUT).dropna(subset=FEATURES+[TARGET_COLUMN])
    X=df[FEATURES]; y=df[TARGET_COLUMN].astype(int)
    Xtr,Xte,ytr,yte=train_test_split(X,y,test_size=.20,random_state=RANDOM_STATE,stratify=y)
    base=RandomForestClassifier(n_estimators=500,max_depth=14,min_samples_leaf=3,class_weight='balanced_subsample',random_state=RANDOM_STATE,n_jobs=-1)
    # OOF probabilities on training partition for threshold selection.
    cv=StratifiedKFold(n_splits=5,shuffle=True,random_state=RANDOM_STATE)
    oof=cross_val_predict(base,Xtr,ytr,cv=cv,method='predict_proba',n_jobs=1)[:,1]
    threshold,f2=best_f2(ytr.to_numpy(),oof)
    calibrated=CalibratedClassifierCV(base,method='sigmoid',cv=5)
    calibrated.fit(Xtr,ytr)
    p=calibrated.predict_proba(Xte)[:,1]
    pred=(p>=threshold).astype(int)
    metrics={'accuracy':accuracy_score(yte,pred),'precision':precision_score(yte,pred,zero_division=0),'recall':recall_score(yte,pred,zero_division=0),'f1':f1_score(yte,pred,zero_division=0),'roc_auc':roc_auc_score(yte,p),'warning_threshold':threshold,'training_rows':len(Xtr),'test_rows':len(Xte),'positive_rows':int(y.sum()),'negative_rows':int((y==0).sum())}
    final=CalibratedClassifierCV(base,method='sigmoid',cv=5); final.fit(X,y)
    bundle={'model':final,'features':FEATURES,'warning_threshold':threshold,'model_type':'calibrated_random_forest','version':'3.0-data-quality-upgrade','metrics':metrics}
    joblib.dump(bundle,MODEL)
    with open(METRICS,'w') as f: json.dump(metrics,f,indent=2)
    print(json.dumps(metrics,indent=2)); print(f'Wrote {MODEL}')
if __name__=='__main__': main()
