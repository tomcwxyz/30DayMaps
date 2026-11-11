(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  let future = true;
  const picture = $("landscape");
  const buttons = {true:$("show-future"),false:$("show-today")};
  function render() {
    picture.src = future ? "./data/2050.png" : "./data/today.png";
    picture.alt = future
      ? "Source-derived North East map showing a hypothetical allocation of half of sampled land to nature-first uses, with true OSM river and former railway geometries."
      : "Measured ESA WorldCover 2021 classification across the North East, with real named river geometries and labelled settlements.";
    $("map-caption").textContent = future
      ? "MODELLED 2050 · The green allocation is hypothetical. Built-up areas are excluded from allocation."
      : "MEASURED 2021 · Downsampled satellite classification, mapped rivers and real town positions. Not a habitat quality assessment.";
    for (const state of [true,false]) buttons[String(state)].setAttribute("aria-pressed",String(future===state));
  }
  for (const state of [true,false]) buttons[String(state)].addEventListener("click",()=>{ future=state;render(); });
  fetch("./data/metrics.json").then(response => {
    if(!response.ok) throw new Error("HTTP "+response.status);
    return response.json();
  }).then(d => {
    if(d.status!=="measured_inputs_modelled_future" || Math.abs(d["2050_nature_first_pct_of_sampled_land"]-50)>.5) throw new Error("Unexpected scenario metadata");
    $("future-share").textContent=d["2050_nature_first_pct_of_sampled_land"].toFixed(1)+"%";
    $("today-area").textContent=d["current_woodland_wetland_km2_approx"].toLocaleString("en-GB");
    $("added-area").textContent=d["modelled_added_km2_approx"].toLocaleString("en-GB");
    $("status").textContent="Computed from WorldCover 2021 and "+d.named_river_ways+
      " named river ways / "+d.former_rail_ways+" former railway ways in OpenStreetMap · "+
      d.resolution_m+" m analysis grid.";
  }).catch(error=>{
    $("status").textContent="Scenario data unavailable: "+error.message+". The map cannot be verified in this browser.";
    $("future-share").textContent="—";
  });
  picture.addEventListener("error",() => {
    $("status").textContent="The generated map image did not load; do not interpret an empty map as geographic evidence.";
  });
  render();
})();