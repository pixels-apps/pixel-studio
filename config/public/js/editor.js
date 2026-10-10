// Éditeur de pixels 16×16 : outils, tracé continu, remplissage, annuler/rétablir.
// Les pixels sont 256 couleurs « rrggbb » (ligne par ligne, index x + 16·y) ; « 000000 » = LED éteinte.

import { SIZE } from "./led.js";

export const OFF = "000000";
const HISTORY = 100;

export class PixelEditor extends EventTarget {
  /** @param {HTMLCanvasElement} canvas */
  constructor(canvas) {
    super();
    this.canvas = canvas;
    this.pixels = Array(SIZE * SIZE).fill(OFF);
    this.tool = "pencil";
    this.color = "ffffff";
    this.undoStack = [];
    this.redoStack = [];
    this.hover = null;
    this.cursor = [0, 0]; // case active au clavier
    this.#bindPointer();
    this.#bindKeyboard();
    new ResizeObserver(() => this.render()).observe(canvas);
  }

  // --- API ---------------------------------------------------------------------------

  setTool(tool) {
    this.tool = tool;
    this.#emit("tool");
  }

  setColor(hex) {
    this.color = hex.replace("#", "").toLowerCase();
    this.#emit("color");
  }

  /** Remplace toute l'image (annulable sauf si record = false). */
  setPixels(pixels, { record = true } = {}) {
    if (pixels.length !== SIZE * SIZE) throw new Error("256 pixels attendus");
    if (record) this.#record(this.pixels);
    this.pixels = pixels.map((p) => p.toLowerCase());
    this.#changed();
  }

  clear() {
    this.setPixels(Array(SIZE * SIZE).fill(OFF));
  }

  undo() {
    if (!this.undoStack.length) return;
    this.redoStack.push(this.pixels);
    this.pixels = this.undoStack.pop();
    this.#changed();
  }

  redo() {
    if (!this.redoStack.length) return;
    this.undoStack.push(this.pixels);
    this.pixels = this.redoStack.pop();
    this.#changed();
  }

  get canUndo() { return this.undoStack.length > 0; }
  get canRedo() { return this.redoStack.length > 0; }

  // --- Rendu -------------------------------------------------------------------------

  render() {
    const ratio = window.devicePixelRatio || 1;
    const size = Math.round(this.canvas.getBoundingClientRect().width * ratio) || this.canvas.width;
    if (this.canvas.width !== size) this.canvas.width = this.canvas.height = size;
    const ctx = this.canvas.getContext("2d");
    const cell = size / SIZE;

    for (let y = 0; y < SIZE; y++) {
      for (let x = 0; x < SIZE; x++) {
        ctx.fillStyle = `#${this.pixels[x + SIZE * y]}`;
        ctx.fillRect(Math.floor(x * cell), Math.floor(y * cell), Math.ceil(cell), Math.ceil(cell));
      }
    }

    // Quadrillage (plus marqué toutes les 4 cases pour se repérer)
    ctx.lineWidth = Math.max(1, ratio * 0.5);
    for (let i = 1; i < SIZE; i++) {
      ctx.strokeStyle = i % 4 === 0 ? "rgb(128 128 128 / 0.55)" : "rgb(128 128 128 / 0.25)";
      const p = Math.round(i * cell) + 0.5;
      ctx.beginPath();
      ctx.moveTo(p, 0); ctx.lineTo(p, size);
      ctx.moveTo(0, p); ctx.lineTo(size, p);
      ctx.stroke();
    }

    // Case survolée
    if (this.hover) {
      const [x, y] = this.hover;
      ctx.lineWidth = Math.max(2, ratio * 1.5);
      ctx.strokeStyle = "rgb(255 255 255 / 0.9)";
      ctx.strokeRect(x * cell + 1, y * cell + 1, cell - 2, cell - 2);
      ctx.strokeStyle = "rgb(0 0 0 / 0.6)";
      ctx.strokeRect(x * cell + 3, y * cell + 3, cell - 6, cell - 6);
    }
  }

  // --- Interaction -------------------------------------------------------------------

  #bindPointer() {
    let stroke = null; // { before, last: [x, y] }

    const cellAt = (event) => {
      const rect = this.canvas.getBoundingClientRect();
      const x = Math.floor(((event.clientX - rect.left) / rect.width) * SIZE);
      const y = Math.floor(((event.clientY - rect.top) / rect.height) * SIZE);
      return x >= 0 && x < SIZE && y >= 0 && y < SIZE ? [x, y] : null;
    };

    this.canvas.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      const cell = cellAt(event);
      if (!cell) return;
      event.preventDefault();
      const [x, y] = cell;
      const tool = event.altKey ? "pick" : this.tool;
      if (tool === "pick" || tool === "fill") {
        this.#applyOnce(x, y, tool);
        return;
      }
      this.canvas.setPointerCapture(event.pointerId);
      stroke = { before: this.pixels.slice(), last: cell, changed: false };
      stroke.changed = this.#paint(x, y);
      if (stroke.changed) this.#changed({ live: true });
    });

    this.canvas.addEventListener("pointermove", (event) => {
      const cell = cellAt(event);
      const hoverChanged = String(cell) !== String(this.hover);
      this.hover = event.pointerType === "mouse" ? cell : null;
      if (stroke && cell) {
        let changed = false;
        for (const [x, y] of line(stroke.last, cell)) changed = this.#paint(x, y) || changed;
        stroke.last = cell;
        if (changed) {
          stroke.changed = true;
          this.#changed({ live: true });
          return;
        }
      }
      if (hoverChanged) this.render();
    });

    const end = () => {
      if (!stroke) return;
      if (stroke.changed) {
        this.#record(stroke.before);
        this.#changed();
      }
      stroke = null;
    };
    this.canvas.addEventListener("pointerup", end);
    this.canvas.addEventListener("pointercancel", end);
    this.canvas.addEventListener("pointerleave", () => {
      this.hover = null;
      this.render();
    });
    this.canvas.addEventListener("contextmenu", (e) => e.preventDefault());
  }

  /** Outil appliqué en un seul geste (clic ou touche) : une entrée d'historique. */
  #applyOnce(x, y, tool = this.tool) {
    if (tool === "pick") {
      this.setColor(this.pixels[x + SIZE * y]);
      if (this.tool === "pick") this.setTool("pencil");
      return;
    }
    const before = this.pixels.slice();
    const changed = tool === "fill" ? this.#fill(x, y, this.color) : this.#paint(x, y);
    if (changed) {
      this.#record(before);
      this.#changed();
    }
  }

  /** Grille utilisable au clavier : flèches = déplacer, Espace/Entrée = appliquer l'outil. */
  #bindKeyboard() {
    this.canvas.tabIndex = 0;
    const show = () => {
      this.hover = this.cursor;
      this.render();
      const [x, y] = this.cursor;
      this.dispatchEvent(new CustomEvent("cursor", {
        detail: { x, y, color: this.pixels[x + SIZE * y] },
      }));
    };
    this.canvas.addEventListener("focus", show);
    this.canvas.addEventListener("blur", () => {
      this.hover = null;
      this.render();
    });
    this.canvas.addEventListener("keydown", (event) => {
      const moves = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
      const move = moves[event.key];
      if (move) {
        event.preventDefault();
        const step = event.shiftKey ? 4 : 1; // Maj + flèche : saut de 4 cases (repères du quadrillage)
        this.cursor = this.cursor.map((v, i) => Math.min(SIZE - 1, Math.max(0, v + move[i] * step)));
        show();
      } else if (event.key === " " || event.key === "Enter") {
        event.preventDefault();
        this.#applyOnce(...this.cursor);
        show();
      }
    });
  }

  #paint(x, y) {
    const i = x + SIZE * y;
    const color = this.tool === "eraser" ? OFF : this.color;
    if (this.pixels[i] === color) return false;
    this.pixels[i] = color;
    return true;
  }

  #fill(x, y, color) {
    const target = this.pixels[x + SIZE * y];
    if (target === color) return false;
    const stack = [[x, y]];
    while (stack.length) {
      const [cx, cy] = stack.pop();
      if (cx < 0 || cy < 0 || cx >= SIZE || cy >= SIZE) continue;
      const i = cx + SIZE * cy;
      if (this.pixels[i] !== target) continue;
      this.pixels[i] = color;
      stack.push([cx + 1, cy], [cx - 1, cy], [cx, cy + 1], [cx, cy - 1]);
    }
    return true;
  }

  #record(before) {
    this.undoStack.push(before.slice());
    if (this.undoStack.length > HISTORY) this.undoStack.shift();
    this.redoStack = [];
  }

  /** live = pendant un tracé (pas encore d'entrée d'historique). */
  #changed({ live = false } = {}) {
    this.render();
    this.dispatchEvent(new CustomEvent("change", { detail: { live } }));
  }

  #emit(type) {
    this.dispatchEvent(new Event(type));
  }
}

/** Cases traversées entre deux points (Bresenham), pour un tracé continu. */
function* line([x0, y0], [x1, y1]) {
  const dx = Math.abs(x1 - x0), dy = -Math.abs(y1 - y0);
  const sx = x0 < x1 ? 1 : -1, sy = y0 < y1 ? 1 : -1;
  let err = dx + dy;
  for (;;) {
    yield [x0, y0];
    if (x0 === x1 && y0 === y1) return;
    const e2 = 2 * err;
    if (e2 >= dy) { err += dy; x0 += sx; }
    if (e2 <= dx) { err += dx; y0 += sy; }
  }
}
