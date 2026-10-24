# pixel-studio

Drive **Divoom pixel displays** from a web browser: pixel editor, image import, gallery and device
controls, served by a [Pyronaut](https://pyronaut.io) application (Python on GraalPy + Micronaut).

| Device | Size | Connection |
|--------|------|------------|
| Timebox Evo | 16×16 | classic Bluetooth, through the `timebox-bridge` relay |
| Pixoo (16×16) | 16×16 | classic Bluetooth, through the `timebox-bridge` relay |
| Pixoo-64 II (and, untested, the original Pixoo-64) | 64×64 | Wi-Fi, local HTTP API |

![pixel-studio web UI: pixel editor with an imported sunset, LED preview and device controls](docs/img/screenshot.png)

```
                                         ┌─TCP──> timebox-bridge (:7777) ──Bluetooth RFCOMM──> Timebox Evo / Pixoo
browser ──HTTP──> pixel-studio (:8080) ──┤
                                         └─HTTP (Wi-Fi) ──────────────────────────────────────> Pixoo-64 II
```

Bluetooth devices are driven over **classic Bluetooth (SPP)**, handled by a small native relay,
[`bridge/macos`](bridge/macos/README.md) (command-line tool or menu bar app), so the application
itself only talks plain TCP. The Pixoo-64 is driven directly over Wi-Fi. Several devices can be
declared; the web UI drives the **active** one. See [`docs/architecture.md`](docs/architecture.md)
(including the GraalPy constraints that shaped the code), [`docs/protocol.md`](docs/protocol.md)
(Bluetooth devices) and [`docs/pixoo64.md`](docs/pixoo64.md) (Wi-Fi API).

> Status: personal project, tested on macOS with one Timebox Evo, one Pixoo and one Pixoo-64 II.
> The UI and code comments are in French; this README and the docs are in English.

## Features

- **Devices** — declare Bluetooth and Wi-Fi devices (with a connection test), pick the active one.
- **Pixel editor** — 16×16 or 64×64: pencil, eraser, fill, color picker, undo/redo, palette and
  recent colors, live LED preview, manual or automatic sending, keyboard support.
- **Image import** — button, drag & drop or paste; crop (fill / fit / stretch); smooth (photos) or
  sharp (pixel art, auto-detected) downscaling to the active device's size, done in the browser;
  imported images are saved to the gallery.
- **Gallery** — 16×16 and 64×64 images: save, copy, convert to the other size (as a copy), rename,
  delete, send to the active device (JSON files on disk).
- **Device controls**, depending on the device — state and brightness; clock / light view, solid
  color and clock color (Bluetooth); channel and screen on / standby (Wi-Fi).
- **REST API** with OpenAPI / Swagger UI.

## Requirements

- Bluetooth devices: macOS, with the device **paired** (System Settings → Bluetooth; the Timebox
  Evo shows up as `TimeBox-Evo-audio`), and Xcode's command line tools to build the relay.
- Wi-Fi devices: the Pixoo-64 on the same network, set up with the Divoom app; its IP address (a
  fixed one, reserved in the router, is best).
- Python ≥ 3.10 and Pyronaut 0.1.0:

  ```bash
  python3 -m pip install 'pyronaut==0.1.0'
  pyronaut setup        # installs the matching GraalVM JDK and GraalPy under ~/.pyronaut
  ```

## Quick start

1. **Bluetooth devices only — build and start the relay**, either the menu bar app (see
   [`bridge/macos`](bridge/macos/README.md)) or the command-line tool, from the **Terminal** app,
   which must be allowed to use Bluetooth (macOS asks on first run):

   ```bash
   bridge/macos/build.sh
   bridge/macos/build/timebox-bridge --list                        # find your device address (→ marks Divoom devices)
   bridge/macos/build/timebox-bridge --address AA-BB-CC-DD-EE-FF   # add --verbose to see the bytes
   ```

   Wait for `écoute sur 127.0.0.1:7777` ("listening"). Close the Divoom phone app: it can hold
   the Bluetooth channel.

2. **Start the application**:

   ```bash
   pyronaut install      # once: creates the GraalPy .venv and resolves dependencies
   pyronaut run
   ```

3. Open **http://localhost:8080/**. A Bluetooth device behind the relay is declared by default;
   add a Wi-Fi device with the **devices** button (next to the device picker): name, IP address,
   **Test**, then **Add**.

Check the relay without the application: `python3 tools/bridge-client.py 46` asks the device for
its state.

## Tests

```bash
pyronaut test
```

Pytest on GraalPy: protocol tests (bytes captured from the real devices), end-to-end HTTP tests
with fake devices injected in place of the relay and of the Wi-Fi API (`@Replaces` +
`@Requires(env="test")`), gallery and device tests in a temporary directory.

## API

Interactive documentation: http://localhost:8080/swagger-ui/index.html

`/device/*` routes address the **active device**, chosen among the declared devices.

| Method | Path | Effect |
|--------|------|--------|
| GET | `/devices` | declared devices and the active one |
| PUT | `/devices/active` | choose the active device `{"id"}` |
| POST | `/devices` | declare a device `{"name", "kind": "bluetooth"\|"wifi", "host", "port"?}` |
| POST | `/devices/test` | query a device without declaring it (same body): its state, or 503 |
| DELETE | `/devices/{id}` | remove a device (not the last one) |
| GET | `/device` | active device: name, kind, size, address, capabilities |
| GET | `/device/state` | decoded device state |
| POST | `/device/color/{rrggbb}?brightness=0..100` | solid color (capability `color`) |
| POST | `/device/clock/color/{rrggbb}` | clock view in this color, style and options kept (capability `views`) |
| POST | `/device/brightness/{0..100}` | brightness |
| POST | `/device/screen/{on\|off}` | screen on / standby (capability `screen`) |
| POST | `/device/channel/{faces\|cloud\|visualizer\|custom}` | channel (capability `channels`) |
| POST | `/device/view/{clock\|light}` | displayed view (capability `views`) |
| POST | `/device/image` | image as JSON `{"pixels": [size² × "rrggbb"]}`, at the active device's size |
| POST | `/device/image/png` | raw image (PNG, GIF, BMP, JPEG) at the active device's size |
| GET | `/device/image` | last image sent to the active device (404 if none) |
| GET / POST | `/gallery` | list / create `{"name", "pixels"}` (16×16 or 64×64, size inferred) |
| GET / PUT / DELETE | `/gallery/{id}` | read / update / delete |
| POST | `/gallery/{id}/send` | display a gallery image on the active device |
| POST | `/gallery/{id}/convert?size=16\|64` | copy of the image at another size |

Images are 16×16 (256 pixels) or 64×64 (4096 pixels), row by row (`x + size·y`). An image is only
sent to a device of the same size; converting creates a copy: enlarging repeats each pixel
(nearest neighbour), shrinking keeps the most frequent color of each block.

Errors: 400 (invalid value, unsupported command), 404 (unknown image or device), 409 (image size
differs from the active device's, or last device removed), 503 (device or relay unreachable,
device silent or refusing the command).

```bash
curl -X POST "http://localhost:8080/device/color/ff8800?brightness=60"
curl -X POST -H "Content-Type: image/png" --data-binary @heart.png http://localhost:8080/device/image/png
```

## Configuration

`config/application.toml`, every key can be overridden with an environment variable
(e.g. `PIXEL_STUDIO_BRIDGE_PORT=7778 MICRONAUT_SERVER_PORT=8081 pyronaut run`).

| Key | Default | Purpose |
|-----|---------|---------|
| `pixel-studio.bridge.host` / `port` | `127.0.0.1` / `7777` | relay of the default Bluetooth device |
| `pixel-studio.bridge.connect-timeout-ms` | `2000` | relay connection timeout |
| `pixel-studio.bridge.reply-timeout-ms` | `2000` | wait for the device reply |
| `pixel-studio.wifi.connect-timeout-ms` | `2000` | Wi-Fi device connection timeout |
| `pixel-studio.wifi.request-timeout-ms` | `5000` | Wi-Fi request timeout (an image takes ~1.5 s) |
| `pixel-studio.storage.dir` | `~/.pixel-studio` | devices, gallery and last images |

Devices are stored in `<storage dir>/devices.json` (managed through `/devices`). Until it exists, a
single device is declared: "Divoom Bluetooth", behind the relay above. Two kinds:

- `bluetooth` — Timebox Evo, Pixoo 16×16: `host` / `port` of the relay (default 7777);
- `wifi` — Pixoo-64: `host` / `port` of the device itself, no relay. Port 9000 (default) is the
  local API of the Pixoo-64 II (`/divoom_api`); port 80 the original Pixoo-64's (`/post`).

```json
{"active": "pixoo-64-ii", "devices": [
  {"id": "evo", "name": "Timebox Evo", "kind": "bluetooth", "host": "127.0.0.1", "port": 7777},
  {"id": "pixoo-64-ii", "name": "Pixoo-64 II", "kind": "wifi", "host": "192.168.1.50", "port": 9000}]}
```

## Project layout

```
src/pixel_studio/
  device.py      Device interface, state, capabilities
  registry.py    declared devices, active device, last image of each
  wifi/          Wi-Fi devices (Pixoo-64): HTTP transport (java.net.http), WifiDevice
  bluetooth/     Bluetooth devices behind the relay (Timebox Evo, Pixoo 16×16)
    protocol.py    Divoom frames, commands, image encoding (pure Python)
    transport.py   Transport (ABC), TcpTransport (java.net.Socket), TransportFactory
    device.py      BluetoothDevice: command → state read that confirms it, shared Java lock
  pixels.py      colors and pixel lists
  storage.py     devices, gallery and last images on disk
  imaging.py     image decoding with javax.imageio
  api.py         REST API and error handling
config/public/   web UI (plain HTML/CSS/JS, no build step)
bridge/macos/    Bluetooth RFCOMM ↔ TCP relay (Swift package: shared core + CLI)
tools/           bridge-client.py, a dependency-free test client for the relay
docs/            protocol (Bluetooth), Pixoo-64 local API and architecture notes
tests/           pytest
```

## Credits and license

Protocol knowledge comes from the community, see [CREDITS.md](CREDITS.md).
Not affiliated with Divoom. Released under the [MIT License](LICENSE).
