// Rendu « écran LED » d'une image 16×16 ou 64×64 sur un <canvas> (pixels ronds sur fond noir).

const OFF = "#1c1c1f"; // LED éteinte : légèrement visible, comme sur l'appareil
const GLOW_MAX = 16; // halo autour des LED allumées jusqu'en 16×16 (trop coûteux pour 4096 LED)

/**
 * @param {HTMLCanvasElement} canvas
 * @param {string[] | null} pixels size² couleurs « rrggbb » (ligne par ligne), ou null (16×16 éteint)
 */
export function drawLeds(canvas, pixels) {
  const ratio = window.devicePixelRatio || 1;
  const size = Math.round(canvas.getBoundingClientRect().width * ratio) || canvas.width;
  if (canvas.width !== size) canvas.width = canvas.height = size;

  const ctx = canvas.getContext("2d");
  const n = pixels ? Math.round(Math.sqrt(pixels.length)) : 16;
  const glow = n <= GLOW_MAX;
  const cell = size / n;
  const radius = cell * 0.4;
  ctx.clearRect(0, 0, size, size);

  for (let y = 0; y < n; y++) {
    for (let x = 0; x < n; x++) {
      const hex = pixels?.[x + n * y];
      const lit = hex && hex !== "000000";
      const cx = (x + 0.5) * cell;
      const cy = (y + 0.5) * cell;
      if (lit && glow) {
        ctx.shadowColor = `#${hex}`;
        ctx.shadowBlur = cell * 0.45;
      }
      ctx.fillStyle = lit ? `#${hex}` : OFF;
      ctx.beginPath();
      ctx.arc(cx, cy, radius, 0, Math.PI * 2);
      ctx.fill();
      ctx.shadowBlur = 0;
    }
  }
}

/** Redessine quand la taille affichée change (responsive, changement de densité d'écran). */
export function keepDrawn(canvas, getPixels) {
  const redraw = () => drawLeds(canvas, getPixels());
  new ResizeObserver(redraw).observe(canvas);
  return redraw;
}
