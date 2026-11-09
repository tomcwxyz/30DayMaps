#!/usr/bin/env node
/* Non-blocking, real external-source check for Days 8 and 9.
   Checks public ArcGIS feature service, Terrascope WMS and ranged AWS COG.
   Run with Node 22+; no API keys. Network failures are reported, not masked. */
"use strict";
const assert=require("node:assert/strict");
async function request(name,url,init={}){
  const response=await fetch(url,{signal:AbortSignal.timeout(25000),...init});
  if(!response.ok)throw Error(name+" returned HTTP "+response.status);
  return response;
}
async function main(){
  const qs=new URLSearchParams({
    f:"json",where:"access IN ('public access','no known public access')",
    geometry:JSON.stringify({xmin:-1.89,ymin:54.65,xmax:-1.85,ymax:54.69,spatialReference:{wkid:4326}}),
    geometryType:"esriGeometryEnvelope",spatialRel:"esriSpatialRelIntersects",inSR:"4326",outSR:"4326",
    outFields:"OBJECTID,access",returnGeometry:"false",resultRecordCount:"50"
  });
  const arcgis="https://services2.arcgis.com/mHXjwgl3OARRqqD4/ArcGIS/rest/services/Woods_For_All/FeatureServer/0/query?"+qs;
  const ar=await request("Forestry Commission ArcGIS",arcgis,{headers:{"Origin":"https://example.org"}});
  const data=await ar.json();
  if(data.error)throw Error(JSON.stringify(data.error));
  assert.ok(Array.isArray(data.features)&&data.features.length>0,"No mapped woodland in sample bbox");
  assert.ok(data.features.every(f=>["public access","no known public access"].includes(f.attributes.access)));
  assert.equal(ar.headers.get("access-control-allow-origin")==="*"||ar.headers.get("access-control-allow-origin")==="https://example.org",true,"ArcGIS CORS header missing");
  console.log("PASS Forestry Commission Woods for All:",data.features.length,"real features; CORS supported");
  const params=new URLSearchParams({
    service:"WMS",version:"1.1.1",request:"GetMap",
    layers:"esa-worldcover-map-10m-2021-v2_map",styles:"",
    srs:"EPSG:4326",bbox:"-1.9,54.65,-1.6,55.0",
    width:"256",height:"256",format:"image/png",transparent:"true"
  });
  const wr=await request("ESA WorldCover WMS","https://mapproxy.terrascope.be/mapproxy/service?"+params);
  const wt=wr.headers.get("content-type")||"";
  assert.match(wt,/image\/png/i,"WMS did not return a PNG tile");
  const png=new Uint8Array(await wr.arrayBuffer());
  assert.deepEqual([...png.slice(0,4)],[137,80,78,71]);
  console.log("PASS ESA WorldCover 2021 WMS:",png.length,"bytes");
  const cog="https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_N54W003_Map.tif";
  const cr=await request("ESA WorldCover COG",cog,{headers:{Range:"bytes=0-4095",Origin:"https://example.org"}});
  assert.equal(cr.status,206,"COG must support HTTP range requests");
  const bytes=new Uint8Array(await cr.arrayBuffer());
  assert.ok(bytes[0]===73&&bytes[1]===73||bytes[0]===77&&bytes[1]===77,"COG response is not a TIFF");
  assert.equal(cr.headers.get("access-control-allow-origin")==="*"||cr.headers.get("access-control-allow-origin")==="https://example.org",true,"COG CORS header missing");
  console.log("PASS ESA WorldCover COG:",bytes.length,"bytes via ranged request; CORS supported");
}
main().catch(e=>{console.error("EXTERNAL SOURCE CHECK FAILED:",e);process.exitCode=1;});