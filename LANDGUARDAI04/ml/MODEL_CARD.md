# LANDGUARD AI model card

## Current model

- Current estimator: HistGradientBoosting, selected from Logistic Regression, Random Forest, Extra Trees, and HistGradientBoosting using mean state-level average precision, with balanced accuracy as a tie-breaker
- Input features: rainfall 1d/3d/7d, surface soil moisture, elevation
- Slope is displayed as contextual terrain information but is not used by the current estimator.
- Training dataset shipped: `LANDGUARD_FINAL_DATASET.csv`
- The training dataset contains 390 historical positive observations and 975 background/pseudo-absence observations.

## Validation

The training script compares four classifiers with leave-one-state-out validation. Every row from the held-out state is excluded from that fold's training set. It also reports 5-fold spatial-group validation using 0.5-degree coordinate blocks and a chronological 80/20 holdout. Candidate selection for the chronological holdout uses only the earlier training period. Metrics include the default 0.50 cutoff and the deployed 0.70 alert cutoff. State folds without both classes are excluded from state-level discrimination averages. Slope is not modeled because it is missing from all rows in the current dataset.

The labels distinguish historical landslide records from sampled background locations; the backgrounds are not verified landslide-free observations. The output is a **screening score, not a calibrated probability of a landslide at a specific place and time**. State-held-out, spatial-group, and chronological checks do not establish operational performance or safety. Before operational use, obtain verified event/non-event observations and independent event-based testing, and seek domain-expert review.

## Risk bands

- LOW: screening score < 0.40
- MEDIUM: screening score 0.40–<0.70
- HIGH: screening score >= 0.70

The warning threshold is fixed at 0.70 to match the UI HIGH-risk band. It is a prototype screening threshold, not an emergency-warning standard.
