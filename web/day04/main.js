import { roosts, conservationLinks } from "./roosts.js";
import { createMap } from "./map.js";
import { createFlock } from "./flock.js";

const map = createMap(document.getElementById("map"), roosts);
const filter = document.getElementById("siteFilter");
const radius = document.getElementById("radius");
const radiusValue = document.getElementById("radiusValue");
const siteList = document.getElementById("siteList");
document.getElementById("siteCount").textContent = String(roosts.length);

function updateSites() {
  const phrase = filter.value.trim().toLocaleLowerCase("en-GB");
  const matches = roosts.filter(site => (site.name + " " + site.region).toLocaleLowerCase("en-GB").includes(phrase));
  radiusValue.value = radius.value + " km";
  radiusValue.textContent = radius.value + " km";
  map.update(matches, Number(radius.value));
  siteList.replaceChildren();
  for (const site of matches) {
    const li = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = site.name;
    const region = document.createElement("span");
    region.textContent = site.region;
    button.append(region);
    button.addEventListener("click", () => map.focusSite(site));
    li.append(button);
    siteList.append(li);
  }
  if (!matches.length) {
    const item = document.createElement("li");
    item.textContent = "No published examples match that search.";
    siteList.append(item);
  }
}
filter.addEventListener("input", updateSites);
radius.addEventListener("input", updateSites);
updateSites();

const actionList = document.getElementById("conservationLinks");
for (let i = 0; i < conservationLinks.length; i++) {
  const action = conservationLinks[i];
  const article = document.createElement("article");
  article.className = "action-card";
  const number = document.createElement("span"); number.className = "mono"; number.textContent = String(i + 1).padStart(2, "0");
  const heading = document.createElement("h3"); heading.textContent = action.label;
  const detail = document.createElement("p"); detail.textContent = action.detail;
  const link = document.createElement("a"); link.href = action.href; link.target = "_blank";
  link.rel = "noopener noreferrer"; link.textContent = "Find out how ↗";
  article.append(number, heading, detail, link); actionList.append(article);
}

const slider = document.getElementById("duskProgress");
const playPause = document.getElementById("playPause");
const phaseName = document.getElementById("phaseName");
const phaseDescription = document.getElementById("phaseDescription");
const output = document.getElementById("duskValue");
const flock = createFlock(document.getElementById("flock"), ({ progress, playing, title, description }) => {
  if (document.activeElement !== slider) slider.value = progress;
  output.textContent = progress + "%";
  phaseName.textContent = title;
  phaseDescription.textContent = description;
  playPause.textContent = playing ? "Pause motion" : "Play motion";
  playPause.setAttribute("aria-pressed", String(!playing));
});
slider.addEventListener("input", () => flock.setProgress(slider.value));
slider.addEventListener("change", () => flock.setProgress(slider.value));
playPause.addEventListener("click", () => flock.setPlaying(!flock.playing));
document.getElementById("restart").addEventListener("click", () => flock.replay());
