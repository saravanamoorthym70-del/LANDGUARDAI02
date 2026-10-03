import React, { useEffect, useState } from "react";
import L from "leaflet";

import {
  MapContainer,
  TileLayer,
  GeoJSON,
  CircleMarker,
  Popup,
  useMap,
  useMapEvents,
} from "react-leaflet";
import {
  Satellite,
  MapPin,
  Loader2,
  MousePointerClick,
  RefreshCw,
  Layers,
  History,
} from "lucide-react";

import "leaflet/dist/leaflet.css";

// ============================================================
// MAP CLICK HANDLER
// ============================================================

function MapClickHandler({
  onLocationClick,
}) {
  useMapEvents({
    click(e) {
      const location = e.latlng;

      // Start live AI analysis
      onLocationClick(location);
    },
  });

  return null;
}

function MapFocusController({ location }) {
  const map = useMap();

  useEffect(() => {
    if (location) {
      map.flyTo([location.lat, location.lng], 11, { duration: 1 });
    }
  }, [location, map]);

  return null;
}

function MapBoundsWatcher({ onBoundsChange }) {
  const map = useMap();

  useEffect(() => {
    const updateBounds = () => {
      const bounds = map.getBounds();
      onBoundsChange(
        [bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()].join(","),
      );
    };
    map.on("moveend", updateBounds);
    updateBounds();
    return () => map.off("moveend", updateBounds);
  }, [map, onBoundsChange]);

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

const EXPOSURE_STYLES = {
  roads: { color: "#5b6870", weight: 2, fillColor: "#5b6870", fillOpacity: 0.16 },
  bridges: { color: "#d07132", weight: 3, fillColor: "#d07132", fillOpacity: 0.5 },
  settlements: { color: "#087f73", weight: 1, fillColor: "#087f73", fillOpacity: 0.35 },
  schools: { color: "#3176a9", weight: 1, fillColor: "#3176a9", fillOpacity: 0.55 },
  hospitals: { color: "#c5363d", weight: 1, fillColor: "#c5363d", fillOpacity: 0.55 },
  railways: { color: "#77713a", weight: 3, fillColor: "#77713a", fillOpacity: 0.25 },
};

const EXPOSURE_LABELS = {
  roads: "Roads",
  bridges: "Bridges",
  settlements: "Settlements",
  schools: "Schools",
  hospitals: "Hospitals",
  railways: "Railways",
};

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

  const color = "#c44d56";

  return (
    <CircleMarker
      center={[
        latitude,
        longitude,
      ]}
      radius={4}
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
            Historical event
          </strong>

          <hr />

          {(item.event_title ?? item.title ?? item.location) && (
            <div>
              <b>Event:</b>{" "}
              {item.event_title ?? item.title ?? item.location}
            </div>
          )}

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

function AssessmentMarker({ item }) {
  const latitude = Number(item.latitude);
  const longitude = Number(item.longitude);

  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
    return null;
  }

  const risk = item.risk_level ?? "UNKNOWN";
  const color = getRiskColor(risk);
  const capturedAt = item.captured_at ?? item.client_captured_at;

  return (
    <CircleMarker
      center={[latitude, longitude]}
      radius={7}
      pathOptions={{
        color: "#ffffff",
        fillColor: color,
        fillOpacity: 0.95,
        weight: 2,
      }}
    >
      <Popup>
        <div className="historical-popup">
          <strong className="popup-title">
            <MapPin size={13} />
            Saved AI assessment
          </strong>
          <hr />
          <div>
            <b>Screening level:</b>{" "}
            <span style={{ color }}>{String(risk).toUpperCase()}</span>
          </div>
          {Number.isFinite(Number(item.risk_percentage)) && (
            <div>
              <b>Screening score:</b> {Number(item.risk_percentage).toFixed(1)}%
            </div>
          )}
          {item.location_name && (
            <div>
              <b>Location:</b> {item.location_name}
            </div>
          )}
          {capturedAt && (
            <div>
              <b>Assessed:</b> {capturedAt}
            </div>
          )}
          <hr />
          <div><b>Latitude:</b> {latitude.toFixed(4)}</div>
          <div><b>Longitude:</b> {longitude.toFixed(4)}</div>
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

  const percentage = Number(
    riskPercentage
  );

  return (
    <>
      {/* ======================================================
          RISK INTENSITY AREA
      ====================================================== */}

      <CircleMarker
        center={[
          location.lat,
          location.lng,
        ]}
        radius={22}
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

function MapLegend({ historyCount, assessmentCount, historyError }) {
  return (
    <div className="map-legend">

      <div className="map-legend-title">
        Map data
      </div>

      <div className="legend-item">
        <span className="legend-dot historic" />
        <span>{historyCount} historical events</span>
      </div>

      <div className="legend-item">
        <span className="legend-dot assessment" />
        <span>{assessmentCount} saved assessments</span>
      </div>

      {historyError && (
        <div className="legend-info">Historical catalog unavailable</div>
      )}

      <div className="legend-divider" />

      <div className="map-legend-title">Assessment level</div>

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
  records = [],
  apiBaseUrl,
  selectedLocation,
  focusLocation,
}) {
  const [historicalEvents, setHistoricalEvents] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState(false);
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0);
  const [gridEnabled, setGridEnabled] = useState(false);
  const [gridBounds, setGridBounds] = useState("");
  const [riskGrid, setRiskGrid] = useState(null);
  const [gridLoading, setGridLoading] = useState(false);
  const [gridError, setGridError] = useState(false);
  const [exposureEnabled, setExposureEnabled] = useState(false);
  const [exposureBounds, setExposureBounds] = useState("");
  const [exposureData, setExposureData] = useState(null);
  const [exposureLoading, setExposureLoading] = useState(false);
  const [exposureError, setExposureError] = useState(false);
  const [visibleExposureLayers, setVisibleExposureLayers] = useState({
    roads: true,
    bridges: true,
    settlements: true,
    schools: true,
    hospitals: true,
    railways: true,
  });
  const [replayDate, setReplayDate] = useState(() => {
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    return yesterday.toISOString().slice(0, 10);
  });
  const [maxReplayDate] = useState(replayDate);
  const [replayDays, setReplayDays] = useState(7);
  const [replayResult, setReplayResult] = useState(null);
  const [replayLoading, setReplayLoading] = useState(false);
  const [replayError, setReplayError] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function loadHistoricalEvents() {
      setHistoryLoading(true);
      setHistoryError(false);
      try {
        const response = await fetch(`${apiBaseUrl}/historical-events`);
        if (!response.ok) {
          throw new Error(`Historical events request failed (${response.status})`);
        }
        const data = await response.json();
        if (!cancelled) {
          setHistoricalEvents(Array.isArray(data.events) ? data.events : []);
        }
      } catch (error) {
        console.warn("Historical event catalog could not be loaded:", error);
        if (!cancelled) setHistoryError(true);
      } finally {
        if (!cancelled) setHistoryLoading(false);
      }
    }

    loadHistoricalEvents();
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, historyRefreshKey]);

  useEffect(() => {
    if (!gridEnabled || !gridBounds) return undefined;

    const controller = new AbortController();
    const timeoutId = setTimeout(async () => {
      setGridLoading(true);
      setGridError(false);
      try {
        const query = new URLSearchParams({ bbox: gridBounds, limit: "5000" });
        const response = await fetch(`${apiBaseUrl}/risk-grid?${query}`, {
          signal: controller.signal,
        });
        if (!response.ok) {
          throw new Error(`Risk grid request failed (${response.status})`);
        }
        const data = await response.json();
        setRiskGrid(data);
      } catch (error) {
        if (error.name !== "AbortError") {
          console.warn("Risk grid could not be loaded:", error);
          setGridError(true);
        }
      } finally {
        if (!controller.signal.aborted) setGridLoading(false);
      }
    }, 250);

    return () => {
      clearTimeout(timeoutId);
      controller.abort();
    };
  }, [apiBaseUrl, gridBounds, gridEnabled]);

  useEffect(() => {
    if (!exposureEnabled || !exposureBounds) return undefined;

    const controller = new AbortController();
    const timeoutId = setTimeout(async () => {
      setExposureLoading(true);
      setExposureError(false);
      try {
        const query = new URLSearchParams({ bbox: exposureBounds, limit: "2000" });
        const response = await fetch(`${apiBaseUrl}/exposure?${query}`, {
          signal: controller.signal,
        });
        if (!response.ok) {
          throw new Error(`Exposure request failed (${response.status})`);
        }
        setExposureData(await response.json());
      } catch (error) {
        if (error.name !== "AbortError") {
          console.warn("Exposure layers could not be loaded:", error);
          setExposureError(true);
        }
      } finally {
        if (!controller.signal.aborted) setExposureLoading(false);
      }
    }, 300);

    return () => {
      clearTimeout(timeoutId);
      controller.abort();
    };
  }, [apiBaseUrl, exposureBounds, exposureEnabled]);

  async function runReplay(event) {
    event.preventDefault();
    if (!selectedLocation) return;
    setReplayLoading(true);
    setReplayError(false);
    try {
      const query = new URLSearchParams({
        latitude: String(selectedLocation.lat),
        longitude: String(selectedLocation.lng),
        date: replayDate,
        days: String(replayDays),
      });
      const response = await fetch(`${apiBaseUrl}/replay?${query}`);
      if (!response.ok) throw new Error(`Replay request failed (${response.status})`);
      setReplayResult(await response.json());
    } catch (error) {
      console.warn("Historical replay could not be loaded:", error);
      setReplayError(true);
      setReplayResult(null);
    } finally {
      setReplayLoading(false);
    }
  }

  // ==========================================================
  // LIVE LOCATION
  // ==========================================================

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
    <>
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

        <MapFocusController location={focusLocation} />
        <MapBoundsWatcher onBoundsChange={setGridBounds} />
        <MapBoundsWatcher onBoundsChange={setExposureBounds} />

        {/* ====================================================
            OPENSTREETMAP
        ==================================================== */}

        <TileLayer
          attribution="&copy; OpenStreetMap contributors"
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {gridEnabled && riskGrid?.features?.length > 0 && (
          <GeoJSON
            key={`${riskGrid.last_updated}-${riskGrid.features.length}`}
            data={riskGrid}
            style={(feature) => {
              const color = getRiskColor(feature.properties?.risk_band);
              return {
                color,
                fillColor: color,
                fillOpacity: 0.38,
                opacity: 0.75,
                weight: 0.5,
              };
            }}
          />
        )}

        {exposureEnabled && Object.entries(EXPOSURE_STYLES).map(([category, style]) => {
          const layer = exposureData?.layers?.[category];
          if (!visibleExposureLayers[category] || !layer?.features?.length) return null;
          return (
            <GeoJSON
              key={`exposure-${category}`}
              data={layer}
              style={style}
              pointToLayer={(_, latlng) => L.circleMarker(latlng, {
                radius: category === "hospitals" ? 6 : 4,
                color: style.color,
                fillColor: style.fillColor,
                fillOpacity: style.fillOpacity,
                weight: 1.5,
              })}
              onEachFeature={(feature, layerInstance) => {
                const properties = feature.properties || {};
                const label = properties.name || properties.ref || properties.feature_id || category;
                layerInstance.bindPopup(
                  `${EXPOSURE_LABELS[category]}: ${String(label)}`,
                );
              }}
            />
          );
        })}

        {historicalEvents.map(
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

        {records.map((item, index) => (
          <AssessmentMarker
            key={item.id ?? item.correlation_id ?? `${item.latitude}-${item.longitude}-${index}`}
            item={item}
          />
        ))}

        {/* ====================================================
            LIVE AI LOCATION
        ==================================================== */}

        <LiveLocationMarker
          location={selectedLocation}
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
        />

      </MapContainer>

      {/* ======================================================
          MAP LEGEND
      ====================================================== */}

      <button
        type="button"
        className="map-history-refresh"
        onClick={() => setHistoryRefreshKey((key) => key + 1)}
        disabled={historyLoading}
        title="Refresh historical event points"
        aria-label="Refresh historical event points"
      >
        <RefreshCw size={15} className={historyLoading ? "spin" : ""} />
        <span>{historyLoading ? "Loading events" : "Refresh events"}</span>
      </button>

      <MapLegend
        historyCount={historicalEvents.length}
        assessmentCount={records.length}
        historyError={historyError}
      />

      <div className="risk-grid-control">
        <button
          type="button"
          className={`risk-grid-toggle ${gridEnabled ? "is-active" : ""}`}
          aria-pressed={gridEnabled}
          onClick={() => setGridEnabled((enabled) => !enabled)}
          title="Toggle the regional screening grid"
        >
          <Layers size={15} />
          <span>Region grid</span>
        </button>
        {gridEnabled && (
          <div className="risk-grid-updated" aria-live="polite">
            {gridLoading ? "Loading grid…" : gridError ? "Grid unavailable" : riskGrid?.last_updated
              ? `Updated ${new Date(riskGrid.last_updated).toLocaleString()}`
              : "No grid results yet"}
          </div>
        )}
      </div>
    </div>

      {gridEnabled && (
        <section className="risk-grid-summary" aria-label="Highest-risk districts">
          <div className="risk-grid-summary-heading">
            <h3>Highest-risk districts</h3>
            <span>{riskGrid?.grid_size_m ? `${riskGrid.grid_size_m} m cells` : "No grid"}</span>
          </div>
          {gridError ? (
            <p className="risk-grid-empty">District summary could not be loaded.</p>
          ) : riskGrid?.district_summary?.length ? (
            <div className="risk-grid-table-wrap">
              <table>
                <thead>
                  <tr><th>District</th><th>State</th><th>Peak</th><th>High cells</th></tr>
                </thead>
                <tbody>
                  {riskGrid.district_summary.map((district) => (
                    <tr key={`${district.state}-${district.district}`}>
                      <td>{district.district}</td>
                      <td>{district.state}</td>
                      <td>{Number(district.max_score).toFixed(1)}%</td>
                      <td>{district.high_cells}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : riskGrid?.count > 0 ? (
            <p className="risk-grid-empty">Cells are scored, but none have an unambiguous district assignment for ranking.</p>
          ) : (
            <p className="risk-grid-empty">No scored cells yet. Run the grid job to populate this view.</p>
          )}
          {riskGrid && !riskGrid.complete && riskGrid.last_updated && (
            <p className="risk-grid-incomplete">
              Incomplete run: {riskGrid.generated_cells} cells processed; {riskGrid.failed_cells} data failures.
            </p>
          )}
          {riskGrid?.district_unassigned_cells > 0 && (
            <p className="risk-grid-incomplete">
              District attribution unavailable for {riskGrid.district_unassigned_cells} cells.
            </p>
          )}
          <p className="risk-grid-disclaimer">Prototype screening score, not an official warning.</p>
        </section>
      )}

      <section className="risk-exposure-panel" aria-label="Exposure overlay">
        <div className="risk-grid-summary-heading">
          <h3>Exposure overlay</h3>
          <button
            type="button"
            className={`risk-grid-toggle ${exposureEnabled ? "is-active" : ""}`}
            aria-pressed={exposureEnabled}
            onClick={() => setExposureEnabled((enabled) => !enabled)}
            title="Toggle exposure layers intersecting HIGH cells"
          >
            <Layers size={15} />
            <span>{exposureEnabled ? "Hide exposure" : "Show exposure"}</span>
          </button>
        </div>
        {exposureEnabled && (
          <>
            <div className="exposure-layer-toggles">
              {Object.entries(EXPOSURE_LABELS).map(([category, label]) => (
                <label key={category} className="exposure-layer-toggle">
                  <input
                    type="checkbox"
                    checked={visibleExposureLayers[category]}
                    onChange={(event) => setVisibleExposureLayers((current) => ({
                      ...current,
                      [category]: event.target.checked,
                    }))}
                  />
                  <span className={`exposure-swatch exposure-swatch--${category}`} />
                  <span>{label}</span>
                  <span className="exposure-count">
                    {exposureData?.summary?.[category] ?? 0}
                  </span>
                </label>
              ))}
            </div>
            {exposureLoading ? (
              <p className="risk-grid-empty">Loading exposure intersections…</p>
            ) : exposureError ? (
              <p className="risk-grid-empty">Exposure layers unavailable. Build the OSM GeoPackage and run a grid update.</p>
            ) : exposureData ? (
              <p className="risk-exposure-headline">
                {exposureData.summary.headline}
              </p>
            ) : (
              <p className="risk-grid-empty">No exposure intersections available for this map extent.</p>
            )}
            <p className="risk-grid-disclaimer">Counts include mapped OSM features only; map completeness varies.</p>
          </>
        )}
      </section>

      <section className="risk-replay-panel" aria-label="Historical replay">
        <div className="risk-grid-summary-heading">
          <h3>Historical replay</h3>
          {selectedLocation && (
            <span>{selectedLocation.lat.toFixed(3)}, {selectedLocation.lng.toFixed(3)}</span>
          )}
        </div>
        <form className="replay-controls" onSubmit={runReplay}>
          <label>
            Event date
            <input
              type="date"
              value={replayDate}
              max={maxReplayDate}
              onChange={(event) => setReplayDate(event.target.value)}
              required
            />
          </label>
          <label>
            Days
            <input
              type="number"
              min="1"
              max="30"
              value={replayDays}
              onChange={(event) => setReplayDays(Number(event.target.value))}
              required
            />
          </label>
          <button
            type="submit"
            className="risk-grid-toggle"
            disabled={!selectedLocation || replayLoading}
          >
            {replayLoading ? <Loader2 size={14} className="spin" /> : <History size={14} />}
            <span>{replayLoading ? "Loading" : "Run replay"}</span>
          </button>
        </form>
        {!selectedLocation && (
          <p className="risk-grid-empty">Select a map location to replay its historical screening scores.</p>
        )}
        {replayError && (
          <p className="risk-grid-empty">Historical weather is unavailable for this date or location.</p>
        )}
        {replayResult && (
          <>
            <div className="replay-timeline" role="list" aria-label="Daily screening scores before event date">
              {replayResult.daily_scores.map((item) => {
                const score = Number(item.risk_score);
                const available = Number.isFinite(score);
                const color = getRiskColor(item.risk_band);
                return (
                  <div className="replay-day" role="listitem" key={item.date}>
                    <div className="replay-score-label">
                      {available ? `${score.toFixed(1)}%` : "N/A"}
                    </div>
                    <div className="replay-bar-track">
                      <span
                        className="replay-bar"
                        style={{
                          width: `${available ? Math.max(score, 2) : 0}%`,
                          backgroundColor: color,
                        }}
                      />
                    </div>
                    <span className="replay-band" style={{ color }}>{item.risk_band}</span>
                    <time dateTime={item.date}>{item.date.slice(5)}</time>
                  </div>
                );
              })}
            </div>
            <p className="risk-grid-disclaimer">
              Historical screening score, not a calibrated event probability or official warning.
            </p>
          </>
        )}
      </section>

    </>
  );
} 