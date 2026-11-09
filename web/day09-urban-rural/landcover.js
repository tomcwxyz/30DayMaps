/* Day 09 — the chart is calculated from ESA WorldCover's actual classification
   raster, not from the WMS colour image. No synthetic land-cover estimates. */
(function(global){
  "use strict";
  const URL="https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_N54W003_Map.tif";
  const START=[54.9783,-1.6178]; // Newcastle
  const END=[54.675,-1.859]; // Hamsterley Forest
  function greatCircleKm(a,b){
    const rad=Math.PI/180,dl=(b[0]-a[0])*rad,dlo=(b[1]-a[1])*rad;
    const h=Math.sin(dl/2)**2+Math.cos(a[0]*rad)*Math.cos(b[0]*rad)*Math.sin(dlo/2)**2;
    return 12742*Math.atan2(Math.sqrt(h),Math.sqrt(1-h));
  }
  function points(n=61){
    return Array.from({length:n},(_,i)=>{
      const f=i/(n-1);
      return [START[0]+(END[0]-START[0])*f,START[1]+(END[1]-START[1])*f];
    });
  }
  function classify(p,codeAt){
    const tally={built:0,trees:0,crop:0,grass:0,other:0};
    let valid=0;
    const lat=p[0],lng=p[1],cos=Math.cos(lat*Math.PI/180);
    // Uniform sample points within a 500m radius, ignoring 'no data'.
    for(let dx=-500;dx<=500;dx+=125)for(let dy=-500;dy<=500;dy+=125){
      if(dx*dx+dy*dy>500*500)continue;
      const code=codeAt(lng+dx/(111320*cos),lat+dy/111320);
      if(!Number.isFinite(code)||code===0||code===255)continue;
      valid++;
      if(code===50)tally.built++;
      else if(code===10)tally.trees++;
      else if(code===40)tally.crop++;
      else if(code===30||code===20)tally.grass++;
      else tally.other++;
    }
    if(!valid)return null;
    return {valid,...Object.fromEntries(Object.entries(tally).map(([k,v])=>[k,100*v/valid]))};
  }
  async function readSection(){
    if(!global.GeoTIFF||typeof global.GeoTIFF.fromUrl!=="function")
      throw Error("GeoTIFF reader unavailable");
    const tiff=await global.GeoTIFF.fromUrl(URL);
    // GeoTIFF.readRasters picks a suitable internal overview for the requested
    // output resolution. This avoids decoding full-resolution blocks unnecessarily.
    const bounds={west:-1.89,south:54.65,east:-1.59,north:55.005};
    const width=560,height=740;
    const image=await tiff.readRasters({
      bbox:[bounds.west,bounds.south,bounds.east,bounds.north],
      width,height,samples:[0],resampleMethod:"nearest"
    });
    const values=image[0];
    if(!values||values.length!==width*height)throw Error("Incomplete raster data");
    function codeAt(lng,lat){
      const x=Math.floor((lng-bounds.west)/(bounds.east-bounds.west)*width);
      const y=Math.floor((bounds.north-lat)/(bounds.north-bounds.south)*height);
      if(x<0||y<0||x>=width||y>=height)return NaN;
      return values[y*width+x];
    }
    const coords=points();
    const section=coords.map((p,index)=>({lat:p[0],lng:p[1],
      distanceKm:greatCircleKm(START,p),index,cover:classify(p,codeAt)}));
    if(section.filter(s=>s.cover).length<45)throw Error("Too few valid land-cover samples");
    return section;
  }
  const api={URL,START,END,greatCircleKm,points,classify,readSection};
  global.LandCover=api;
  if(typeof module!=="undefined"&&module.exports)module.exports=api;
})(typeof window!=="undefined"?window:globalThis);