/* Small geometry helpers used by Day 08. All distances are approximations on WGS84, not walking-route lengths. */
(function(global){
  "use strict";
  const RAD=Math.PI/180;
  function toXY(lon,lat,origin){
    return [(lon-origin[1])*111320*Math.cos(origin[0]*RAD),(lat-origin[0])*111320];
  }
  function segmentDistance(p,a,b){
    const dx=b[0]-a[0],dy=b[1]-a[1],length=dx*dx+dy*dy;
    const t=length?Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/length)):0;
    const near=[a[0]+t*dx,a[1]+t*dy];
    return {metres:Math.hypot(p[0]-near[0],p[1]-near[1]),point:near};
  }
  function insideRing(point,ring){
    let inside=false;
    for(let i=0,j=ring.length-1;i<ring.length;j=i++){
      const a=ring[i],b=ring[j];
      if(((a[1]>point[1])!==(b[1]>point[1])) &&
        point[0]<(b[0]-a[0])*(point[1]-a[1])/(b[1]-a[1])+a[0]) inside=!inside;
    }
    return inside;
  }
  function distanceToGeometry(origin,geometry){
    if(!geometry||!geometry.coordinates)return null;
    const polygons=geometry.type==="Polygon"?[geometry.coordinates]:
      geometry.type==="MultiPolygon"?geometry.coordinates:[];
    if(!polygons.length)return null;
    const p=[0,0];let best={metres:Infinity,point:origin.slice()};
    const back=(xy)=>[origin[0]+xy[1]/111320,origin[1]+xy[0]/(111320*Math.cos(origin[0]*RAD))];
    for(const poly of polygons){
      const rings=poly.map(ring=>ring.map(c=>toXY(c[0],c[1],origin)));
      if(!rings.length||!rings[0].length)continue;
      if(insideRing(p,rings[0])&&!rings.slice(1).some(h=>insideRing(p,h))){
        return {metres:0,point:origin.slice()};
      }
      for(const ring of rings){
        for(let i=1;i<ring.length;i++){
          const d=segmentDistance(p,ring[i-1],ring[i]);
          if(d.metres<best.metres)best={metres:d.metres,point:back(d.point)};
        }
        if(ring.length>2){
          const d=segmentDistance(p,ring[ring.length-1],ring[0]);
          if(d.metres<best.metres)best={metres:d.metres,point:back(d.point)};
        }
      }
    }
    return Number.isFinite(best.metres)?best:null;
  }
  const api={distanceToGeometry};
  global.WildGeo=api;
  if(typeof module!=="undefined"&&module.exports)module.exports=api;
})(typeof window!=="undefined"?window:globalThis);