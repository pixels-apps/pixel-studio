# Credits

The Divoom protocols are not documented by Divoom. This project builds on knowledge shared by these
projects (no code is copied from them):

- [RomRider/node-divoom-timebox-evo](https://github.com/RomRider/node-divoom-timebox-evo) (MIT) —
  frame format, checksum, commands and image encoding (`PROTOCOL.md`).
- [d03n3rfr1tz3/hass-divoom](https://github.com/d03n3rfr1tz3/hass-divoom) (MIT) — command list,
  RFCOMM channel notes, payload escaping history.
- [spezifisch/divo](https://github.com/spezifisch/divo) (GPL-3.0) — example image frames that helped
  confirm the bit packing. The test vectors in this repository were produced and validated on the
  device independently.
- [glaforge/jixoo](https://github.com/glaforge/jixoo) (Apache-2.0) — Pixoo-64 local API notes
  (`SPECIFICATION.md`): HTTP/1.1 only, `Command` as the first key, image commands, channels.
- [cyanheads/pixoo-toolkit](https://github.com/cyanheads/pixoo-toolkit) and
  [4ch1m/pixoo-rest](https://github.com/4ch1m/pixoo-rest) — Pixoo-64 commands and known quirks.

Divoom, Timebox and Pixoo are trademarks of their owner. This project is not affiliated with Divoom.
