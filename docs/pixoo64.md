# Pixoo-64 (Wi-Fi) local API

What this project relies on, as observed on one **Pixoo-64 II** (October 2026). Unofficial: Divoom
does not document this API. Credits in [CREDITS.md](../CREDITS.md).

## Transport

- `POST http://<device-ip>:9000/divoom_api`, JSON body, **HTTP/1.1 only** (the device's ESP32
  server rejects HTTP/2 with `400`). No authentication.
- `"Command"` must be the **first key** of the JSON object (the firmware's JSON parser may drop the
  command otherwise).
- On the Pixoo-64 II, **port 80 is closed**: the `/post` endpoint used by the original Pixoo-64 (and
  by most community libraries) does not exist. The same command vocabulary is served on port 9000.
- Replies carry `"ReturnCode"` (`0` = success) and `"ReturnMessage"`, plus `DeviceId`, `PacketFlag`
  (a counter) and `WifiSingal`. An unknown command returns
  `{"ReturnCode": 1, "ReturnMessage": "Only accept JSON parameters"}`.
- The original Pixoo-64 (`/post` on port 80) replies with `"error_code"` instead, sometimes as a
  string (`"Request data illegal json"`). pixel-studio accepts both envelopes; declare such a device
  with port 80 (untested).

## Commands used by pixel-studio

| Command | Fields | Effect / reply |
|---------|--------|----------------|
| `Channel/GetIndex` | — | `SelectIndex`: `0` clock faces, `1` cloud, `2` visualizer, `3` custom |
| `Channel/SetIndex` | `SelectIndex` | switch channel; also cancels a queued HTTP image (see below) |
| `Channel/GetClockInfo` | — | `Brightness` (0–100), `ClockId` |
| `Channel/SetBrightness` | `Brightness` | brightness 0–100 |
| `Channel/GetOnOffScreen` | — | `OnOff` (`1` on, `0` standby); brightness reads `0` in standby |
| `Channel/OnOffScreen` | `OnOff` | screen on / standby |
| `Draw/ResetHttpGifId` | — | reset the picture counter (called before every image) |
| `Draw/SendHttpGif` | `PicNum`, `PicWidth`, `PicOffset`, `PicID`, `PicSpeed`, `PicData` | display a picture |

`Channel/GetAllConf`, `Sys/GetConf`, `Device/GetDeviceTime` and `Draw/GetHttpGifId` answer
`ReturnCode 0` without any field on the Pixoo-64 II.

## Images

A still image is a one-frame "animation":

```json
{"Command": "Draw/SendHttpGif", "PicNum": 1, "PicWidth": 64, "PicOffset": 0, "PicID": 1,
 "PicSpeed": 1000, "PicData": "<base64 of 64 × 64 × 3 RGB bytes, row by row>"}
```

Observations that shaped the client:

- **Each image plays for `PicSpeed` ms before the next one.** With a long duration (60 s, a common
  choice for still images), images sent in a row are **queued**: 18 images sent 3–6 s apart showed
  up minutes later. With a **short duration** (1–2 s), each image replaces the previous one right
  away, and the **last image stays on screen** after its duration. pixel-studio uses 1000 ms.
- A queue left by long durations is cleared by `Channel/SetIndex` (even to the current channel).
- **Each `SendHttpGif` takes ~1.45 s** to be answered, whatever the spacing between requests, while a
  read takes ~50 ms: the device sets the pace (~0.7 image per second). pixel-studio sends one image
  at a time and, when several are waiting (automatic sending from the editor), only the latest.
- `Draw/ResetHttpGifId` before every image keeps `PicID` at 1. Community reports say the original
  Pixoo-64 freezes after ~300 images without a reset; 50 images in a row were fine here.

## Colors

The LEDs have a **cold white balance**: pure white (`ffffff`) and light grays look bluish, more so as
they get brighter; warmer whites (`ffe4c4`, `ffd8b0`) look closer to white without being neutral.
pixel-studio sends the colors as they are (no correction yet).

## Finding the device

The IP address is shown in the Divoom app (device settings) and in the router's list of devices;
reserving a fixed address in the router avoids surprises. A quick check from a terminal:

```bash
curl --http1.1 -d '{"Command":"Channel/GetIndex"}' http://<device-ip>:9000/divoom_api
```
