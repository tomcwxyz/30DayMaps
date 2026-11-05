/* Day 05 — Sight: real, published GBIF records, never modelled sightings. */
(() => {
  "use strict";
  const API = "https://api.gbif.org/v1";
  const { circlePolygon } = window.SightGeo;
  const TAXA = {
    birds: { key: 212, label: "Birds" },
    mammals: { key: 359, label: "Mammals" },
    butterflies: { key: 797, label: "Butterflies & moths" },
    plants: { key: 6, label: "Plants" }
  };
  const MONTHS = ["January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December"];
  // Only use the example town if the browser location is unavailable or refused.
  // It must never be described as the visitor's location.
  const EXAMPLE = { lat: 54.617, lng: -1.578, place: "Newton Aycliffe (example)" };
  const state = {
    lat: null, lng: null, place: "",
    locationResolved: false, locationToken: 0,
    month: new Date().getMonth() + 1, radius: 5, taxon: "birds",
    includeCurrent: false, requestId: 0, controller: null,
    selectedKey: null, facet: [], observed: [], total: 0, searchUrl: ""
  };
  const $ = (id) => document.getElementById(id);
  // Start with a UK overview while location permission is being resolved.
  const map = L.map("map", { scrollWheelZoom: false, zoomControl: false }).setView([54.5, -2.5], 6);
  L.control.zoom({ position: "bottomright" }).addTo(map);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
  }).addTo(map);
  const selected = L.circleMarker([54.5, -2.5], {
    radius: 8, weight: 3, color: "#fffef9", fillColor: "#173e30", fillOpacity: 1
  });
  const circle = L.circle([54.5, -2.5], {
    radius: state.radius * 1000, color: "#356c54", weight: 2,
    fillColor: "#93b19b", fillOpacity: .10
  });
  const occurrences = L.layerGroup().addTo(map);
  const nf = new Intl.NumberFormat("en-GB");
  let debounce = null;

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
  function setLocationStatus(message) { $("location-status").textContent = message; }
  function withinBritain(lat, lng) {
    return Number.isFinite(lat) && Number.isFinite(lng) &&
      lat >= 49.5 && lat <= 61.2 && lng >= -9 && lng <= 2.5;
  }
  function updateTitles() {
    $("guide-title").textContent = TAXA[state.taxon].label + " in " + MONTHS[state.month - 1];
    $("guide-subtitle").textContent = "Near " + state.place + " · within " + state.radius + " km";
    $("period-note").textContent = "Observation years: 2021–" + (state.includeCurrent ? "2026 (current year incomplete)" : "2025");
    $("data-notes").textContent = "Observation years: 2021–" + (state.includeCurrent ? "2026, including an incomplete current year." : "2025.") +
      " The map displays at most the first 300 returned records for the selected search. The field-guide species counts use the GBIF full-search species facets, not the map sample. All results are subject to recording and location biases.";
  }
  function updateLocation(fit = true) {
    if (!state.locationResolved) return;
    selected.setLatLng([state.lat, state.lng]);
    circle.setLatLng([state.lat, state.lng]).setRadius(state.radius * 1000);
    if (!map.hasLayer(circle)) circle.addTo(map);
    if (!map.hasLayer(selected)) selected.addTo(map);
    if (fit) map.fitBounds(circle.getBounds(), { padding: [25, 25], maxZoom: 13 });
    updateTitles();
  }
  function scheduleLoad() {
    clearTimeout(debounce);
    if (!state.locationResolved) return;
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
    button.dataset.speciesKey = String(taxon.key);
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
    const counts = facets.find(f => /species.?key/i.test(f.field || ""));
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
  function renderSeasonalCounts(data, speciesLabel) {
    const facet = (data.facets || []).find(f => String(f.field || "").toLowerCase() === "month");
    if (!facet || !Array.isArray(facet.counts)) throw new Error("Month counts not returned by GBIF");
    const byMonth = new Map(facet.counts.map(x => [Number(x.name), Number(x.count)]));
    const max = Math.max(1, ...Array.from(byMonth.values()));
    const bars = $("season-bars");
    bars.replaceChildren();
    const accessible = [];
    MONTHS.forEach((name, i) => {
      const month = i + 1;
      const count = byMonth.get(month) || 0;
      accessible.push(name + ": " + nf.format(count) + " records");
      const item = document.createElement("div");
      item.className = "season-month" + (state.month === month ? " current" : "");
      item.title = name + ": " + nf.format(count) + " published observations";
      const column = document.createElement("div"); column.className = "chart-column";
      const fill = document.createElement("span"); fill.className = "chart-fill";
      fill.style.height = count > 0 ? Math.max(3, 100 * count / max) + "%" : "0";
      column.append(fill);
      const short = document.createElement("span"); short.className = "abbr";
      short.textContent = name.slice(0, 1);
      item.append(column, short);
      bars.append(item);
    });
    bars.setAttribute("aria-label", "Monthly published observation counts for " +
      speciesLabel + ". " + accessible.join("; "));
    $("season-title").textContent = speciesLabel + " through the year";
    $("season-note").textContent =
      "Records by observation month across 2021–" + (state.includeCurrent ? "2026" : "2025") +
      ". Taller bars mean more published records, not a higher probability of seeing this species.";
    $("seasonality").hidden = false;
  }
  async function selectSpecies(key) {
    if (!state.facet.some(f => String(f.name) === String(key))) return;
    if (state.controller) state.controller.abort();
    state.controller = new AbortController();
    const signal = state.controller.signal;
    const requestId = ++state.requestId;
    state.selectedKey = key;
    $("seasonality").hidden = true;
    const p = getQuery(key);
    setStatus("Finding published locations for this species…");
    try {
      const data = await getJson(API + "/occurrence/search?" + p.toString(), signal);
      if (requestId !== state.requestId) return;
      plotRecords(data.results || [], data.count || 0, true);
      $("species-list").querySelectorAll(".species-item").forEach(row => {
        const selectedRow = row.dataset.speciesKey === String(key);
        row.classList.toggle("selected", selectedRow);
        row.setAttribute("aria-pressed", String(selectedRow));
      });
      setStatus(nf.format(data.count || 0) + " records match this species. The map shows at most the first 300.");
      const chosen = Array.from($("species-list").querySelectorAll(".species-item"))
        .find(row => row.dataset.speciesKey === String(key));
      const speciesLabel = chosen?.querySelector(".common")?.textContent || "Selected species";
      const seasonalQuery = getQuery(key);
      seasonalQuery.delete("month");
      seasonalQuery.set("limit", "0");
      seasonalQuery.set("facet", "month");
      seasonalQuery.set("facetLimit", "12");
      try {
        const annual = await getJson(API + "/occurrence/search?" + seasonalQuery.toString(), signal);
        if (requestId === state.requestId) renderSeasonalCounts(annual, speciesLabel);
      } catch (error) {
        if (error.name === "AbortError") throw error;
        if (requestId === state.requestId) {
          $("season-title").textContent = speciesLabel + " through the year";
          $("season-note").textContent = "A monthly comparison is not available from the data provider at present.";
          $("season-bars").replaceChildren();
          $("seasonality").hidden = false;
        }
      }
    } catch (error) {
      if (error.name !== "AbortError") setStatus("Could not load this species: " + error.message);
    }
  }
  async function loadRecords() {
    if (!state.locationResolved) {
      setStatus("Waiting for a location before looking up wildlife…");
      return;
    }
    if (state.controller) state.controller.abort();
    state.controller = new AbortController();
    const signal = state.controller.signal;
    const requestId = ++state.requestId;
    state.selectedKey = null; state.facet = [];
    $("seasonality").hidden = true;
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
      state.facet = ((data.facets || []).find(f => /species.?key/i.test(f.field || "")) || {}).counts || [];
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
  function moveTo(lat, lng, title, message, fromLocationCallback = false) {
    if (!withinBritain(lat, lng)) {
      setLocationStatus("Choose a point in Britain to explore nearby records.");
      return;
    }
    // A manual place search or map click must win if the original permission
    // prompt resolves later. Never override a deliberate visitor choice.
    if (!fromLocationCallback) state.locationToken++;
    state.lat = lat; state.lng = lng; state.place = title;
    state.locationResolved = true;
    if (message) setLocationStatus(message);
    updateLocation(true);
    scheduleLoad();
  }

  function useExample(reason) {
    moveTo(EXAMPLE.lat, EXAMPLE.lng, EXAMPLE.place,
      reason + " Showing Newton Aycliffe as an example; search or click the map to change it.",
      true);
  }

  function requestVisitorLocation() {
    const attempt = ++state.locationToken;
    if (!navigator.geolocation || !window.isSecureContext) {
      useExample("Your browser cannot share a location here.");
      return;
    }
    setLocationStatus("Finding your area… Your browser may ask for location permission.");
    setStatus("Waiting for your location before looking up nearby wildlife…");
    navigator.geolocation.getCurrentPosition(
      position => {
        if (attempt !== state.locationToken) return;
        const lat = Math.round(Number(position.coords.latitude) * 1000) / 1000;
        const lng = Math.round(Number(position.coords.longitude) * 1000) / 1000;
        if (!withinBritain(lat, lng)) {
          useExample("Your location appears to be outside the current Britain-only map.");
          return;
        }
        $("place").value = "";
        moveTo(lat, lng, "your approximate location",
          "Using your approximate location (rounded to around 100 metres). You can choose somewhere else.", true);
      },
      error => {
        if (attempt !== state.locationToken) return;
        const reason = error && error.code === 1
          ? "Location permission wasn't granted."
          : "We couldn't find your location.";
        useExample(reason);
      },
      { enableHighAccuracy: false, timeout: 9000, maximumAge: 60000 }
    );
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
    $("seasonality").hidden = true;
    $("species-list").querySelectorAll(".species-item").forEach(row => {
      row.classList.remove("selected");
      row.setAttribute("aria-pressed", "false");
    });
    plotRecords(state.observed, state.total, false);
    setStatus("Showing the first " + state.observed.length + " returned records across all selected wildlife.");
  });
  map.on("click", (e) => {
    $("place").value = "";
    moveTo(e.latlng.lat, e.latlng.lng, "selected map point",
      "Using the point you chose on the map. The location isn't saved.");
  });
  $("locate").addEventListener("click", requestVisitorLocation);
  let lastSearchAt = 0;
  $("place-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const q = $("place").value.trim(); if (!q) return;
    ++state.locationToken; // A manual search takes priority over an automatic location callback.
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
      if (!data.length) {
        setLocationStatus("Place not found. Try a nearby town or choose a point on the map.");
        if (!state.locationResolved) useExample("Search didn't return a place.");
        return;
      }
      moveTo(Number(data[0].lat), Number(data[0].lon), data[0].name || q,
        "Showing records near " + (data[0].name || q) + ". Change the month to explore the seasons.");
    } catch (error) {
      setLocationStatus("Place search unavailable. You can click the map instead.");
      if (!state.locationResolved) useExample("Place search couldn't be completed.");
    }
  });
  // Location is the first choice, not a fixed hometown. This deliberately
  // defers the first GBIF query until the browser answers or the example is shown.
  requestVisitorLocation();
})();
