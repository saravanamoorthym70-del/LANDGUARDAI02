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
from sklearn.model_selection import LeaveOneGroupOut
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
        fold_predictions = (fold_probabilities >= 0.5).astype(int)
        per_state_metrics[state] = {
            "rows": int(len(test_indices)),
            "balanced_accuracy": float(
                balanced_accuracy_score(fold_target, fold_predictions)
            ),
            "average_precision": float(
                average_precision_score(fold_target, fold_probabilities)
            ),
        }

    if not np.isfinite(out_of_fold).all():
        raise RuntimeError("State-held-out validation did not predict every row.")

    predictions = (out_of_fold >= 0.5).astype(int)
    true_negative, false_positive, false_negative, true_positive = confusion_matrix(
        target, predictions, labels=[0, 1]
    ).ravel()
    metrics = {
        "threshold": 0.5,
        "accuracy": float(accuracy_score(target, predictions)),
        "balanced_accuracy": float(balanced_accuracy_score(target, predictions)),
        "precision": float(precision_score(target, predictions, zero_division=0)),
        "recall": float(recall_score(target, predictions, zero_division=0)),
        "f1": float(f1_score(target, predictions, zero_division=0)),
        "roc_auc": float(roc_auc_score(target, out_of_fold)),
        "average_precision": float(average_precision_score(target, out_of_fold)),
        "brier_score": float(brier_score_loss(target, out_of_fold)),
        "false_positive_rate": float(
            false_positive / max(false_positive + true_negative, 1)
        ),
        "true_negative": int(true_negative),
        "false_positive": int(false_positive),
        "false_negative": int(false_negative),
        "true_positive": int(true_positive),
        "held_out_states": sorted(set(held_out_states)),
        "mean_state_balanced_accuracy": float(
            np.mean([values["balanced_accuracy"] for values in per_state_metrics.values()])
        ),
        "mean_state_average_precision": float(
            np.mean([values["average_precision"] for values in per_state_metrics.values()])
        ),
        "per_state_metrics": per_state_metrics,
    }
    return metrics


def main():
    if not os.path.exists(INPUT):
        raise SystemExit(f"Missing {INPUT}; rebuild the dataset first.")

    data = pd.read_csv(INPUT).dropna(
        subset=list(MODEL_FEATURES) + [TARGET_COLUMN, "state"]
    )
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
            comparison[name]["mean_state_balanced_accuracy"],
            comparison[name]["mean_state_average_precision"],
            -comparison[name]["false_positive_rate"],
        ),
    )
    selected_model = clone(candidates[selected_name]).fit(features, target)

    result = {
        "selected_model": selected_name,
        "validation_method": "leave_one_state_out",
        "validation_rows": int(len(data)),
        "state_count": int(state_counts),
        "class_counts": class_counts,
        "threshold_for_metrics": 0.5,
        "score_semantics": "screening score; not a calibrated event probability",
        "models": comparison,
    }
    artifact = {
        "model": selected_model,
        "features": list(MODEL_FEATURES),
        "warning_threshold": ALERT_THRESHOLD,
        "model_type": selected_name,
        "version": "4.0-state-held-out-validation",
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