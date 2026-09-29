# LANDGUARD AI model card

## Current model

- Estimator: calibrated Random Forest (`CalibratedClassifierCV` + `RandomForestClassifier`)
- Input features: rainfall 1d/3d/7d, surface soil moisture, elevation, slope
- Training dataset shipped: `LANDGUARD_FINAL_DATASET.csv`
- The shipped dataset contains 494 historical positive observations and 649 background/pseudo-absence observations.

## Validation

The training script creates a stratified 80/20 holdout and uses out-of-fold probabilities on the training partition to select a recall-oriented warning threshold. The test set is not used to tune that threshold.

Important: the shipped dataset is still based on historical events plus pseudo-absence background samples. Random train/test validation can overestimate generalization when nearby locations are correlated. **Do not describe the current metrics as operational or spatially validated.** Run the improved polygon + date-matched pipeline and spatial/group validation before deployment.

## Risk bands

- LOW: probability < 0.40
- MEDIUM: 0.40–<0.70
- HIGH: >= 0.70

The model also stores a separate optimized `warning_threshold` for alerting. An alert threshold is not the same thing as the UI HIGH-risk band.
