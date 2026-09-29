import React, { useState } from "react";

import {
  MapContainer,
  TileLayer,
  CircleMarker,
  Circle,
  Popup,
  useMapEvents,
} from "react-leaflet";
import { Satellite, MapPin, Loader2, MousePointerClick } from "lucide-react";

import "leaflet/dist/leaflet.css";

import landslideData from "./landslideData.json";

// ============================================================
// MAP CLICK HANDLER
// ============================================================

function MapClickHandler({
  onLocationClick,
  onLiveLocation,
}) {
  useMapEvents({
    click(e) {
      const location = e.latlng;

      // Immediately display clicked location
      onLiveLocation(location);

      // Start live AI analysis
      onLocationClick(location);
    },
  });

  return null;
}

// ============================================================
// RISK COLOR
// ============================================================

function getRiskColor(risk) {
  const value = String(risk || "").toUpperCase();

  if (value === "HIGH") {
    return "#E2434B";
  }

  if (value === "MEDIUM") {
    return "#E0A64D";
  }

  if (value === "LOW") {
    return "#3FA672";
  }

  // Blue = analysis in progress
  return "#3E7CB1";
}

// ============================================================
// HISTORICAL LANDSLIDE MARKER
// ============================================================

function HistoricalMarker({ item }) {
  const latitude = Number(
    item.latitude ?? item.lat
  );

  const longitude = Number(
    item.longitude ??
      item.lon ??
      item.lng
  );

  // Ignore invalid coordinates
  if (
    !Number.isFinite(latitude) ||
    !Number.isFinite(longitude)
  ) {
    return null;
  }

  const risk =
    item.risk_level ??
    item.riskLevel ??
    item.risk ??
    "LOW";

  const color = getRiskColor(risk);

  return (
    <CircleMarker
      center={[
        latitude,
        longitude,
      ]}
      radius={6}
      pathOptions={{
        color,
        fillColor: color,
        fillOpacity: 0.75,
        weight: 1,
      }}
    >
      <Popup>

        <div className="historical-popup">

          <strong className="popup-title">
            <Satellite size={13} />
            Historical landslide
          </strong>

          <hr />

          <div>
            <b>Risk:</b>{" "}
            <span style={{ color }}>
              {String(risk).toUpperCase()}
            </span>
          </div>

          {(item.date ?? item.event_date) && (
            <div>
              <b>Date:</b>{" "}
              {item.date ?? item.event_date}
            </div>
          )}

          {item.state && (
            <div>
              <b>State:</b>{" "}
              {item.state}
            </div>
          )}

          {(item.category ?? item.landslide_category) && (
            <div>
              <b>Category:</b>{" "}
              {item.category ?? item.landslide_category}
            </div>
          )}

          {(item.trigger ?? item.landslide_trigger) && (
            <div>
              <b>Trigger:</b>{" "}
              {item.trigger ?? item.landslide_trigger}
            </div>
          )}

          <hr />

          <div>
            <b>Latitude:</b>{" "}
            {latitude.toFixed(4)}
          </div>

          <div>
            <b>Longitude:</b>{" "}
            {longitude.toFixed(4)}
          </div>

        </div>

      </Popup>
    </CircleMarker>
  );
}

// ============================================================
// LIVE LOCATION MARKER
// ============================================================

function LiveLocationMarker({
  location,
  riskLevel,
  riskPercentage,
}) {
  if (!location) {
    return null;
  }

  const color = riskLevel
    ? getRiskColor(riskLevel)
    : "#2563eb";

  const displayRisk =
    riskLevel || "ANALYZING";

  // ==========================================================
  // RISK VISUALIZATION RADIUS
  // ==========================================================

  const percentage = Number(
    riskPercentage
  );

  const radius =
    Number.isFinite(percentage)
      ? Math.max(
          300,
          Math.min(
            percentage * 12,
            1200
          )
        )
      : 500;

  return (
    <>
      {/* ======================================================
          RISK INTENSITY AREA
      ====================================================== */}

      <Circle
        center={[
          location.lat,
          location.lng,
        ]}
        radius={radius}
        pathOptions={{
          color,
          fillColor: color,
          fillOpacity: 0.12,
          weight: 2,
        }}
      />

      {/* ======================================================
          LIVE LOCATION MARKER
      ====================================================== */}

      <CircleMarker
        center={[
          location.lat,
          location.lng,
        ]}
        radius={12}
        pathOptions={{
          color,
          fillColor: color,
          fillOpacity: 0.95,
          weight: 4,
        }}
      >
        <Popup>

          <div className="live-location-popup">

            <strong className="popup-title">
              <MapPin size={13} />
              LANDGUARD AI
            </strong>

            <hr />

            <div>
              <b>Status:</b>{" "}

              <span
                style={{
                  color,
                  fontWeight: "700",
                }}
              >
                {displayRisk}
              </span>
            </div>

            {Number.isFinite(percentage) && (
              <div>
                <b>Risk Score:</b>{" "}
                {percentage.toFixed(1)}%
              </div>
            )}

            <hr />

            <div>
              <b>Latitude:</b>{" "}
              {location.lat.toFixed(4)}
            </div>

            <div>
              <b>Longitude:</b>{" "}
              {location.lng.toFixed(4)}
            </div>

            {!riskLevel && (
              <>
                <hr />

                <div className="popup-progress">
                  <Loader2 size={13} className="spin" />
                  AI analysis in progress...
                </div>
              </>
            )}

          </div>

        </Popup>
      </CircleMarker>
    </>
  );
}

// ============================================================
// MAP LEGEND
// ============================================================

function MapLegend() {
  return (
    <div className="map-legend">

      <div className="map-legend-title">
        Landslide risk
      </div>

      <div className="legend-item">

        <span className="legend-dot high" />

        <span>
          High
        </span>

      </div>

      <div className="legend-item">

        <span className="legend-dot medium" />

        <span>
          Medium
        </span>

      </div>

      <div className="legend-item">

        <span className="legend-dot low" />

        <span>
          Low
        </span>

      </div>

      <div className="legend-divider" />

      <div className="legend-info">
        <MousePointerClick size={12} />
        Click map for live AI analysis
      </div>

    </div>
  );
}

// ============================================================
// MAIN RISK MAP
// ============================================================

export default function RiskMap({
  onLocationClick,
  liveRisk,
}) {
  // ==========================================================
  // LIVE LOCATION
  // ==========================================================

  const [
    liveLocation,
    setLiveLocation,
  ] = useState(null);

  // ==========================================================
  // LIVE AI RESULT
  // ==========================================================

  const riskLevel =
    liveRisk?.prediction?.risk_level;

  const riskPercentage =
    liveRisk?.prediction?.risk_percentage;

  // ==========================================================
  // DEFAULT MAP CENTER
  // ==========================================================

  const defaultCenter = [
    25.5,
    91.5,
  ];

  return (
    <div className="risk-map-wrapper">

      {/* ======================================================
          LEAFLET MAP
      ====================================================== */}

      <MapContainer
        center={defaultCenter}
        zoom={6}
        scrollWheelZoom={true}
        className="risk-map"
      >

        {/* ====================================================
            OPENSTREETMAP
        ==================================================== */}

        <TileLayer
          attribution="&copy; OpenStreetMap contributors"
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {/* ====================================================
            HISTORICAL NASA LANDSLIDE DATA
        ==================================================== */}

        {Array.isArray(landslideData) &&
          landslideData.map(
            (item, index) => (
              <HistoricalMarker
                key={
                  item.event_id ??
                  item.id ??
                  index
                }
                item={item}
              />
            )
          )}

        {/* ====================================================
            LIVE AI LOCATION
        ==================================================== */}

        <LiveLocationMarker
          location={liveLocation}
          riskLevel={riskLevel}
          riskPercentage={
            riskPercentage
          }
        />

        {/* ====================================================
            MAP CLICK LISTENER
        ==================================================== */}

        <MapClickHandler
          onLocationClick={
            onLocationClick
          }
          onLiveLocation={
            setLiveLocation
          }
        />

      </MapContainer>

      {/* ======================================================
          MAP LEGEND
      ====================================================== */}

      <MapLegend />

    </div>
  );
} 