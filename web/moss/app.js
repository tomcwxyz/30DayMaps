/* Day 04 — UK moss observation clusters. Vanilla Leaflet; no fabricated data. */
(() => {
  'use strict';

  const MAP_HOME = [54.7, -3.5];
  const GROUPS = {
    all: { label: 'All eight species', colour: '#2c7150' },
    bog: { label: 'Bog mosses', colour: '#396e72' },
    woodland: { label: 'Woodland mosses', colour: '#396648' },
    grassland: { label: 'Grassland moss', colour: '#668753' },
    stone: { label: 'Stone & walls mosses', colour: '#746c46' }
  };
  const LEVELS = { broad: 'Broader', focus: 'Focused', strong: 'Strongest' };
  const html = value => String(value).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
  const count = n => Number(n).toLocaleString('en-GB');
  const byId = id => document.getElementById(id);
  const status = byId('status');
  const details = byId('details');
  const ranked = byId('ranked');

  const map = L.map('map', { scrollWheelZoom: false, zoomControl: false, preferCanvas: true })
    .setView(MAP_HOME, 5);
  L.control.zoom({ position: 'topright' }).addTo(map);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors',
    maxZoom: 16
  }).addTo(map);
  map.createPane('clusters');
  map.getPane('clusters').style.zIndex = 410;
  map.createPane('evidence');
  map.getPane('evidence').style.zIndex = 420;

  const state = {
    group: 'all', level: 'focus', grid: false,
    clusters: null, source: null, attribution: null, report: null,
    layer: null, evidence: null, selected: null, layerById: new Map(),
    localeSpecies: new Map()
  };
  const clusterRenderer = L.svg({ pane: 'clusters', padding: 0.5 });
  const evidenceRenderer = L.canvas({ pane: 'evidence', padding: 0.5 });

  function profileFeatures() {
    if (!state.clusters) return [];
    return state.clusters.features.filter(f =>
      f.properties.group === state.group && f.properties.level === state.level);
  }

  function styleCluster(feature, emphasised = false) {
    const p = feature.properties;
    const selected = state.selected === p.id;
    return {
      pane: 'clusters', renderer: clusterRenderer, className: 'cluster-shape',
      color: selected ? '#122c1f' : GROUPS[state.group].colour,
      weight: selected ? 2.6 : (emphasised ? 2.2 : 1),
      opacity: selected ? 1 : 0.82,
      fillColor: GROUPS[state.group].colour,
      fillOpacity: selected ? 0.78 : (emphasised ? 0.72 : 0.58),
      lineCap: 'round', lineJoin: 'round'
    };
  }

  function getMeta(name) {
    return state.localeSpecies.get(name)?.common || name;
  }

  function showCluster(feature) {
    const p = feature.properties;
    state.selected = p.id;
    const names = Object.entries(p.species)
      .sort((a, b) => b[1] - a[1]);
    details.innerHTML =
      '<span class="detail-title">Gathering ' + count(p.rank) + '</span>' +
      '<p class="detail-metric">' + count(p.cell_count) + ' neighbouring 10 km squares</p>' +
      '<p>' + count(p.observations) + ' recorded observations across ' +
      count(p.species_count) + ' selected moss species.</p>' +
      '<strong>Recorded species</strong><ul>' +
      names.map(([name, value]) => '<li>' + html(getMeta(name)) +
        ' <span class="hint">(' + html(name) + ')</span> — ' + count(value) + '</li>').join('') +
      '</ul><p class="detail-note">Source grids: ' +
      html(p.grid_refs.slice(0, 10).join(', ')) +
      (p.grid_refs.length > 10 ? ' and ' + count(p.grid_refs.length - 10) + ' more' : '') +
      '. Counts reflect recording activity, not moss abundance.</p>';
    if (state.layer) {
      state.layer.eachLayer(layer => {
        layer.setStyle(styleCluster(layer.feature));
      });
    }
  }

  function showSquare(feature) {
    const p = feature.properties;
    const entries = Object.entries(p.species).sort((a, b) => b[1] - a[1]);
    details.innerHTML = '<span class="detail-title">' + html(p.grid) + '</span>' +
      '<p class="detail-metric">Original 10 km source square</p>' +
      '<p>' + count(p.richness) + ' of the eight species recorded · ' +
      count(p.records) + ' observations</p><ul>' +
      entries.map(([name, value]) => '<li>' + html(getMeta(name)) +
        ' — ' + count(value) + '</li>').join('') + '</ul>' +
      '<p class="detail-note">This square is evidence, not a point location or a survey of all moss.</p>';
    state.selected = null;
    if (state.layer) state.layer.eachLayer(l => l.setStyle(styleCluster(l.feature)));
  }

  function showRanked(features) {
    ranked.replaceChildren();
    if (!features.length) {
      const msg = document.createElement('p');
      msg.className = 'hint';
      msg.textContent = 'No clusters meet these thresholds.';
      ranked.append(msg);
      return;
    }
    features.slice(0, 5).forEach((feature, index) => {
      const p = feature.properties;
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'rank-item';
      const n = document.createElement('span');
      n.className = 'rank-n';
      n.textContent = String(index + 1).padStart(2, '0');
      const desc = document.createElement('span');
      desc.className = 'rank-copy';
      desc.textContent = 'Gathering ' + p.rank;
      const sub = document.createElement('small');
      sub.textContent = count(p.cell_count) + ' recorded squares · ' +
        count(p.species_count) + ' selected species';
      desc.append(sub);
      btn.append(n, desc);
      btn.addEventListener('click', () => {
        const layer = state.layerById.get(p.id);
        if (layer) {
          showCluster(feature);
          map.fitBounds(layer.getBounds(), { padding: [35, 35], maxZoom: 9 });
        }
      });
      ranked.append(btn);
    });
  }

  function updateThreshold(profile) {
    if (!profile) return;
    const minSp = profile.min_species;
    const minRe = profile.min_records;
    const total = (state.attribution?.species || []).filter(s => {
      if (state.group === 'all') return true;
      return (state.group === 'stone' ? s.type === 'Stone and walls'
        : s.type.toLowerCase() === state.group);
    }).length;
    const records = minRe
      ? ' and at least ' + count(minRe) + ' observations'
      : '';
    byId('threshold').textContent =
      'At least ' + minSp + ' of ' + total + ' selected species' +
      records + ' per square, with at least three touching squares per cluster.';
  }

  function refreshEvidence() {
    if (state.evidence) {
      map.removeLayer(state.evidence);
      state.evidence = null;
    }
    if (!state.grid || !state.source) return;
    const selected = new Set(
      profileFeatures().flatMap(feature => feature.properties.grid_refs));
    state.evidence = L.geoJSON(state.source, {
      pane: 'evidence', renderer: evidenceRenderer,
      style: feature => {
        const active = selected.has(feature.properties.grid);
        return {
          pane: 'evidence', renderer: evidenceRenderer,
          color: active ? '#395743' : '#8f9e8d',
          weight: active ? 0.8 : 0.42,
          opacity: active ? 0.77 : 0.43,
          fillColor: '#fffff3', fillOpacity: active ? 0.09 : 0.02
        };
      },
      onEachFeature: (f, layer) => {
        layer.bindTooltip(html(f.properties.grid) + ' · original 10 km grid',
          { sticky: true, className: 'moss-tooltip' });
        layer.on('click', () => showSquare(f));
      }
    }).addTo(map);
  }

  function refresh() {
    if (!state.clusters || !state.report) return;
    state.selected = null;
    if (state.layer) map.removeLayer(state.layer);
    state.layerById.clear();

    document.querySelectorAll('[data-group]').forEach(button => {
      const chosen = button.dataset.group === state.group;
      button.setAttribute('aria-pressed', String(chosen));
      button.classList.toggle('selected', chosen);
    });
    document.querySelectorAll('[data-level]').forEach(button =>
      button.setAttribute('aria-pressed', String(button.dataset.level === state.level)));

    const features = profileFeatures();
    state.layer = L.geoJSON(
      { type: 'FeatureCollection', features },
      {
        pane: 'clusters', renderer: clusterRenderer,
        style: f => styleCluster(f),
        onEachFeature: (feature, layer) => {
          const p = feature.properties;
          state.layerById.set(p.id, layer);
          layer.bindTooltip(
            '<strong>Gathering ' + count(p.rank) + '</strong><br>' +
            count(p.cell_count) + ' recorded 10 km squares<br>' +
            count(p.species_count) + ' selected moss species',
            { sticky: true, className: 'moss-tooltip' });
          layer.on('mouseover', () => layer.setStyle(styleCluster(feature, true)));
          layer.on('mouseout', () => layer.setStyle(styleCluster(feature)));
          layer.on('click', () => showCluster(feature));
        }
      }
    ).addTo(map);

    const profile = state.report.profiles[state.group + '-' + state.level];
    updateThreshold(profile);
    status.textContent = count(features.length) + ' ' +
      GROUPS[state.group].label.toLowerCase() + ' clusters · ' +
      count(profile.cells_in_clusters) + ' recorded squares connected';
    details.textContent = 'Select a coloured cluster on the map, or choose a gathering below.';
    showRanked(features);
    refreshEvidence();
  }

  document.querySelectorAll('[data-group]').forEach(btn => {
    btn.addEventListener('click', () => { state.group = btn.dataset.group; refresh(); });
  });
  document.querySelectorAll('[data-level]').forEach(btn => {
    btn.addEventListener('click', () => { state.level = btn.dataset.level; refresh(); });
  });
  byId('show-grid').addEventListener('change', event => {
    state.grid = event.target.checked;
    refreshEvidence();
  });
  byId('reset-view').addEventListener('click', () => map.setView(MAP_HOME, 5));

  async function loadJson(name) {
    const result = await fetch('./' + name);
    if (!result.ok) throw new Error(name + ': HTTP ' + result.status);
    return result.json();
  }

  Promise.all([
    loadJson('moss-clusters.geojson'), loadJson('moss-clusters-manifest.json'),
    loadJson('moss.geojson'), loadJson('moss-manifest.json')
  ]).then(([clusters, report, source, attribution]) => {
    if (!clusters?.features?.length || !source?.features?.length) {
      throw new Error('No real NBN Atlas data is available.');
    }
    state.clusters = clusters;
    state.report = report;
    state.source = source;
    state.attribution = attribution;
    attribution.species.forEach(s => state.localeSpecies.set(s.name, s));
    refresh();
  }).catch(error => {
    status.textContent = 'The real NBN Atlas cluster dataset is not available.';
    details.textContent =
      'No substitute data is shown. Build the dataset with python -m maps.moss_clusters, or inspect the source workflow.';
    ranked.replaceChildren();
    console.error('Moss cluster load:', error);
  });
})();
