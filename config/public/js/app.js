import { api, ApiError } from "./api.js";
import { PixelEditor, SIZES } from "./editor.js";
import { GalleryView } from "./gallery.js";
import { imageToPixels, loadImage, looksLikePixelArt } from "./importer.js";
import { drawLeds, keepDrawn } from "./led.js";

const $ = (id) => document.getElementById(id);
const VIEW_LABELS = {
  clock: "Horloge", light: "Lumière",
  faces: "Cadrans", cloud: "Cloud", visualizer: "Visualiseur", custom: "Personnalisé",
};
const PRESETS = ["ff0000", "ff8800", "ffd000", "33cc55", "00a0ff", "3344ff", "b040ff", "ffffff"];

const ui = {
  device: $("device"),
  capabilityBlocks: [...document.querySelectorAll("[data-capability]")],
  connection: $("connection"),
  connectionLabel: $("connection-label"),
  refresh: $("refresh"),
  view: $("state-view"),
  viewLabel: $("state-view-label"),
  power: $("state-power"),
  channelButtons: [...document.querySelectorAll("[data-channel]")],
  screenToggle: $("screen-toggle"),
  sizeBadge: $("size-badge"),
  swatch: $("state-swatch"),
  color: $("state-color"),
  brightnessState: $("state-brightness"),
  updated: $("state-updated"),
  viewButtons: [...document.querySelectorAll("[data-view]")],
  brightness: $("brightness"),
  brightnessValue: $("brightness-value"),
  colorInput: $("color"),
  colorTitle: $("color-title"),
  colorLabel: $("state-color-label"),
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

// --- Appareil actif --------------------------------------------------------------------

let device = null; // { id, name, kind, size, address, capabilities }

function deviceName() {
  return device ? `« ${device.name} »` : "l'appareil";
}

function showDevices(list) {
  ui.device.replaceChildren(...list.devices.map((d) => new Option(d.name, d.id, d.active, d.active)));
  ui.device.disabled = list.devices.length < 2;
  device = list.devices.find((d) => d.active) ?? null;
  ui.device.title = device ? `${device.name} — ${device.address}` : "Appareil piloté";
  // N'affiche que les commandes que l'appareil sait faire (couleur unie, écrans…)
  ui.capabilityBlocks.forEach((el) => (el.hidden = !device?.capabilities.includes(el.dataset.capability)));
  ui.viewLabel.textContent = device?.capabilities.includes("channels") ? "Canal" : "Écran";
  updateSendState();
  if (devicesUi.dialog.open) renderDeviceList(list);
}

/** L'image n'est envoyée qu'à un appareil de même taille (sinon : copie convertie, depuis la galerie). */
function sizeMismatch() {
  return device && editor.size !== device.size;
}

function updateSendState() {
  const mismatch = sizeMismatch();
  ui.send.disabled = !!mismatch;
  ui.send.title = mismatch
    ? `Image ${editor.size}×${editor.size} : ${deviceName()} affiche du ${device.size}×${device.size}. `
      + "Enregistrez-la puis copiez-la à la bonne taille depuis la galerie, ou créez une nouvelle image."
    : `Afficher sur ${deviceName()}`;
}

async function loadDevices() {
  try {
    showDevices(await api.devices());
  } catch { /* serveur indisponible : l'indicateur de connexion le signale */ }
}

async function activate(id) {
  try {
    showDevices(await api.activate(id));
  } catch (e) {
    toast(e.message, "error");
    await loadDevices();
    return false;
  }
  await deviceChanged();
  return true;
}

/** Après un changement d'appareil actif : l'image en cours d'édition est conservée ; on la compare
 *  désormais à la dernière image envoyée à cet appareil. */
async function deviceChanged() {
  try {
    sentPixels = (await api.lastImage())?.pixels ?? null;
  } catch { sentPixels = null; }
  updateDirty();
  await refresh();
}

ui.device.addEventListener("change", () => activate(ui.device.value));

// --- Gestion des appareils (ajout, test, retrait) ---------------------------------------

const devicesUi = {
  dialog: $("devices-dialog"),
  open: $("manage-devices"),
  list: $("device-list"),
  form: $("device-form"),
  test: $("device-test"),
  add: $("device-add"),
  result: $("device-test-result"),
  hint: $("device-hint"),
};
const KIND_LABELS = { bluetooth: "Bluetooth", wifi: "Wi-Fi" }; // l'adresse Bluetooth dit déjà « relais … »
const KIND_FORM = {
  wifi: { port: "9000", host: "192.168.1.50",
    hint: "Wi-Fi : adresse IP de l'appareil (visible dans l'application Divoom ou sur la box) ; port 9000 pour le Pixoo-64 II, 80 pour le Pixoo-64 d'origine." },
  bluetooth: { port: "7777", host: "127.0.0.1",
    hint: "Bluetooth : adresse du relais Timebox Bridge (cette machine : 127.0.0.1) ; l'appareil se choisit dans le menu du relais." },
};

function renderDeviceList(list) {
  devicesUi.list.replaceChildren(...list.devices.map((d) => {
    const li = document.createElement("li");
    const meta = document.createElement("div");
    meta.className = "device-meta";
    const name = document.createElement("strong");
    name.textContent = d.active ? `${d.name} · actif` : d.name;
    const details = document.createElement("span");
    details.className = "muted small";
    details.textContent = `${KIND_LABELS[d.kind] ?? d.kind} · ${d.address} · ${d.size}×${d.size}`;
    meta.append(name, details);

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "secondary";
    remove.textContent = "Retirer";
    remove.disabled = list.devices.length < 2;
    remove.title = remove.disabled ? "Dernier appareil : ajoutez-en un autre avant de le retirer" : `Retirer « ${d.name} »`;
    let armed = false;
    remove.addEventListener("click", async () => {
      if (!armed) { // confirmation en deux clics
        armed = true;
        remove.textContent = "Confirmer";
        setTimeout(() => { armed = false; remove.textContent = "Retirer"; }, 4000);
        return;
      }
      const wasActive = d.active;
      try {
        await api.removeDevice(d.id);
        showDevices(await api.devices());
        toast(`« ${d.name} » retiré`);
        if (wasActive) await deviceChanged();
      } catch (e) {
        toast(e.message, "error");
      }
    });
    li.append(meta, remove);
    return li;
  }));
}

function deviceFormValues() {
  const form = new FormData(devicesUi.form);
  const port = form.get("port");
  return { name: form.get("name").trim(), kind: form.get("kind"), host: form.get("host").trim(),
    port: port ? Number(port) : null };
}

function showDeviceKind() {
  const kind = KIND_FORM[deviceFormValues().kind];
  devicesUi.form.elements.port.placeholder = kind.port;
  devicesUi.form.elements.host.placeholder = kind.host;
  devicesUi.hint.textContent = kind.hint;
  showTestResult("");
}

function showTestResult(message, kind = "") {
  devicesUi.result.textContent = message;
  devicesUi.result.dataset.kind = kind;
}

devicesUi.open.addEventListener("click", async () => {
  try {
    renderDeviceList(await api.devices());
  } catch (e) {
    toast(e.message, "error");
    return;
  }
  showDeviceKind();
  devicesUi.dialog.showModal();
});
devicesUi.form.addEventListener("change", (e) => e.target.name === "kind" && showDeviceKind());
// Entrée dans un champ : ne ferme pas la fenêtre (seul le bouton Fermer la ferme)
devicesUi.form.addEventListener("submit", (e) => e.submitter?.value !== "cancel" && e.preventDefault());

devicesUi.test.addEventListener("click", async () => {
  if (!devicesUi.form.reportValidity()) return;
  showTestResult("Test en cours…");
  devicesUi.test.disabled = true;
  try {
    const state = await api.testDevice(deviceFormValues());
    showTestResult(`Appareil joignable : ${VIEW_LABELS[state.view] ?? state.view}, luminosité ${state.brightness} %.`, "ok");
  } catch (e) {
    showTestResult(e.message, "error");
  } finally {
    devicesUi.test.disabled = false;
  }
});

devicesUi.add.addEventListener("click", async () => {
  if (!devicesUi.form.reportValidity()) return;
  devicesUi.add.disabled = true;
  try {
    const added = await api.addDevice(deviceFormValues());
    devicesUi.form.reset();
    showDeviceKind();
    if (await activate(added.id)) toast(`« ${added.name} » ajouté et sélectionné`);
  } catch (e) {
    showTestResult(e.message, "error");
  } finally {
    devicesUi.add.disabled = false;
  }
});

function unavailableMessage() {
  if (device?.kind === "bluetooth") {
    return `${deviceName()} injoignable : vérifiez que le relais Bluetooth (Timebox Bridge) est lancé et l'appareil allumé.`;
  }
  return `${deviceName()} injoignable : vérifiez son adresse et qu'il est allumé.`;
}

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
      setConnection(unavailable ? "down" : "ok", unavailable ? "Appareil indisponible" : "Connecté");
      ui.connection.title = unavailable ? e.message : "";
      toast(unavailable
        ? (e.status === 0 ? "Serveur injoignable : l'application pixel-studio est-elle lancée ?" : unavailableMessage())
        : e.message, "error");
    } finally {
      busy.forEach((el) => (el.disabled = false));
    }
  });
  queue = task.catch(() => {});
  return task;
}

// --- État de l'appareil --------------------------------------------------------------

// Le contrôle de couleur agit sur l'écran affiché : couleur de l'horloge, ou couleur unie.
let currentView = null;

function showColorTarget() {
  const clock = currentView === "clock";
  ui.colorTitle.textContent = clock ? "Couleur de l'horloge" : "Couleur unie";
  ui.applyColor.textContent = clock ? "Appliquer à l'horloge" : "Afficher cette couleur";
  ui.colorLabel.textContent = clock ? "Horloge" : "Couleur";
}

function showState(state) {
  currentView = state.view;
  showColorTarget();
  ui.view.textContent = VIEW_LABELS[state.view] ?? state.view;
  ui.power.textContent = state.power ? "allumé" : "en veille";
  ui.screenToggle.textContent = state.power ? "Mettre en veille" : "Allumer l'écran";
  ui.screenToggle.dataset.power = state.power ? "on" : "off";
  ui.channelButtons.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.channel === state.view)));
  const shown = state.view === "clock" ? state.clock_color : state.light_color;
  ui.swatch.style.background = shown ? `#${shown}` : "transparent";
  ui.color.textContent = shown ? `#${shown}` : "—";
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

ui.channelButtons.forEach((button) =>
  button.addEventListener("click", () => run(() => api.channel(button.dataset.channel), { busy: ui.channelButtons })),
);

ui.screenToggle.addEventListener("click", () =>
  run(() => api.screen(ui.screenToggle.dataset.power === "off" ? "on" : "off"), { busy: [ui.screenToggle] }),
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

ui.applyColor.addEventListener("click", () => {
  const rgb = ui.colorInput.value.slice(1);
  run(() => (currentView === "clock" ? api.clockColor(rgb) : api.color(rgb, ui.brightness.value)),
    { busy: [ui.applyColor] });
});

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
  ui.dirty.hidden = sentPixels !== null && sentPixels.length === editor.pixels.length
    && sentPixels.every((p, i) => p === editor.pixels[i]);
  ui.dirty.textContent = sentPixels === null ? "pas encore envoyé" : "modifié depuis l'envoi";
  ui.undo.disabled = !editor.canUndo;
  ui.redo.disabled = !editor.canRedo;
}

function showSize() {
  ui.sizeBadge.textContent = `${editor.size}×${editor.size}`;
  updateSendState();
}

editor.addEventListener("change", (event) => {
  redrawPreview();
  updateDirty();
  showSize();
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

// Envoi : manuel, ou automatique au plus toutes les 300 ms. Un seul envoi à la fois : le Pixoo-64
// met ~1,5 s par image ; les modifications faites pendant un envoi partent ensuite, en une fois.
let sending = false;
let sendAgain = false;

async function sendImage() {
  if (sizeMismatch()) {
    toast(ui.send.title, "error");
    return;
  }
  if (sending) {
    sendAgain = true;
    return;
  }
  sending = true;
  try {
    const pixels = editor.pixels.slice();
    const result = await run(() => api.sendImage(pixels), { busy: [ui.send] });
    if (result) {
      sentPixels = pixels;
      updateDirty();
    }
  } finally {
    sending = false;
    updateSendState();
  }
  if (sendAgain) {
    sendAgain = false;
    if (ui.autoSend.checked) sendImage();
  }
}

let autoTimer = null;
function scheduleAutoSend() {
  if (sizeMismatch()) return;
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
  // rappel visible tant que le dessin n'est pas dans la galerie (seul l'import enregistre de lui-même)
  docUi.savedState.classList.toggle("neutral", !!clean);
  docUi.savedState.title = clean ? "" : "« Enregistrer » (⌘S / Ctrl+S) pour la garder dans la galerie";
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
      editor.setPixels(item.pixels); // annulable ; l'éditeur prend la taille de l'image
      setDoc({ id: item.id, name: item.name });
    },
    async convert(item, size) {
      const copy = await galleryAction(() => api.galleryConvert(item.id, size));
      if (!copy) return;
      await loadGallery();
      toast(`Copie « ${copy.name} » ajoutée à la galerie`);
    },
    async send(item) {
      const result = await run(() => api.gallerySend(item.id));
      if (result) {
        sentPixels = result.pixels;
        updateDirty();
        toast(`« ${item.name} » affichée sur ${deviceName()}`);
      }
    },
    async rename(item, name) {
      const updated = await galleryAction(() => api.galleryUpdate(item.id, { name }));
      if (!updated) return;
      if (doc.id === item.id) doc.name = updated.name;
      await loadGallery();
    },
    confirmRemove(item) {
      toast(`Cliquez à nouveau sur la coche rouge pour supprimer « ${item.name} »`);
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
  editor.clear(device?.size ?? editor.size); // annulable ; à la taille de l'appareil actif
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
  return { fit: form.get("fit"), mode: form.get("mode"), size: device?.size ?? editor.size };
}

function updateImportPreview() {
  if (!importing) return;
  const options = importOptions();
  importing.pixels = imageToPixels(importing.image, options);
  $("import-size").textContent = `Résultat ${options.size}×${options.size}`;
  drawLeds(importUi.preview, importing.pixels);
}

async function openImport(blob, name) {
  try {
    const image = await loadImage(blob);
    if (importing) URL.revokeObjectURL(importing.url);
    importing = { image, url: URL.createObjectURL(blob), pixels: null, name: imageName(name) };
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
/** Nom de galerie tiré du fichier : sans extension, 60 caractères au plus. */
function imageName(fileName) {
  const base = (fileName || "").replace(/\.[a-z0-9]{2,5}$/i, "").replace(/[_-]+/g, " ").trim();
  return (base || "Image importée").slice(0, 60);
}

// Une image importée est aussitôt enregistrée dans la galerie (sous le nom du fichier)
importUi.dialog.addEventListener("close", async () => {
  importUi.file.value = "";
  if (importUi.dialog.returnValue !== "import" || !importing?.pixels) return;
  const { pixels, name } = importing;
  editor.setPixels(pixels); // annulable
  const item = await galleryAction(() => api.galleryCreate(name, pixels));
  if (!item) return; // erreur signalée ; l'image reste dans l'éditeur, non enregistrée
  doc = { id: item.id, name: item.name };
  await loadGallery();
  toast(`« ${item.name} » importée et enregistrée dans la galerie`);
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
  const valid = (p) => Array.isArray(p) && SIZES.some((s) => p.length === s * s);
  const initial = valid(draft) ? draft : valid(lastImage) ? lastImage : null;
  if (initial) editor.setPixels(initial, { record: false });
  else if (device) editor.setPixels(Array(device.size * device.size).fill("000000"), { record: false });
  else editor.render();
  updateDirty();
  showSize();
  await loadGallery();
}

loadDevices().then(() => {
  refresh();
  start();
});
