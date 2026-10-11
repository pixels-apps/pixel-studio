# timebox-bridge (macOS)

Transparent relay between a TCP socket and the Timebox Evo's Bluetooth RFCOMM channel, written in
Swift (IOBluetooth + Network.framework). Contract: [docs/architecture.md](../../docs/architecture.md).

A Swift package with three targets:

| Target | Role |
|--------|------|
| `TimeboxBridgeCore` | the relay itself (TCP server, Bluetooth channel, retries, logging), shared with the upcoming menu bar app |
| `timebox-bridge` | the command-line tool |
| `TimeboxBridgeCoreTests` | unit tests of the relay logic, with a fake Bluetooth device and a manual clock |

## Build

Xcode's command-line tools are enough (`xcode-select --install`):

```bash
./build.sh      # → build/timebox-bridge
./test.sh       # unit tests (Swift Testing); uses Xcode when installed
```

The binary embeds an `Info.plist` declaring Bluetooth usage (see `Package.swift`) — macOS kills a
command-line tool that uses Bluetooth without that declaration.

## Run

Run it from an app that is allowed to use Bluetooth (e.g. **Terminal**; macOS asks on first run):

```bash
build/timebox-bridge --list                        # paired devices; "→" marks Divoom devices
build/timebox-bridge --address AA-BB-CC-DD-EE-FF   # the Timebox Evo appears as TimeBox-Evo-audio
```

| Option | Environment | Default |
|--------|-------------|---------|
| `--address` | `TIMEBOX_ADDRESS` | required |
| `--channel` | `TIMEBOX_CHANNEL` | `1` |
| `--host` | `BRIDGE_HOST` | `127.0.0.1` |
| `--port` | `BRIDGE_PORT` | `7777` |
| `--retries` | `BRIDGE_RETRIES` | `5` |
| `--verbose` | `BRIDGE_VERBOSE=1` | off (logs every byte) |

Each opening attempt gives up after 5 seconds without an answer (the channel may be held by
another program, such as the Divoom phone app), then retries after 1 second.

Ctrl-C closes the channel cleanly. Log messages are in French; they also go to the macOS unified
log (`log show --predicate 'subsystem == "local.divoom.timebox-bridge"'`).

## Test against the device

With the relay running, from the repository root:

```bash
python3 tools/bridge-client.py 46                              # read the device state
python3 tools/bridge-client.py 4501 00ff00 64 00 01 000000     # solid green
```
