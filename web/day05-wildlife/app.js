/* Day 05 — Sight: real, published GBIF records, never modelled sightings. */
(() => {
  "use strict";
  const API = "https://api.gbif.org/v1";
  const TAXA = {
    birds: { key: 212, label: "Birds" },
    mammals: { key: 359, label: "Mammals" },
    butterflies: { key: 797, label: "Butterflies & moths" },
    plants: { key: 6, label: "Plants" }
  };
  const MONTHS = ["January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December"];
  const state = {
    lat: 54.617, lng: -1.578, place: "Newton Aycliffe",
    month: new Date().getMonth() + 1, radius: 5, taxon: "birds",
    includeCurrent: false, requestId: 0, controller: null,
    selectedKey: null, facet: [], observed: [], total: 0, searchUrl: ""
  };
  const $ = (id) => document.getElementById(id);
  const map = L.map("map", { scrollWheelZoom: false, zoomControl: false }).setView([state.lat, state.lng], 12);
  L.control.zoom({ position: "bottomright" }).addTo(map);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
  }).addTo(map);
  const selected = L.circleMarker([state.lat, state.lng], {
    radius: 8, weight: 3, color: "#fffef9", fillColor: "#173e30", fillOpacity: 1
  }).addTo(map);
  const circle = L.circle([state.lat, state.lng], {
    radius: state.radius * 1000, color: "#356c54", weight: 2,
    fillColor: "#93b19b", fillOpacity: .10
  }).addTo(map);
  const occurrences = L.layerGroup().addTo(map);
  const nf = new Intl.NumberFormat("en-GB");
  let debounce = null;

  function circlePolygon(lon, lat, radiusKm, sides = 36) {
    if (Math.abs(lat) > 85) throw new Error("Please choose a location in Britain.");
    const earthKm = 6371.0088;
    const distance = radiusKm / earthKm;
    const latitude = lat * Math.PI / 180;
    const longitude = lon * Math.PI / 180;
    const points = [];
    for (let i = 0; i <= sides; i++) {
      const bearing = 2 * Math.PI * i / sides;
      const destLat = Math.asin(Math.sin(latitude) * Math.cos(distance) +
        Math.cos(latitude) * Math.sin(distance) * Math.cos(bearing));
      const destLon = longitude + Math.atan2(Math.sin(bearing) * Math.sin(distance) * Math.cos(latitude),
        Math.cos(distance) - Math.sin(latitude) * Math.sin(destLat));
      points.push([destLon * 180 / Math.PI, destLat * 180 / Math.PI]);
    }
    // GBIF interprets exterior polygons counter-clockwise. Bearings generate a clockwise ring.
    points.reverse();
    return "POLYGON((" + points.map(p => p[0].toFixed(6) + " " + p[1].toFixed(6)).join(",") + "))";
  }

  function getQuery(taxonKey = TAXA[state.taxon].key) {
    const p = new URLSearchParams({
      geometry: circlePolygon(state.lng, state.lat, state.radius),
      year: "2021," + (state.includeCurrent ? "2026" : "2025"),
      month: String(state.month),
      taxonKey: String(taxonKey),
      hasCoordinate: "true", hasGeospatialIssue: "false",
      occurrenceStatus: "PRESENT",
      limit: "300"
    });
    return p;
  }

  function setStatus(message) { $("status").textContent = message; }
  function updateTitles() {
    $("guide-title").textContent = TAXA[state.taxon].label + " in " + MONTHS[state.month - 1];
    $("guide-subtitle").textContent = "Near " + state.place + " · within " + state.radius + " km";
    $("period-note").textContent = "Observation years: 2021–" + (state.includeCurrent ? "2026 (current year incomplete)" : "2025");
    $("data-notes").textContent = "Observation years: 2021–" + (state.includeCurrent ? "2026, including an incomplete current year." : "2025.") +
      " The map displays at most the first 300 returned records for the selected search. The field-guide species counts use the GBIF full-search species facets, not the map sample. All results are subject to recording and location biases.";
  }
  function updateLocation(fit = true) {
    selected.setLatLng([state.lat, state.lng]);
    circle.setLatLng([state.lat, state.lng]).setRadius(state.radius * 1000);
    if (fit) map.fitBounds(circle.getBounds(), { padding: [25, 25], maxZoom: 13 });
    updateTitles();
  }
  function scheduleLoad() {
    clearTimeout(debounce);
    debounce = setTimeout(loadRecords, 300);
  }
  function safeDate(item) {
    const d = item.eventDate || (item.year && item.month ? item.year + "-" + String(item.month).padStart(2, "0") : "");
    return d ? String(d).slice(0, 10) : "Date not supplied";
  }
  function speciesName(r) { return r.vernacularName || r.species || r.scientificName || "Unidentified species"; }
  function makeOccurrencePopup(r) {
    const root = document.createElement("div");
    const name = document.createElement("strong"); name.textContent = speciesName(r);
    const latin = document.createElement("em"); latin.textContent = r.species || r.scientificName || "";
    latin.style.display = "block";
    const date = document.createElement("span"); date.className = "date";
    date.textContent = "Observed: " + safeDate(r);
    const publisher = document.createElement("small");
    publisher.textContent = r.datasetName || r.institutionCode || "GBIF contributor";
    publisher.style.display = "block";
    const precision = document.createElement("small");
    precision.style.display = "block";
    precision.textContent = r.coordinateUncertaintyInMeters ?
      "Published co-ordinate uncertainty: " + nf.format(Math.round(r.coordinateUncertaintyInMeters)) + " m" :
      "Location accuracy not supplied; the published point may be generalised.";
    const link = document.createElement("a");
    link.href = "https://www.gbif.org/occurrence/" + encodeURIComponent(r.key);
    link.target = "_blank"; link.rel = "noopener";
    link.textContent = "Open original record and licence";
    root.append(name, latin, date, publisher, precision, link);
    return root;
  }
  function plotRecords(items, total, selectedTaxon) {
    occurrences.clearLayers();
    let plotted = 0;
    for (const r of items) {
      if (typeof r.decimalLatitude !== "number" || typeof r.decimalLongitude !== "number") continue;
      if (!Number.isFinite(r.decimalLatitude) || !Number.isFinite(r.decimalLongitude)) continue;
      // GBIF geometry is the authoritative geographic filter; published coordinates may be generalised.
      const pt = L.circleMarker([r.decimalLatitude, r.decimalLongitude], {
        radius: 5, weight: 1, color: "#fffef9", fillColor: selectedTaxon ? "#ad5c31" : "#c66d38", fillOpacity: .78
      });
      pt.bindPopup(() => makeOccurrencePopup(r));
      occurrences.addLayer(pt);
      plotted++;
    }
    const qualifier = selectedTaxon ? " for this selected species" : "";
    $("map-note").textContent = nf.format(plotted) + " published points shown, from the first " +
      nf.format(items.length) + " results of " + nf.format(total) + " matching records" + qualifier +
      ". Locations may be generalised.";
    $("clear-filter").hidden = !selectedTaxon;
  }
  async function getJson(url, signal) {
    const response = await fetch(url, { signal, headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error("The data service returned HTTP " + response.status + ".");
    return response.json();
  }
  async function speciesLabel(key, sample, signal) {
    const known = sample.find(r => String(r.speciesKey) === String(key));
    if (known) return { key, common: known.vernacularName || known.species || known.scientificName,
      scientific: known.species || known.scientificName || "" };
    try {
      const data = await getJson(API + "/species/" + encodeURIComponent(key), signal);
      return { key, common: data.vernacularName || data.canonicalName || data.scientificName || "Species " + key,
        scientific: data.canonicalName || data.scientificName || "" };
    } catch (error) {
      if (error.name === "AbortError") throw error;
      return { key, common: "Species " + key, scientific: "Check taxon on GBIF" };
    }
  }
  function createSpeciesRow(taxon, count, isSelected) {
    const button = document.createElement("button");
    button.type = "button"; button.className = "species-item" + (isSelected ? " selected" : "");
    const names = document.createElement("span"); names.className = "names";
    const common = document.createElement("span"); common.className = "common"; common.textContent = taxon.common;
    const latin = document.createElement("span"); latin.className = "latin";
    if (taxon.scientific !== taxon.common) latin.textContent = taxon.scientific;
    names.append(common, latin);
    const amount = document.createElement("span"); amount.className = "n"; amount.textContent = nf.format(count) + " records";
    button.append(names, amount);
    button.setAttribute("aria-pressed", isSelected ? "true" : "false");
    button.addEventListener("click", () => selectSpecies(taxon.key));
    return button;
  }
  async function renderFacets(facets, sample, requestId, signal) {
    const container = $("species-list"); container.replaceChildren();
    const counts = facets.find(f => f.field === "SPECIES_KEY" || f.field === "speciesKey");
    const ranking = (counts && counts.counts || []).filter(x => x.name && x.count > 0);
    $("species-total").textContent = nf.format(ranking.length) + (ranking.length >= 25 ? "+" : "");
    if (!ranking.length) {
      $("list-description").textContent = "The provider did not return species-level totals for this query. The map still shows the returned records.";
      return;
    }
    $("list-title").textContent = "Most recorded species";
    $("list-description").textContent = "The leading " + ranking.length +
      " species by published records across the whole search — not a likelihood or abundance ranking.";
    // Request metadata in small concurrent groups rather than 25 simultaneous requests.
    for (let i = 0; i < ranking.length; i += 5) {
      const chunk = ranking.slice(i, i + 5);
      const labels = await Promise.all(chunk.map(x => speciesLabel(x.name, sample, signal)));
      if (requestId !== state.requestId) return;
      for (let j = 0; j < chunk.length; j++) {
        container.append(createSpeciesRow(labels[j], chunk[j].count, false));
      }
    }
  }
  async function selectSpecies(key) {
    if (!state.facet.some(f => String(f.name) === String(key))) return;
    if (state.controller) state.controller.abort();
    state.controller = new AbortController();
    const signal = state.controller.signal;
    const requestId = ++state.requestId;
    state.selectedKey = key;
    const p = getQuery(key);
    setStatus("Finding published locations for this species…");
    try {
      const data = await getJson(API + "/occurrence/search?" + p.toString(), signal);
      if (requestId !== state.requestId) return;
      plotRecords(data.results || [], data.count || 0, true);
      $("species-list").querySelectorAll(".species-item").forEach(row => {
        const selectedRow = row === state.rowForKey;
        row.classList.toggle("selected", selectedRow);
      });
      setStatus(nf.format(data.count || 0) + " records match this species. The map shows at most the first 300.");
    } catch (error) {
      if (error.name !== "AbortError") setStatus("Could not load this species: " + error.message);
    }
  }
  async function loadRecords() {
    if (state.controller) state.controller.abort();
    state.controller = new AbortController();
    const signal = state.controller.signal;
    const requestId = ++state.requestId;
    state.selectedKey = null; state.facet = [];
    updateTitles(); updateLocation(false);
    const p = getQuery();
    p.set("facet", "speciesKey"); p.set("facetLimit", "25");
    state.searchUrl = API + "/occurrence/search?" + p.toString();
    setStatus("Looking for published observations…");
    $("record-total").textContent = "…";
    $("species-total").textContent = "…";
    $("empty").hidden = true;
    $("species-list").replaceChildren();
    $("clear-filter").hidden = true;
    try {
      const data = await getJson(state.searchUrl, signal);
      if (requestId !== state.requestId) return;
      state.observed = data.results || [];
      state.total = Number(data.count || 0);
      state.facet = ((data.facets || []).find(f => f.field === "SPECIES_KEY" || f.field === "speciesKey") || {}).counts || [];
      $("record-total").textContent = nf.format(state.total);
      plotRecords(state.observed, state.total, false);
      if (!state.total) {
        $("species-total").textContent = "0";
        $("empty").hidden = false;
        setStatus("No published records matched the selected filters.");
        return;
      }
      setStatus(nf.format(state.total) + " published records. The map shows at most the first 300.");
      await renderFacets(data.facets || [], state.observed, requestId, signal);
    } catch (error) {
      if (error.name === "AbortError" || requestId !== state.requestId) return;
      $("record-total").textContent = "—"; $("species-total").textContent = "—";
      occurrences.clearLayers();
      $("map-note").textContent = "Data service unavailable. Map still works for choosing a location.";
      setStatus("Couldn't load GBIF records: " + error.message + " Try changing the month or retrying.");
    }
  }
  function moveTo(lat, lng, title) {
    state.lat = lat; state.lng = lng; state.place = title;
    updateLocation(true); scheduleLoad();
  }
  for (let i = 0; i < MONTHS.length; i++) {
    const option = document.createElement("option");
    option.value = String(i + 1); option.textContent = MONTHS[i];
    $("month").append(option);
  }
  $("month").value = String(state.month);
  $("month").addEventListener("change", (e) => { state.month = Number(e.target.value); scheduleLoad(); });
  $("radius").addEventListener("change", (e) => {
    state.radius = Number(e.target.value); updateLocation(true); scheduleLoad();
  });
  $("include-current").addEventListener("change", (e) => {
    state.includeCurrent = Boolean(e.target.checked); scheduleLoad();
  });
  document.querySelectorAll("[data-taxon]").forEach(button => {
    button.addEventListener("click", () => {
      state.taxon = button.dataset.taxon;
      document.querySelectorAll("[data-taxon]").forEach(b => {
        const active = b === button; b.classList.toggle("active", active);
        b.setAttribute("aria-pressed", String(active));
      });
      scheduleLoad();
    });
  });
  $("clear-filter").addEventListener("click", () => {
    if (state.controller) state.controller.abort();
    ++state.requestId;
    state.selectedKey = null;
    plotRecords(state.observed, state.total, false);
    setStatus("Showing the first " + state.observed.length + " returned records across all selected wildlife.");
  });
  map.on("click", (e) => {
    $("place").value = "";
    moveTo(e.latlng.lat, e.latlng.lng, "selected map point");
  });
  $("locate").addEventListener("click", () => {
    if (!navigator.geolocation) { setStatus("Your browser does not support location."); return; }
    setStatus("Asking your browser for location permission…");
    navigator.geolocation.getCurrentPosition(
      pos => { $("place").value = ""; moveTo(pos.coords.latitude, pos.coords.longitude, "your approximate location"); },
      () => setStatus("Location permission was unavailable. Search for a place or click the map."),
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 }
    );
  });
  let lastSearchAt = 0;
  $("place-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const q = $("place").value.trim(); if (!q) return;
    // Nominatim public instance: user-initiated searches only, at most once per second.
    const now = Date.now();
    if (now - lastSearchAt < 1100) { setStatus("Please leave a moment between place searches."); return; }
    lastSearchAt = now;
    setStatus("Finding " + q + "…");
    try {
      const search = new URL("https://nominatim.openstreetmap.org/search");
      search.searchParams.set("format", "jsonv2");
      search.searchParams.set("countrycodes", "gb");
      search.searchParams.set("limit", "1");
      search.searchParams.set("q", q);
      const data = await getJson(search.toString());
      if (!data.length) { setStatus("Place not found. Try a nearby town or choose a point on the map."); return; }
      moveTo(Number(data[0].lat), Number(data[0].lon), data[0].name || q);
    } catch (error) { setStatus("Place search unavailable: " + error.message + ". You can click the map instead."); }
  });
  updateLocation(true);
  loadRecords();
})();
