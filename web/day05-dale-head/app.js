/* Day 05 / Sight — a real elevation terrain viewer, not a calculated viewshed. */
(() => {
  "use strict";
  const SUMMIT = { lng: -3.201936, lat: 54.527271 };
  const DIRECTIONS = { north: 0, east: 90, south: 180, west: 270 };
  const state = { mode: "summit", direction: "north", exaggeration: 1, ready: false };
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
    for (const [id, mode] of [["summit-view", "summit"], ["overview-view", "overview"]]) {
      const el = $(id), on = state.mode === mode;
      el.classList.toggle("on", on); el.setAttribute("aria-pressed", String(on));
    }
    for (const b of document.querySelectorAll("[data-direction]")) {
      const on = b.dataset.direction === state.direction;
      b.classList.toggle("on", on); b.setAttribute("aria-pressed", String(on));
    }
    for (const [id, value] of [["true-scale", 1], ["exaggerate", 1.5]]) {
      const el = $(id), on = state.exaggeration === value;
      el.classList.toggle("on", on); el.setAttribute("aria-pressed", String(on));
    }
    $("compass-direction").textContent = state.direction.slice(0, 1).toUpperCase();
  }
  function showOverview() {
    map.easeTo({
      center: [SUMMIT.lng, SUMMIT.lat], zoom: 12.6, pitch: 74,
      bearing: DIRECTIONS[state.direction], duration: 1300
    });
    status("3D overview · real terrain, at " + state.exaggeration + "× vertical scale.");
  }
  function showSummit() {
    // A FreeCamera placed near the real summit ground is more faithful to a human viewpoint
    // than the usual 3D map 'drone' camera. DEM tile accuracy limits exact eye height.
    const elevation = summitElevation();
    const modelHeight = elevation === null ? 753 : elevation;
    const eyeHeight = modelHeight * state.exaggeration + 2.5;
    const camera = map.getFreeCameraOptions();
    camera.position = maplibregl.MercatorCoordinate.fromLngLat(
      [SUMMIT.lng, SUMMIT.lat], eyeHeight
    );
    camera.lookAtPoint(lookTarget(DIRECTIONS[state.direction]));
    try {
      map.setFreeCameraOptions(camera);
      status("Looking " + state.direction + " from near the summit · DEM height " +
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
    else showOverview();
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
  });
  map.on("error", (event) => {
    if (!state.ready) status("The basemap or elevation tiles could not load. Check your connection.");
  });
  $("summit-view").addEventListener("click", () => { state.mode = "summit"; updateView(); });
  $("overview-view").addEventListener("click", () => { state.mode = "overview"; updateView(); });
  document.querySelectorAll("[data-direction]").forEach(button => {
    button.addEventListener("click", () => {
      state.direction = button.dataset.direction; updateView();
    });
  });
  $("true-scale").addEventListener("click", () => setVerticalScale(1));
  $("exaggerate").addEventListener("click", () => setVerticalScale(1.5));
  function setVerticalScale(value) {
    state.exaggeration = value;
    if (state.ready) map.setTerrain({ source: "dem", exaggeration: value });
    updateView();
  }
  markControls();
})();