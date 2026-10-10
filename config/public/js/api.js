// Accès à l'API REST de timebox-evo.

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }

  /** Relais injoignable ou appareil muet (503), ou serveur hors service (0). */
  get unavailable() {
    return this.status === 503 || this.status === 0;
  }
}

function messageOf(body, fallback) {
  return body?.message && body.message !== "Bad Request"
    ? body.message
    : body?._embedded?.errors?.[0]?.message ?? body?.message ?? fallback;
}

async function request(method, path, { json, body, headers } = {}) {
  let response;
  try {
    response = await fetch(path, {
      method,
      headers: json !== undefined ? { "Content-Type": "application/json", ...headers } : headers,
      body: json !== undefined ? JSON.stringify(json) : body,
    });
  } catch {
    throw new ApiError(0, "Serveur injoignable");
  }
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) throw new ApiError(response.status, messageOf(data, `HTTP ${response.status}`));
  return data;
}

export const api = {
  state: () => request("GET", "/timebox/state"),
  color: (rgb, brightness) => request("POST", `/timebox/color/${rgb}?brightness=${brightness}`),
  brightness: (level) => request("POST", `/timebox/brightness/${level}`),
  view: (name) => request("POST", `/timebox/view/${name}`),
  sendImage: (pixels) => request("POST", "/timebox/image", { json: { pixels } }),
  gallery: () => request("GET", "/timebox/gallery"),
  galleryCreate: (name, pixels) => request("POST", "/timebox/gallery", { json: { name, pixels } }),
  galleryUpdate: (id, changes) => request("PUT", `/timebox/gallery/${id}`, { json: changes }),
  galleryDelete: (id) => request("DELETE", `/timebox/gallery/${id}`),
  gallerySend: (id) => request("POST", `/timebox/gallery/${id}/send`),
  lastImage: () =>
    request("GET", "/timebox/image").catch((e) => (e.status === 404 ? null : Promise.reject(e))),
};
