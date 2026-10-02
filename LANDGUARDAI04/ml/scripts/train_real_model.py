"""Compare landslide classifiers with held-out-state validation and save the best."""

import json
import os
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import GroupKFold, LeaveOneGroupOut
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from ml.scripts.common import DATASET_DIR, MODELS_DIR, MODEL_FEATURES, TARGET_COLUMN, RANDOM_STATE

INPUT = os.path.join(DATASET_DIR, "LANDGUARD_FINAL_DATASET.csv")
MODEL = os.path.join(MODELS_DIR, "landslide_model.pkl")
METRICS = os.path.join(MODELS_DIR, "model_metrics.json")
ALERT_THRESHOLD = 0.70


def build_candidates():
    return {
        "logistic_regression": make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=2000, random_state=RANDOM_STATE),
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=400,
            max_depth=12,
            min_samples_leaf=8,
            max_features=0.8,
            random_state=RANDOM_STATE,
            n_jobs=-1,
        ),
        "extra_trees": ExtraTreesClassifier(
            n_estimators=400,
            min_samples_leaf=8,
            max_features=0.8,
            random_state=RANDOM_STATE,
            n_jobs=-1,
        ),
        "hist_gradient_boosting": HistGradientBoostingClassifier(
            max_iter=200,
            learning_rate=0.05,
            max_leaf_nodes=15,
            l2_regularization=2.0,
            random_state=RANDOM_STATE,
        ),
    }


def _metrics_at_threshold(target, probabilities, threshold):
    predictions = (probabilities >= threshold).astype(int)
    true_negative, false_positive, false_negative, true_positive = confusion_matrix(
        target, predictions, labels=[0, 1]
    ).ravel()
    has_both_classes = target.nunique() == 2
    return {
        "threshold": float(threshold),
        "accuracy": float(accuracy_score(target, predictions)),
        "balanced_accuracy": (
            float(balanced_accuracy_score(target, predictions))
            if has_both_classes else None
        ),
        "precision": float(precision_score(target, predictions, zero_division=0)),
        "recall": float(recall_score(target, predictions, zero_division=0)),
        "f1": float(f1_score(target, predictions, zero_division=0)),
        "false_positive_rate": (
            float(false_positive / (false_positive + true_negative))
            if false_positive + true_negative else None
        ),
        "true_negative": int(true_negative),
        "false_positive": int(false_positive),
        "false_negative": int(false_negative),
        "true_positive": int(true_positive),
    }


def _summarize_predictions(target, probabilities):
    has_both_classes = target.nunique() == 2
    return {
        "rows": int(len(target)),
        "class_counts": {
            str(key): int(value) for key, value in target.value_counts().items()
        },
        "roc_auc": (
            float(roc_auc_score(target, probabilities)) if has_both_classes else None
        ),
        "average_precision": (
            float(average_precision_score(target, probabilities))
            if has_both_classes else None
        ),
        "brier_score": float(brier_score_loss(target, probabilities)),
        "metrics_at_0_5": _metrics_at_threshold(target, probabilities, 0.5),
        "metrics_at_alert_threshold": _metrics_at_threshold(
            target, probabilities, ALERT_THRESHOLD
        ),
    }


def evaluate_by_state(estimator, features, target, groups):
    splitter = LeaveOneGroupOut()
    out_of_fold = np.full(len(target), np.nan)
    held_out_states = []
    per_state_metrics = {}

    for train_indices, test_indices in splitter.split(features, target, groups):
        fold_model = clone(estimator)
        fold_model.fit(features.iloc[train_indices], target.iloc[train_indices])
        fold_probabilities = fold_model.predict_proba(
            features.iloc[test_indices]
        )[:, 1]
        out_of_fold[test_indices] = fold_probabilities
        state = str(groups.iloc[test_indices[0]])
        held_out_states.append(state)
        fold_target = target.iloc[test_indices]
        fold_summary = _summarize_predictions(fold_target, fold_probabilities)
        metrics_at_default = fold_summary["metrics_at_0_5"]
        per_state_metrics[state] = {
            **fold_summary,
            "has_both_classes": fold_target.nunique() == 2,
            "balanced_accuracy": metrics_at_default["balanced_accuracy"],
        }

    if not np.isfinite(out_of_fold).all():
        raise RuntimeError("State-held-out validation did not predict every row.")

    valid_state_metrics = [
        values for values in per_state_metrics.values() if values["has_both_classes"]
    ]
    if not valid_state_metrics:
        raise RuntimeError("State-held-out validation has no two-class state folds.")

    pooled = _summarize_predictions(target, out_of_fold)
    default_metrics = pooled["metrics_at_0_5"]
    alert_metrics = pooled["metrics_at_alert_threshold"]
    return {
        "threshold": 0.5,
        **default_metrics,
        "roc_auc": pooled["roc_auc"],
        "average_precision": pooled["average_precision"],
        "brier_score": pooled["brier_score"],
        "alert_threshold": ALERT_THRESHOLD,
        "alert_metrics": alert_metrics,
        "held_out_states": sorted(set(held_out_states)),
        "states_excluded_from_state_means": sorted(
            state for state, values in per_state_metrics.items()
            if not values["has_both_classes"]
        ),
        "mean_state_balanced_accuracy": float(np.mean([
            values["balanced_accuracy"] for values in valid_state_metrics
        ])),
        "mean_state_average_precision": float(np.mean([
            values["average_precision"] for values in valid_state_metrics
        ])),
        "mean_state_alert_precision": float(np.mean([
            values["metrics_at_alert_threshold"]["precision"]
            for values in valid_state_metrics
        ])),
        "per_state_metrics": per_state_metrics,
    }


def evaluate_spatial_cv(estimator, features, target, spatial_groups):
    splitter = GroupKFold(n_splits=5)
    out_of_fold = np.full(len(target), np.nan)
    for train_indices, test_indices in splitter.split(
        features, target, groups=spatial_groups
    ):
        fold_model = clone(estimator)
        fold_model.fit(features.iloc[train_indices], target.iloc[train_indices])
        out_of_fold[test_indices] = fold_model.predict_proba(
            features.iloc[test_indices]
        )[:, 1]

    if not np.isfinite(out_of_fold).all():
        raise RuntimeError("Spatial validation did not predict every row.")
    return {
        "method": "5-fold grouped validation with 0.5-degree coordinate blocks",
        **_summarize_predictions(target, out_of_fold),
    }


def evaluate_temporal_holdout(candidates, data, features, target, groups):
    date_values = pd.Series(pd.NaT, index=data.index, dtype="datetime64[ns]")
    for column in ("event_date", "sample_date"):
        if column in data:
            date_values = date_values.fillna(
                pd.to_datetime(data[column], errors="coerce")
            )

    valid_dates = date_values.notna()
    if valid_dates.sum() < 10:
        return {"available": False, "reason": "Insufficient dated samples."}

    cutoff = date_values.loc[valid_dates].quantile(0.8)
    train_mask = valid_dates & (date_values <= cutoff)
    test_mask = valid_dates & (date_values > cutoff)
    train_indices = np.flatnonzero(train_mask.to_numpy())
    test_indices = np.flatnonzero(test_mask.to_numpy())
    train_target = target.iloc[train_indices]
    test_target = target.iloc[test_indices]
    if train_target.nunique() < 2 or test_target.nunique() < 2:
        return {
            "available": False,
            "reason": "The chronological split must contain both classes in train and test.",
            "cutoff": cutoff.date().isoformat(),
        }

    train_groups = groups.iloc[train_indices]
    temporal_comparison = {
        name: evaluate_by_state(
            estimator,
            features.iloc[train_indices].reset_index(drop=True),
            train_target.reset_index(drop=True),
            train_groups.reset_index(drop=True),
        )
        for name, estimator in candidates.items()
    }
    selected_name = max(
        temporal_comparison,
        key=lambda name: (
            temporal_comparison[name]["mean_state_average_precision"],
            temporal_comparison[name]["mean_state_balanced_accuracy"],
            -temporal_comparison[name]["alert_metrics"]["false_positive_rate"],
        ),
    )
    temporal_model = clone(candidates[selected_name]).fit(
        features.iloc[train_indices], train_target
    )
    probabilities = temporal_model.predict_proba(features.iloc[test_indices])[:, 1]
    return {
        "available": True,
        "method": "chronological 80/20 holdout; model selected using training period only",
        "cutoff": cutoff.date().isoformat(),
        "selected_model": selected_name,
        "train_rows": int(len(train_indices)),
        "test_rows": int(len(test_indices)),
        **_summarize_predictions(test_target, probabilities),
    }


def main():
    if not os.path.exists(INPUT):
        raise SystemExit(f"Missing {INPUT}; rebuild the dataset first.")

    data = pd.read_csv(INPUT).dropna(
        subset=list(MODEL_FEATURES) + [TARGET_COLUMN, "state"]
    ).reset_index(drop=True)
    if data.empty:
        raise SystemExit("No complete labeled training rows are available.")

    state_counts = data["state"].nunique()
    if state_counts < 3:
        raise SystemExit(
            "At least three distinct state groups are required for validation. "
            "Rebuild the dataset with state metadata preserved."
        )

    features = data[list(MODEL_FEATURES)]
    target = data[TARGET_COLUMN].astype(int)
    groups = data["state"].astype(str)
    class_counts = {str(key): int(value) for key, value in target.value_counts().items()}

    comparison = {}
    candidates = build_candidates()
    for name, estimator in candidates.items():
        comparison[name] = evaluate_by_state(estimator, features, target, groups)

    selected_name = max(
        comparison,
        key=lambda name: (
            comparison[name]["mean_state_average_precision"],
            comparison[name]["mean_state_balanced_accuracy"],
            -comparison[name]["alert_metrics"]["false_positive_rate"],
        ),
    )
    selected_model = clone(candidates[selected_name]).fit(features, target)

    temporal_validation = evaluate_temporal_holdout(
        candidates, data, features, target, groups
    )
    if {"latitude", "longitude"}.issubset(data.columns):
        spatial_groups = (
            (np.floor(data["latitude"].astype(float) * 2).astype(int).astype(str))
            + ":"
            + (np.floor(data["longitude"].astype(float) * 2).astype(int).astype(str))
        )
        if spatial_groups.nunique() >= 5:
            spatial_validation = evaluate_spatial_cv(
                candidates[selected_name], features, target, spatial_groups
            )
        else:
            spatial_validation = {
                "available": False,
                "reason": "Fewer than five spatial blocks are available.",
            }
    else:
        spatial_validation = {
            "available": False,
            "reason": "Latitude and longitude columns are unavailable.",
        }

    result = {
        "selected_model": selected_name,
        "selection_objective": "mean_state_average_precision",
        "validation_method": "leave_one_state_out",
        "validation_rows": int(len(data)),
        "state_count": int(state_counts),
        "class_counts": class_counts,
        "threshold_for_metrics": 0.5,
        "alert_threshold": ALERT_THRESHOLD,
        "spatial_validation": spatial_validation,
        "temporal_validation": temporal_validation,
        "score_semantics": "screening score; not a calibrated event probability",
        "models": comparison,
    }
    artifact = {
        "model": selected_model,
        "features": list(MODEL_FEATURES),
        "warning_threshold": ALERT_THRESHOLD,
        "model_type": selected_name,
        "version": "5.0-threshold-spatial-temporal-validation",
        "score_semantics": result["score_semantics"],
        "validation_method": result["validation_method"],
        "metrics": comparison[selected_name],
    }

    os.makedirs(MODELS_DIR, exist_ok=True)
    joblib.dump(artifact, MODEL)
    with open(METRICS, "w", encoding="utf-8") as metrics_file:
        json.dump(result, metrics_file, indent=2)

    print(json.dumps(result, indent=2))
    print(f"\nSelected {selected_name}; wrote {MODEL}")


if __name__ == "__main__":
    main()