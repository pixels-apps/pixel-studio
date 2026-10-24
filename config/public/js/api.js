// Accès à l'API REST de pixel-studio.

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }

  /** Appareil (ou relais) injoignable ou muet (503), ou serveur hors service (0). */
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
  devices: () => request("GET", "/devices"),
  activate: (id) => request("PUT", "/devices/active", { json: { id } }),
  addDevice: (device) => request("POST", "/devices", { json: device }),
  testDevice: (device) => request("POST", "/devices/test", { json: device }),
  removeDevice: (id) => request("DELETE", `/devices/${id}`),
  state: () => request("GET", "/device/state"),
  color: (rgb, brightness) => request("POST", `/device/color/${rgb}?brightness=${brightness}`),
  clockColor: (rgb) => request("POST", `/device/clock/color/${rgb}`),
  brightness: (level) => request("POST", `/device/brightness/${level}`),
  view: (name) => request("POST", `/device/view/${name}`),
  channel: (name) => request("POST", `/device/channel/${name}`),
  screen: (power) => request("POST", `/device/screen/${power}`),
  sendImage: (pixels) => request("POST", "/device/image", { json: { pixels } }),
  lastImage: () =>
    request("GET", "/device/image").catch((e) => (e.status === 404 ? null : Promise.reject(e))),
  gallery: () => request("GET", "/gallery"),
  galleryCreate: (name, pixels) => request("POST", "/gallery", { json: { name, pixels } }),
  galleryUpdate: (id, changes) => request("PUT", `/gallery/${id}`, { json: changes }),
  galleryDelete: (id) => request("DELETE", `/gallery/${id}`),
  gallerySend: (id) => request("POST", `/gallery/${id}/send`),
  galleryConvert: (id, size) => request("POST", `/gallery/${id}/convert?size=${size}`),
};
