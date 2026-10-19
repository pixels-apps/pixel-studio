# Timebox Evo protocol

What this project relies on, as observed on one Timebox Evo (October 2026). Unofficial: Divoom
does not document the protocol. Credits for the original reverse engineering in
[CREDITS.md](../CREDITS.md).

## Transport

- The device exposes two Bluetooth identities:
  - `TimeBox-Evo-audio` — classic Bluetooth: audio profiles (A2DP, AVRCP, HFP) and a
    **Serial Port** service (SPP, UUID `0x1101`) on **RFCOMM channel 1** — this is the control
    channel;
  - `TimeBox-Evo-light` — Bluetooth Low Energy, exposing a Microchip "transparent UART" service
    (`49535343-FE7D-…`). Writing control frames there is acknowledged but has **no effect** and
    gets no reply: it is not used.
- On macOS, the `/dev/cu.TimeBox-Evo-audio` serial port does **not** establish a working RFCOMM
  connection. Opening channel 1 through IOBluetooth does, but the **first attempt usually fails**
  (`kIOReturnError`) and the second succeeds: retry.
- The connection stays open while idle (tested over 30 s); no keep-alive needed.
- Only one client at a time: close the Divoom phone app.

### Divoom Pixoo (16×16)

Observed on one Pixoo (October 2026), same frames and commands:

- Classic Bluetooth identity `Pixoo` (plus a BLE advertisement, not used). Its **Serial Port**
  service (UUID `0x1101`) is on **RFCOMM channel 2**; channel 10 carries a vendor service
  (`JL_SPP`, JieLi chip, UUID `fe010000-1234-5678-abcd-00805f9b34fb`); there is no channel 1.
- First opening attempt fails, the second succeeds — as on the Evo.
- `46` gets the usual `04 46 55 …` reply, with two more data bytes; the device also sends an
  unsolicited `04 f7 55 …` frame.
- Images (`44`) are displayed but **not acknowledged**. pixel-studio therefore confirms an image
  by reading the state (`46`) right after it, which both devices answer once the image is handled.

## Frames

```
01 | LLLL | payload | CRCR | 02
```

- `LLLL`: payload length + 2, little-endian.
- `CRCR`: sum of the bytes of `LLLL + payload`, modulo 2¹⁶, little-endian.
- No byte escaping on the Evo.

Device replies use the payload `04 | command | 55 | data` (`55` = acknowledged). The device also
sends unsolicited status frames.

## Commands used

| Payload | Effect | Reply |
|---------|--------|-------|
| `46` | read the current state | `46 55` + 20–22 bytes (see below) |
| `45 VV` | switch view (`00` clock, `01` light, …) | `45 55 VV` |
| `45 01 RR GG BB BB EE PP 00 00 00` | light view: color, brightness 0–100, effect (`00` = solid), power (`01`) | `31 55 xx` (unsolicited) then `45 55 01` |
| `74 BB` | brightness 0–100 | `32 55 BB` |
| `44 00 0a 0a 04` + frame | display a 16×16 image | `44 55 XX` (`XX` varies, meaning unknown); none on the Pixoo |

Examples (complete frames): brightness 50 → `01 04 00 74 32 aa 00 02`; solid red at 100 % →
`01 0d 00 45 01 ff 00 00 64 00 01 00 00 00 b7 01 02`.

## State (reply to `46`)

Partial decoding of the data bytes:

| Byte | Meaning |
|------|---------|
| 0 | current view (`00` clock, `01` light) |
| 3–5 | light color (RGB) |
| 6 | brightness (0–100) |
| 7 | effect (`00` = solid) |
| 8 | power (`01` = on) |
| 10 | brightness (copy) |

Caveats: while an image is displayed the view still reads `01`; in some modes byte 6 holds values
above 100 (e.g. `aa`) and byte 8 reads `00` — not decoded yet.

## Images (command `44`)

```
payload = 44 00 0a 0a 04 | frame
frame   = aa | LLLL | TTTT | RR | NN | colors | pixels
```

| Field | Meaning |
|-------|---------|
| `aa` | frame start |
| `LLLL` | length of the whole frame (from `aa`), little-endian |
| `TTTT` | duration in ms (animations); `0000` for a still image |
| `RR` | palette reset — **must be `00`**: with `01` the image is acknowledged but not displayed |
| `NN` | number of colors (`00` = 256) |
| colors | `NN` × RGB |
| pixels | 256 palette indexes, row by row (`x + 16·y`, (0, 0) = top left), each on `max(1, ⌈log2 NN⌉)` bits, **least significant bit first**, bytes filled the same way |

Validated on the device: 1, 2, 16 and 256 colors. A 256-color frame (1 042 bytes) is larger than
the RFCOMM MTU (666): the relay splits it and the device reassembles it.

Worked example — a blue/red checkerboard: 2 colors, 1 bit per pixel; the first pixel is blue
(index 0), so a row "blue, red, blue…" packs to `0b10101010` = `aa` and the next row to `55`:

```
aa 2d 00 | 00 00 | 00 | 02 | 0000ff ff0000 | (aa aa 55 55) × 8
```

The same frame format (with a duration) is used by animations (command `49`), not implemented yet.
