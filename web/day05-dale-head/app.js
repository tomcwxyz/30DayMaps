/* Day 05 / Sight — a real elevation terrain viewer, not a calculated viewshed. */
(() => {
  "use strict";
  const SUMMIT = { lng: -3.201936, lat: 54.527271 };
  const DIRECTIONS = { north: 0, east: 90, south: 180, west: 270 };
  const state = { mode: "summit", direction: "north", exaggeration: 1, ready: false,
    viewshedReady: false, viewshedManifest: null, targetPeak: null,
    visiblePeaks: [], peakMarkers: [] };
  const $ = id => document.getElementById(id);
  const map = new maplibregl.Map({
    container: "map",
    style: {
      version: 8,
      sources: {
        "base": {
          type: "raster",
          tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
          tileSize: 256,
          attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        }
      },
      layers: [{ id: "base", type: "raster", source: "base" }]
    },
    center: [SUMMIT.lng, SUMMIT.lat],
    zoom: 12.6,
    bearing: 0,
    pitch: 76,
    maxPitch: 85,
    maxZoom: 17,
    attributionControl: { compact: true }
  });
  map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "bottom-right");
  const status = message => { $("status").textContent = message; };

  // Approximate great-circle target in the desired direction. These are view headings, not named peaks.
  function lookTarget(heading, kilometres = 14) {
    const bearing = heading * Math.PI / 180;
    const lat = SUMMIT.lat * Math.PI / 180;
    const lon = SUMMIT.lng * Math.PI / 180;
    const angle = kilometres / 6371.0088;
    const destLat = Math.asin(Math.sin(lat) * Math.cos(angle) +
      Math.cos(lat) * Math.sin(angle) * Math.cos(bearing));
    const destLon = lon + Math.atan2(Math.sin(bearing) * Math.sin(angle) * Math.cos(lat),
      Math.cos(angle) - Math.sin(lat) * Math.sin(destLat));
    return [destLon * 180 / Math.PI, destLat * 180 / Math.PI];
  }
  function summitElevation() {
    try {
      const val = map.queryTerrainElevation([SUMMIT.lng, SUMMIT.lat], { exaggerated: false });
      return typeof val === "number" && Number.isFinite(val) ? val : null;
    } catch (_) { return null; }
  }
  function markControls() {
    for (const [id, mode] of [["summit-view", "summit"], ["overview-view", "overview"], ["viewshed-view", "viewshed"]]) {
      const el = $(id), on = state.mode === mode;
      el.classList.toggle("on", on); el.setAttribute("aria-pressed", String(on));
    }
    for (const b of document.querySelectorAll("[data-direction]")) {
      const on = !state.targetPeak && b.dataset.direction === state.direction;
      b.classList.toggle("on", on); b.setAttribute("aria-pressed", String(on));
    }
    for (const [id, value] of [["true-scale", 1], ["exaggerate", 1.5]]) {
      const el = $(id), on = state.exaggeration === value;
      el.classList.toggle("on", on); el.setAttribute("aria-pressed", String(on));
    }
    $("compass-direction").textContent = state.targetPeak ? Math.round(state.targetPeak.bearing_deg) + "°" : state.direction.slice(0, 1).toUpperCase();
  }
  function showComputedLayer(on) {
    if (map.getLayer("viewshed-layer")) {
      map.setLayoutProperty("viewshed-layer", "visibility", on ? "visible" : "none");
    }
    // A flat, accurate 2D projected overlay must not be draped over a
    // vertically exaggerated 3D surface.
    map.setTerrain(on ? null : { source: "dem", exaggeration: state.exaggeration });
    $("viewshed-legend").hidden = !on;
  }
  function showViewshed() {
    if (!state.viewshedReady || !state.viewshedManifest) return;
    showComputedLayer(true);
    map.easeTo({
      center: [SUMMIT.lng, SUMMIT.lat], zoom: 10.7,
      pitch: 0, bearing: 0, duration: 1200
    });
    const meta = state.viewshedManifest;
    const visibleArea = meta.approx_visible_ground_area_km2;
    status("Calculated ground visibility within " + meta.analysis_radius_km +
      " km · approx. " + visibleArea + " km² visible · " +
      meta.dem_resolution_m + " m terrain grid.");
  }
  function showOverview() {
    showComputedLayer(false);
    map.easeTo({
      center: [SUMMIT.lng, SUMMIT.lat], zoom: 12.6, pitch: 74,
      bearing: state.targetPeak ? state.targetPeak.bearing_deg : DIRECTIONS[state.direction], duration: 1300
    });
    status("3D overview · real terrain, at " + state.exaggeration + "× vertical scale.");
  }
  function showSummit() {
    showComputedLayer(false);
    // A FreeCamera placed near the real summit ground is more faithful to a human viewpoint
    // than the usual 3D map 'drone' camera. DEM tile accuracy limits exact eye height.
    const elevation = summitElevation();
    const modelHeight = elevation === null ? 753 : elevation;
    const eyeHeight = modelHeight * state.exaggeration + 2.5;
    const camera = map.getFreeCameraOptions();
    camera.position = maplibregl.MercatorCoordinate.fromLngLat(
      [SUMMIT.lng, SUMMIT.lat], eyeHeight
    );
    const targetCoordinates = state.targetPeak
      ? [state.targetPeak.longitude, state.targetPeak.latitude]
      : lookTarget(DIRECTIONS[state.direction]);
    camera.lookAtPoint(targetCoordinates);
    try {
      map.setFreeCameraOptions(camera);
      status("Looking " + (state.targetPeak ? "towards " + state.targetPeak.name + " (" + state.targetPeak.distance_km + " km)" : state.direction) + " from near the summit · DEM height " +
        (elevation === null ? "estimated" : Math.round(elevation) + " m") +
        " · " + state.exaggeration + "× relief.");
    } catch (error) {
      status("Ground-level camera unavailable. Showing a 3D overview instead.");
      showOverview();
    }
  }
  function updateView() {
    markControls();
    if (!state.ready) return;
    if (state.mode === "summit") showSummit();
    else if (state.mode === "viewshed") showViewshed();
    else showOverview();
  }
  async function loadCalculatedViewshed() {
    try {
      const response = await fetch("./data/viewshed-manifest.json", { cache: "no-store" });
      if (!response.ok) throw new Error("viewshed data not yet generated");
      const meta = await response.json();
      const corners = meta.image_corners_lonlat;
      if (meta.status !== "computed" ||
          !Array.isArray(corners) || corners.length !== 4 ||
          !corners.every(p => Array.isArray(p) && p.length === 2 &&
          p.every(Number.isFinite))) {
        throw new Error("the viewshed manifest is incomplete");
      }
      const imageName = String(meta.overlay_png || "");
      if (!/^viewshed-overlay\.png$/.test(imageName)) throw new Error("unexpected overlay path");
      map.addSource("viewshed-image", {
        type: "image",
        url: "./data/" + imageName,
        coordinates: corners,
        attribution: "Calculated from Tilezen terrain with GDAL"
      });
      map.addLayer({
        id: "viewshed-layer", type: "raster", source: "viewshed-image",
        layout: { visibility: "none" }, paint: { "raster-opacity": 1 }
      });
      state.viewshedManifest = meta;
      state.viewshedReady = true;
      $("viewshed-view").disabled = false;
      $("viewshed-view").title = "Switch to the computed terrain viewshed";
      if (state.mode !== "viewshed") {
        status("Real elevation loaded. Calculated viewshed also available.");
      }
    } catch (error) {
      $("viewshed-view").disabled = true;
      $("viewshed-view").title = "Calculated viewshed not yet available";
      if (state.ready) status(
        "Real elevation loaded. Computed viewshed not available in this preview."
      );
    }
  }


  function turnTowardsPeak(peak) {
    state.targetPeak = peak;
    state.mode = "summit";
    updateView();
  }

  async function loadNamedPeaks() {
    try {
      const response = await fetch("./data/peaks.json", { cache: "no-store" });
      if (!response.ok) return; // No invented names if the OSM source failed.
      const data = await response.json();
      if (data.status !== "computed_from_real_data" || !Array.isArray(data.labelled_peaks)) {
        throw new Error("Summit name data are incomplete");
      }
      const entries = data.labelled_peaks.filter(p =>
        p.visibility === "visible" && p.gdal_visible === true &&
        p.independent_ray_visible === true && typeof p.name === "string" &&
        p.name.length <= 65 && Number.isFinite(p.longitude) &&
        Number.isFinite(p.latitude) && Number.isFinite(p.bearing_deg) &&
        Number.isFinite(p.distance_km));
      if (!entries.length) return;
      const list = $("peak-list");
      list.replaceChildren();
      for (const peak of entries) {
        const markerButton = document.createElement("button");
        markerButton.type = "button";
        markerButton.className = "peak-marker";
        markerButton.textContent = peak.name;
        markerButton.title = "Look towards " + peak.name;
        markerButton.setAttribute("aria-label", "Look towards " + peak.name);
        markerButton.addEventListener("click", () => turnTowardsPeak(peak));
        const marker = new maplibregl.Marker({ element: markerButton, anchor: "bottom" })
          .setLngLat([peak.longitude, peak.latitude])
          .addTo(map);
        state.peakMarkers.push(marker);

        const button = document.createElement("button");
        button.type = "button"; button.className = "peak-button";
        const label = document.createElement("span");
        const title = document.createElement("strong"); title.textContent = peak.name;
        const details = document.createElement("small");
        const height = peak.osm_height_m == null
          ? Math.round(peak.dem_height_m) + " m DEM"
          : Math.round(peak.osm_height_m) + " m mapped";
        details.textContent = height + " · " + peak.distance_km +
          " km away · " + Math.round(peak.bearing_deg) + "°";
        label.append(title, details);
        const arrow = document.createElement("span"); arrow.className = "arrow";
        arrow.textContent = "↗"; arrow.setAttribute("aria-hidden", "true");
        button.append(label, arrow);
        button.addEventListener("click", () => turnTowardsPeak(peak));
        list.append(button);
      }
      state.visiblePeaks = entries;
      $("peak-guide").hidden = false;
      $("peak-summary").textContent = entries.length +
        " named summits are labelled here, from " + data.visible_count +
        " candidate peaks modelled visible in the 20 km terrain study. Only places where the GDAL viewshed and an independent ray agree are included. Select one to look towards it.";
    } catch (error) {
      // This is enrichment, not a prerequisite for displaying terrain/viewshed.
      console.warn("Named summit data unavailable:", error);
    }
  }

  map.on("load", () => {
    map.addSource("dem", {
      type: "raster-dem",
      tiles: ["https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"],
      tileSize: 256, encoding: "terrarium", maxzoom: 15,
      attribution: '<a href="https://github.com/tilezen/joerd/blob/master/docs/attribution.md">Tilezen / AWS open elevation tiles</a>'
    });
    map.setTerrain({ source: "dem", exaggeration: 1 });
    map.addLayer({
      id: "hillshade", type: "hillshade", source: "dem",
      paint: {
        "hillshade-exaggeration": .45,
        "hillshade-highlight-color": "#f5f3d9",
        "hillshade-shadow-color": "#526962"
      }
    });
    const pin = document.createElement("div");
    pin.title = "Dale Head summit viewpoint";
    pin.style.cssText = "width:14px;height:14px;background:#e0b775;border:3px solid #fff;border-radius:50%;box-shadow:0 0 0 2px #244c3d";
    new maplibregl.Marker({ element: pin, anchor: "center" }).setLngLat([SUMMIT.lng, SUMMIT.lat])
      .setPopup(new maplibregl.Popup({ offset: 12 }).setText("Dale Head · approximate summit viewpoint, 753 m"))
      .addTo(map);
    state.ready = true;
    status("Elevation tiles connected. Waiting for detailed terrain…");
    // Wait for visible DEM tiles to settle before positioning a near-surface camera.
    map.once("idle", () => updateView());
    loadCalculatedViewshed();
    loadNamedPeaks();
  });
  map.on("error", (event) => {
    if (!state.ready) status("The basemap or elevation tiles could not load. Check your connection.");
  });
  $("summit-view").addEventListener("click", () => { state.mode = "summit"; updateView(); });
  $("overview-view").addEventListener("click", () => { state.mode = "overview"; updateView(); });
  $("viewshed-view").addEventListener("click", () => {
    if (!state.viewshedReady) return;
    state.mode = "viewshed";
    updateView();
  });
  document.querySelectorAll("[data-direction]").forEach(button => {
    button.addEventListener("click", () => {
      state.targetPeak = null; state.direction = button.dataset.direction; updateView();
    });
  });
  $("true-scale").addEventListener("click", () => setVerticalScale(1));
  $("exaggerate").addEventListener("click", () => setVerticalScale(1.5));
  function setVerticalScale(value) {
    state.exaggeration = value;
    if (state.ready && state.mode !== "viewshed") {
      map.setTerrain({ source: "dem", exaggeration: value });
    }
    updateView();
  }
  markControls();
})();