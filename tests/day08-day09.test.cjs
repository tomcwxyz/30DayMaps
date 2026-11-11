const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const base=path.join(__dirname,"..");
const read=filename=>fs.readFileSync(path.join(base,filename),"utf8");

test("Day 8 is a sourced, not invented, geographic scenario",()=>{
  const html=read("web/day08-utopia/index.html");
  const app=read("web/day08-utopia/app.js");
  assert.match(html,/North East, 2050/);
  assert.match(html,/hypothetical|imagined|modelling rule/i);
  assert.match(app,/data\/2050\.png/);
  assert.match(app,/data\/today\.png/);
  assert.match(app,/data\/metrics\.json/);
  assert.doesNotMatch(app,/cartocdn|tile\.openstreetmap\.org|Math\.random|mapproxy/i);
});
test("Day 9 chart is built from committed satellite sample percentages",()=>{
  const html=read("web/day09-urban-rural/index.html");
  const app=read("web/day09-urban-rural/app.js");
  assert.match(html,/Measured, not imagined/i);
  assert.match(html,/data\/transect\.png/);
  assert.match(app,/data\/profile\.json/);
  for(const col of ["built","trees","cropland","open","other"]){
    assert.ok(app.includes(col));
  }
  assert.doesNotMatch(app,/Math\.random|mapproxy|GeoTIFF|cartocdn/i);
});
test("precomputed datasets are present and numerically consistent",()=>{
  const day8=JSON.parse(read("web/day08-utopia/data/metrics.json"));
  const day9=JSON.parse(read("web/day09-urban-rural/data/profile.json"));
  assert.equal(day8.status,"measured_inputs_modelled_future");
  assert.ok(day8.modelled_added_km2_approx>0);
  assert.equal(day8["2050_nature_first_pct_of_sampled_land"],50);
  assert.equal(day9.status,"measured");
  assert.equal(day9.samples.length,85);
  assert.ok(day9.distance_km>30&&day9.distance_km<50);
  for(const item of day9.samples){
    const sum=["built","trees","cropland","open","other"].reduce((a,k)=>a+item[k],0);
    assert.ok(Math.abs(sum-100)<.2,"composition percentages must sum to 100");
  }
  for(const image of ["web/day08-utopia/data/today.png","web/day08-utopia/data/2050.png","web/day09-urban-rural/data/transect.png"]){
    const bytes=fs.readFileSync(path.join(base,image));
    assert.deepEqual([...bytes.subarray(0,8)],[137,80,78,71,13,10,26,10]);
    assert.ok(bytes.length>10000);
  }
});
