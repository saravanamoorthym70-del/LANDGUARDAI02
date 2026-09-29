import logging
import os

import joblib
import pandas as pd

from backend.risk_engine import calculate_risk

logger = logging.getLogger("landguard.ml_predictor")

MODEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "ml", "models", "landslide_model.pkl",
)

FEATURES = [
    "rainfall_1d_mm", "rainfall_3d_mm", "rainfall_7d_mm",
    "soil_moisture_0_7cm", "elevation_m",
]

LOW_THRESHOLD = 0.40
HIGH_THRESHOLD = 0.70
DEFAULT_ALERT_THRESHOLD = HIGH_THRESHOLD


def _load_model():
    if not os.path.exists(MODEL_PATH):
        logger.warning("Model file not found at %s; rule-based fallback active.", MODEL_PATH)
        return None
    try:
        return joblib.load(MODEL_PATH)
    except Exception:
        logger.exception("Failed to load model at %s", MODEL_PATH)
        return None


model = _load_model()


def model_is_loaded() -> bool:
    return model is not None


def _unwrap_model(artifact):
    """Support both the old sklearn estimator and the new model bundle."""
    if isinstance(artifact, dict) and "model" in artifact:
        return artifact["model"], artifact
    return artifact, {}


def predict_risk(
    rainfall_1d_mm, rainfall_3d_mm, rainfall_7d_mm,
    soil_moisture_0_7cm, elevation_m, slope_deg,
):
    if model is not None:
        estimator, metadata = _unwrap_model(model)
        data = pd.DataFrame([{
            "rainfall_1d_mm": rainfall_1d_mm,
            "rainfall_3d_mm": rainfall_3d_mm,
            "rainfall_7d_mm": rainfall_7d_mm,
            "soil_moisture_0_7cm": soil_moisture_0_7cm,
            "elevation_m": elevation_m,
        }])[FEATURES]

        probability = float(estimator.predict_proba(data)[0][1])
        # Keep alerts consistent with the HIGH band, including older artifacts
        # whose optimized threshold may be lower.
        if probability >= HIGH_THRESHOLD:
            risk_level = "HIGH"
        elif probability >= LOW_THRESHOLD:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        alert_threshold = max(
            float(metadata.get("warning_threshold", DEFAULT_ALERT_THRESHOLD)),
            HIGH_THRESHOLD,
        )
        return {
            "risk_probability": round(probability, 4),
            "risk_percentage": round(probability * 100, 2),
            "risk_level": risk_level,
            "alert_triggered": probability >= alert_threshold,
            "alert_threshold_percentage": round(alert_threshold * 100, 2),
            "mode": "ml_model",
            "model_version": metadata.get("version", "unknown"),
            "score_semantics": metadata.get(
                "score_semantics",
                "prototype screening score; not a calibrated event probability",
            ),
        }

    fallback = calculate_risk(
        rainfall=rainfall_7d_mm,
        soil_moisture=soil_moisture_0_7cm * 100 if soil_moisture_0_7cm <= 1 else soil_moisture_0_7cm,
        slope=slope_deg,
        elevation=elevation_m,
        past_landslide=False,
    )
    return {
        "risk_probability": round(fallback["risk_score"] / 100, 4),
        "risk_percentage": float(fallback["risk_score"]),
        "risk_level": fallback["risk_level"],
        "alert_triggered": fallback["risk_score"] >= 70,
        "alert_threshold_percentage": 70.0,
        "mode": "rule_based_fallback",
        "model_version": "fallback",
        "score_semantics": "rule-based screening score; not an event probability",
    }
