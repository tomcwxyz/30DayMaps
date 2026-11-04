/* True static export of the same NBN Atlas GeoJSON layers used by app.js.
 * This page does not generate, infer, smooth or reposition any observations.
 */
(() => {
  'use strict';
  const CONFIG = Object.freeze({
    bog: {
      label: 'Bog mosses',
      subtitle: 'Clusters of recorded bog moss observations in the UK',
      group: 'bog',
      colour: '#396e72',
      profile: 'bog-focus'
    },
    stone: {
      label: 'Stone & wall mosses',
      subtitle: 'Clusters of recorded stone and wall moss observations in the UK',
      group: 'stone',
      colour: '#746c46',
      profile: 'stone-focus'
    },
    all: {
      label: 'All eight recorded together',
      subtitle: '10 km squares with all eight selected moss species recorded',
      group: 'all',
      colour: '#285d42',
      profile: 'all-focus'
    }
  });
  const params = new URLSearchParams(window.location.search);
  const view = params.get('view') || 'bog';
  const config = CONFIG[view];

  function readyFailure(message) {
    const reason = message instanceof Error ? message.message : String(message);
    console.error('Moss poster failed:', reason);
    document.querySelector('#subtitle').textContent = 'Unable to render verified NBN Atlas data';
    window.__mossPoster = { ready: false, error: reason };
  }
  if (!config || typeof window.L === 'undefined') {
    readyFailure('Unknown view or Leaflet library did not load');
    return;
  }
  document.title = config.label + ' · real NBN moss map · Day 04';
  document.querySelector('#title').textContent = config.label;
  document.querySelector('#subtitle').textContent = config.subtitle;
  const map = L.map('map', {
    zoomControl: false,
    attributionControl: false,
    scrollWheelZoom: false,
    doubleClickZoom: false,
    dragging: false,
    touchZoom: false,
    boxZoom: false,
    keyboard: false,
    preferCanvas: false,
    fadeAnimation: false,
    zoomAnimation: false
  });
  // Precisely the same basemap and subdued colour treatment as the live map.
  let loadedTiles = 0;
  const tiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 16, minZoom: 4, attribution: '© OpenStreetMap contributors',
    updateWhenIdle: true, keepBuffer: 1
  }).on('tileload', () => { loadedTiles++; }).addTo(map);

  map.createPane('source-squares');
  map.getPane('source-squares').style.zIndex = '405';
  map.createPane('record-clusters');
  map.getPane('record-clusters').style.zIndex = '420';
  const clusterColour = config.colour;
  const featureCollection = features => ({ type: 'FeatureCollection', features });
  const fmt = n => Number(n).toLocaleString('en-GB');

  function addLegendItem(label, colour) {
    const item = document.createElement('span');
    item.className = 'key-item';
    const marker = document.createElement('span');
    marker.className = 'key-swatch';
    marker.style.background = colour;
    const text = document.createElement('span');
    text.textContent = label;
    item.append(marker, text);
    document.querySelector('#legend').append(item);
  }

  async function loadJson(file) {
    const response = await fetch('./' + file, { cache: 'no-store' });
    if (!response.ok) throw new Error('Missing actual data: ' + file + ' (' + response.status + ')');
    return response.json();
  }

  Promise.all([
    loadJson('moss.geojson'),
    loadJson('moss-clusters.geojson'),
    loadJson('moss-manifest.json'),
    loadJson('moss-clusters-manifest.json')
  ]).then(([source, clusters, provenance, report]) => {
    if (source?.type !== 'FeatureCollection' ||
        clusters?.type !== 'FeatureCollection' ||
        !Array.isArray(source.features) ||
        !Array.isArray(clusters.features) ||
        !report?.profiles?.[config.profile]) {
      throw new Error('Source or derived GeoJSON is incomplete');
    }

    const features = clusters.features.filter(feature =>
      feature.properties.group === config.group &&
      feature.properties.level === 'focus');
    const expected = report.profiles[config.profile];
    if (!features.length || features.length !== expected.clusters ||
        source.features.length !== report.input_grids) {
      throw new Error('Actual data and its cluster manifest are inconsistent');
    }
    const profileRefs = new Set(features.flatMap(f => f.properties.grid_refs));
    if (profileRefs.size !== expected.cells_in_clusters) {
      throw new Error('Cluster grid membership mismatch');
    }

    let allEightCount = 0;
    if (view === 'all') {
      const taxonNames = provenance.species.map(s => s.name);
      const allEightFeatures = source.features.filter(feature =>
        taxonNames.every(name => Number(feature.properties.species?.[name] || 0) > 0));
      allEightCount = allEightFeatures.length;
      if (allEightCount < expected.cells_in_clusters) {
        throw new Error('There cannot be more clustered squares than eight-species squares');
      }
      // Exactly as the interactive map: gold squares, with dark-green
      // connected-cluster polygons drawn on top.
      L.geoJSON(featureCollection(allEightFeatures), {
        pane: 'source-squares',
        renderer: L.svg({ pane: 'source-squares', padding: 0.4 }),
        style: () => ({
          pane: 'source-squares', color: '#aa8150', weight: 0.55,
          opacity: 0.87, fillColor: '#efc987', fillOpacity: 0.75
        })
      }).addTo(map);
      addLegendItem('Connected clusters (3+ neighbouring squares)', clusterColour);
      addLegendItem('Other squares with all eight species', '#efc987');
      document.querySelector('#note').textContent =
        fmt(allEightCount) + ' squares have all eight selected mosses recorded; ' +
        fmt(expected.cells_in_clusters) + ' belong to ' + fmt(features.length) +
        ' clusters. The remaining ' + fmt(allEightCount - expected.cells_in_clusters) +
        ' are outside those clusters.';
    } else {
      addLegendItem('Neighbouring 10 km squares meeting the focused clustering threshold', clusterColour);
      document.querySelector('#note').textContent =
        fmt(features.length) + ' clusters spanning ' + fmt(expected.cells_in_clusters) +
        ' qualifying 10 km squares. These are concentrations of recordings, not moss-covered habitats.';
    }

    // Use original, derived, smoothed cluster geometries and original colours.
    // No generated hotspots, approximate coordinates or raster interpolation.
    L.geoJSON(featureCollection(features), {
      pane: 'record-clusters',
      renderer: L.svg({ pane: 'record-clusters', padding: 0.4 }),
      style: () => ({
        pane: 'record-clusters',
        className: 'cluster-shape',
        color: clusterColour,
        weight: 1,
        opacity: 0.85,
        fillColor: clusterColour,
        fillOpacity: 0.6,
        lineJoin: 'round',
        lineCap: 'round'
      })
    }).addTo(map);

    // Fixed identical map framing across all three posters. The entire UK
    // (including Shetland and Northern Ireland) is included for comparison.
    map.invalidateSize();
    map.fitBounds([[49.8, -8.8], [60.9, 2.2]], {
      animate: false, padding: [26, 26]
    });
    const reportReady = {
      ready: true,
      view,
      clusterCount: features.length,
      clusterSquares: profileRefs.size,
      eightSpeciesSquares: allEightCount,
      sourceSquares: source.features.length,
      sourceTimestamp: provenance.generated_at,
      profile: config.profile,
      screenshotPixels: [3507, 4962]
    };
    window.__mossPoster = reportReady;
    document.documentElement.dataset.posterReady = 'true';
    console.info('Verified real NBN moss poster:', reportReady);
  }).catch(readyFailure);
})();
