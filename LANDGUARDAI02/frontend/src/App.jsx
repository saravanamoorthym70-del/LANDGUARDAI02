import React, { useMemo, useState } from "react";
import {
  Loader2,
  CheckCircle2,
  XCircle,
  MapPin,
  CloudRain,
  Droplets,
  Mountain,
  TrendingUp,
  Satellite,
  CloudSun,
  Layers,
  Cpu,
  TriangleAlert,
  CircleAlert,
  ShieldCheck,
} from "lucide-react";

import "./App.css";
import RiskMap from "./RiskMap";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

// ============================================================
// BRAND MARK — a contour-line peak, echoing the topographic
// data (elevation/slope) the whole system is built on.
// ============================================================

function BrandMark({ size = 28 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        d="M2 24 L12 8 L16 14 L21 5 L30 24"
        stroke="currentColor"
        strokeWidth="2.1"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <path
        d="M2 24 L30 24"
        stroke="currentColor"
        strokeWidth="2.1"
        strokeLinecap="round"
        opacity="0.35"
      />
      <path
        d="M8 24 C 11 20, 14 20, 17 24"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        opacity="0.55"
      />
      <path
        d="M17 24 C 20.5 19.5, 23.5 19.5, 27 24"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        opacity="0.55"
      />
    </svg>
  );
}

// ============================================================
// CONTOUR BACKGROUND — decorative topographic-line texture
// used once, behind the hero panel.
// ============================================================

function ContourField() {
  const lines = [18, 34, 50, 66, 82, 98, 114, 130];

  return (
    <svg
      className="contour-field"
      viewBox="0 0 600 200"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      {lines.map((y, i) => (
        <path
          key={y}
          d={`M -20 ${y} C 100 ${y - 22}, 180 ${y + 26}, 300 ${y} S 520 ${
            y - 18
          }, 640 ${y + 10}`}
          fill="none"
          stroke="currentColor"
          strokeWidth="1"
          opacity={0.85 - i * 0.09}
        />
      ))}
    </svg>
  );
}

// ============================================================
// RISK ICON — maps a risk level to a consistent icon. Declared
// at module scope (not inside App) so it isn't recreated every
// render.
// ============================================================

function RiskIcon({ level, size = 20 }) {
  const value = String(level || "").toUpperCase();

  if (value === "HIGH") {
    return <TriangleAlert size={size} />;
  }

  if (value === "MEDIUM") {
    return <CircleAlert size={size} />;
  }

  if (value === "LOW") {
    return <ShieldCheck size={size} />;
  }

  return <Loader2 size={size} className="spin" />;
}

// ============================================================
// RAINFALL CHART DATA
// ============================================================

function getRainfallChartData(liveRisk) {
  const rainfallDaily =
    liveRisk?.environment?.rainfall_daily || [];

  return rainfallDaily.slice(-7);
}

// ============================================================
// MAIN APP
// ============================================================

export default function App() {
  // ==========================================================
  // MANUAL PREDICTION FORM
  // ==========================================================

  const [formData, setFormData] = useState({
    rainfall_1d_mm: "",
    rainfall_3d_mm: "",
    rainfall_7d_mm: "",
    soil_moisture_0_7cm: "",
    elevation_m: "",
    slope_deg: "",
  });

  const [prediction, setPrediction] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // ==========================================================
  // LIVE MAP RISK
  // ==========================================================

  const [liveRisk, setLiveRisk] = useState(null);
  const [liveLoading, setLiveLoading] = useState(false);
  const [locationName, setLocationName] = useState("");

  const [mapMessage, setMapMessage] = useState(
    "Click anywhere on the map to perform a live AI risk assessment."
  );

  const [mapStatus, setMapStatus] = useState("idle");

  // ==========================================================
  // HANDLE FORM INPUT
  // ==========================================================

  function handleChange(event) {
    const { name, value } = event.target;

    setFormData((previous) => ({
      ...previous,
      [name]: value,
    }));
  }

  // ==========================================================
  // MANUAL AI PREDICTION
  // ==========================================================

  async function handlePrediction(event) {
    event.preventDefault();

    setLoading(true);
    setError("");
    setPrediction(null);

    try {
      const payload = {
        rainfall_1d_mm: Number(formData.rainfall_1d_mm),
        rainfall_3d_mm: Number(formData.rainfall_3d_mm),
        rainfall_7d_mm: Number(formData.rainfall_7d_mm),
        soil_moisture_0_7cm: Number(
          formData.soil_moisture_0_7cm
        ),
        elevation_m: Number(formData.elevation_m),
        slope_deg: Number(formData.slope_deg),
      };

      const response = await fetch(
        `${API_BASE}/predict-risk`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(payload),
        }
      );

      if (!response.ok) {
        throw new Error(
          `Prediction failed (${response.status})`
        );
      }

      const data = await response.json();

      setPrediction(data);
    } catch (err) {
      console.error(err);

      setError(
        "Unable to connect to the LANDGUARD AI backend. Make sure FastAPI is running."
      );
    } finally {
      setLoading(false);
    }
  }

  // ==========================================================
  // LIVE MAP CLICK
  // ==========================================================

  async function handleMapClick(location) {
    const latitude = Number(location.lat);
    const longitude = Number(location.lng);

    setLiveLoading(true);
    setLiveRisk(null);
    setLocationName("");

    setMapStatus("analyzing");
    setMapMessage(
      "LANDGUARD AI is analyzing this location..."
    );

    try {
      // ------------------------------------------------------
      // LIVE RISK
      // ------------------------------------------------------

      const riskResponse = await fetch(
        `${API_BASE}/live-risk?latitude=${latitude}&longitude=${longitude}`
      );

      if (!riskResponse.ok) {
        throw new Error(
          `Live risk request failed (${riskResponse.status})`
        );
      }

      const riskData = await riskResponse.json();

      console.log("LIVE RISK:", riskData);

      console.log(
        "DAILY RAINFALL:",
        riskData?.environment?.rainfall_daily
      );

      setLiveRisk(riskData);

      // ------------------------------------------------------
      // REVERSE GEOCODING
      // ------------------------------------------------------

      try {
        const geoResponse = await fetch(
          `${API_BASE}/reverse-geocode?latitude=${latitude}&longitude=${longitude}`
        );

        if (geoResponse.ok) {
          const geoData = await geoResponse.json();

          const name =
            geoData?.display_name ||
            geoData?.location_name ||
            geoData?.name ||
            "";

          setLocationName(name);
        }
      } catch (geoError) {
        console.warn(
          "Reverse geocoding failed:",
          geoError
        );
      }

      setMapStatus("success");
      setMapMessage(
        "Live AI risk assessment completed."
      );
    } catch (err) {
      console.error("LIVE RISK ERROR:", err);

      setMapStatus("error");
      setMapMessage(
        "Unable to analyze this location. Please check the backend connection."
      );

      setLiveRisk(null);
    } finally {
      setLiveLoading(false);
    }
  }

  // ==========================================================
  // CLEAR MANUAL PREDICTION
  // ==========================================================

  function clearPrediction() {
    setFormData({
      rainfall_1d_mm: "",
      rainfall_3d_mm: "",
      rainfall_7d_mm: "",
      soil_moisture_0_7cm: "",
      elevation_m: "",
      slope_deg: "",
    });

    setPrediction(null);
    setError("");
  }

  // ==========================================================
  // CLEAR LIVE RESULT
  // ==========================================================

  function clearLiveRisk() {
    setLiveRisk(null);
    setLocationName("");
    setMapStatus("idle");

    setMapMessage(
      "Click anywhere on the map to perform a live AI risk assessment."
    );
  }

  // ==========================================================
  // LIVE DATA
  // ==========================================================

  const liveEnvironment =
    liveRisk?.environment || {};

  const liveLocation =
    liveRisk?.location || {};

  const livePrediction =
    liveRisk?.prediction || {};

  const liveTerrain =
    liveRisk?.terrain || {};

  const liveRiskLevel =
    livePrediction?.risk_level || "";

  const liveRiskPercentage =
    livePrediction?.risk_percentage;

  const liveSoilMoisture =
    liveEnvironment?.soil_moisture_0_to_7cm ??
    liveEnvironment?.soil_moisture_0_7cm;

  // ==========================================================
  // RAINFALL DATA
  // ==========================================================

  const rainfallChartData = useMemo(
    () => getRainfallChartData(liveRisk),
    [liveRisk]
  );

  // ==========================================================
  // RISK FACTOR HELPERS
  // ==========================================================

  function getRainfallStatus(value) {
    const rainfall = Number(value);

    if (!Number.isFinite(rainfall)) {
      return "Unavailable";
    }

    if (rainfall >= 100) {
      return "Very High";
    }

    if (rainfall >= 50) {
      return "High";
    }

    if (rainfall >= 20) {
      return "Moderate";
    }

    return "Low";
  }

  function getSlopeStatus(value) {
    const slope = Number(value);

    if (!Number.isFinite(slope)) {
      return "Unavailable";
    }

    if (slope >= 35) {
      return "Very High";
    }

    if (slope >= 25) {
      return "High";
    }

    if (slope >= 15) {
      return "Moderate";
    }

    return "Low";
  }

  function getSoilStatus(value) {
    const soil = Number(value);

    if (!Number.isFinite(soil)) {
      return "Unavailable";
    }

    if (soil >= 0.45) {
      return "High";
    }

    if (soil >= 0.35) {
      return "Moderate";
    }

    return "Low";
  }

  // ==========================================================
  // RISK CLASS
  // ==========================================================

  function getRiskClass(level) {
    return String(level || "")
      .toLowerCase()
      .replace(/\s+/g, "-");
  }

  function formatRiskLabel(level) {
    const value = String(level || "");
    if (!value) return "Unknown";
    return value.charAt(0).toUpperCase() + value.slice(1).toLowerCase();
  }

  // ==========================================================
  // RISK ICON
  // ==========================================================
  // RISK RECOMMENDATION
  // ==========================================================

  function getRiskRecommendation(level) {
    const risk = String(level || "").toUpperCase();

    if (risk === "HIGH") {
      return "Immediate caution recommended. Avoid unnecessary travel through vulnerable terrain and monitor local warnings.";
    }

    if (risk === "MEDIUM") {
      return "Moderate landslide risk detected. Continue monitoring rainfall and terrain conditions.";
    }

    if (risk === "LOW") {
      return "Current environmental conditions indicate relatively low landslide risk.";
    }

    return "AI risk assessment is being processed.";
  }

  // ==========================================================
  // RENDER
  // ==========================================================

  return (
    <div className="dashboard">

      {/* ======================================================
          HEADER
      ====================================================== */}

      <header className="dashboard-header">

        <div className="header-content">

          <div className="brand">

            <div className="brand-icon">
              <BrandMark />
            </div>

            <div>
              <h1>LANDGUARD AI</h1>

              <p>
                Landslide risk monitoring for the North Eastern Region
              </p>
            </div>

          </div>

          <div className="header-status">
            <span className="status-dot" />
            System online
          </div>

        </div>

      </header>

      {/* ======================================================
          HERO
      ====================================================== */}

      <section className="hero-section">

        <ContourField />

        <div className="hero-content">

          <h2>
            Landslide risk, monitored in real time
          </h2>

          <p>
            LANDGUARD AI combines rainfall, soil moisture, and terrain
            data with a trained model to flag high-risk ground across
            NER and South India. Click anywhere on the map for an
            instant assessment.
          </p>

          <div className="hero-stats">

            <div className="hero-stat">
              <strong>494</strong>
              <span>Historical events tracked</span>
            </div>

            <div className="hero-stat">
              <strong>13</strong>
              <span>States covered</span>
            </div>

            <div className="hero-stat">
              <strong>6</strong>
              <span>Environmental signals</span>
            </div>

          </div>

        </div>

      </section>

      <main className="main-container">

        {/* ====================================================
            LIVE GIS MAP
        ==================================================== */}

        <section className="dashboard-card live-section">

          <div className="section-header">

            <div>
              <h2>
                Interactive risk map
              </h2>

              <p>
                Click anywhere on the map to perform a
                real-time AI risk assessment.
              </p>
            </div>

            {liveRisk && (
              <button
                className="clear-live-button"
                onClick={clearLiveRisk}
              >
                Clear live analysis
              </button>
            )}

          </div>

          <div className={`map-message map-message--${liveLoading ? "analyzing" : mapStatus}`}>

            {liveLoading || mapStatus === "analyzing" ? (
              <Loader2 size={15} className="spin" />
            ) : mapStatus === "success" ? (
              <CheckCircle2 size={15} />
            ) : mapStatus === "error" ? (
              <XCircle size={15} />
            ) : (
              <MapPin size={15} />
            )}

            <span>{mapMessage}</span>

          </div>

          <RiskMap
            onLocationClick={handleMapClick}
            liveRisk={liveRisk}
          />

        </section>

        {/* ====================================================
            LIVE WARNING
        ==================================================== */}

        {liveRisk && (
          <section
            className={`dashboard-card live-warning-panel ${getRiskClass(
              liveRiskLevel
            )}`}
          >

            <div className="warning-header">

              <div className="warning-icon">
                <RiskIcon level={liveRiskLevel} size={24} />
              </div>

              <div>
                <h2>
                  {formatRiskLabel(liveRiskLevel)} risk
                </h2>
              </div>

              {liveRiskPercentage !== undefined && (
                <div className="risk-score">

                  <strong>
                    {Number(
                      liveRiskPercentage
                    ).toFixed(1)}
                    %
                  </strong>

                  <span>
                    Risk score
                  </span>

                </div>
              )}

              {livePrediction?.alert_triggered && (
                <div className="early-warning-badge">
                  <TriangleAlert size={15} />
                  Early-warning threshold crossed
                </div>
              )}

            </div>

            <div className="warning-content">

              <div className="location-info">

                <span className="info-label">
                  <MapPin size={13} />
                  Location
                </span>

                <strong>
                  {locationName ||
                    "Selected map location"}
                </strong>

                <small>
                  {Number(
                    liveLocation.latitude
                  ).toFixed(4)}
                  ,{" "}
                  {Number(
                    liveLocation.longitude
                  ).toFixed(4)}
                </small>

              </div>

              <div className="recommendation">

                {livePrediction?.model_version && (
                  <small className="model-version">
                    Model: {livePrediction.model_version}
                  </small>
                )}

                <span className="info-label">
                  Recommendation
                </span>

                <p>
                  {getRiskRecommendation(
                    liveRiskLevel
                  )}
                </p>

              </div>

            </div>

          </section>
        )}


        {/* ====================================================
            LIVE ENVIRONMENT
        ==================================================== */}

        {liveRisk && (
          <section className="dashboard-card">

            <div className="section-header">

              <div>
                <h2>
                  Live environmental data
                </h2>
              </div>

            </div>

            <div className="environment-grid">

              <div className="environment-card">

                <div className="environment-icon">
                  <CloudRain size={19} />
                </div>

                <div className="environment-content">

                  <span>
                    24-hour rainfall
                  </span>

                  <strong>
                    {Number(
                      liveEnvironment.rainfall_1d_mm
                    ).toFixed(1)}
                    <small> mm</small>
                  </strong>

                </div>

              </div>

              <div className="environment-card">

                <div className="environment-icon">
                  <CloudRain size={19} />
                </div>

                <div className="environment-content">

                  <span>
                    3-day rainfall
                  </span>

                  <strong>
                    {Number(
                      liveEnvironment.rainfall_3d_mm
                    ).toFixed(1)}
                    <small> mm</small>
                  </strong>

                </div>

              </div>

              <div className="environment-card">

                <div className="environment-icon">
                  <CloudRain size={19} />
                </div>

                <div className="environment-content">

                  <span>
                    7-day rainfall
                  </span>

                  <strong>
                    {Number(
                      liveEnvironment.rainfall_7d_mm
                    ).toFixed(1)}
                    <small> mm</small>
                  </strong>

                </div>

              </div>

              <div className="environment-card">

                <div className="environment-icon">
                  <Droplets size={19} />
                </div>

                <div className="environment-content">

                  <span>
                    Soil moisture
                  </span>

                  <strong>
                    {Number.isFinite(
                      Number(liveSoilMoisture)
                    )
                      ? Number(
                          liveSoilMoisture
                        ).toFixed(3)
                      : "N/A"}
                  </strong>

                </div>

              </div>

              <div className="environment-card">

                <div className="environment-icon">
                  <Mountain size={19} />
                </div>

                <div className="environment-content">

                  <span>
                    Elevation
                  </span>

                  <strong>
                    {Number(
                      liveEnvironment.elevation_m
                    ).toFixed(0)}
                    <small> m</small>
                  </strong>

                </div>

              </div>

              <div className="environment-card">

                <div className="environment-icon">
                  <TrendingUp size={19} />
                </div>

                <div className="environment-content">

                  <span>
                    Terrain slope
                  </span>

                  <strong>
                    {Number(
                      liveTerrain.slope_deg
                    ).toFixed(2)}
                    <small>°</small>
                  </strong>

                </div>

              </div>

            </div>

          </section>
        )}

        {/* ====================================================
            RAINFALL CHART
        ==================================================== */}

        {liveRisk &&
          rainfallChartData.length > 0 && (

          <section className="dashboard-card rainfall-chart-section">

            <div className="section-header">

              <div>
                <h2>
                  Recent daily rainfall
                </h2>

                <p>
                  Rainfall observed across the latest
                  available days.
                </p>
              </div>

            </div>

            <div className="rainfall-chart">

              {rainfallChartData.map(
                (item, index) => {

                  const value = Number(
                    item.rainfall_mm
                  );

                  const maxRainfall =
                    Math.max(
                      ...rainfallChartData.map(
                        (entry) =>
                          Number(
                            entry.rainfall_mm
                          )
                      ),
                      1
                    );

                  const height =
                    Math.max(
                      (value /
                        maxRainfall) *
                        100,
                      4
                    );

                  return (
                    <div
                      className="rainfall-bar-wrapper"
                      key={`${item.date}-${index}`}
                    >

                      <div className="rainfall-value">
                        {value.toFixed(1)}
                      </div>

                      <div className="rainfall-bar-container">

                        <div
                          className="rainfall-bar"
                          style={{
                            height: `${height}%`,
                          }}
                        />

                      </div>

                      <div className="rainfall-date">
                        {item.date}
                      </div>

                    </div>
                  );
                }
              )}

            </div>

          </section>
        )}

        {/* ====================================================
            EXPLAINABLE AI
        ==================================================== */}

        {liveRisk && (
          <section className="dashboard-card">

            <div className="section-header">

              <div>
                <h2>
                  Key risk factors
                </h2>

                <p>
                  Environmental indicators associated
                  with landslide risk at the selected
                  location.
                </p>
              </div>

            </div>

            <div className="risk-factors-grid">

              <div className="risk-factor-card">

                <div className="factor-icon">
                  <CloudRain size={18} />
                </div>

                <div className="factor-content">

                  <span>
                    24h rainfall
                  </span>

                  <strong>
                    {Number(
                      liveEnvironment.rainfall_1d_mm
                    ).toFixed(1)}
                    {" "}mm
                  </strong>

                  <small>
                    {getRainfallStatus(
                      liveEnvironment.rainfall_1d_mm
                    )}
                  </small>

                </div>

              </div>

              <div className="risk-factor-card">

                <div className="factor-icon">
                  <TrendingUp size={18} />
                </div>

                <div className="factor-content">

                  <span>
                    Terrain slope
                  </span>

                  <strong>
                    {Number(
                      liveTerrain.slope_deg
                    ).toFixed(2)}
                    °
                  </strong>

                  <small>
                    {getSlopeStatus(
                      liveTerrain.slope_deg
                    )}
                  </small>

                </div>

              </div>

              <div className="risk-factor-card">

                <div className="factor-icon">
                  <Droplets size={18} />
                </div>

                <div className="factor-content">

                  <span>
                    Soil moisture
                  </span>

                  <strong>
                    {Number.isFinite(
                      Number(liveSoilMoisture)
                    )
                      ? Number(
                          liveSoilMoisture
                        ).toFixed(3)
                      : "N/A"}
                  </strong>

                  <small>
                    {getSoilStatus(
                      liveSoilMoisture
                    )}
                  </small>

                </div>

              </div>

              <div className="risk-factor-card">

                <div className="factor-icon">
                  <CloudRain size={18} />
                </div>

                <div className="factor-content">

                  <span>
                    7-day rainfall
                  </span>

                  <strong>
                    {Number(
                      liveEnvironment.rainfall_7d_mm
                    ).toFixed(1)}
                    {" "}mm
                  </strong>

                  <small>
                    {getRainfallStatus(
                      liveEnvironment.rainfall_7d_mm
                    )}
                  </small>

                </div>

              </div>

            </div>

          </section>
        )}

        {/* ====================================================
            MANUAL PREDICTION
        ==================================================== */}

        <section className="dashboard-card prediction-section">

          <div className="section-header">

            <div>
              <h2>
                Analyze environmental conditions
              </h2>

              <p>
                Enter environmental parameters to
                calculate landslide risk using the
                trained Random Forest model.
              </p>
            </div>

          </div>

          <form
            className="prediction-form"
            onSubmit={handlePrediction}
          >

            <div className="form-grid">

              <div className="form-group">

                <label>
                  24-Hour Rainfall (mm)
                </label>

                <input
                  type="number"
                  step="any"
                  name="rainfall_1d_mm"
                  value={
                    formData.rainfall_1d_mm
                  }
                  onChange={handleChange}
                  placeholder="e.g. 50"
                  required
                />

              </div>

              <div className="form-group">

                <label>
                  3-Day Rainfall (mm)
                </label>

                <input
                  type="number"
                  step="any"
                  name="rainfall_3d_mm"
                  value={
                    formData.rainfall_3d_mm
                  }
                  onChange={handleChange}
                  placeholder="e.g. 120"
                  required
                />

              </div>

              <div className="form-group">

                <label>
                  7-Day Rainfall (mm)
                </label>

                <input
                  type="number"
                  step="any"
                  name="rainfall_7d_mm"
                  value={
                    formData.rainfall_7d_mm
                  }
                  onChange={handleChange}
                  placeholder="e.g. 250"
                  required
                />

              </div>

              <div className="form-group">

                <label>
                  Soil Moisture (0–7 cm)
                </label>

                <input
                  type="number"
                  step="any"
                  name="soil_moisture_0_7cm"
                  value={
                    formData.soil_moisture_0_7cm
                  }
                  onChange={handleChange}
                  placeholder="e.g. 0.45"
                  required
                />

              </div>

              <div className="form-group">

                <label>
                  Elevation (m)
                </label>

                <input
                  type="number"
                  step="any"
                  name="elevation_m"
                  value={
                    formData.elevation_m
                  }
                  onChange={handleChange}
                  placeholder="e.g. 1500"
                  required
                />

              </div>

              <div className="form-group">

                <label>
                  Slope (degrees)
                </label>

                <input
                  type="number"
                  step="any"
                  name="slope_deg"
                  value={
                    formData.slope_deg
                  }
                  onChange={handleChange}
                  placeholder="e.g. 30"
                  required
                />

              </div>

            </div>

            <div className="form-actions">

              <button
                type="submit"
                className="primary-button"
                disabled={loading}
              >
                {loading ? (
                  <>
                    <Loader2 size={16} className="spin" />
                    Analyzing...
                  </>
                ) : (
                  <>
                    <Cpu size={16} />
                    Predict landslide risk
                  </>
                )}
              </button>

              <button
                type="button"
                className="secondary-button"
                onClick={clearPrediction}
              >
                Clear
              </button>

            </div>

          </form>

          {/* ==================================================
              MANUAL PREDICTION RESULT
          ================================================== */}

          {error && (
            <div className="error-message">
              <XCircle size={16} />
              {error}
            </div>
          )}

          {prediction && (
            <div
              className={`prediction-result ${getRiskClass(
                prediction.risk_level
              )}`}
            >

              <div className="prediction-result-header">

                <div className="prediction-result-title">
                  <RiskIcon level={prediction.risk_level} size={20} />

                  <h3>
                    {formatRiskLabel(prediction.risk_level)} risk
                  </h3>
                </div>

                <div className="prediction-score">

                  <strong>
                    {Number(
                      prediction.risk_percentage
                    ).toFixed(1)}
                    %
                  </strong>

                  <span>
                    Risk probability
                  </span>

                </div>

              </div>

            </div>
          )}

        </section>

        {/* ====================================================
            DATA SOURCES
        ==================================================== */}

        <section className="dashboard-card data-source-section">

          <div className="section-header">

            <div>
              <h2>
                Data sources
              </h2>
            </div>

          </div>

          <div className="source-grid">

            <div className="source-card">

              <div className="source-icon">
                <Satellite size={18} />
              </div>

              <h3>
                NASA Landslide Catalog
              </h3>

              <p>
                Historical landslide records used
                for model development and analysis.
              </p>

            </div>

            <div className="source-card">

              <div className="source-icon">
                <CloudSun size={18} />
              </div>

              <h3>
                Open-Meteo
              </h3>

              <p>
                Rainfall and soil-moisture data used
                for environmental risk assessment.
              </p>

            </div>

            <div className="source-card">

              <div className="source-icon">
                <Layers size={18} />
              </div>

              <h3>
                Terrain data
              </h3>

              <p>
                Elevation and terrain slope features
                used by the AI risk model.
              </p>

            </div>

            <div className="source-card">

              <div className="source-icon">
                <Cpu size={18} />
              </div>

              <h3>
                Random Forest AI
              </h3>

              <p>
                Machine-learning model combining
                environmental and terrain indicators.
              </p>

            </div>

          </div>

        </section>

      </main>

      {/* ======================================================
          FOOTER
      ====================================================== */}

      <footer className="dashboard-footer">

        <div className="footer-content">

          <div>
            <strong>
              LANDGUARD AI
            </strong>

            <span>
              Landslide risk monitoring for the North Eastern Region
            </span>
          </div>

          <div className="footer-meta">
            <span>SIH Problem Statement 26001</span>
            <span>Ministry of Development of North Eastern Region</span>
          </div>

        </div>

      </footer>

    </div>
  );
}