# timebox-bridge (macOS)

Transparent relay between a TCP socket and the Timebox Evo's Bluetooth RFCOMM channel, written in
Swift (IOBluetooth + Network.framework). Contract: [docs/architecture.md](../../docs/architecture.md).

## Build

```bash
./build.sh
```

Compiles `main.swift` with an embedded `Info.plist` declaring Bluetooth usage — macOS kills a
command-line tool that uses Bluetooth without that declaration.

## Run

Run it from an app that is allowed to use Bluetooth (e.g. **Terminal**; macOS asks on first run):

```bash
./timebox-bridge --list                        # paired devices; "→" marks Divoom devices
./timebox-bridge --address AA-BB-CC-DD-EE-FF   # the Timebox Evo appears as TimeBox-Evo-audio
```

| Option | Environment | Default |
|--------|-------------|---------|
| `--address` | `TIMEBOX_ADDRESS` | required |
| `--channel` | `TIMEBOX_CHANNEL` | `1` |
| `--host` | `BRIDGE_HOST` | `127.0.0.1` |
| `--port` | `BRIDGE_PORT` | `7777` |
| `--retries` | `BRIDGE_RETRIES` | `5` |
| `--verbose` | `BRIDGE_VERBOSE=1` | off (logs every byte) |

Ctrl-C closes the channel cleanly. Log messages are in French.

## Test

With the relay running, from the repository root:

```bash
python3 tools/bridge-client.py 46                              # read the device state
python3 tools/bridge-client.py 4501 00ff00 64 00 01 000000     # solid green
```
