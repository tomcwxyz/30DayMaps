#!/usr/bin/env node
"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const {chromium}=require("playwright");
const base=(process.env.DAY_MAP_BASE||"http://127.0.0.1:8011").replace(/\/$/,"");
const out=process.env.DAY_MAP_OUTPUT||"browser-screenshots";
fs.mkdirSync(out,{recursive:true});

async function inspect(browser,route,isMobile){
  const page=await browser.newPage({
    viewport:isMobile?{width:390,height:844}:{width:1370,height:900},
    isMobile,hasTouch:isMobile
  });
  const errors=[];
  page.on("pageerror",e=>errors.push(e.message));
  await page.goto(base+"/"+route+"/",{waitUntil:"domcontentloaded",timeout:30000});
  await page.locator("#status").waitFor();
  if(route==="day08-utopia"){
    await page.waitForFunction(()=>document.querySelector("#status")?.textContent?.includes("Computed from WorldCover"),null,{timeout:20000});
    const value=(await page.locator("#future-share").textContent()).trim();
    assert.match(value,/^50\.0%$/);
    assert.equal(await page.locator("#show-future").getAttribute("aria-pressed"),"true");
    let loaded=await page.locator("#landscape").evaluate(img=>img.complete&&img.naturalWidth>500);
    assert.ok(loaded,"Day 8 future model image must load");
    await page.locator("#show-today").click();
    assert.equal(await page.locator("#show-today").getAttribute("aria-pressed"),"true");
    assert.match(await page.locator("#landscape").getAttribute("src"),/data\/today\.png$/);
    await page.waitForFunction(()=>document.querySelector("#landscape")?.complete&&document.querySelector("#landscape")?.naturalWidth>500);
    await page.locator("#show-future").click();
    await page.waitForFunction(()=>document.querySelector("#landscape")?.complete&&document.querySelector("#landscape")?.naturalWidth>500);
  }else{
    await page.waitForFunction(()=>document.querySelector("#status")?.textContent?.includes("Measured 85 transect locations"),null,{timeout:20000});
    assert.equal(await page.locator("#chart path").count(),5);
    await page.waitForFunction(()=>document.querySelector("#strip")?.complete&&document.querySelector("#strip")?.naturalWidth>500);
    await page.locator("#chart").focus();
    await page.keyboard.press("End");
    assert.match(await page.locator("#position").textContent(),/Hamsterley Forest/);
    await page.keyboard.press("Home");
    assert.match(await page.locator("#position").textContent(),/Newcastle/);
  }
  assert.deepEqual(errors,[],route+" browser JavaScript errors");
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth);
  assert.ok(overflow<4,route+" must not overflow horizontally: "+overflow);
  const target=path.join(out,route+(isMobile?"-mobile":"-desktop")+".png");
  await page.screenshot({path:target,fullPage:true});
  console.log("PASS "+route+" "+(isMobile?"mobile":"desktop")+"; screenshot "+target);
  await page.close();
}

(async()=>{
  const browser=await chromium.launch({headless:true});
  try{
    for(const route of ["day08-utopia","day09-urban-rural"]){
      await inspect(browser,route,false);
      await inspect(browser,route,true);
    }
  }finally{
    await browser.close();
  }
})().catch(e=>{console.error("DAY 8/9 BROWSER FAILED:",e);process.exitCode=1;});
