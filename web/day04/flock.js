// Visual study, not tracked wildlife. Small independent bird agents with local rules
// (separation / alignment / cohesion) and a gentle time-dependent roost attraction.
const phases = [
  { at: 0, title: "Scattered", description: "Small groups arrive from different directions." },
  { at: 26, title: "Gathering", description: "Neighbours influence one another's direction." },
  { at: 55, title: "Murmuration", description: "A constantly changing shape emerges from the crowd." },
  { at: 82, title: "Towards the reeds", description: "The flock becomes denser as dusk approaches." },
  { at: 98, title: "Roost", description: "The flock settles; the movement gradually subsides." }
];
export function getPhase(progress) {
  let current = phases[0];
  for (const phase of phases) if (progress >= phase.at) current = phase;
  return current;
}
const clamp = (n, min, max) => Math.max(min, Math.min(max, n));
function randomBird() {
  const theta = Math.random() * Math.PI * 2;
  return { x: .08 + Math.random() * .84, y: .12 + Math.random() * .76,
    vx: Math.cos(theta) * .0018, vy: Math.sin(theta) * .0018 };
}
export function createFlock(canvas, onState) {
  const context = canvas.getContext("2d");
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let width = 800, height = 440, time = 0, progress = 0, playing = !reduced, frame = 0, phase = "", raf;
  const birds = Array.from({ length: window.innerWidth < 620 ? 170 : 310 }, randomBird);
  function resize() {
    const rect = canvas.getBoundingClientRect();
    width = Math.max(1, rect.width);
    height = Math.max(1, rect.height);
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    context.setTransform(dpr, 0, 0, dpr, 0, 0);
    context.fillStyle = "#0b1621";
    context.fillRect(0, 0, width, height);
  }
  function emit() {
    const nextPhase = getPhase(progress);
    if (nextPhase.title !== phase || frame % 8 === 0) {
      phase = nextPhase.title;
      onState({ progress: Math.round(progress), playing, ...nextPhase });
    }
  }
  function draw() {
    const strength = progress / 100;
    const gather = strength * strength;
    const centerX = .5 + .1 * Math.sin(time * .00042);
    const centerY = .5 + .16 * Math.sin(time * .0007) + .12 * gather;
    // Fade previous frames rather than clearing them: recent movement leaves a ghost.
    context.fillStyle = "rgba(11, 22, 33, 0.20)";
    context.fillRect(0, 0, width, height);
    const length = birds.length;
    const near2 = .012, avoid2 = .00034;
    for (let i = 0; i < length; i++) {
      const bird = birds[i];
      let n = 0, alignX = 0, alignY = 0, cohX = 0, cohY = 0, repelX = 0, repelY = 0;
      // Strided neighbour sampling keeps mobile animation cheap.
      const stride = length > 250 ? 4 : 3;
      for (let j = (i % stride); j < length; j += stride) {
        if (i === j) continue;
        const other = birds[j], dx = other.x - bird.x, dy = other.y - bird.y;
        const d2 = dx * dx + dy * dy;
        if (d2 < near2) {
          n++; alignX += other.vx; alignY += other.vy;
          cohX += other.x; cohY += other.y;
          if (d2 < avoid2 && d2 > .0000001) {
            repelX -= dx / d2; repelY -= dy / d2;
          }
        }
      }
      const swirlX = -.25 * (bird.y - centerY);
      const swirlY = .25 * (bird.x - centerX);
      let ax = (centerX - bird.x) * (.000008 + gather * .000065) + swirlX * (.00002 + gather * .00008);
      let ay = (centerY - bird.y) * (.000008 + gather * .000065) + swirlY * (.00002 + gather * .00008);
      if (n) {
        ax += ((alignX / n) - bird.vx) * .007 + ((cohX / n) - bird.x) * .0003;
        ay += ((alignY / n) - bird.vy) * .007 + ((cohY / n) - bird.y) * .0003;
        ax += repelX * .000000013;
        ay += repelY * .000000013;
      }
      bird.vx = (bird.vx + ax) * .995;
      bird.vy = (bird.vy + ay) * .995;
      const speed = Math.hypot(bird.vx, bird.vy) || .001;
      const desired = (.0024 - .0014 * gather) * (1 + .14 * Math.sin(i * 2.3));
      bird.vx = bird.vx / speed * desired;
      bird.vy = bird.vy / speed * desired;
      bird.x += bird.vx;
      bird.y += bird.vy;
      if (bird.x < -.04 || bird.x > 1.04) { bird.vx *= -.95; bird.x = clamp(bird.x, -.035, 1.035); }
      if (bird.y < -.04 || bird.y > 1.04) { bird.vy *= -.95; bird.y = clamp(bird.y, -.035, 1.035); }
      const x = bird.x * width, y = bird.y * height;
      if (x < 0 || x > width || y < 0 || y > height) continue;
      const angle = Math.atan2(bird.vy, bird.vx);
      const size = width < 640 ? 2.7 : 3.7;
      context.save(); context.translate(x, y); context.rotate(angle);
      context.strokeStyle = i % 8 === 0 ? "rgba(245, 169, 108, .84)" : "rgba(244, 229, 204, .82)";
      context.lineWidth = .85;
      context.beginPath(); context.moveTo(-size, -size * .32);
      context.lineTo(size * .45, 0); context.lineTo(-size, size * .32);
      context.stroke(); context.restore();
    }
  }
  function tick(timestamp) {
    raf = requestAnimationFrame(tick);
    if (!playing || document.hidden) return;
    time = timestamp;
    draw();
    frame++;
    if (progress < 100) progress = Math.min(100, progress + .018);
    else playing = false;
    emit();
  }
  function setProgress(value) {
    progress = clamp(Number(value) || 0, 0, 100);
    if (progress === 100) playing = false;
    context.fillStyle = "#0b1621";
    context.fillRect(0, 0, width, height);
    draw(); emit();
  }
  function setPlaying(value) {
    playing = Boolean(value);
    if (playing && progress === 100) progress = 0;
    emit();
  }
  function replay() {
    progress = 0;
    time = 0;
    playing = true;
    birds.splice(0, birds.length, ...Array.from({ length: birds.length }, randomBird));
    context.fillStyle = "#0b1621";
    context.fillRect(0, 0, width, height);
    emit();
  }
  const observer = new ResizeObserver(resize);
  observer.observe(canvas);
  resize();
  raf = requestAnimationFrame(tick);
  emit();
  return { setProgress, setPlaying, replay, get playing() { return playing; },
    destroy() { cancelAnimationFrame(raf); observer.disconnect(); } };
}
