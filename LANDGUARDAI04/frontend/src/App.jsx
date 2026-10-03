import React, { useEffect, useMemo, useState } from "react";
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
  Download,
  FileJson,
  History,
  Trash2,
  RefreshCw,
} from "lucide-react";

import "./App.css";
import RiskMap from "./RiskMap";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
const RECORDS_STORAGE_KEY = "landguard-live-records-v1";
const SESSION_STORAGE_KEY = "landguard-session-id-v1";
const MAX_STORED_RECORDS = 50;

function createTraceId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function getSessionId() {
  try {
    const existing = localStorage.getItem(SESSION_STORAGE_KEY);
    if (existing) return existing;
    const sessionId = createTraceId();
    localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
    return sessionId;
  } catch {
    return createTraceId();
  }
}

const SESSION_ID = getSessionId();

function downloadFile(filename, content, type) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function toCsv(records) {
  const columns = [
    "id",
    "correlation_id",
    "session_id",
    "trigger",
    "captured_at",
    "client_captured_at",
    "location_name",
    "latitude",
    "longitude",
    "risk_level",
    "risk_percentage",
    "rainfall_1d_mm",
    "rainfall_3d_mm",
    "rainfall_7d_mm",
    "soil_moisture_0_7cm",
    "elevation_m",
    "slope_deg",
    "raw_result",
  ];
  const escape = (value) => `"${String(value ?? "").replaceAll('"', '""')}"`;
  return [
    columns.join(","),
    ...records.map((record) => columns.map((column) => {
      const value = column === "raw_result"
        ? JSON.stringify(record[column] ?? {})
        : record[column];
      return escape(value);
    }).join(",")),
  ].join("\n");
}

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

function DashboardHeader({ activeView, onNavigate, systemStatus }) {
  const items = [
    { id: "home", label: "Dashboard" },
    { id: "historical", label: "Historical Data" },
    { id: "current", label: "Current Status" },
  ];

  return (
    <header className="dashboard-header">
      <div className="header-content">
        <div className="brand">
          <div className="brand-icon"><BrandMark /></div>
          <div>
            <h1>LANDGUARD AI</h1>
            <p>AI-Based Landslide Risk Monitoring System</p>
          </div>
        </div>

        <nav className="primary-nav" aria-label="Main navigation">
          {items.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`primary-nav-link ${activeView === item.id ? "is-active" : ""}`}
              aria-current={activeView === item.id ? "page" : undefined}
              onClick={() => onNavigate(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>

        <div className="header-tools">
          <div className={`header-status ${systemStatus === "Backend unavailable" ? "is-offline" : ""}`}>
            <span className={`status-dot ${systemStatus === "Backend unavailable" ? "is-offline" : systemStatus === "Checking status" ? "is-checking" : ""}`} />
            {systemStatus}
          </div>
          {activeView !== "home" && (
            <button className="back-button" type="button" onClick={() => onNavigate("home")}>
              <span aria-hidden="true">&#8592;</span> Back to Dashboard
            </button>
          )}
        </div>
      </div>
    </header>
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
  const [activeView, setActiveView] = useState("home");
  const [systemStatus, setSystemStatus] = useState("Checking status");

  useEffect(() => {
    const controller = new AbortController();

    async function checkSystemStatus() {
      try {
        const response = await fetch(`${API_BASE}/health`, { signal: controller.signal });
        if (!response.ok) throw new Error(`Health check failed (${response.status})`);
        setSystemStatus("Monitoring System Online");
      } catch (statusError) {
        if (statusError.name !== "AbortError") setSystemStatus("Backend unavailable");
      }
    }

    checkSystemStatus();
    const intervalId = window.setInterval(checkSystemStatus, 30_000);
    return () => {
      controller.abort();
      window.clearInterval(intervalId);
    };
  }, []);

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
  const [locating, setLocating] = useState(false);
  const [locationName, setLocationName] = useState("");
  const [monitorLocation, setMonitorLocation] = useState(null);
  const [mapFocusLocation, setMapFocusLocation] = useState(null);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [liveRecords, setLiveRecords] = useState([]);

  const [mapMessage, setMapMessage] = useState(
    "Click anywhere on the map to perform a live AI risk assessment."
  );

  const [mapStatus, setMapStatus] = useState("idle");

  useEffect(() => {
    async function loadRecords() {
      try {
        const response = await fetch(`${API_BASE}/records?limit=${MAX_STORED_RECORDS}`);
        if (!response.ok) throw new Error(`Records request failed (${response.status})`);
        const data = await response.json();
        setLiveRecords(Array.isArray(data.records) ? data.records : []);
      } catch (loadError) {
        console.warn("Using cached live records:", loadError);
        try {
          const stored = localStorage.getItem(RECORDS_STORAGE_KEY);
          setLiveRecords(stored ? JSON.parse(stored) : []);
        } catch {
          setLiveRecords([]);
        }
      }
    }

    loadRecords();
  }, []);

  useEffect(() => {
    localStorage.setItem(RECORDS_STORAGE_KEY, JSON.stringify(liveRecords));
  }, [liveRecords]);

  useEffect(() => {
    if (!autoRefresh || !monitorLocation) return undefined;

    const timer = window.setInterval(() => {
      handleMapClick(monitorLocation, "scheduled-refresh");
    }, 15 * 60 * 1000);

    return () => window.clearInterval(timer);
  }, [autoRefresh, monitorLocation]);

  async function saveLiveRecord(riskData, resolvedLocationName, trigger) {
    const environment = riskData.environment || {};
    const predictionResult = riskData.prediction || {};
    const terrain = riskData.terrain || {};
    const record = {
      captured_at: new Date().toISOString(),
      session_id: SESSION_ID,
      correlation_id: createTraceId(),
      trigger,
      location_name: resolvedLocationName || "Selected map location",
      latitude: riskData.location?.latitude,
      longitude: riskData.location?.longitude,
      risk_level: predictionResult.risk_level,
      risk_percentage: predictionResult.risk_percentage,
      rainfall_1d_mm: environment.rainfall_1d_mm,
      rainfall_3d_mm: environment.rainfall_3d_mm,
      rainfall_7d_mm: environment.rainfall_7d_mm,
      soil_moisture_0_7cm:
        environment.soil_moisture_0_to_7cm ?? environment.soil_moisture_0_7cm,
      elevation_m: environment.elevation_m,
      slope_deg: terrain.slope_deg,
      raw_result: {
        ...riskData,
        trace: {
          reverse_geocode_endpoint: `${API_BASE}/reverse-geocode`,
          records_endpoint: `${API_BASE}/records`,
        },
      },
    };

    try {
      const response = await fetch(`${API_BASE}/records`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(record),
      });
      if (!response.ok) throw new Error(`Record save failed (${response.status})`);
      const savedRecord = await response.json();
      setLiveRecords((previous) => [savedRecord, ...previous].slice(0, MAX_STORED_RECORDS));
    } catch (saveError) {
      console.warn("Live record saved to browser cache only:", saveError);
      setLiveRecords((previous) => [
        { id: `${Date.now()}-${record.latitude}-${record.longitude}`, ...record },
        ...previous,
      ].slice(0, MAX_STORED_RECORDS));
    }
  }

  function downloadRecords(format) {
    if (!liveRecords.length) return;
    const stamp = new Date().toISOString().slice(0, 10);
    if (format === "json") {
      downloadFile(
        `landguard-live-records-${stamp}.json`,
        JSON.stringify(liveRecords, null, 2),
        "application/json"
      );
      return;
    }
    downloadFile(
      `landguard-live-records-${stamp}.csv`,
      toCsv(liveRecords),
      "text/csv;charset=utf-8"
    );
  }

  async function clearLiveRecords() {
    try {
      const response = await fetch(`${API_BASE}/records`, { method: "DELETE" });
      if (!response.ok) throw new Error(`Record deletion failed (${response.status})`);
    } catch (clearError) {
      console.warn("Backend records could not be cleared:", clearError);
    }
    setLiveRecords([]);
  }

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

    if (
      Object.values(formData).some((value) => value.trim() === "") ||
      Object.values(payload).some((value) => !Number.isFinite(value))
    ) {
      setError("Enter a valid number in every field.");
      return;
    }

    setLoading(true);
    setError("");
    setPrediction(null);

    try {

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

  async function handleMapClick(location, trigger = "map-click") {
    const latitude = Number(location.lat);
    const longitude = Number(location.lng);
    setMonitorLocation({ lat: latitude, lng: longitude });

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
      const environment = riskData.environment || {};
      const terrain = riskData.terrain || {};
      setFormData({
        rainfall_1d_mm: String(environment.rainfall_1d_mm ?? ""),
        rainfall_3d_mm: String(environment.rainfall_3d_mm ?? ""),
        rainfall_7d_mm: String(environment.rainfall_7d_mm ?? ""),
        soil_moisture_0_7cm: String(
          environment.soil_moisture_0_to_7cm ??
          environment.soil_moisture_0_7cm ??
          ""
        ),
        elevation_m: String(environment.elevation_m ?? ""),
        slope_deg: String(terrain.slope_deg ?? ""),
      });

      // ------------------------------------------------------
      // REVERSE GEOCODING
      // ------------------------------------------------------

      let resolvedLocationName = "";

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

          resolvedLocationName = name;
          setLocationName(name);
        }
      } catch (geoError) {
        console.warn(
          "Reverse geocoding failed:",
          geoError
        );
      }

      await saveLiveRecord(riskData, resolvedLocationName, trigger);

      setMapStatus("success");
      setMapMessage(environment.is_live_data === false
        ? `Assessment uses delayed NASA POWER data through ${environment.observed_through}; weather is not live.`
        : "Live AI risk assessment completed.");
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

  function handleCurrentLocation() {
    if (!navigator.geolocation) {
      setMapStatus("error");
      setMapMessage("This browser does not support location access.");
      return;
    }

    setLocating(true);
    setMapStatus("analyzing");
    setMapMessage("Finding your current location...");

    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        const location = {
          lat: coords.latitude,
          lng: coords.longitude,
        };
        setMapFocusLocation(location);
        setLocating(false);
        handleMapClick(location, "current-location");
      },
      (geoError) => {
        setLocating(false);
        setMapStatus("error");
        if (geoError.code === 1) {
          setMapMessage("Location access was denied. Allow location permission and try again.");
        } else if (geoError.code === 3) {
          setMapMessage("Finding your location timed out. Please try again.");
        } else {
          setMapMessage("Your location is unavailable. Check your device location settings and try again.");
        }
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 }
    );
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
    setMonitorLocation(null);
    setAutoRefresh(false);
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

  if (activeView === "home") {
    return (
      <div className="dashboard landing-page">
        <DashboardHeader activeView={activeView} onNavigate={setActiveView} systemStatus={systemStatus} />

        <main>
          <section className="hero-section landing-hero">
            <ContourField />
            <div className="hero-content">
              <span className="landing-kicker">Environmental intelligence platform</span>
              <h2>AI-Powered Landslide Risk Intelligence</h2>
              <p>
                Monitor historical landslide patterns, analyze environmental conditions,
                and assess current landslide risk across India.
              </p>
            </div>
          </section>

          <section className="view-options" aria-label="Choose a dashboard view">
            <button
              type="button"
              className="view-option-card historical-option"
              onClick={() => setActiveView("historical")}
            >
              <span className="view-option-icon"><History size={23} /></span>
              <span className="view-option-copy">
                <strong>Historical Data</strong>
                <span>Explore historical landslide events, patterns and affected regions across India.</span>
                <span className="view-option-cta">Explore Historical Data</span>
              </span>
              <span className="view-option-arrow" aria-hidden="true">&#8594;</span>
            </button>

            <button
              type="button"
              className="view-option-card current-option"
              onClick={() => setActiveView("current")}
            >
              <span className="view-option-icon"><ShieldCheck size={23} /></span>
              <span className="view-option-copy">
                <strong>Current Risk Status</strong>
                <span>Analyze current environmental conditions and AI-powered landslide risk.</span>
                <span className="view-option-cta">Check Current Risk</span>
              </span>
              <span className="view-option-arrow" aria-hidden="true">&#8594;</span>
            </button>
          </section>
        </main>
      </div>
    );
  }

  if (activeView === "historical") {
    return (
      <div className="dashboard historical-page">
        <DashboardHeader activeView={activeView} onNavigate={setActiveView} systemStatus={systemStatus} />

        <main className="main-container">
          <section className="page-intro">
            <span className="landing-kicker">Historical intelligence</span>
            <h2>Historical Landslide Intelligence</h2>
            <p>Explore historical landslide events and spatial patterns across India.</p>
          </section>

          <section className="dashboard-card historical-map-card">
            <RiskMap
              onLocationClick={handleMapClick}
              liveRisk={liveRisk}
              records={liveRecords}
              apiBaseUrl={API_BASE}
              selectedLocation={monitorLocation}
              focusLocation={mapFocusLocation}
              fitHistoricalEvents
            />
          </section>
        </main>
      </div>
    );
  }

  return (
    <div className="dashboard">

      {/* ======================================================
          HEADER
      ====================================================== */}

      <DashboardHeader activeView={activeView} onNavigate={setActiveView} systemStatus={systemStatus} />

      {/* ======================================================
          HERO
      ====================================================== */}

      <section className="hero-section">

        <ContourField />

        <div className="hero-content">

          <h2>
            Current Landslide Risk
          </h2>

          <p>
            Real-time environmental conditions and AI-based risk assessment.
          </p>

          <div className="current-risk-summary" aria-live="polite">
            <div className="current-risk-reading">
              <span>Current risk</span>
              <strong className={liveRisk ? getRiskClass(liveRiskLevel) : "pending"}>
                {liveRisk ? formatRiskLabel(liveRiskLevel) : "Awaiting assessment"}
              </strong>
            </div>
            <div className="current-risk-reading">
              <span>Model screening score</span>
              <strong>
                {liveRiskPercentage === undefined
                  ? "—"
                  : `${Number(liveRiskPercentage).toFixed(1)}%`}
              </strong>
            </div>
            <div className="current-risk-status">
              <span className="status-dot" />
              {liveLoading ? "Analyzing selected area" : liveRisk ? "Assessment complete" : "Ready for assessment"}
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

            <div className="map-actions">
              <button
                className="monitor-button"
                onClick={handleCurrentLocation}
                disabled={locating || liveLoading}
                title="Use your device GPS to assess your current location"
              >
                {locating ? <Loader2 size={14} className="spin" /> : <MapPin size={14} />}
                {locating ? "Finding location..." : "Check my current location"}
              </button>
              {monitorLocation && (
                <button
                  className={`monitor-button ${autoRefresh ? "is-active" : ""}`}
                  onClick={() => setAutoRefresh((enabled) => !enabled)}
                  title="Refresh selected location every 15 minutes"
                >
                  <RefreshCw size={14} />
                  {autoRefresh ? "Monitoring on" : "Monitor location"}
                </button>
              )}
              {liveRisk && (
                <button
                  className="clear-live-button"
                  onClick={clearLiveRisk}
                >
                  Clear live analysis
                </button>
              )}
            </div>

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
            records={liveRecords}
            apiBaseUrl={API_BASE}
            selectedLocation={monitorLocation}
            focusLocation={mapFocusLocation}
            showHistoricalData={false}
          />

        </section>

        {/* ====================================================
            LIVE RECORD LOG
        ==================================================== */}

        <section className="dashboard-card records-section">

          <div className="section-header records-header">

            <div>
              <div className="eyebrow"><History size={13} /> Local assessment log</div>
              <h2>Live records</h2>
              <p>
                Completed map assessments are saved in this browser for quick review and download.
              </p>
            </div>

            <div className="record-actions">
              <button
                className="secondary-button compact-button"
                onClick={() => downloadRecords("csv")}
                disabled={!liveRecords.length}
                title="Download records as CSV"
              >
                <Download size={15} /> CSV
              </button>
              <button
                className="secondary-button compact-button"
                onClick={() => downloadRecords("json")}
                disabled={!liveRecords.length}
                title="Download complete records as JSON"
              >
                <FileJson size={15} /> JSON
              </button>
              <button
                className="icon-button"
                onClick={clearLiveRecords}
                disabled={!liveRecords.length}
                title="Clear saved live records"
                aria-label="Clear saved live records"
              >
                <Trash2 size={16} />
              </button>
            </div>

          </div>

          {liveRecords.length ? (
            <div className="records-table-wrap">
              <table className="records-table">
                <thead>
                  <tr>
                    <th>Captured</th>
                    <th>Location</th>
                    <th>Risk</th>
                    <th>Score</th>
                    <th>Rainfall 24h</th>
                    <th>Slope</th>
                  </tr>
                </thead>
                <tbody>
                  {liveRecords.slice(0, 8).map((record) => (
                    <tr key={record.id}>
                      <td className="record-time">
                        {new Date(record.captured_at).toLocaleString([], {
                          dateStyle: "medium",
                          timeStyle: "short",
                        })}
                      </td>
                      <td>
                        <strong>{record.location_name}</strong>
                        <small>{Number(record.latitude).toFixed(4)}, {Number(record.longitude).toFixed(4)}</small>
                      </td>
                      <td>
                        <span className={`record-risk ${getRiskClass(record.risk_level)}`}>
                          <RiskIcon level={record.risk_level} size={14} />
                          {formatRiskLabel(record.risk_level)}
                        </span>
                      </td>
                      <td className="record-number">{Number(record.risk_percentage).toFixed(1)}%</td>
                      <td className="record-number">{Number(record.rainfall_1d_mm).toFixed(1)} mm</td>
                      <td className="record-number">{Number(record.slope_deg).toFixed(1)}°</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {liveRecords.length > 8 && (
                <p className="records-note">Showing the 8 most recent records. Download the file for all {liveRecords.length} saved records.</p>
              )}
            </div>
          ) : (
            <div className="records-empty">
              <History size={24} />
              <strong>No live records yet</strong>
              <span>Click a location on the map to create the first assessment.</span>
            </div>
          )}

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
                    Model screening score
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
                  <Mountain size={18} />
                </div>

                <div className="factor-content">

                  <span>
                    Elevation
                  </span>

                  <strong>
                    {Number.isFinite(
                      Number(liveEnvironment.elevation_m)
                    )
                      ? Number(
                          liveEnvironment.elevation_m
                        ).toFixed(0)
                      : "N/A"}
                    {Number.isFinite(
                      Number(liveEnvironment.elevation_m)
                    ) && " m"}
                  </strong>

                  <small>
                    Above sea level
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
                The screening model uses rainfall, soil moisture, and elevation.
                Slope is contextual and is not used in its score. This is not a
                calibrated event probability.
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
                  type="text"
                  inputMode="decimal"
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
                  type="text"
                  inputMode="decimal"
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
                  type="text"
                  inputMode="decimal"
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
                  type="text"
                  inputMode="decimal"
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
                  Elevation above sea level (m)
                </label>

                <input
                  type="text"
                  inputMode="decimal"
                  name="elevation_m"
                  value={
                    formData.elevation_m
                  }
                  onChange={handleChange}
                  placeholder="e.g. 328"
                  required
                />

              </div>

              <div className="form-group">

                <label>
                  Slope (degrees)
                </label>

                <input
                  type="text"
                  inputMode="decimal"
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
                    Model screening score
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
            <span>Ministry of Development of North Eastern Region</span>
          </div>

        </div>

      </footer>

    </div>
  );
}