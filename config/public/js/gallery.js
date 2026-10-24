// Galerie : vignettes (16×16 ou 64×64), ouverture, envoi, conversion de taille, renommage sur place,
// suppression confirmée.

const CONFIRM_DELAY = 4000;
const CHECK_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>';

/** Vignette nette : 1 pixel du canvas par LED, agrandi en CSS (image-rendering: pixelated). */
export function drawThumb(canvas, pixels) {
  const size = Math.round(Math.sqrt(pixels.length));
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d");
  const image = ctx.createImageData(size, size);
  pixels.forEach((hex, i) => {
    image.data.set([0, 2, 4].map((k) => parseInt(hex.slice(k, k + 2), 16)).concat(255), i * 4);
  });
  ctx.putImageData(image, 0, 0);
}

const dateFormat = new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeStyle: "short" });

export class GalleryView {
  /**
   * @param {object} options
   * @param {HTMLElement} options.list  <ul> des vignettes
   * @param {HTMLElement} options.empty message « galerie vide »
   * @param {HTMLElement} options.count compteur
   * @param {HTMLTemplateElement} options.template modèle de vignette
   * @param {{ open, send, convert, rename, remove, confirmRemove }} options.actions rappels (image[, valeur])
   */
  constructor({ list, empty, count, template, actions }) {
    Object.assign(this, { list, empty, count, template, actions });
  }

  render(items, currentId) {
    this.empty.hidden = items.length > 0;
    this.count.textContent = items.length ? `(${items.length})` : "";
    this.list.replaceChildren(...items.map((item) => this.#tile(item, item.id === currentId)));
  }

  #tile(item, current) {
    const tile = this.template.content.firstElementChild.cloneNode(true);
    tile.dataset.id = item.id;
    tile.classList.toggle("current", current);
    if (current) tile.setAttribute("aria-current", "true");

    const name = tile.querySelector(".tile-name");
    const rename = tile.querySelector(".tile-rename");
    name.textContent = name.title = item.name;
    tile.querySelector(".tile-date").textContent = dateFormat.format(new Date(item.updated));
    drawThumb(tile.querySelector("canvas"), item.pixels);

    const thumb = tile.querySelector(".thumb");
    thumb.setAttribute("aria-label", `Ouvrir « ${item.name} » dans l'éditeur`);
    thumb.addEventListener("click", () => this.actions.open(item));
    tile.querySelector('[data-action="send"]').addEventListener("click", () => this.actions.send(item));

    // Conversion 16×16 ↔ 64×64 : crée une copie dans la galerie
    const target = item.size === 64 ? 16 : 64;
    const convert = tile.querySelector('[data-action="convert"]');
    convert.title = `Copier en ${target}×${target}`;
    convert.setAttribute("aria-label", `Copier « ${item.name} » en ${target}×${target}`);
    convert.addEventListener("click", () => this.actions.convert(item, target));
    tile.querySelector(".tile-date").textContent += ` · ${item.size}×${item.size}`;

    // Renommage sur place : Entrée ou perte du focus = valider, Échap = annuler
    const startRename = () => {
      name.hidden = true;
      rename.hidden = false;
      rename.value = item.name;
      rename.focus();
      rename.select();
    };
    let cancelled = false;
    const finishRename = () => {
      if (rename.hidden) return;
      rename.hidden = true;
      name.hidden = false;
      const value = rename.value.trim();
      if (!cancelled && value && value !== item.name) this.actions.rename(item, value);
      cancelled = false;
    };
    tile.querySelector('[data-action="rename"]').addEventListener("click", startRename);
    name.addEventListener("dblclick", startRename);
    rename.addEventListener("keydown", (e) => {
      if (e.key === "Enter") rename.blur();
      if (e.key === "Escape") { cancelled = true; rename.blur(); }
    });
    rename.addEventListener("blur", finishRename);

    // Suppression en deux clics (confirmation intégrée, sans boîte de dialogue)
    const remove = tile.querySelector('[data-action="delete"]');
    const icon = remove.innerHTML;
    let timer = null;
    remove.addEventListener("click", () => {
      if (timer) {
        clearTimeout(timer);
        this.actions.remove(item);
        return;
      }
      // Taille inchangée (pas de texte) : le second clic tombe au même endroit
      remove.classList.add("confirm");
      remove.innerHTML = CHECK_ICON;
      remove.title = "Cliquer à nouveau pour supprimer";
      remove.setAttribute("aria-label", `Confirmer la suppression de « ${item.name} »`);
      this.actions.confirmRemove?.(item);
      timer = setTimeout(() => {
        timer = null;
        remove.classList.remove("confirm");
        remove.innerHTML = icon;
        remove.title = "Supprimer";
        remove.setAttribute("aria-label", "Supprimer");
      }, CONFIRM_DELAY);
    });
    return tile;
  }
}
