# Architecture

```
                                         ┌─TCP──> timebox-bridge (:7777) ──RFCOMM──> Timebox Evo / Pixoo (16×16)
browser ──HTTP──> pixel-studio (:8080) ──┤
                                         └─HTTP/1.1 (Wi-Fi) ──────────────────────> Pixoo-64 II (64×64)

Wi-Fi devices need no relay: the JVM reaches them directly with `java.net.http` (see
[pixoo64.md](pixoo64.md)). The rest of this page is about the Bluetooth relay.
```

## Why a relay

On macOS, reaching the device's RFCOMM channel requires the native IOBluetooth framework and the
user's Bluetooth permission, which belongs to the app that launches the process (e.g. Terminal).
The JVM/GraalPy application cannot do that directly. A small native relay owns Bluetooth and
exposes a plain TCP socket; the application stays portable and testable.

## Relay contract (v1)

- Listens on TCP (default `127.0.0.1:7777`), **one client at a time**: a new client replaces the
  previous one.
- **Transparent**: bytes received over TCP are written as-is to the device's RFCOMM channel (split to the
  MTU), and vice versa. The relay does not parse frames.
- Owns the Bluetooth link: opens the channel when a client connects or on the first write, retries
  (the first attempt usually fails), reopens on demand if the device closes it; buffers TCP bytes
  until the channel is open.
- Configuration: device address (required), channel (default: the device's Serial Port channel as
  recorded by macOS at pairing — 1 on the Timebox Evo, 2 on the Pixoo — else 1), TCP host and port,
  retries.

Any implementation honoring this contract can replace [`bridge/macos`](../bridge/macos/README.md).

## Linux (not implemented)

Linux needs no native code: CPython's standard library supports RFCOMM sockets
(`socket.AF_BLUETOOTH`, `BTPROTO_RFCOMM`), so a ~50-line `asyncio` script can implement the same
contract (alternatively `rfcomm bind` + `socat`). An ESP32 (original model, which supports classic
Bluetooth SPP) could also act as a Wi-Fi relay.

## Application

- `device.py` — the `Device` interface shared by all device families: state, brightness, image,
  optional capabilities (`color`, `views`). The web UI only shows what the active device supports.
- `registry.py` — `DeviceRegistry` (`@Singleton`): declared devices (`devices.json`), active device,
  last image sent to each (devices cannot report it).
- `bluetooth/protocol.py` — pure Python: frame encoding/decoding, commands, image encoding.
- `bluetooth/transport.py` — `Transport` interface; `TcpTransport` talks to the relay;
  `TransportFactory` (bean) creates one per device. Tests replace the factory with a fake device
  (`@Replaces(TransportFactory)`, `@Requires(env="test")`; the fake must subclass the factory).
- `bluetooth/device.py` — `BluetoothDevice`: sends a command, then confirms it by reading the state
  (`46`), serialized by a lock.
- `storage.py` — devices, gallery (one JSON file per image) and last images, atomic writes.
- `wifi/transport.py` — `HttpTransport`; `JavaHttpTransport` (`java.net.http.HttpClient`, forced to
  HTTP/1.1; the Python `socket` module is not available); `HttpTransportFactory` (bean, replaced
  by a fake Pixoo-64 in tests).
- `wifi/device.py` — `WifiDevice`: state from three reads, brightness, screen, channel; images sent
  one at a time, only the latest when several wait.
- `pixels.py` — 16×16 / 64×64 images, size conversion (nearest neighbour up, most frequent color
  per block down).
- `api.py` — REST API (`/devices`, `/device/*`, `/gallery/*`), error mapping (400 / 404 / 409 / 503).
- `config/public/` — the web UI, plain ES modules served as static resources.

## GraalPy constraints

Pyronaut runs Python on GraalPy inside the JVM. Things that shaped the code:

- The Python `socket` module is excluded and Python code may not create threads → the TCP
  transport uses `java.net.Socket`; tests use bean replacement rather than an in-process server.
- Several GraalPy contexts serve requests and module globals are not shared between them; only
  `@Singleton` beans are → shared state (socket, lock) lives in a singleton and uses Java objects
  (`ReentrantLock`).
- `os.replace` fails ("Atomic move not supported") → `java.nio.file.Files.move` with
  `ATOMIC_MOVE`.
- Exceptions defined in the application become Java classes (handled by typed `@Error` methods);
  built-in Python exceptions reach Micronaut wrapped in a `PolyglotException`.
