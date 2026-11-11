(() => {
  "use strict";
  const $=id=>document.getElementById(id);
  const NS="http://www.w3.org/2000/svg";
  const ORDER=[
    {key:"built",label:"Built-up",color:"#a98b84"},
    {key:"trees",label:"Tree cover",color:"#356945"},
    {key:"cropland",label:"Cropland",color:"#d9c79d"},
    {key:"open",label:"Grass / shrub",color:"#a4b48b"},
    {key:"other",label:"Other",color:"#729eaa"}
  ];
  let samples=[],last=0,marker=null;
  const svg=$("chart"),left=65,top=44,width=870,height=309;
  function element(tag,attributes,content){
    const el=document.createElementNS(NS,tag);
    for(const [key,value] of Object.entries(attributes))el.setAttribute(key,value);
    if(content!==undefined)el.textContent=content;
    svg.append(el);return el;
  }
  const xx=index=>left+index/Math.max(1,samples.length-1)*width;
  const yy=pct=>top+height*(1-pct/100);
  function inspect(index){
    if(!samples.length)return;
    last=Math.min(samples.length-1,Math.max(0,index));
    const d=samples[last];
    $("position").textContent=(last===0?"Newcastle":last===samples.length-1?"Hamsterley Forest":"Along the transect")+" · "+d.distance_km.toFixed(1)+" km";
    $("built-share").textContent=d.built.toFixed(1)+"%";
    $("details").textContent="Trees "+d.trees.toFixed(1)+"% · Cropland "+d.cropland.toFixed(1)+"% · Grass/shrub "+d.open.toFixed(1)+"% · Other "+d.other.toFixed(1)+"%";
    if(marker)marker.setAttribute("x1",xx(last)),marker.setAttribute("x2",xx(last));
    svg.setAttribute("aria-valuetext",d.distance_km.toFixed(1)+" km from Newcastle, built-up "+d.built.toFixed(1)+" percent");
  }
  function render(){
    svg.replaceChildren();
    for(let percent=0;percent<=100;percent+=20){
      const y=yy(percent);
      element("line",{x1:left,y1:y,x2:left+width,y2:y,stroke:"#d5d7ce","stroke-width":"1"});
      element("text",{x:left-12,y:y+4,"text-anchor":"end","font-size":13,fill:"#627468"},percent+"%");
    }
    let sum=new Array(samples.length).fill(0);
    for(const series of ORDER){
      const base=sum.slice();
      const upper=samples.map((d,i)=>base[i]+d[series.key]);
      const topLine=upper.map((v,i)=>(i?"L":"M")+xx(i).toFixed(1)+" "+yy(v).toFixed(1)).join(" ");
      const bottomLine=base.map((v,i)=>"L"+xx(i).toFixed(1)+" "+yy(v).toFixed(1)).reverse().join(" ");
      element("path",{d:topLine+" "+bottomLine+" Z",fill:series.color,stroke:"none"});
      sum=upper;
    }
    for(let i=0;i<=4;i++){
      const dist=(samples[samples.length-1].distance_km*i/4).toFixed(0);
      const x=xx((samples.length-1)*i/4);
      element("text",{x,y:top+height+26,"text-anchor":"middle","font-size":13,fill:"#637567"},dist+" km");
    }
    element("text",{x:left,y:20,"font-size":13,fill:"#52675a"},"Measured class share within 500 m");
    marker=element("line",{x1:xx(0),x2:xx(0),y1:top-2,y2:top+height+2,stroke:"#1c3b2e","stroke-width":"2","stroke-dasharray":"5 5"});
    const detectIndex=event=>{
      const box=svg.getBoundingClientRect(),coord=(event.clientX-box.left)*980/box.width;
      return Math.round((coord-left)/width*(samples.length-1));
    };
    svg.addEventListener("pointermove",e=>inspect(detectIndex(e)));
    svg.addEventListener("pointerdown",e=>inspect(detectIndex(e)));
    svg.addEventListener("keydown",e=>{
      if(e.key==="ArrowRight"){inspect(last+1);e.preventDefault();}
      if(e.key==="ArrowLeft"){inspect(last-1);e.preventDefault();}
      if(e.key==="Home"){inspect(0);e.preventDefault();}
      if(e.key==="End"){inspect(samples.length-1);e.preventDefault();}
    });
    inspect(0);
  }
  fetch("./data/profile.json").then(r=>{
    if(!r.ok)throw Error("HTTP "+r.status);
    return r.json();
  }).then(d=>{
    if(d.status!=="measured"||d.samples.length!==85)throw Error("Unexpected or unverified data");
    samples=d.samples;
    for(const row of samples){
      const total=ORDER.reduce((s,item)=>s+row[item.key],0);
      if(Math.abs(total-100)>.2||row.sample_count<100)throw Error("Invalid sample composition");
    }
    $("length").textContent=d.distance_km.toFixed(1)+" km · straight line";
    $("status").textContent="Measured "+samples.length+" transect locations using real classified raster samples (2021). No browser-side raster download or invented values.";
    render();
  }).catch(error=>{
    svg.replaceChildren();
    element("text",{x:60,y:100,"font-size":23,fill:"#9b624f"},"Measured profile unavailable");
    $("status").textContent=error.message+". No values have been substituted.";
  });
  $("strip").addEventListener("error",()=>{
    $("status").textContent="The source-derived transect image could not be loaded.";
  });
})();