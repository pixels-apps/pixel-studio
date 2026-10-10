"""Client de test pour timebox-bridge (bibliothèque standard uniquement).

Encapsule chaque payload dans une trame Divoom (01 LLLL payload CRCR 02), l'envoie au relais
et affiche les trames reçues en retour.

    python3 client.py 46                              # lecture de l'écran affiché
    python3 client.py 4501 0000ff 64 00 01 000000     # couleur unie bleue
    python3 client.py 74 32 , 46                      # plusieurs trames, séparées par « , »
"""

import argparse
import socket
import sys
import time


def frame(payload: bytes) -> bytes:
    body = (len(payload) + 2).to_bytes(2, "little") + payload
    return b"\x01" + body + (sum(body) & 0xFFFF).to_bytes(2, "little") + b"\x02"


def split_frames(buffer: bytearray) -> list[bytes]:
    """Extrait les trames complètes du tampon (sans échappement)."""
    frames = []
    while True:
        start = buffer.find(0x01)
        if start < 0 or len(buffer) < start + 3:
            break
        length = int.from_bytes(buffer[start + 1:start + 3], "little")
        end = start + 3 + length
        if len(buffer) < end + 1:
            break
        frames.append(bytes(buffer[start:end + 1]))
        del buffer[:end + 1]
    return frames


def describe(f: bytes) -> str:
    body, crc = f[1:-3], int.from_bytes(f[-3:-1], "little")
    ok = "✓" if sum(body) & 0xFFFF == crc else "✗ CRC"
    payload = f[3:-3]
    if payload[:1] == b"\x04" and len(payload) >= 3:
        return f"réponse cmd={payload[1]:02x} statut={payload[2]:02x} données={payload[3:].hex(' ')} {ok}"
    return f"{payload.hex(' ')} {ok}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("payload", nargs="*", default=["46"], help="payload hexadécimal")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7777)
    parser.add_argument("--wait", type=float, default=3.0, help="secondes d'écoute après le dernier envoi")
    parser.add_argument("--gap", type=float, default=0.3, help="secondes entre deux trames")
    args = parser.parse_args()

    payloads = [bytes.fromhex(p) for p in " ".join(args.payload).split(",") if p.strip()]
    buffer = bytearray()

    with socket.create_connection((args.host, args.port), timeout=5) as sock:
        sock.settimeout(0.1)

        def drain(seconds: float) -> None:
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                try:
                    chunk = sock.recv(4096)
                except TimeoutError:
                    continue
                if not chunk:
                    print("relais : connexion fermée")
                    return
                buffer.extend(chunk)
                for f in split_frames(buffer):
                    print(f"← {f.hex(' ')}\n  {describe(f)}")

        for payload in payloads:
            data = frame(payload)
            print(f"→ {data.hex(' ')}")
            sock.sendall(data)
            drain(args.gap)
        drain(args.wait)

    if buffer:
        print(f"octets restants non décodés : {buffer.hex(' ')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
