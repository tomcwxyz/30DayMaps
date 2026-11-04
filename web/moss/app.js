/* Day 04 — observed moss, co-occurrence and spatial clusters; no inferred absences. */
(() => {
  'use strict';

  const HOME = [54.7, -3.5];
  const GROUPS = {
    coverage: { label: 'All recorded moss', colour: '#3c6c47' },
    all: { label: 'All 8 recorded together', colour: '#285d42' },
    bog: { label: 'Bog mosses', colour: '#396e72' },
    woodland: { label: 'Woodland mosses', colour: '#396648' },
    grassland: { label: 'Grassland moss', colour: '#668753' },
    stone: { label: 'Stone & walls mosses', colour: '#746c46' }
  };
  const SPECIES_COLOURS = [
    '#357f84', '#765d9a', '#3e6841', '#6d9c50',
    '#b9913c', '#b87853', '#ba675e', '#98547d'
  ];
  // A deliberately ordered, eight-step sequential scale: one to eight recorded taxa.
  const RICHNESS_COLOURS = [
    '#dcebb9', '#c3dc99', '#a8ca7e', '#89b46c',
    '#649859', '#48834e', '#2d6846', '#174c38'
  ];
  const escapeHTML = value => String(value).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
  const format = n => Number(n).toLocaleString('en-GB');
  const el = id => document.getElementById(id);
  const map = L.map('map', { scrollWheelZoom: false, zoomControl: false, preferCanvas: true })
    .setView(HOME, 5);
  L.control.zoom({ position: 'topright' }).addTo(map);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors', maxZoom: 16
  }).addTo(map);

  for (const [name, order] of [['coverage', 405], ['evidence', 412], ['clusters', 420]]) {
    map.createPane(name);
    map.getPane(name).style.zIndex = String(order);
  }
  const coverageRenderer = L.canvas({ pane: 'coverage', padding: 0.5 });
  const clusterRenderer = L.svg({ pane: 'clusters', padding: 0.5 });
  const evidenceRenderer = L.canvas({ pane: 'evidence', padding: 0.5 });

  const state = {
    group: 'coverage', level: 'focus', colour: 'leading', grid: false,
    source: null, clusters: null, report: null, attribution: null,
    coverageLayer: null, clusterLayer: null, evidenceLayer: null,
    selectedId: null, byId: new Map(), species: new Map(), colourBySpecies: new Map()
  };

  function sourceSpecies() {
    return state.attribution?.species || [];
  }
  function speciesLabel(name) {
    return state.species.get(name)?.common || name;
  }
  function isCoverage() {
    return state.group === 'coverage';
  }
  function isAllEight() {
    return state.group === 'all';
  }
  function groupSpecies() {
    if (isCoverage() || isAllEight()) return sourceSpecies().map(s => s.name);
    return sourceSpecies()
      .filter(s => state.group === 'stone'
        ? s.type === 'Stone and walls' : s.type.toLowerCase() === state.group)
      .map(s => s.name);
  }
  function groupObservations(properties, names = groupSpecies()) {
    return names.reduce((total, name) => total + Number(properties.species?.[name] || 0), 0);
  }

  // A square can have many taxa; the categorical colour is the one with
  // the highest number of *recorded observations*, never a claim of dominance.
  function leadingSpecies(properties) {
    const entries = Object.entries(properties.species || {});
    entries.sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
    return entries.length ? entries[0][0] : null;
  }
  function squareColour(feature) {
    const p = feature.properties;
    if (state.colour === 'richness') {
      const count = Object.keys(p.species || {}).filter(k => p.species[k] > 0).length;
      return RICHNESS_COLOURS[Math.min(RICHNESS_COLOURS.length - 1, Math.max(0, count - 1))];
    }
    return state.colourBySpecies.get(leadingSpecies(p)) || '#7a9880';
  }

  function addLegendItem(label, colour) {
    const item = document.createElement('div');
    item.className = 'legend-item';
    const swatch = document.createElement('span');
    swatch.className = 'legend-swatch';
    swatch.style.backgroundColor = colour;
    const name = document.createElement('span');
    name.textContent = label;
    item.append(swatch, name);
    el('colour-legend').append(item);
  }

  function drawLegend() {
    const legend = el('colour-legend');
    legend.replaceChildren();
    if (state.colour === 'leading') {
      el('colour-explain').textContent =
        'Colour shows which of the eight species has the most recorded observations in that square. Other species may also occur there.';
      sourceSpecies().forEach(s => addLegendItem(s.common, state.colourBySpecies.get(s.name)));
    } else {
      el('colour-explain').textContent =
        'Colour shows the number of different selected species recorded in each square, from one to eight.';
      RICHNESS_COLOURS.forEach((colour, index) =>
        addLegendItem((index + 1) + ' of 8 species', colour));
    }
  }

  function showSquare(feature) {
    const p = feature.properties;
    const entries = Object.entries(p.species).sort((a, b) => b[1] - a[1]);
    el('details').innerHTML =
      '<span class="detail-title">' + escapeHTML(p.grid) + '</span>' +
      '<p class="detail-metric">10 km source square</p>' +
      '<p>' + format(entries.length) + ' of eight selected species recorded · ' +
      format(p.records) + ' observation records</p>' +
      '<ul>' + entries.map(([name, total]) =>
        '<li>' + escapeHTML(speciesLabel(name)) + ' — ' + format(total) + '</li>'
      ).join('') + '</ul>' +
      '<p class="detail-note">A record is not a moss individual or a measure of abundance. Locations are imprecise to 10 km.</p>';
    state.selectedId = null;
    if (state.clusterLayer) {
      state.clusterLayer.eachLayer(layer => layer.setStyle(clusterStyle(layer.feature)));
    }
  }

  function showCluster(feature) {
    const p = feature.properties;
    state.selectedId = p.id;
    const members = Object.entries(p.species).sort((a, b) => b[1] - a[1]);
    el('details').innerHTML =
      '<span class="detail-title">Gathering ' + format(p.rank) + '</span>' +
      '<p class="detail-metric">' + format(p.cell_count) + ' neighbouring 10 km squares</p>' +
      '<p>' + format(p.observations) + ' observations across ' +
      format(p.species_count) + ' selected moss species.</p>' +
      '<strong>Recorded species</strong><ul>' +
      members.map(([name, total]) =>
        '<li>' + escapeHTML(speciesLabel(name)) +
        ' <span class="hint">(' + escapeHTML(name) + ')</span> — ' +
        format(total) + '</li>').join('') +
      '</ul><p class="detail-note">Source grids: ' +
      escapeHTML(p.grid_refs.slice(0, 10).join(', ')) +
      (p.grid_refs.length > 10 ? ' and ' + format(p.grid_refs.length - 10) + ' more' : '') +
      '. These are recording clusters, not physical moss cover.</p>';
    if (state.clusterLayer) {
      state.clusterLayer.eachLayer(layer => layer.setStyle(clusterStyle(layer.feature)));
    }
  }

  function clusterStyle(feature, hovered = false) {
    const chosen = state.selectedId === feature.properties.id;
    return {
      pane: 'clusters', renderer: clusterRenderer, className: 'cluster-shape',
      color: chosen ? '#172f24' : GROUPS[state.group].colour,
      weight: chosen ? 2.7 : hovered ? 2.2 : 1,
      opacity: chosen ? 1 : 0.85,
      fillColor: GROUPS[state.group].colour,
      fillOpacity: chosen ? 0.82 : hovered ? 0.72 : 0.6,
      lineCap: 'round', lineJoin: 'round'
    };
  }

  function profileFeatures() {
    if (!state.clusters || isCoverage()) return [];
    // The co-occurrence comparison must *always* require all eight.
    // Its old "broader" setting required only seven, which contradicted
    // the earlier "All eight" wording.
    const level = isAllEight() ? 'focus' : state.level;
    return state.clusters.features.filter(feature =>
      feature.properties.group === state.group && feature.properties.level === level);
  }

  function removeLayer(name) {
    if (state[name]) map.removeLayer(state[name]);
    state[name] = null;
  }

  function renderCoverage() {
    removeLayer('coverageLayer');
    if (!state.source || (!isCoverage() && !isAllEight())) return;
    const overview = isCoverage();
    const targetCount = sourceSpecies().length;
    state.coverageLayer = L.geoJSON(state.source, {
      pane: 'coverage', renderer: coverageRenderer,
      filter: feature => overview ||
        Object.keys(feature.properties.species).filter(k => feature.properties.species[k] > 0).length === targetCount,
      style: feature => ({
        pane: 'coverage', renderer: coverageRenderer,
        color: overview ? '#537965' : '#aa8150',
        weight: overview ? 0.2 : 0.55,
        opacity: overview ? 0.6 : 0.87,
        fillColor: overview ? squareColour(feature) : '#efc987',
        fillOpacity: overview ? 0.89 : 0.75
      }),
      onEachFeature: (feature, layer) => {
        const p = feature.properties;
        const rich = Object.keys(p.species).length;
        layer.bindTooltip(
          escapeHTML(p.grid) + ' · ' + rich + ' of 8 species recorded',
          { sticky: true, className: 'moss-tooltip' });
        layer.on('click', () => showSquare(feature));
      }
    }).addTo(map);
  }

  function renderClusters(features) {
    removeLayer('clusterLayer');
    state.byId.clear();
    if (!features.length) return;
    state.clusterLayer = L.geoJSON(
      { type: 'FeatureCollection', features }, {
        pane: 'clusters', renderer: clusterRenderer,
        style: feature => clusterStyle(feature),
        onEachFeature: (feature, layer) => {
          const p = feature.properties;
          state.byId.set(p.id, layer);
          layer.bindTooltip(
            '<strong>Gathering ' + format(p.rank) + '</strong><br>' +
            format(p.cell_count) + ' recorded 10 km squares<br>' +
            format(p.species_count) + ' selected moss species',
            { sticky: true, className: 'moss-tooltip' });
          layer.on('mouseover', () => layer.setStyle(clusterStyle(feature, true)));
          layer.on('mouseout', () => layer.setStyle(clusterStyle(feature)));
          layer.on('click', () => showCluster(feature));
        }
      }
    ).addTo(map);
  }

  function showRanked(features) {
    const container = el('ranked');
    container.replaceChildren();
    if (!features.length) {
      const message = document.createElement('p');
      message.className = 'hint';
      message.textContent = 'No connected clusters meet these thresholds.';
      container.append(message);
      return;
    }
    features.slice(0, 5).forEach((feature, i) => {
      const p = feature.properties;
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'rank-item';
      const rank = document.createElement('span');
      rank.className = 'rank-n';
      rank.textContent = String(i + 1).padStart(2, '0');
      const copy = document.createElement('span');
      copy.className = 'rank-copy';
      copy.textContent = 'Gathering ' + p.rank;
      const sub = document.createElement('small');
      sub.textContent = format(p.cell_count) + ' recorded squares · ' +
        format(p.species_count) + ' species';
      copy.append(sub);
      button.append(rank, copy);
      button.addEventListener('click', () => {
        const layer = state.byId.get(p.id);
        if (!layer) return;
        showCluster(feature);
        map.fitBounds(layer.getBounds(), { padding: [35, 35], maxZoom: 9 });
      });
      container.append(button);
    });
  }

  function thresholdDescription(profile) {
    if (!profile) return '';
    const species = groupSpecies().length;
    const count = profile.min_species === species
      ? 'all ' + species + ' selected species'
      : 'at least ' + profile.min_species + ' of ' + species + ' selected species';
    const records = profile.min_records
      ? ' and at least ' + format(profile.min_records) + ' combined observation records'
      : '';
    return 'A cluster is shown only when at least three neighbouring 10 km squares each contain ' +
      count + records + '. These are recording concentrations, not habitat or moss abundance.';
  }

  function renderEvidence() {
    removeLayer('evidenceLayer');
    // The all-eight view already displays ALL of its eligible source squares
    // in gold; the overview already shows the full source.
    if (!state.grid || !state.source || isCoverage() || isAllEight()) return;
    const names = groupSpecies();
    const clusteredGrids = new Set(profileFeatures().flatMap(f => f.properties.grid_refs));
    state.evidenceLayer = L.geoJSON(state.source, {
      pane: 'evidence', renderer: evidenceRenderer,
      filter: feature => groupObservations(feature.properties, names) > 0,
      style: feature => {
        const clustered = clusteredGrids.has(feature.properties.grid);
        return {
          pane: 'evidence', renderer: evidenceRenderer,
          color: clustered ? '#547055' : '#b08f5c',
          weight: clustered ? 0.45 : 0.65,
          opacity: clustered ? 0.35 : 0.75,
          fillColor: clustered ? '#ffffff' : '#d5bb86',
          fillOpacity: clustered ? 0.03 : 0.40
        };
      },
      onEachFeature: (feature, layer) => {
        const p = feature.properties;
        const number = names.filter(name => Number(p.species?.[name] || 0) > 0).length;
        const records = groupObservations(p, names);
        layer.bindTooltip(
          escapeHTML(p.grid) + ' · ' + number + ' of ' + names.length +
          ' selected species recorded · ' + format(records) + ' records',
          { sticky: true, className: 'moss-tooltip' });
        layer.on('click', () => showSquare(feature));
      }
    }).addTo(map);
  }

  function updateControls() {
    document.querySelectorAll('[data-group]').forEach(button => {
      const selected = button.dataset.group === state.group;
      button.setAttribute('aria-pressed', String(selected));
      button.classList.toggle('selected', selected);
    });
    document.querySelectorAll('[data-level]').forEach(button =>
      button.setAttribute('aria-pressed', String(button.dataset.level === state.level)));
    document.querySelectorAll('[data-colour]').forEach(button =>
      button.setAttribute('aria-pressed', String(button.dataset.colour === state.colour)));
    el('colour-section').hidden = !isCoverage();
    el('strength-section').hidden = isCoverage() || isAllEight();
    el('evidence-section').hidden = isCoverage() || isAllEight();
    el('cluster-explainer').hidden = isCoverage() || isAllEight();
    el('ranked-section').hidden = isCoverage();
  }

  function updateText(features) {
    if (isCoverage()) {
      const countGrids = state.source.features.length;
      el('status').textContent = format(countGrids) +
        ' 10 km squares with at least one of the eight selected moss species recorded';
      el('details').textContent =
        'Choose any coloured square to see every one of the eight species recorded there.';
      el('map-note').innerHTML =
        '<span class="key-dot"></span> Every coloured square has at least one recorded species <span class="divider-dot">·</span> 10 km resolution';
      return;
    }
    if (isAllEight()) {
      const allEight = state.source.features.filter(f =>
        Object.keys(f.properties.species).length === sourceSpecies().length).length;
      const linked = state.report.profiles['all-focus'].cells_in_clusters;
      el('status').textContent = format(allEight) +
        ' squares with all 8 species recorded · ' +
        format(features.length) + ' clusters containing ' + format(linked) +
        ' squares · ' + format(allEight - linked) + ' outside clusters';
      el('details').textContent =
        'Dark green areas connect at least three neighbouring squares with all eight species recorded. The pale gold squares also contain all eight, but are not part of a qualifying cluster.';
      el('map-note').innerHTML =
        '<span class="key-dot"></span> Dark green: connected all-eight clusters · Gold: all-eight source squares';
      return;
    }
    const profile = state.report.profiles[state.group + '-' + state.level];
    const names = groupSpecies();
    const recordedSquares = state.source.features.filter(feature =>
      groupObservations(feature.properties, names) > 0).length;
    const withoutShownCluster = recordedSquares - profile.cells_in_clusters;
    el('threshold').textContent = thresholdDescription(profile);
    el('status').textContent = format(features.length) +
      ' concentrations of ' + GROUPS[state.group].label.toLowerCase() +
      ' recordings · ' + format(profile.cells_in_clusters) +
      ' clustered squares of ' + format(recordedSquares) +
      ' squares with sightings';
    el('evidence-description').textContent =
      format(withoutShownCluster) + ' recorded 10 km squares for this group are ' +
      'outside the currently highlighted clusters. Reveal them as muted squares ' +
      'to inspect the underlying observations.';
    el('details').textContent =
      'Select a highlighted gathering, or reveal source squares to inspect sightings outside the clusters.';
    el('map-note').innerHTML =
      '<span class="key-dot"></span> Highlighted = qualifying recording clusters. ' +
      'No highlighted area does <strong>not</strong> mean no moss sightings.';
  }

  function refresh() {
    if (!state.source || !state.clusters || !state.report || !state.attribution) return;
    state.selectedId = null;
    updateControls();
    const features = profileFeatures();
    renderCoverage();
    renderClusters(features);
    renderEvidence();
    drawLegend();
    showRanked(features);
    updateText(features);
  }

  document.querySelectorAll('[data-group]').forEach(button =>
    button.addEventListener('click', () => {
      state.group = button.dataset.group;
      refresh();
    }));
  document.querySelectorAll('[data-level]').forEach(button =>
    button.addEventListener('click', () => {
      state.level = button.dataset.level;
      refresh();
    }));
  document.querySelectorAll('[data-colour]').forEach(button =>
    button.addEventListener('click', () => {
      state.colour = button.dataset.colour;
      refresh();
    }));
  el('show-grid').addEventListener('change', event => {
    state.grid = event.target.checked;
    renderEvidence();
  });
  el('reset-view').addEventListener('click', () => map.setView(HOME, 5));

  async function readJson(name) {
    const response = await fetch('./' + name);
    if (!response.ok) throw new Error(name + ': HTTP ' + response.status);
    return response.json();
  }

  Promise.all([
    readJson('moss-clusters.geojson'), readJson('moss-clusters-manifest.json'),
    readJson('moss.geojson'), readJson('moss-manifest.json')
  ]).then(([clusters, report, source, attribution]) => {
    if (!clusters?.features?.length || !source?.features?.length ||
        !attribution?.species?.length || !report?.profiles?.['all-focus']) {
      throw new Error('Real NBN Atlas source or derived cluster data unavailable');
    }
    state.clusters = clusters;
    state.source = source;
    state.report = report;
    state.attribution = attribution;
    attribution.species.forEach((s, i) => {
      state.species.set(s.name, s);
      state.colourBySpecies.set(s.name, SPECIES_COLOURS[i % SPECIES_COLOURS.length]);
    });
    refresh();
  }).catch(error => {
    el('status').textContent = 'The verified NBN Atlas map data is unavailable.';
    el('details').textContent = 'No substitute records are shown. Check the GitHub data-generation workflow.';
    el('ranked').replaceChildren();
    console.error('Moss map error:', error);
  });
})();
