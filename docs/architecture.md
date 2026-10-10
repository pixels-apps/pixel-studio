# Architecture

```
browser ──HTTP──> timebox-evo (Pyronaut, :8080) ──TCP──> timebox-bridge (:7777) ──RFCOMM ch. 1──> Timebox Evo
```

## Why a relay

On macOS, reaching the device's RFCOMM channel requires the native IOBluetooth framework and the
user's Bluetooth permission, which belongs to the app that launches the process (e.g. Terminal).
The JVM/GraalPy application cannot do that directly. A small native relay owns Bluetooth and
exposes a plain TCP socket; the application stays portable and testable.

## Relay contract (v1)

- Listens on TCP (default `127.0.0.1:7777`), **one client at a time**: a new client replaces the
  previous one.
- **Transparent**: bytes received over TCP are written as-is to RFCOMM channel 1 (split to the
  MTU), and vice versa. The relay does not parse frames.
- Owns the Bluetooth link: opens the channel when a client connects or on the first write, retries
  (the first attempt usually fails), reopens on demand if the device closes it; buffers TCP bytes
  until the channel is open.
- Configuration: device address (required), channel (default 1), TCP host and port, retries.

Any implementation honoring this contract can replace [`bridge/macos`](../bridge/macos/README.md).

## Linux (not implemented)

Linux needs no native code: CPython's standard library supports RFCOMM sockets
(`socket.AF_BLUETOOTH`, `BTPROTO_RFCOMM`), so a ~50-line `asyncio` script can implement the same
contract (alternatively `rfcomm bind` + `socat`). An ESP32 (original model, which supports classic
Bluetooth SPP) could also act as a Wi-Fi relay.

## Application

- `protocol.py` — pure Python: frame encoding/decoding, commands, image encoding.
- `transport.py` — `Transport` interface; `TcpTransport` talks to the relay. Tests replace it with a
  fake device (`@Replaces(TcpTransport)`, `@Requires(env="test")`).
- `client.py` — `TimeboxClient` (`@Singleton`): sends a command and waits for the reply that
  confirms it, serialized by a lock; remembers and persists the last image sent (the device cannot
  report it).
- `storage.py` — gallery (one JSON file per image) and last image, atomic writes.
- `controller.py` — REST API under `/timebox`, error mapping (400 / 404 / 503).
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
