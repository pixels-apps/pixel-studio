// Rendu « écran LED » d'une image 16×16 sur un <canvas> (pixels ronds sur fond noir).

export const SIZE = 16;
const OFF = "#1c1c1f"; // LED éteinte : légèrement visible, comme sur l'appareil

/**
 * @param {HTMLCanvasElement} canvas
 * @param {string[] | null} pixels 256 couleurs « rrggbb » (ligne par ligne), ou null
 */
export function drawLeds(canvas, pixels) {
  const ratio = window.devicePixelRatio || 1;
  const size = Math.round(canvas.getBoundingClientRect().width * ratio) || canvas.width;
  if (canvas.width !== size) canvas.width = canvas.height = size;

  const ctx = canvas.getContext("2d");
  const cell = size / SIZE;
  const radius = cell * 0.4;
  ctx.clearRect(0, 0, size, size);

  for (let y = 0; y < SIZE; y++) {
    for (let x = 0; x < SIZE; x++) {
      const hex = pixels?.[x + SIZE * y];
      const lit = hex && hex !== "000000";
      const cx = (x + 0.5) * cell;
      const cy = (y + 0.5) * cell;
      if (lit) {
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
