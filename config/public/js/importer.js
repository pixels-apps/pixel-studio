// Import d'image : réduction d'une image quelconque en 16×16 ou 64×64 dans le navigateur.

const WORK = 512; // toile de travail 512×512 : 32×32 pixels par case en 16×16, 8×8 en 64×64

/** Fichier ou Blob (PNG, JPEG, GIF → 1re image, WebP…) → ImageBitmap. */
export async function loadImage(blob) {
  if (!blob.type.startsWith("image/")) throw new Error("Ce fichier n'est pas une image.");
  try {
    return await createImageBitmap(blob);
  } catch {
    throw new Error("Image illisible ou format non pris en charge.");
  }
}

/**
 * Pixel art probable : petite image, ou peu de couleurs distinctes (≤ 64).
 * Sert à choisir le rendu « net » par défaut.
 */
export function looksLikePixelArt(image) {
  if (Math.max(image.width, image.height) <= 64) return true;
  if (image.width * image.height > 1024 * 1024) return false;
  const canvas = new OffscreenCanvas(image.width, image.height);
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  ctx.drawImage(image, 0, 0);
  const data = ctx.getImageData(0, 0, image.width, image.height).data;
  const seen = new Set();
  for (let i = 0; i < data.length; i += 4) {
    seen.add((data[i] << 24) | (data[i + 1] << 16) | (data[i + 2] << 8) | data[i + 3]);
    if (seen.size > 64) return false;
  }
  return true;
}

/**
 * Réduit une image en size² couleurs « rrggbb ».
 * @param {ImageBitmap} image
 * @param {{ fit: "cover" | "contain" | "stretch", mode: "smooth" | "sharp", size: 16 | 64 }} options
 *   fit : cover = remplir (recadre au centre), contain = ajuster (bandes noires), stretch = étirer
 *   mode : smooth = moyenne de chaque case (photos), sharp = couleur majoritaire (pixel art)
 */
export function imageToPixels(image, { fit = "cover", mode = "smooth", size = 16 } = {}) {
  const cell = WORK / size;
  const canvas = new OffscreenCanvas(WORK, WORK);
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, WORK, WORK);
  ctx.imageSmoothingEnabled = mode === "smooth";
  ctx.imageSmoothingQuality = "high";

  const { sx, sy, sw, sh, dx, dy, dw, dh } = geometry(image.width, image.height, fit);
  ctx.drawImage(image, sx, sy, sw, sh, dx, dy, dw, dh);
  const data = ctx.getImageData(0, 0, WORK, WORK).data;

  const pixels = [];
  for (let cy = 0; cy < size; cy++) {
    for (let cx = 0; cx < size; cx++) {
      pixels.push(mode === "sharp" ? dominant(data, cx, cy, cell) : average(data, cx, cy, cell));
    }
  }
  return pixels;
}

function geometry(w, h, fit) {
  const full = { sx: 0, sy: 0, sw: w, sh: h, dx: 0, dy: 0, dw: WORK, dh: WORK };
  if (fit === "stretch") return full;
  const ratio = w / h;
  if (fit === "cover") {
    // recadre la source au centre pour obtenir un carré
    return ratio > 1
      ? { ...full, sx: (w - h) / 2, sw: h }
      : { ...full, sy: (h - w) / 2, sh: w };
  }
  // contain : toute l'image, centrée, bandes noires
  return ratio > 1
    ? { ...full, dh: WORK / ratio, dy: (WORK - WORK / ratio) / 2 }
    : { ...full, dw: WORK * ratio, dx: (WORK - WORK * ratio) / 2 };
}

const hex = (r, g, b) => ((1 << 24) | (r << 16) | (g << 8) | b).toString(16).slice(1);

function* cellPixels(data, cx, cy, cell) {
  for (let y = cy * cell; y < (cy + 1) * cell; y++) {
    for (let x = cx * cell; x < (cx + 1) * cell; x++) {
      const i = (x + y * WORK) * 4;
      yield [data[i], data[i + 1], data[i + 2]];
    }
  }
}

function average(data, cx, cy, cell) {
  let r = 0, g = 0, b = 0, n = 0;
  for (const [pr, pg, pb] of cellPixels(data, cx, cy, cell)) {
    r += pr; g += pg; b += pb; n++;
  }
  return hex(Math.round(r / n), Math.round(g / n), Math.round(b / n));
}

function dominant(data, cx, cy, cell) {
  const counts = new Map();
  let best = "000000", bestCount = 0;
  for (const [r, g, b] of cellPixels(data, cx, cy, cell)) {
    const key = hex(r, g, b);
    const count = (counts.get(key) ?? 0) + 1;
    counts.set(key, count);
    if (count > bestCount) { best = key; bestCount = count; }
  }
  return best;
}
