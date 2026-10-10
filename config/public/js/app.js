import { api, ApiError } from "./api.js";
import { PixelEditor } from "./editor.js";
import { GalleryView } from "./gallery.js";
import { imageToPixels, loadImage, looksLikePixelArt } from "./importer.js";
import { drawLeds, keepDrawn } from "./led.js";

const $ = (id) => document.getElementById(id);
const VIEW_LABELS = { clock: "Horloge", light: "Lumière" };
const PRESETS = ["ff0000", "ff8800", "ffd000", "33cc55", "00a0ff", "3344ff", "b040ff", "ffffff"];

const ui = {
  connection: $("connection"),
  connectionLabel: $("connection-label"),
  refresh: $("refresh"),
  view: $("state-view"),
  swatch: $("state-swatch"),
  color: $("state-color"),
  brightnessState: $("state-brightness"),
  updated: $("state-updated"),
  viewButtons: [...document.querySelectorAll("[data-view]")],
  brightness: $("brightness"),
  brightnessValue: $("brightness-value"),
  colorInput: $("color"),
  presets: $("presets"),
  applyColor: $("apply-color"),
  toast: $("toast"),
  // éditeur
  tools: [...document.querySelectorAll("[data-tool]")],
  undo: $("undo"),
  redo: $("redo"),
  clear: $("clear"),
  paintColor: $("paint-color"),
  paintHex: $("paint-hex"),
  palette: $("palette"),
  recent: $("recent"),
  preview: $("preview"),
  send: $("send"),
  autoSend: $("auto-send"),
  dirty: $("dirty"),
};

// --- Connexion et messages -----------------------------------------------------------

function setConnection(state, label) {
  ui.connection.dataset.state = state;
  ui.connectionLabel.textContent = label;
}

let toastTimer;
function toast(message, kind = "info") {
  ui.toast.textContent = message;
  ui.toast.dataset.kind = kind;
  ui.toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (ui.toast.hidden = true), kind === "error" ? 6000 : 2500);
}

/** Exécute une action sur l'appareil, une à la fois, et met à jour l'interface. */
let queue = Promise.resolve();
function run(action, { busy = [] } = {}) {
  const task = queue.then(async () => {
    busy.forEach((el) => (el.disabled = true));
    setConnection("busy", "Envoi…");
    try {
      const state = await action();
      if (state?.view !== undefined) showState(state);
      setConnection("ok", "Connecté");
      return state;
    } catch (e) {
      const unavailable = e instanceof ApiError && e.unavailable;
      setConnection(unavailable ? "down" : "ok", unavailable ? "Relais indisponible" : "Connecté");
      ui.connection.title = unavailable ? e.message : "";
      toast(unavailable
        ? (e.status === 0
          ? "Serveur injoignable : l'application pixel-studio est-elle lancée ?"
          : "Timebox injoignable : vérifiez que timebox-bridge est lancé et l'appareil allumé.")
        : e.message, "error");
    } finally {
      busy.forEach((el) => (el.disabled = false));
    }
  });
  queue = task.catch(() => {});
  return task;
}

// --- État de l'appareil --------------------------------------------------------------

function showState(state) {
  ui.view.textContent = VIEW_LABELS[state.view] ?? state.view;
  ui.swatch.style.background = `#${state.light_color}`;
  ui.color.textContent = `#${state.light_color}`;
  // Décodage partiel de l'état : dans certains modes, l'octet lu n'est pas une luminosité (0–100)
  const knownBrightness = state.brightness >= 0 && state.brightness <= 100;
  ui.brightnessState.textContent = knownBrightness ? `${state.brightness} %` : "?";
  ui.brightnessState.title = knownBrightness ? "" : `valeur brute ${state.brightness} (mode non décodé)`;
  ui.updated.textContent = `Lu à ${new Date().toLocaleTimeString()}`;
  ui.viewButtons.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.view === state.view)));
  if (knownBrightness && document.activeElement !== ui.brightness) {
    ui.brightness.value = state.brightness;
    ui.brightnessValue.value = state.brightness;
  }
}

async function refresh() {
  ui.refresh.setAttribute("aria-busy", "true");
  await run(() => api.state(), { busy: [ui.refresh] });
  ui.refresh.removeAttribute("aria-busy");
}

// --- Contrôles -----------------------------------------------------------------------

ui.refresh.addEventListener("click", refresh);

ui.viewButtons.forEach((button) =>
  button.addEventListener("click", () => run(() => api.view(button.dataset.view), { busy: ui.viewButtons })),
);

ui.brightness.addEventListener("input", () => (ui.brightnessValue.value = ui.brightness.value));
ui.brightness.addEventListener("change", () => run(() => api.brightness(ui.brightness.value)));

for (const hex of PRESETS) {
  const b = document.createElement("button");
  b.type = "button";
  b.style.background = `#${hex}`;
  b.title = b.ariaLabel = `#${hex}`;
  b.addEventListener("click", () => (ui.colorInput.value = `#${hex}`));
  ui.presets.append(b);
}

ui.applyColor.addEventListener("click", () =>
  run(() => api.color(ui.colorInput.value.slice(1), ui.brightness.value), { busy: [ui.applyColor] }),
);

// --- Éditeur -------------------------------------------------------------------------

const editor = new PixelEditor($("editor"));
const redrawPreview = keepDrawn(ui.preview, () => editor.pixels);
const cursorStatus = $("cursor-status");
editor.addEventListener("cursor", ({ detail: { x, y, color } }) => {
  cursorStatus.textContent = `Colonne ${x + 1}, ligne ${y + 1} : ${color === "000000" ? "éteinte" : `#${color}`}`;
});

const BASE_PALETTE = [
  "000000", "ffffff", "808080", "ff0000", "ff8800", "ffd000", "88ff00", "00c040",
  "00e0c0", "00a0ff", "0040ff", "8040ff", "ff40c0", "ff8080", "804020", "ffd8a0",
];
const RECENT_MAX = 16;
const DRAFT_KEY = "pixel-studio.draft";
const storage = {
  get(key) { try { return JSON.parse(localStorage.getItem(key)); } catch { return null; } },
  set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* indisponible */ } },
};

let recent = storage.get("pixel-studio.recent") ?? [];
let sentPixels = null; // dernière image envoyée (pour l'indicateur « modifié »)

function swatch(hex, onPick) {
  const b = document.createElement("button");
  b.type = "button";
  b.style.background = `#${hex}`;
  b.dataset.hex = hex;
  b.title = b.ariaLabel = `#${hex}`;
  b.addEventListener("click", () => onPick(hex));
  return b;
}

function renderPalettes() {
  ui.recent.replaceChildren(...recent.map((hex) => swatch(hex, pickColor)));
  for (const b of document.querySelectorAll(".palette button")) {
    b.setAttribute("aria-pressed", String(b.dataset.hex === editor.color));
  }
}

function pickColor(hex) {
  editor.setColor(hex);
  if (editor.tool === "eraser" || editor.tool === "pick") editor.setTool("pencil");
}

function rememberColor(hex) {
  if (recent[0] === hex) return;
  recent = [hex, ...recent.filter((c) => c !== hex)].slice(0, RECENT_MAX);
  storage.set("pixel-studio.recent", recent);
  renderPalettes();
}

ui.palette.append(...BASE_PALETTE.map((hex) => swatch(hex, pickColor)));

editor.addEventListener("tool", () =>
  ui.tools.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.tool === editor.tool))),
);
editor.addEventListener("color", () => {
  ui.paintColor.value = `#${editor.color}`;
  ui.paintHex.textContent = `#${editor.color}`;
  renderPalettes();
});

function updateDirty() {
  ui.dirty.hidden = sentPixels !== null && sentPixels.every((p, i) => p === editor.pixels[i]);
  ui.dirty.textContent = sentPixels === null ? "pas encore envoyé" : "modifié depuis l'envoi";
  ui.undo.disabled = !editor.canUndo;
  ui.redo.disabled = !editor.canRedo;
}

editor.addEventListener("change", (event) => {
  redrawPreview();
  updateDirty();
  updateSavedState(); // déclarée plus bas : appelée seulement après le chargement du module
  if (!event.detail.live) {
    storage.set(DRAFT_KEY, editor.pixels);
    if (editor.tool === "pencil" || editor.tool === "fill") rememberColor(editor.color);
  }
  if (ui.autoSend.checked) scheduleAutoSend();
});

ui.tools.forEach((b) => b.addEventListener("click", () => editor.setTool(b.dataset.tool)));
ui.undo.addEventListener("click", () => editor.undo());
ui.redo.addEventListener("click", () => editor.redo());
ui.clear.addEventListener("click", () => editor.clear());
ui.paintColor.addEventListener("input", () => pickColor(ui.paintColor.value.slice(1)));

// Envoi : manuel, ou automatique au plus toutes les 300 ms (l'image la plus récente)
async function sendImage() {
  const pixels = editor.pixels.slice();
  const result = await run(() => api.sendImage(pixels), { busy: [ui.send] });
  if (result) {
    sentPixels = pixels;
    updateDirty();
  }
}

let autoTimer = null;
function scheduleAutoSend() {
  autoTimer ??= setTimeout(() => {
    autoTimer = null;
    sendImage();
  }, 300);
}

ui.send.addEventListener("click", sendImage);
ui.autoSend.addEventListener("change", () => ui.autoSend.checked && scheduleAutoSend());

// Raccourcis clavier
const SHORTCUTS = { b: "pencil", e: "eraser", g: "fill", i: "pick" };
document.addEventListener("keydown", (event) => {
  if (document.querySelector("dialog[open]")) return;
  // Ne pas intercepter la saisie de texte (les cases à cocher, curseurs, etc. laissent passer)
  if (event.target.closest("textarea, select, input:not([type=checkbox], [type=range], [type=color], [type=radio])")) return;
  const key = event.key.toLowerCase();
  if ((event.metaKey || event.ctrlKey) && key === "z") {
    event.preventDefault();
    event.shiftKey ? editor.redo() : editor.undo();
  } else if ((event.metaKey || event.ctrlKey) && key === "y") {
    event.preventDefault();
    editor.redo();
  } else if (!event.metaKey && !event.ctrlKey && !event.altKey && SHORTCUTS[key]) {
    editor.setTool(SHORTCUTS[key]);
  }
});

// --- Galerie et document courant ----------------------------------------------------

const docUi = {
  name: $("doc-name"),
  savedState: $("saved-state"),
  save: $("save"),
  saveCopy: $("save-copy"),
  newImage: $("new-image"),
};
const DOC_KEY = "pixel-studio.doc";
let doc = storage.get(DOC_KEY) ?? { id: null, name: "" }; // image de la galerie en cours d'édition
let galleryItems = [];

const sameStrings = (a, b) => a.length === b.length && a.every((v, i) => v === b[i]);

function setDoc(next) {
  doc = { id: next.id ?? null, name: next.name ?? "" };
  storage.set(DOC_KEY, doc);
  docUi.name.value = doc.name;
  docUi.saveCopy.hidden = !doc.id;
  updateSavedState();
  galleryView.render(galleryItems, doc.id);
}

function updateSavedState() {
  const saved = doc.id && galleryItems.find((i) => i.id === doc.id);
  const clean = saved && saved.name === (docUi.name.value.trim() || "Sans titre")
    && sameStrings(saved.pixels, editor.pixels);
  docUi.savedState.hidden = false;
  docUi.savedState.textContent = !doc.id ? "non enregistrée" : clean ? "enregistrée" : "modifications non enregistrées";
}

/** Action sur la galerie (pas sur l'appareil) : erreurs signalées sans toucher à l'état de connexion. */
async function galleryAction(action, busy = []) {
  busy.forEach((el) => (el.disabled = true));
  try {
    return await action();
  } catch (e) {
    toast(e.message, "error");
  } finally {
    busy.forEach((el) => (el.disabled = false));
  }
}

async function loadGallery() {
  const items = await galleryAction(() => api.gallery());
  if (items) galleryItems = items;
  if (doc.id && items && !items.some((i) => i.id === doc.id)) doc.id = null; // supprimée ailleurs
  setDoc(doc);
}

async function save({ copy = false } = {}) {
  const name = docUi.name.value.trim() || "Sans titre";
  const pixels = editor.pixels.slice();
  const item = await galleryAction(async () => {
    if (doc.id && !copy) {
      try {
        return await api.galleryUpdate(doc.id, { name, pixels });
      } catch (e) {
        if (!(e instanceof ApiError && e.status === 404)) throw e; // supprimée entre-temps : on recrée
      }
    }
    return api.galleryCreate(copy ? `${name} (copie)`.slice(0, 60) : name, pixels);
  }, [docUi.save, docUi.saveCopy]);
  if (!item) return;
  doc = { id: item.id, name: item.name };
  await loadGallery();
  toast(copy ? `Copie enregistrée : « ${item.name} »` : `« ${item.name} » enregistrée`);
}

const galleryView = new GalleryView({
  list: $("gallery"),
  empty: $("gallery-empty"),
  count: $("gallery-count"),
  template: $("tile-template"),
  actions: {
    open(item) {
      editor.setPixels(item.pixels); // annulable
      setDoc({ id: item.id, name: item.name });
    },
    async send(item) {
      const result = await run(() => api.gallerySend(item.id));
      if (result) {
        sentPixels = result.pixels;
        updateDirty();
        toast(`« ${item.name} » affichée sur le Timebox`);
      }
    },
    async rename(item, name) {
      const updated = await galleryAction(() => api.galleryUpdate(item.id, { name }));
      if (!updated) return;
      if (doc.id === item.id) doc.name = updated.name;
      await loadGallery();
    },
    async remove(item) {
      const ok = await galleryAction(() => api.galleryDelete(item.id).then(() => true));
      if (!ok) return;
      if (doc.id === item.id) doc.id = null; // le dessin reste dans l'éditeur, non enregistré
      await loadGallery();
      toast(`« ${item.name} » supprimée`);
    },
  },
});

docUi.save.addEventListener("click", () => save());
docUi.saveCopy.addEventListener("click", () => save({ copy: true }));
docUi.name.addEventListener("input", () => {
  doc.name = docUi.name.value;
  storage.set(DOC_KEY, doc);
  updateSavedState();
});
docUi.name.addEventListener("keydown", (e) => e.key === "Enter" && docUi.name.blur());
docUi.newImage.addEventListener("click", () => {
  editor.clear(); // annulable
  setDoc({ id: null, name: "" });
  docUi.name.focus();
});

// Raccourci ⌘S / Ctrl+S : enregistrer
document.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
    e.preventDefault();
    save();
  }
});

// --- Import d'image -----------------------------------------------------------------

const importUi = {
  button: $("import"),
  file: $("import-file"),
  dialog: $("import-dialog"),
  form: $("import-dialog").querySelector("form"),
  source: $("import-source"),
  name: $("import-name"),
  preview: $("import-preview"),
  card: $("editor-card"),
};
let importing = null; // { image, url, pixels }

function importOptions() {
  const form = new FormData(importUi.form);
  return { fit: form.get("fit"), mode: form.get("mode") };
}

function updateImportPreview() {
  if (!importing) return;
  importing.pixels = imageToPixels(importing.image, importOptions());
  drawLeds(importUi.preview, importing.pixels);
}

async function openImport(blob, name) {
  try {
    const image = await loadImage(blob);
    if (importing) URL.revokeObjectURL(importing.url);
    importing = { image, url: URL.createObjectURL(blob), pixels: null };
    importUi.source.src = importing.url;
    importUi.name.textContent = `${name || "image collée"} · ${image.width}×${image.height}`;
    importUi.form.elements.mode.value = looksLikePixelArt(image) ? "sharp" : "smooth";
    importUi.dialog.showModal();
    updateImportPreview(); // après showModal : le canvas a sa taille d'affichage
  } catch (e) {
    toast(e.message, "error");
  }
}

importUi.form.addEventListener("change", updateImportPreview);
importUi.dialog.addEventListener("close", () => {
  if (importUi.dialog.returnValue === "import" && importing?.pixels) {
    editor.setPixels(importing.pixels); // annulable
    toast("Image importée dans l'éditeur");
  }
  importUi.file.value = "";
});

importUi.button.addEventListener("click", () => importUi.file.click());
importUi.file.addEventListener("change", () => {
  const file = importUi.file.files[0];
  if (file) openImport(file, file.name);
});

// Glisser-déposer sur l'éditeur
let dragDepth = 0;
importUi.card.addEventListener("dragenter", (e) => {
  if (![...e.dataTransfer.types].includes("Files")) return;
  e.preventDefault();
  dragDepth++;
  importUi.card.classList.add("dropping");
});
importUi.card.addEventListener("dragover", (e) => e.preventDefault());
importUi.card.addEventListener("dragleave", () => {
  if (--dragDepth <= 0) { dragDepth = 0; importUi.card.classList.remove("dropping"); }
});
importUi.card.addEventListener("drop", (e) => {
  e.preventDefault();
  dragDepth = 0;
  importUi.card.classList.remove("dropping");
  const file = [...e.dataTransfer.files].find((f) => f.type.startsWith("image/"));
  if (file) openImport(file, file.name);
  else toast("Déposez un fichier image (PNG, JPEG, GIF…)", "error");
});

// Coller une image (⌘V / Ctrl+V)
document.addEventListener("paste", (e) => {
  if (e.target.closest("textarea, input:not([type=checkbox], [type=range], [type=color], [type=radio])")) return;
  const item = [...(e.clipboardData?.items ?? [])].find((i) => i.type.startsWith("image/"));
  if (!item) return;
  e.preventDefault();
  openImport(item.getAsFile(), "image collée");
});

// --- Démarrage -----------------------------------------------------------------------

async function start() {
  editor.setTool("pencil");
  editor.setColor("ff8800");
  renderPalettes();

  let lastImage = null;
  try {
    lastImage = (await api.lastImage())?.pixels ?? null;
  } catch { /* serveur indisponible : l'indicateur de connexion le signale */ }
  sentPixels = lastImage;

  // Brouillon local en priorité, sinon dernière image envoyée
  const draft = storage.get(DRAFT_KEY);
  const initial = Array.isArray(draft) && draft.length === 256 ? draft : lastImage;
  if (initial) editor.setPixels(initial, { record: false });
  else editor.render();
  updateDirty();
  await loadGallery();
}

refresh();
start();
