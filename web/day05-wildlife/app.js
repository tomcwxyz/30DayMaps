/* Day 05 — Sight: real, published GBIF records, never modelled sightings. */
(() => {
  "use strict";
  const API = "https://api.gbif.org/v1";
  const { circlePolygon } = window.SightGeo;
  const { pickSpeciesPhoto } = window.SightMedia;
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
  function renderMonthNavigation(shouldScroll = false) {
    $("month-summary").textContent = MONTHS[state.month - 1] +
      " observations from previous years. Explore another month to see how the records change.";
    const buttons = $("month-strip").querySelectorAll("[data-month]");
    buttons.forEach(button => {
      const selectedMonth = Number(button.dataset.month) === state.month;
      button.classList.toggle("active", selectedMonth);
      button.setAttribute("aria-pressed", String(selectedMonth));
      button.setAttribute("aria-current", selectedMonth ? "date" : "false");
      button.tabIndex = selectedMonth ? 0 : -1;
    });
    if (shouldScroll) {
      const selected = $("month-strip").querySelector('[data-month="' + state.month + '"]');
      // Only scroll the horizontal ribbon, never jump the entire document.
      const ribbon = $("month-strip");
      if (selected) ribbon.scrollTo({
        left: Math.max(0, selected.offsetLeft - ribbon.offsetLeft -
          (ribbon.clientWidth - selected.offsetWidth) / 2),
        behavior: shouldScroll === "initial" ||
          window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth"
      });
    }
  }

  function chooseMonth(month, focus = false) {
    const number = Number(month);
    if (!Number.isInteger(number) || number < 1 || number > 12) return;
    const changed = state.month !== number;
    state.month = number;
    renderMonthNavigation(true);
    if (focus) {
      $("month-strip").querySelector('[data-month="' + number + '"]')?.focus({ preventScroll: true });
    }
    if (changed) {
      if (state.locationResolved) updateTitles();
      // The species panel represents this month's data, so refresh its
      // records rather than displaying a chart from a previous month.
      $("seasonality").hidden = true;
      scheduleLoad();
    }
  }
  function buildMonthNavigation() {
    const ribbon = $("month-strip");
    const fragment = document.createDocumentFragment();
    MONTHS.forEach((name, i) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "month-choice";
      button.dataset.month = String(i + 1);
      button.textContent = name.slice(0, 3);
      button.title = "Show records observed in " + name + " across the comparison years";
      button.setAttribute("aria-label", "Show " + name + " observations");
      button.addEventListener("click", () => chooseMonth(i + 1));
      fragment.append(button);
    });
    ribbon.append(fragment);
    ribbon.addEventListener("keydown", event => {
      const current = event.target.closest("[data-month]");
      if (!current) return;
      let target = Number(current.dataset.month);
      if (event.key === "ArrowRight") target = target % 12 + 1;
      else if (event.key === "ArrowLeft") target = (target + 10) % 12 + 1;
      else if (event.key === "Home") target = 1;
      else if (event.key === "End") target = 12;
      else return;
      event.preventDefault();
      chooseMonth(target, true);
    });
    $("month-prev").addEventListener("click", () => chooseMonth((state.month + 10) % 12 + 1));
    $("month-next").addEventListener("click", () => chooseMonth(state.month % 12 + 1));
    renderMonthNavigation();
    // If the default is November, don't open a mobile ribbon at January
    // with the active month entirely off-screen.
    requestAnimationFrame(() => renderMonthNavigation("initial"));
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
    const wrapper=document.createElement("div");
    wrapper.className="species-entry";
    const button = document.createElement("button");
    button.type = "button"; button.className = "species-item" + (isSelected ? " selected" : "");
    button.dataset.speciesKey = String(taxon.key);
    const photo=document.createElement("span"); photo.className="species-photo";
    const noPhoto=document.createElement("span");
    noPhoto.className="species-no-photo";
    noPhoto.textContent="PHOTO";
    photo.append(noPhoto);
    const names = document.createElement("span"); names.className = "names";
    const common = document.createElement("span"); common.className = "common"; common.textContent = taxon.common;
    const latin = document.createElement("span"); latin.className = "latin";
    if (taxon.scientific !== taxon.common) latin.textContent = taxon.scientific;
    names.append(common, latin);
    const amount = document.createElement("span"); amount.className = "n"; amount.textContent = nf.format(count) + " records";
    button.append(photo, names, amount);
    button.setAttribute("aria-pressed", isSelected ? "true" : "false");
    button.addEventListener("click", () => selectSpecies(taxon.key));
    const credit=document.createElement("div");
    credit.className="photo-credit"; credit.hidden=true;
    wrapper.append(button,credit);
    return wrapper;
  }
  function showSpeciesPhoto(row, photo, title) {
    if (!photo || !row.isConnected) return;
    const container=row.querySelector(".species-photo");
    const img=document.createElement("img");
    // The entire species row is already lazy-loaded with IntersectionObserver.
    // An <img loading=lazy> kept outside the DOM until its load event can
    // deadlock: the browser will not fetch it, so the load event never fires.
    img.loading="eager"; img.decoding="async"; img.referrerPolicy="no-referrer";
    img.alt=title+" — species reference photograph, not a local sighting";
    img.addEventListener("load",()=>{
      if(!row.isConnected)return;
      container.replaceChildren(img);
      const credit=row.querySelector(".photo-credit");
      const link=document.createElement("a");
      link.href=photo.sourceUrl; link.target="_blank"; link.rel="noopener noreferrer";
      link.textContent="Photograph: "+photo.creator+" · "+photo.licence+" · source record";
      credit.replaceChildren(link);
      credit.hidden=false;
    },{once:true});
    img.addEventListener("error",()=>{ img.remove(); },{once:true});
    // Register handlers before assigning src; eager fetches can happen
    // without a DOM attachment, while the photo row controls laziness.
    img.src=photo.url;
  }
  const photoQueue=[];
  let photoActive=0;
  function runPhotoQueue() {
    while(photoActive<2 && photoQueue.length) {
      const job=photoQueue.shift();
      if(job.signal.aborted || !job.row.isConnected) continue;
      photoActive++;
      (async()=>{
        try {
          const cached=pickSpeciesPhoto(job.sample,job.taxon.key);
          if(cached) { showSpeciesPhoto(job.row,cached,job.taxon.common); return; }
          // Media are species-wide reference pictures, NOT local observations.
          // Check the media licence itself: occurrence/data licences can differ.
          const params=new URLSearchParams({
            taxonKey:String(job.taxon.key), mediaType:"StillImage",limit:"32",
            occurrenceStatus:"PRESENT"
          });
          const data=await getJson(API+"/occurrence/search?"+params,job.signal);
          if(job.signal.aborted || !job.row.isConnected) return;
          showSpeciesPhoto(job.row,pickSpeciesPhoto(data.results,job.taxon.key),
            job.taxon.common);
        } catch(error) {
          // A missing or unlicensed photograph is an acceptable state.
          if(error.name!=="AbortError") console.info("Species photo unavailable:",job.taxon.common);
        } finally {
          photoActive--; runPhotoQueue();
        }
      })();
    }
  }
  const photoObserver=typeof IntersectionObserver==="function"
    ? new IntersectionObserver(entries=>{
        for(const entry of entries) {
          if(!entry.isIntersecting)continue;
          photoObserver.unobserve(entry.target);
          const task=entry.target._speciesPhotoTask;
          if(task)photoQueue.push(task);
        }
        runPhotoQueue();
      },{root:$("field-guide"),rootMargin:"160px 0px"})
    : null;
  function queueSpeciesPhoto(row,taxon,sample,signal) {
    const job={row,taxon,sample,signal};
    if(photoObserver) {
      row._speciesPhotoTask=job;
      photoObserver.observe(row);
    } else {
      photoQueue.push(job);runPhotoQueue();
    }
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
        const row=createSpeciesRow(labels[j],chunk[j].count,false);
        container.append(row);
        if(i+j<8)queueSpeciesPhoto(row,labels[j],sample,signal);
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
      const item = document.createElement("button");
      item.type = "button";
      item.className = "season-month" + (state.month === month ? " current" : "");
      item.title = name + ": " + nf.format(count) + " published observation records. Choose " + name + ".";
      item.setAttribute("aria-label", name + ": " + nf.format(count) +
        " published records. Show " + name + " observations.");
      item.setAttribute("aria-pressed", String(state.month === month));
      const value = document.createElement("span"); value.className = "chart-value";
      value.textContent = new Intl.NumberFormat("en-GB", {
        notation: "compact", maximumFractionDigits: 0
      }).format(count);
      const column = document.createElement("span"); column.className = "chart-column";
      const fill = document.createElement("span"); fill.className = "chart-fill";
      fill.style.height = count > 0 ? Math.max(3, 100 * count / max) + "%" : "0";
      column.append(fill);
      const short = document.createElement("span"); short.className = "abbr";
      short.textContent = name.slice(0, 3);
      item.append(value, column, short);
      item.addEventListener("click", () => chooseMonth(month));
      bars.append(item);
    });
    bars.setAttribute("aria-label", "Monthly published observation counts for " +
      speciesLabel + ". Choose a month to explore it. " + accessible.join("; "));
    $("season-title").textContent = speciesLabel + " through the year";
    $("season-note").textContent =
      "Records by observation month across 2021–" + (state.includeCurrent ? "2026" : "2025") +
      ". Taller bars mean more published records, not a higher chance of seeing the species. Select a month to explore it.";
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
    photoQueue.length=0;
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
  buildMonthNavigation();
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
