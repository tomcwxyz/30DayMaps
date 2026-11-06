// Paints a Peaks sheet (a list of items in millimetres) to a canvas or to SVG text.
// Text is placed on its alphabetic baseline using the font's own metrics, so canvas and
// SVG put every word in the same place.
(function (root) {
  "use strict";
  const MEASURE = 100;   // measure at 100 px and scale
  let mctx = null;
  function measurer() {
    if (!mctx) mctx = (typeof OffscreenCanvas !== "undefined" ? new OffscreenCanvas(8, 8) : document.createElement("canvas")).getContext("2d");
    return mctx;
  }
  const fontAt = (it, px) => `${it.weight || 400} ${px}px "${it.family}"`;
  const metricCache = new Map();

  // Left x of each glyph run, baseline y, total width.
  function placeText(it) {
    const ctx = measurer();
    ctx.font = fontAt(it, MEASURE);
    const k = it.size / MEASURE;
    const key = ctx.font;
    if (!metricCache.has(key)) {
      const m = ctx.measureText("Hg");
      metricCache.set(key, [m.fontBoundingBoxAscent ?? m.actualBoundingBoxAscent, m.fontBoundingBoxDescent ?? m.actualBoundingBoxDescent]);
    }
    const [asc, desc] = metricCache.get(key).map(v => v * k);
    const chars = it.spacing ? [...it.s] : null;
    let widths = null, width;
    if (chars) {
      widths = chars.map(ch => ctx.measureText(ch).width * k);
      width = widths.reduce((a, b) => a + b, 0) + it.spacing * it.size * (chars.length - 1);
    } else width = ctx.measureText(it.s).width * k;
    const x0 = it.align === "center" ? -width / 2 : it.align === "right" ? -width : 0;
    const base = it.base || "alphabetic";
    const y0 = base === "top" ? asc : base === "bottom" ? -desc : base === "middle" ? (asc - desc) / 2 : 0;
    let xs = null;
    if (chars) { xs = []; let x = x0; chars.forEach((ch, i) => { xs.push(x); x += widths[i] + it.spacing * it.size; }); }
    return { x0, y0, width, chars, xs };
  }

  // ---- canvas ----------------------------------------------------------------------
  function toCanvas(canvas, items, pw, ph, pxPerMM) {
    canvas.width = Math.round(pw * pxPerMM); canvas.height = Math.round(ph * pxPerMM);
    const ctx = canvas.getContext("2d");
    ctx.setTransform(pxPerMM, 0, 0, pxPerMM, 0, 0);
    ctx.lineJoin = "round"; ctx.lineCap = "round";
    for (const it of items) {
      switch (it.t) {
        case "rect":
          if (it.fill) { ctx.fillStyle = it.fill; ctx.fillRect(it.x, it.y, it.w, it.h); }
          if (it.stroke) { ctx.strokeStyle = it.stroke; ctx.lineWidth = it.w; ctx.strokeRect(it.x, it.y, it.w, it.h); }
          break;
        case "clip":
          ctx.save(); ctx.beginPath(); ctx.rect(it.x, it.y, it.w, it.h); ctx.clip(); break;
        case "unclip":
          ctx.restore(); ctx.lineJoin = "round"; ctx.lineCap = "round"; break;
        case "grad": {
          const g = ctx.createLinearGradient(0, it.y, 0, it.y + it.h);
          g.addColorStop(0, it.top); g.addColorStop(1, it.bottom);
          ctx.fillStyle = g; ctx.fillRect(it.x, it.y, it.w, it.h); break;
        }
        case "path": case "poly": case "line": {
          const p = new Path2D();
          const rings = it.t === "path" ? it.rings : [it.pts];
          const open = it.open || it.t === "line";
          for (const r of rings) {
            if (r.length < 4) continue;
            p.moveTo(r[0], r[1]);
            for (let i = 2; i < r.length; i += 2) p.lineTo(r[i], r[i + 1]);
            if (!open) p.closePath();
          }
          ctx.globalAlpha = it.alpha ?? 1;
          if (it.fill) { ctx.fillStyle = it.fill; ctx.fill(p, it.rule || "nonzero"); }
          if (it.stroke) { ctx.strokeStyle = it.stroke; ctx.lineWidth = it.w; ctx.stroke(p); }
          ctx.globalAlpha = 1;
          break;
        }
        case "circle":
          ctx.beginPath(); ctx.arc(it.x, it.y, it.r, 0, 2 * Math.PI);
          if (it.fill) { ctx.fillStyle = it.fill; ctx.fill(); }
          if (it.stroke) { ctx.strokeStyle = it.stroke; ctx.lineWidth = it.w; ctx.stroke(); }
          break;
        case "text": {
          const P = placeText(it);
          ctx.save();
          ctx.translate(it.x, it.y);
          if (it.rot) ctx.rotate(it.rot);
          ctx.font = fontAt(it, it.size);
          ctx.textAlign = "left"; ctx.textBaseline = "alphabetic";
          const draw = fn => { if (P.chars) P.chars.forEach((ch, i) => fn(ch, P.xs[i], P.y0)); else fn(it.s, P.x0, P.y0); };
          if (it.halo) {
            ctx.strokeStyle = it.halo.color; ctx.lineWidth = it.halo.width * 2; ctx.lineJoin = "round";
            draw((s, x, y) => ctx.strokeText(s, x, y));
          }
          ctx.fillStyle = it.fill;
          draw((s, x, y) => ctx.fillText(s, x, y));
          ctx.restore();
          break;
        }
      }
    }
  }

  // ---- SVG ----------------------------------------------------------------------------
  const esc = s => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const f2 = v => (Math.round(v * 100) / 100).toString();

  function toSVG(items, pw, ph, fontCSS = "") {
    const out = [], defs = [];
    let clip = 0, grad = 0;
    for (const it of items) {
      switch (it.t) {
        case "rect":
          out.push(`<rect x="${f2(it.x)}" y="${f2(it.y)}" width="${f2(it.w)}" height="${f2(it.h)}" fill="${it.fill || "none"}"${it.stroke ? ` stroke="${it.stroke}" stroke-width="${f2(it.w)}"` : ""}/>`);
          break;
        case "clip":
          defs.push(`<clipPath id="c${++clip}"><rect x="${f2(it.x)}" y="${f2(it.y)}" width="${f2(it.w)}" height="${f2(it.h)}"/></clipPath>`);
          out.push(`<g clip-path="url(#c${clip})">`); break;
        case "unclip":
          out.push("</g>"); break;
        case "grad":
          defs.push(`<linearGradient id="g${++grad}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${it.top}"/><stop offset="1" stop-color="${it.bottom}"/></linearGradient>`);
          out.push(`<rect x="${f2(it.x)}" y="${f2(it.y)}" width="${f2(it.w)}" height="${f2(it.h)}" fill="url(#g${grad})"/>`);
          break;
        case "path": case "poly": case "line": {
          const rings = it.t === "path" ? it.rings : [it.pts];
          const open = it.open || it.t === "line";
          const d = [];
          for (const r of rings) {
            if (r.length < 4) continue;
            let s = `M${f2(r[0])} ${f2(r[1])}`;
            for (let i = 2; i < r.length; i += 2) s += `L${f2(r[i])} ${f2(r[i + 1])}`;
            d.push(open ? s : s + "Z");
          }
          if (!d.length) break;
          out.push(`<path d="${d.join("")}" fill="${it.fill || "none"}"${it.rule ? ` fill-rule="${it.rule}"` : ""}${it.stroke ? ` stroke="${it.stroke}" stroke-width="${f2(it.w)}" stroke-linejoin="round" stroke-linecap="round"` : ""}${it.alpha != null && it.alpha !== 1 ? ` opacity="${it.alpha}"` : ""}/>`);
          break;
        }
        case "circle":
          out.push(`<circle cx="${f2(it.x)}" cy="${f2(it.y)}" r="${f2(it.r)}" fill="${it.fill || "none"}"${it.stroke ? ` stroke="${it.stroke}" stroke-width="${f2(it.w)}"` : ""}/>`);
          break;
        case "text": {
          const P = placeText(it);
          const xs = P.chars ? P.xs.map(x => f2(x)).join(" ") : f2(P.x0);
          const tf = `translate(${f2(it.x)} ${f2(it.y)})${it.rot ? ` rotate(${f2(it.rot * 180 / Math.PI)})` : ""}`;
          const halo = it.halo ? ` stroke="${it.halo.color}" stroke-width="${f2(it.halo.width * 2)}" stroke-linejoin="round" paint-order="stroke"` : "";
          out.push(`<text transform="${tf}" x="${xs}" y="${f2(P.y0)}" font-family="${esc(it.family)}" font-weight="${it.weight || 400}" font-size="${f2(it.size)}" fill="${it.fill}"${halo} xml:space="preserve">${esc(it.s)}</text>`);
          break;
        }
      }
    }
    return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${pw}mm" height="${ph}mm" viewBox="0 0 ${pw} ${ph}">
<defs>${fontCSS ? `<style>${fontCSS}</style>` : ""}${defs.join("")}</defs>
${out.join("\n")}
</svg>`;
  }

  root.PeaksRender = { toCanvas, toSVG };
})(typeof window !== "undefined" ? window : globalThis);
