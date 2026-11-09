/* Day 09 — visualise an authentic remote-sensing classification, not an artist's impression. */
(() => {
  "use strict";
  const $=id=>document.getElementById(id),LCC=window.LandCover;
  const map=L.map("map",{scrollWheelZoom:false,zoomControl:false});
  L.control.zoom({position:"bottomright"}).addTo(map);
  L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",{
    subdomains:"abcd",maxZoom:18,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>'
  }).addTo(map);
  const wms=L.tileLayer.wms("https://mapproxy.terrascope.be/mapproxy/service",{
    layers:"esa-worldcover-map-10m-2021-v2_map",
    format:"image/png",transparent:true,version:"1.1.1",
    opacity:.82,attribution:'&copy; ESA WorldCover project 2021'
  }).addTo(map);
  const bounds=L.latLngBounds(LCC.START,LCC.END).pad(.23);
  const path=L.polyline([LCC.START,LCC.END],{
    color:"#fffdf8",weight:5,opacity:.95
  }).addTo(map);
  L.polyline([LCC.START,LCC.END],{
    color:"#293e36",weight:2,dashArray:"5 5"
  }).addTo(map);
  const start=L.circleMarker(LCC.START,{radius:6,color:"#263c32",fillColor:"#fff",weight:2,fillOpacity:1}).addTo(map);
  const finish=L.circleMarker(LCC.END,{radius:6,color:"#263c32",fillColor:"#fff",weight:2,fillOpacity:1}).addTo(map);
  start.bindTooltip("Newcastle city centre");finish.bindTooltip("Hamsterley Forest");
  const probe=L.circleMarker(LCC.START,{radius:8,color:"#fff",fillColor:"#a34d3b",weight:2,fillOpacity:1}).addTo(map);
  map.fitBounds(bounds,{padding:[28,28]});
  let section=[],selectedIndex=0,failedWms=false;
  wms.on("tileerror",()=>{
    if(failedWms)return;
    failedWms=true;
    $("status").textContent+=" The land-cover overlay has not loaded; the basemap alone cannot show land-cover classification.";
  });
  function toggle(show){
    if(show){if(!map.hasLayer(wms))wms.addTo(map);}else{if(map.hasLayer(wms))map.removeLayer(wms);}
    $("satellite").classList.toggle("active",show);
    $("outline").classList.toggle("active",!show);
    $("satellite").setAttribute("aria-pressed",String(show));
    $("outline").setAttribute("aria-pressed",String(!show));
  }
  $("satellite").addEventListener("click",()=>toggle(true));
  $("outline").addEventListener("click",()=>toggle(false));
  $("reset").addEventListener("click",()=>map.fitBounds(bounds,{padding:[28,28]}));
  const NS="http://www.w3.org/2000/svg",svg=$("profile");
  function elt(tag,attrs,parent=svg){
    const el=document.createElementNS(NS,tag);
    for(const [k,v] of Object.entries(attrs))el.setAttribute(k,String(v));
    parent.append(el);return el;
  }
  function drawProfile(){
    svg.replaceChildren();
    const n=section.length,left=14,width=292,top=28,height=90,step=width/n;
    const shades={built:"#b25c50",trees:"#3f7759",crop:"#d9ad67",grass:"#a8b985",other:"#83a9b8"};
    [0,25,50,75,100].forEach(p=>{
      const y=top+height*(1-p/100);
      elt("line",{x1:left,y1:y,x2:left+width,y2:y,stroke:"#cfd4c9","stroke-width":.65});
    });
    for(let i=0;i<n;i++){
      const s=section[i],c=s.cover;
      if(!c)continue;
      let y=top+height;
      for(const key of ["built","trees","crop","grass","other"]){
        const h=height*c[key]/100;
        y-=h;
        elt("rect",{x:left+i*step,y,width:step+.3,height:Math.max(0,h),fill:shades[key]});
      }
    }
    const x=left+(selectedIndex+.5)*step;
    elt("rect",{x:x-3.5,y:top-3,width:7,height:height+6,fill:"none",stroke:"#24392f","stroke-width":2,rx:1});
    elt("text",{x:left,y:17,"font-size":10,fill:"#5c6b5d"}).textContent="Local land cover (% of sampled pixels)";
    elt("text",{x:left,y:145,"font-size":10,fill:"#5c6b5d"}).textContent="0 km";
    elt("text",{x:width+left,y:145,"font-size":10,fill:"#5c6b5d","text-anchor":"end"})
      .textContent=LCC.greatCircleKm(LCC.START,LCC.END).toFixed(1)+" km";
  }
  function inspect(index){
    if(!section.length)return;
    selectedIndex=Math.max(0,Math.min(section.length-1,index));
    const p=section[selectedIndex],c=p.cover;
    probe.setLatLng([p.lat,p.lng]);
    $("built-up").textContent=c?Math.round(c.built)+"% built-up":"No data";
    $("point-description").textContent=c?
      p.distanceKm.toFixed(1)+" km along transect · within roughly 500 m: "+
      Math.round(c.trees)+"% tree cover, "+Math.round(c.crop)+"% cropland, "+
      Math.round(c.grass)+"% grass/shrub land.":
      "No classified data at this point.";
    drawProfile();
  }
  function pointerIndex(event){
    const rect=svg.getBoundingClientRect();
    const px=(event.clientX-rect.left)/rect.width*320;
    return Math.round((px-14)/292*section.length-.5);
  }
  svg.addEventListener("pointermove",e=>{if(section.length)inspect(pointerIndex(e));});
  svg.addEventListener("click",e=>{if(section.length)inspect(pointerIndex(e));});
  svg.addEventListener("keydown",e=>{
    if(!section.length)return;
    if(e.key==="ArrowRight"){inspect(selectedIndex+1);e.preventDefault();}
    if(e.key==="ArrowLeft"){inspect(selectedIndex-1);e.preventDefault();}
    if(e.key==="Home"){inspect(0);e.preventDefault();}
    if(e.key==="End"){inspect(section.length-1);e.preventDefault();}
  });
  async function initialise(){
    try{
      section=await LCC.readSection();
      const observed=section.filter(s=>s.cover).length;
      $("status").textContent="Measured "+observed+" of "+section.length+
        " points from ESA WorldCover 2021, downsampled for this overview.";
      inspect(0);
    }catch(error){
      $("status").textContent="Land-cover profile unavailable: "+error.message+
        ". No modelled or invented percentages are shown.";
      $("built-up").textContent="Unavailable";
      $("point-description").textContent="The map may still show the published WMS imagery. A numeric profile needs access to the original GeoTIFF.";
      svg.replaceChildren();
      elt("text",{x:18,y:68,"font-size":13,fill:"#596f62"}).textContent="Source raster unavailable";
      elt("text",{x:18,y:92,"font-size":10,fill:"#596f62"}).textContent="No estimated percentages substituted.";
    }
  }
  initialise();
})();