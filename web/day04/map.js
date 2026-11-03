import { sources } from "./roosts.js";
import { clusterNearby } from "./clusters.js";

function anchor(href, text) {
  const a = document.createElement("a");
  a.href = href;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  a.textContent = text;
  return a;
}
function popupForSites(sites) {
  const node = document.createElement("div");
  node.className = "roost-popup";
  const title = document.createElement("strong");
  title.textContent = sites.length === 1 ? sites[0].name : sites.length + " published example sites";
  node.append(title);
  const list = document.createElement("ul");
  for (const site of sites) {
    const item = document.createElement("li");
    const name = document.createElement("span");
    name.textContent = site.name + " · " + site.region + " — ";
    item.append(name, anchor(sources[site.source], "source ↗"));
    list.append(item);
  }
  node.append(list);
  const qualifier = document.createElement("p");
  qualifier.textContent = "Indicative public site locations; no live roost status or bird-count information.";
  node.append(qualifier);
  return node;
}
export function createMap(element, sites) {
  if (!window.L) {
    document.getElementById("mapFallback").hidden = false;
    return { update() {}, focusSite() {} };
  }
  const map = window.L.map(element, { scrollWheelZoom: false, zoomControl: true, preferCanvas: true }).setView([53.22, -2.7], 6);
  window.L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
    maxZoom: 18
  }).addTo(map);
  const group = window.L.layerGroup().addTo(map);
  let current = sites;
  let radius = 65;
  function update(nextSites = current, nextRadius = radius) {
    current = nextSites;
    radius = nextRadius;
    group.clearLayers();
    for (const cluster of clusterNearby(current, radius)) {
      const grouped = cluster.sites.length > 1;
      const circle = window.L.circleMarker([cluster.lat, cluster.lon], {
        radius: grouped ? Math.min(28, 12 + Math.sqrt(cluster.sites.length) * 3) : 7,
        color: grouped ? "#ffd7a2" : "#f8dbad",
        weight: grouped ? 1.6 : 1.3,
        fillColor: grouped ? "#e69c5e" : "#ffc686",
        fillOpacity: grouped ? .79 : .98,
        className: "site-marker"
      }).addTo(group);
      if (grouped) {
        circle.bindTooltip(String(cluster.sites.length), { permanent: true, direction: "center", className: "cluster-count", opacity: 1 });
      }
      circle.bindPopup(popupForSites(cluster.sites), { minWidth: 220, maxWidth: 300 });
    }
  }
  function focusSite(site) {
    map.setView([site.lat, site.lon], 10, { animate: true });
    const marker = window.L.circleMarker([site.lat, site.lon], { radius: 12, color: "#ffffff", weight: 2, fillColor: "#e9a571", fillOpacity: 1 }).addTo(map);
    marker.bindPopup(popupForSites([site])).openPopup();
    map.once("popupclose", () => map.removeLayer(marker));
  }
  update(sites, radius);
  return { update, focusSite };
}
