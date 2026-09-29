# LANDGUARD AI model card

## Current model

- Current estimator: HistGradientBoosting, selected from Logistic Regression, Random Forest, Extra Trees, and HistGradientBoosting using held-out-state validation
- Input features: rainfall 1d/3d/7d, surface soil moisture, elevation
- Slope is displayed as contextual terrain information but is not used by the current estimator.
- Training dataset shipped: `LANDGUARD_FINAL_DATASET.csv`
- The training dataset contains 390 historical positive observations and 975 background/pseudo-absence observations.

## Validation

The training script compares four classifiers with leave-one-state-out validation. Every row from the held-out state is excluded from that fold's training set. The saved metrics include balanced accuracy, precision, recall, ROC AUC, average precision, Brier score, and false-positive rate at a 0.50 screening threshold.

The labels distinguish historical landslide records from sampled background locations; the backgrounds are not verified landslide-free observations. The output is a **screening score, not a calibrated probability of a landslide at a specific place and time**. State-held-out results are a stronger check than random splitting, but do not establish operational performance or safety. Use verified event/non-event observations, temporal validation, and domain review before operational use.

## Risk bands

- LOW: screening score < 0.40
- MEDIUM: screening score 0.40–<0.70
- HIGH: screening score >= 0.70

The warning threshold is fixed at 0.70 to match the UI HIGH-risk band. It is a prototype screening threshold, not an emergency-warning standard.
