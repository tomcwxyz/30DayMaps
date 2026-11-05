/* Day 05 Sight — pure canvas renderer for measured terrain silhouettes.
   All geometry comes from panorama.json (actual DEM, not generated scenery). */
(() => {
  "use strict";
  const FIELD_DEGREES = 90;
  const COLOURS = ["#b9ccc4", "#83a99a", "#527f68", "#255947"];
  const wrap = degrees => (degrees % 360 + 360) % 360;
  const signedDiff = (a, b) => ((a - b + 540) % 360) - 180;

  function create({ canvas, labels, data, peaks = [], onHeadingChange = () => {} }) {
    const host = canvas.parentElement;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("2D panorama canvas unavailable");
    const profile = data.profile;
    if (profile.step_deg !== 0.5 || profile.samples_per_revolution !== 720 ||
        profile.bands_near_to_far.length < 3 ||
        !profile.bands_near_to_far.every(b => b.angles_deg.length === 720)) {
      throw new Error("The source panorama profile is incomplete");
    }
    const minimumAngle = Math.min(-20, profile.min_skyline_angle_deg - 5);
    const maximumAngle = Math.max(16, profile.max_skyline_angle_deg + 6);
    let heading = 0, dragging = null, pending = false;
    let peakRecords = peaks;
    let width = 800, height = 500;
    const angleY = angle => height * ((maximumAngle - angle) / (maximumAngle - minimumAngle));
    const sampleAngle = (values, bearing) =>
      values[Math.round(wrap(bearing) / profile.step_deg) % 720];

    function renderLabels() {
      labels.replaceChildren();
      let previousX = -1000;
      const visible = peakRecords.filter(p => p.visibility === "visible" &&
        p.gdal_visible && p.independent_ray_visible &&
        Math.abs(signedDiff(p.bearing_deg, heading)) < FIELD_DEGREES / 2 - 2);
      visible.sort((a,b) => signedDiff(a.bearing_deg,heading) - signedDiff(b.bearing_deg,heading));
      for (const p of visible) {
        const x = (signedDiff(p.bearing_deg, heading) / FIELD_DEGREES + .5) * width;
        if (x - previousX < 88) continue; // Keep labels legible, not a thicket of names.
        const distance = p.distance_km * 1000;
        const groundZ = p.dem_height_m;
        const earthDrop = (6 / 7) * distance * distance / (2 * 6371008.8);
        const angle = Math.atan2(
          groundZ - data.observer_eye_altitude_m - earthDrop, distance
        ) * 180 / Math.PI;
        const y = Math.max(95, Math.min(height - 120, angleY(angle) - 9));
        const marker = document.createElement("button");
        marker.type = "button";
        marker.className = "panorama-peak";
        marker.textContent = p.name;
        marker.title = p.name + " · " + p.distance_km + " km";
        marker.style.left = x + "px";
        marker.style.top = y + "px";
        marker.addEventListener("click", e => {
          e.stopPropagation();
          setHeading(p.bearing_deg);
        });
        labels.append(marker);
        previousX = x;
      }
    }

    function paint() {
      pending = false;
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      width = Math.max(1, host.clientWidth);
      height = Math.max(1, host.clientHeight);
      const pxWidth = Math.round(width * dpr), pxHeight = Math.round(height * dpr);
      if (canvas.width !== pxWidth || canvas.height !== pxHeight) {
        canvas.width = pxWidth; canvas.height = pxHeight;
      }
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
      context.clearRect(0, 0, width, height);
      const sky = context.createLinearGradient(0, 0, 0, height);
      sky.addColorStop(0, "#e0ebe6");
      sky.addColorStop(.56, "#e9eee6");
      sky.addColorStop(1, "#eeeadd");
      context.fillStyle = sky;
      context.fillRect(0, 0, width, height);

      // Paint far-to-near range bands, so nearer ridges cover obscured ground.
      const bands = [...profile.bands_near_to_far].reverse();
      for (let layer = 0; layer < bands.length; layer++) {
        const band = bands[layer];
        context.beginPath();
        context.moveTo(0, height);
        for (let x = 0; x <= width; x += 2) {
          const bearing = wrap(heading + (x / width - .5) * FIELD_DEGREES);
          const angle = sampleAngle(band.angles_deg, bearing);
          context.lineTo(x, angleY(angle));
        }
        context.lineTo(width, height);
        context.closePath();
        context.fillStyle = COLOURS[Math.min(layer, COLOURS.length - 1)];
        context.fill();
        context.lineWidth = 1;
        context.strokeStyle = "rgba(255,255,250,.25)";
        context.stroke();
      }

      // Bearing marks remain anchored to real grid directions.
      const first = Math.floor((heading - FIELD_DEGREES / 2) / 15) * 15;
      context.fillStyle = "rgba(29,69,56,.72)";
      context.font = "700 11px system-ui,sans-serif";
      context.textAlign = "center";
      for (let bearing = first; bearing <= heading + FIELD_DEGREES / 2; bearing += 15) {
        const x = (bearing - heading) / FIELD_DEGREES * width + width / 2;
        if (x < 12 || x > width - 12) continue;
        const azimuth = wrap(bearing);
        const label = azimuth === 0 ? "N" : azimuth === 90 ? "E" :
          azimuth === 180 ? "S" : azimuth === 270 ? "W" :
          Math.round(azimuth) + "°";
        context.fillText(label, x, 36);
        context.fillRect(x, 42, 1, 7);
      }
      renderLabels();
    }

    function schedule() {
      if (pending) return;
      pending = true;
      requestAnimationFrame(paint);
    }
    function setHeading(next) {
      if (!Number.isFinite(next)) return;
      heading = wrap(next);
      onHeadingChange(heading);
      schedule();
    }
    function currentHeading() { return heading; }
    function setPeaks(next) { peakRecords = Array.isArray(next) ? next : []; schedule(); }

    host.addEventListener("pointerdown", event => {
      if (event.target.closest(".panorama-peak")) return;
      dragging = { x: event.clientX, heading };
      host.setPointerCapture(event.pointerId);
      host.classList.add("dragging");
    });
    host.addEventListener("pointermove", event => {
      if (!dragging) return;
      setHeading(dragging.heading + (dragging.x - event.clientX) / Math.max(width,1) * FIELD_DEGREES);
    });
    const release = () => { dragging = null; host.classList.remove("dragging"); };
    host.addEventListener("pointerup", release);
    host.addEventListener("pointercancel", release);
    host.addEventListener("keydown", event => {
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      event.preventDefault();
      setHeading(heading + (event.key === "ArrowRight" ? 10 : -10));
    });
    new ResizeObserver(schedule).observe(host);
    setHeading(0);
    return { setHeading, currentHeading, setPeaks, repaint: schedule };
  }
  window.SightPanorama = { create };
})();