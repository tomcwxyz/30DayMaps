/* Day 05 / Sight — a real elevation terrain viewer, not a calculated viewshed. */
(() => {
  "use strict";
  const SUMMIT = { lng: -3.201936, lat: 54.527271 };
  const DIRECTIONS = { north: 0, east: 90, south: 180, west: 270 };
  const state = { mode: "overview", direction: "north", exaggeration: 1, ready: false,
    viewshedReady: false, viewshedManifest: null, targetPeak: null,
    visiblePeaks: [], peakMarkers: [], panoramaController: null,
    panoramaReady: false, userChangedMode: false,
    terrainEnabled: false, terrainScale: null, terrainChanges: 0,
    viewshedLayerVisible: false, activeView: null };
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
    pitch: 64,
    maxPitch: 85,
    maxZoom: 17,
    attributionControl: { compact: true }
  });
  map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "bottom-right");
  const status = message => { $("status").textContent = message; };

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
    // Exaggeration applies to the 3D landscape, not the measured panorama or viewshed.
    $("true-scale").disabled = state.mode !== "overview";
    $("exaggerate").disabled = state.mode !== "overview";
    $("compass-direction").textContent = state.mode === "summit" && state.panoramaController
      ? Math.round(state.panoramaController.currentHeading()) + "°"
      : state.targetPeak ? Math.round(state.targetPeak.bearing_deg) + "°"
      : state.direction.slice(0, 1).toUpperCase();
  }
  function showComputedLayer(on) {
    // IMPORTANT: don't call setTerrain again on every compass click. MapLibre
    // may rebuild its elevation mesh and show stale/draped tiles on mobile.
    if (map.getLayer("viewshed-layer") && state.viewshedLayerVisible !== on) {
      map.setLayoutProperty("viewshed-layer", "visibility", on ? "visible" : "none");
      state.viewshedLayerVisible = on;
    }
    const enableTerrain = !on;
    const needsUpdate = state.terrainEnabled !== enableTerrain ||
      (enableTerrain && state.terrainScale !== state.exaggeration);
    if (needsUpdate) {
      map.setTerrain(enableTerrain ? { source: "dem", exaggeration: state.exaggeration } : null);
      state.terrainEnabled = enableTerrain;
      state.terrainScale = enableTerrain ? state.exaggeration : null;
      state.terrainChanges += 1;
      $("map").dataset.terrainChanges = String(state.terrainChanges);
    }
    $("viewshed-legend").hidden = !on;
  }

  function refreshMap() {
    // Ensure a fresh WebGL frame after a compass change or showing the map.
    requestAnimationFrame(() => {
      map.resize();
      map.triggerRepaint();
    });
  }
  function showViewshed() {
    $("panorama").hidden = true;
    if (!state.viewshedReady || !state.viewshedManifest) return;
    const arriving = state.activeView !== "viewshed";
    showComputedLayer(true);
    if (arriving) {
      map.stop();
      map.jumpTo({
        center: [SUMMIT.lng, SUMMIT.lat], zoom: 10.7,
        pitch: 0, bearing: 0
      });
    }
    state.activeView = "viewshed";
    refreshMap();
    const meta = state.viewshedManifest;
    const visibleArea = meta.approx_visible_ground_area_km2;
    status("Calculated ground visibility within " + meta.analysis_radius_km +
      " km · approx. " + visibleArea + " km² visible · " +
      meta.dem_resolution_m + " m terrain grid.");
  }
  function showOverview() {
    $("panorama").hidden = true;
    const arriving = state.activeView !== "overview";
    showComputedLayer(false);
    const bearing = state.targetPeak ? state.targetPeak.bearing_deg : DIRECTIONS[state.direction];
    map.stop();
    if (arriving) {
      // A modest pitch avoids extreme near-ground ray angles on phone GPUs.
      const mobile = window.matchMedia("(max-width: 740px)").matches;
      map.jumpTo({
        center: [SUMMIT.lng, SUMMIT.lat],
        zoom: mobile ? 11.7 : 12.3,
        pitch: mobile ? 48 : 58,
        bearing
      });
    } else {
      // A compass change must rotate the existing mesh, not create another.
      map.setBearing(bearing);
    }
    state.activeView = "overview";
    $("map").dataset.direction = String(Math.round(bearing));
    refreshMap();
    status("3D overview looking " +
      (state.targetPeak ? "towards " + state.targetPeak.name : state.direction) +
      " · real terrain, " + state.exaggeration + "× vertical scale.");
  }
  function showSummit() {
    if (!state.panoramaReady || !state.panoramaController) {
      state.mode = "overview";
      showOverview();
      status("The calculated summit panorama is unavailable; showing the real 3D overview.");
      return;
    }
    // The panorama already contains real DEM measurements, so do not reset
    // MapLibre terrain underneath it on each change of direction.
    $("viewshed-legend").hidden = true;
    $("panorama").hidden = false;
    state.activeView = "summit";
    const bearing = state.targetPeak ? state.targetPeak.bearing_deg : DIRECTIONS[state.direction];
    state.panoramaController.setHeading(bearing);
    state.panoramaController.repaint();
    const sight = state.targetPeak
      ? "towards " + state.targetPeak.name + " (" + state.targetPeak.distance_km + " km)"
      : state.direction;
    status("Looking " + sight +
      " from Dale Head · calculated landscape silhouettes at 753 m summit and 1.7 m eye height.");
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
      if (state.mode === "overview") {
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


  async function loadCalculatedPanorama() {
    try {
      const response = await fetch("./data/panorama.json", { cache: "no-store" });
      if (!response.ok) throw new Error("calculated summit profile not present");
      const data = await response.json();
      if (data.status !== "computed_from_real_dem" ||
          !Number.isFinite(data.observer_eye_altitude_m) ||
          !data.profile || !Array.isArray(data.profile.bands_near_to_far)) {
        throw new Error("incomplete real terrain panorama profile");
      }
      state.panoramaController = window.SightPanorama.create({
        canvas: $("panorama-canvas"), labels: $("panorama-labels"), data,
        peaks: state.visiblePeaks,
        onHeadingChange: heading => {
          if (state.mode === "summit") $("compass-direction").textContent = Math.round(heading) + "°";
        }
      });
      state.panoramaReady = true;
      $("summit-view").disabled = false;
      $("summit-view").title = "Look around from the documented summit viewpoint";
      if (!state.userChangedMode) {
        state.mode = "summit";
        updateView();
      }
    } catch (error) {
      $("summit-view").disabled = true;
      $("summit-view").title = "Calculated summit panorama unavailable";
      console.warn("Calculated panorama unavailable:", error);
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
      if (state.panoramaController) state.panoramaController.setPeaks(entries);
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
    state.terrainEnabled = true;
    state.terrainScale = 1;
    state.terrainChanges = 1;
    $("map").dataset.terrainChanges = "1";
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
    loadCalculatedPanorama();
    loadNamedPeaks();
  });
  map.on("error", (event) => {
    if (!state.ready) status("The basemap or elevation tiles could not load. Check your connection.");
  });
  $("summit-view").addEventListener("click", () => { state.userChangedMode = true; state.mode = "summit"; updateView(); });
  $("overview-view").addEventListener("click", () => { state.userChangedMode = true; state.mode = "overview"; updateView(); });
  $("viewshed-view").addEventListener("click", () => {
    if (!state.viewshedReady) return;
    state.userChangedMode = true;
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
    if (state.mode !== "overview" || state.exaggeration === value) return;
    state.exaggeration = value;
    // A single terrain update is performed by showComputedLayer(false).
    updateView();
  }
  markControls();
})();