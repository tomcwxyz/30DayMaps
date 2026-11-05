const {test}=require("node:test");
const assert=require("node:assert/strict");
const {mediaLicence,safeImageUrl,usableMedia,pickSpeciesPhoto}=require("../web/day05-wildlife/media.js");

test("only explicit reusable media licences pass",()=>{
  for(const license of ["CC0_1_0","https://creativecommons.org/publicdomain/zero/1.0/",
      "CC_BY_4_0","https://creativecommons.org/licenses/by/4.0/",
      "https://creativecommons.org/licenses/by/4.0/legalcode"]) {
    assert.ok(mediaLicence(license),license);
  }
  for(const license of [null,"","copyright","CC_BY_NC_4_0",
      "https://creativecommons.org/licenses/by-nc/4.0/",
      "https://creativecommons.org/licenses/by-sa/4.0/"]) {
    assert.equal(mediaLicence(license),null,String(license));
  }
});
test("unsafe or non-HTTPS external images are rejected",()=>{
  assert.equal(safeImageUrl("http://example.org/photo.jpg"),null);
  assert.equal(safeImageUrl("javascript:alert(1)"),null);
  assert.equal(safeImageUrl("https://alice:secret@example.com/image.jpg"),null);
  assert.equal(safeImageUrl("data:image/png;base64,x"),null);
  assert.equal(safeImageUrl("https://example.com/photo.jpg"),"https://example.com/photo.jpg");
});
test("record-level open licence cannot stand in for a restricted image",()=>{
  const occurrence={key:123,speciesKey:42,license:"CC0_1_0",media:[
    {type:"StillImage",identifier:"https://example.com/image.jpg",license:"CC_BY_NC_4_0"}
  ]};
  assert.equal(usableMedia(occurrence,42),null);
});
test("image must belong to the requested species key",()=>{
  const r={key:123,speciesKey:43,media:[
    {type:"StillImage",identifier:"https://example.com/image.jpg",license:"CC_BY_4_0"}
  ]};
  assert.equal(usableMedia(r,42),null);
});
test("usable photo includes creator, explicit licence and source link",()=>{
  const r={key:123,speciesKey:42,media:[
    {type:"StillImage",identifier:"https://example.com/robin.jpg",license:"CC_BY_4_0",creator:"A. Photographer"}
  ]};
  const photo=usableMedia(r,42);
  assert.equal(photo.licence,"CC BY 4.0");
  assert.equal(photo.creator,"A. Photographer");
  assert.equal(photo.sourceUrl,"https://www.gbif.org/occurrence/123");
  assert.match(photo.label,/not necessarily recorded nearby/i);
});
test("find a later valid image when first has no explicit licence",()=>{
  const source=[
    {key:1,speciesKey:42,media:[{type:"StillImage",identifier:"https://example.org/a.jpg"}]},
    {key:2,speciesKey:42,media:[{type:"StillImage",identifier:"https://example.org/b.jpg",license:"CC0_1_0"}]}
  ];
  assert.equal(pickSpeciesPhoto(source,42)?.sourceUrl,"https://www.gbif.org/occurrence/2");
});
