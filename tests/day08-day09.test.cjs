const test=require("node:test");const assert=require("node:assert/strict");
const wild=require("../web/day08-utopia/geo.js");
const cover=require("../web/day09-urban-rural/landcover.js");
test("distance to access woodland is zero for point within polygon",()=>{
  const poly={type:"Polygon",coordinates:[[[-1.6,54.7],[-1.5,54.7],[-1.5,54.8],[-1.6,54.8],[-1.6,54.7]]]};
  assert.equal(wild.distanceToGeometry([54.75,-1.55],poly).metres,0);
});
test("distance excludes holes (private inholdings)",()=>{
  const poly={type:"Polygon",coordinates:[
    [[-1.7,54.7],[-1.5,54.7],[-1.5,54.9],[-1.7,54.9],[-1.7,54.7]],
    [[-1.61,54.79],[-1.59,54.79],[-1.59,54.81],[-1.61,54.81],[-1.61,54.79]]
  ]};
  const d=wild.distanceToGeometry([54.8,-1.6],poly);
  assert.ok(d.metres>500&&d.metres<1500);
});
test("distance to nearby woodland has metres and destination",()=>{
  const poly={type:"Polygon",coordinates:[[[-1.61,54.8],[-1.6,54.8],[-1.6,54.81],[-1.61,54.81],[-1.61,54.8]]]};
  const d=wild.distanceToGeometry([54.8,-1.62],poly);
  assert.ok(d.metres>500&&d.metres<750);
  assert.equal(d.point.length,2);
});
test("worldcover transect endpoints are fixed and samples follow the line",()=>{
  const p=cover.points(11);
  assert.deepEqual(p[0],cover.START);
  assert.deepEqual(p[10],cover.END);
  assert.ok(cover.greatCircleKm(cover.START,cover.END)>30);
});
test("land-cover fractions derive exclusively from sample codes",()=>{
  const a=cover.classify([54.8,-1.7],()=>50);
  assert.equal(a.built,100);
  assert.equal(a.trees,0);
  const b=cover.classify([54.8,-1.7],()=>10);
  assert.equal(b.trees,100);
  assert.equal(b.built,0);
  assert.equal(cover.classify([54.8,-1.7],()=>0),null);
});

test("Day 8 and Day 9 use key-free OpenStreetMap tiles, with no CARTO dependency",()=>{
  const fs=require("node:fs");
  for(const page of ["day08-utopia","day09-urban-rural"]){
    const app=fs.readFileSync(require("node:path").join(__dirname,"..","web",page,"app.js"),"utf8");
    assert.match(app,/https:\/\/tile\.openstreetmap\.org\/\{z\}\/\{x\}\/\{y\}\.png/);
    assert.doesNotMatch(app,/cartocdn|carto\.com\/attributions/i);
    assert.match(app,/openstreetmap\.org\/copyright/);
  }
});
