/* Day 08 — source-derived woodland access + deliberately hypothetical alternative */
(() => {
  "use strict";
  const ENDPOINT="https://services2.arcgis.com/mHXjwgl3OARRqqD4/ArcGIS/rest/services/Woods_For_All/FeatureServer/0/query";
  const PLACES={
    newcastle:{label:"Newcastle",lat:54.9783,lng:-1.6178},
    chester:{label:"Chester-le-Street",lat:54.8585,lng:-1.5726},
    durham:{label:"Durham",lat:54.7753,lng:-1.5849},
    bishop:{label:"Bishop Auckland",lat:54.6556,lng:-1.6771},
    hamsterley:{label:"Hamsterley Forest",lat:54.675,lng:-1.859}
  };
  const $=id=>document.getElementById(id);
  const map=L.map("map",{scrollWheelZoom:false,zoomControl:false}).setView([PLACES.durham.lat,PLACES.durham.lng],12);
  L.control.zoom({position:"bottomright"}).addTo(map);
  L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",{
    subdomains:"abcd",maxZoom:18,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>'
  }).addTo(map);
  const woodland=L.geoJSON(null,{style:styleFeature,onEachFeature(feature,layer){
    const p=feature.properties||{};
    const name=p.category||p.ift_ioa||"Mapped woodland";
    const access=p.access||"Unclassified access";
    const node=document.createElement("div");
    const title=document.createElement("b");title.textContent=name;node.append(title);
    const desc=document.createElement("p");desc.textContent=access+" (Forestry Commission Woods for All)";node.append(desc);
    layer.bindPopup(node);
  }}).addTo(map);
  const circle=L.circle([PLACES.durham.lat,PLACES.durham.lng],{
    radius:800,weight:1.5,color:"#294e3d",fillColor:"#5c9370",fillOpacity:.08,dashArray:"5 5"
  }).addTo(map);
  const selected=L.circleMarker([PLACES.durham.lat,PLACES.durham.lng],{
    radius:7,color:"#fff",weight:3,fillColor:"#233f35",fillOpacity:1
  }).addTo(map);
  const whatIfLayer=L.layerGroup().addTo(map);
  let origin=[PLACES.durham.lat,PLACES.durham.lng],label="Durham",features=[],future=false,request=0,controller=null;
  function styleFeature(f){
    const access=(f.properties||{}).access;
    const open=access==="public access";
    return {color:open?"#2d6047":"#ba9970",weight:.6,fillColor:open?"#3a7958":"#d6ba8b",fillOpacity:open?.67:.36};
  }
  function setOrigin(lat,lng,name){
    origin=[lat,lng];label=name||"Selected location";
    selected.setLatLng(origin);circle.setLatLng(origin);
    $("map-title").textContent=label;
    $("map-subtitle").textContent="800 m straight-line radius (illustrative)";
    document.querySelectorAll("[data-place]").forEach(b=>b.classList.toggle("active",b.dataset.place===name));
    render();
  }
  function nearest(type){
    let best=null;
    for(const feature of features){
      if((feature.properties||{}).access!==type)continue;
      const result=WildGeo.distanceToGeometry(origin,feature.geometry);
      if(result&&(!best||result.metres<best.metres))best={...result,feature};
    }
    return best;
  }
  function number(m){return m<1000?Math.round(m)+" m":(m/1000).toFixed(1)+" km";}
  function render(){
    whatIfLayer.clearLayers();
    $("now").classList.toggle("active",!future);$("future").classList.toggle("active",future);
    $("now").setAttribute("aria-pressed",String(!future));$("future").setAttribute("aria-pressed",String(future));
    if(!features.length){
      $("distance").textContent="—";$("distance-label").textContent="Nearest mapped accessible woodland";
      return;
    }
    const open=nearest("public access"), closed=nearest("no known public access");
    if(!future){
      $("distance").textContent=open?number(open.metres):"Not found";
      $("distance-label").textContent="Straight-line distance to mapped public-access woodland";
      $("interpretation").textContent=open&&open.metres<=800
        ?"Public-access woodland intersects this indicative 800 m circle."
        :"No publicly accessible woodland found within this illustrative 800 m radius in the data loaded.";
      return;
    }
    // One intentionally hypothetical intervention. There is no asserted right of access,
    // identified route, permission, or landowner agreement.
    const candidate=closed&&closed.metres<=2500?closed:null;
    const newBest=candidate&&(!open||candidate.metres<open.metres)?candidate:open;
    $("distance").textContent=newBest?number(newBest.metres):"Not found";
    $("distance-label").textContent="Illustrative distance if the nearest unconfirmed-access woodland were opened";
    if(!candidate){
      $("interpretation").textContent="No unconfirmed-access woodland was found within 2.5 km in the loaded area; try another place.";
      return;
    }
    L.geoJSON(candidate.feature,{style:{
      color:"#b2654b",weight:2.5,fillColor:"#c47d50",fillOpacity:.5,dashArray:"6 4"
    }}).addTo(whatIfLayer);
    L.polyline([origin,candidate.point],{
      color:"#b2654b",weight:3,dashArray:"8 7",opacity:.9
    }).addTo(whatIfLayer).bindPopup("Imagined connection only — not a known path or access right.");
    $("interpretation").textContent="Imagine this nearby woodland becoming publicly accessible. The orange line is a conceptual connection, not a feasible walking route.";
  }
  async function load(){
    const id=++request;
    if(controller)controller.abort();
    controller=new AbortController();
    const bounds=map.getBounds().pad(.12);
    if(bounds.getWest()<-9||bounds.getEast()>3||bounds.getSouth()<49||bounds.getNorth()>60)return;
    $("status").textContent="Loading mapped woods for this view…";
    try{
      const all=[];const LIMIT=2000;
      for(let offset=0;offset<6000;offset+=LIMIT){
        const bbox={xmin:bounds.getWest(),ymin:bounds.getSouth(),xmax:bounds.getEast(),ymax:bounds.getNorth(),spatialReference:{wkid:4326}};
        const qs=new URLSearchParams({
          f:"geojson",where:"access IN ('public access','no known public access')",
          geometry:JSON.stringify(bbox),geometryType:"esriGeometryEnvelope",
          spatialRel:"esriSpatialRelIntersects",inSR:"4326",outSR:"4326",
          outFields:"OBJECTID,category,ift_ioa,access,area_ha",
          returnGeometry:"true",resultOffset:String(offset),resultRecordCount:String(LIMIT)
        });
        const response=await fetch(ENDPOINT+"?"+qs,{signal:controller.signal});
        if(!response.ok)throw Error("Source returned HTTP "+response.status);
        const data=await response.json();
        if(data.error)throw Error(data.error.message||"Service error");
        if(!Array.isArray(data.features))throw Error("Unexpected response from woodland service");
        all.push(...data.features);
        if(data.features.length<LIMIT)break;
      }
      if(id!==request)return;
      features=all;
      woodland.clearLayers();woodland.addData({type:"FeatureCollection",features});
      $("status").textContent=all.length.toLocaleString("en-GB")+" source woodland polygons in the view"+
        (all.length>=6000?" (limit reached; zoom in for a fuller view)":"")+".";
      render();
    }catch(err){
      if(err.name==="AbortError"||id!==request)return;
      features=[];woodland.clearLayers();
      $("status").textContent="Woodland data unavailable: "+err.message+". The basemap is not evidence of access.";
      render();
    }
  }
  let debounce;
  map.on("moveend",()=>{clearTimeout(debounce);debounce=setTimeout(load,250);});
  map.on("click",e=>setOrigin(e.latlng.lat,e.latlng.lng,"Selected location"));
  document.querySelectorAll("[data-place]").forEach(button=>button.addEventListener("click",()=>{
    const p=PLACES[button.dataset.place];
    setOrigin(p.lat,p.lng,button.dataset.place);
    $("map-title").textContent=p.label;
    map.setView([p.lat,p.lng],12);
  }));
  $("now").addEventListener("click",()=>{future=false;render();});
  $("future").addEventListener("click",()=>{future=true;render();});
  load();
})();