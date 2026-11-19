"""Disegna le icone della web app (PNG) con la sola libreria standard: un microfono da radio stilizzato.
    python3 strumenti/icone.py   → web/icona-180.png, web/icona-192.png, web/icona-512.png"""
import math, os, struct, zlib

def png(path, n):
    sfondo, rosso, bianco = (13, 15, 18), (225, 6, 0), (238, 241, 245)
    righe = []
    c = n / 2
    for y in range(n):
        r = bytearray([0])
        for x in range(n):
            dx, dy = (x + .5 - c) / n, (y + .5 - c) / n
            d = math.hypot(dx, dy)
            col = sfondo
            if d < 0.42:
                col = rosso
            # tre archi bianchi (onde radio) a destra del centro
            ang = math.atan2(dy, dx)
            if abs(ang) < 0.75:
                for raggio in (0.12, 0.21, 0.30):
                    if abs(d - raggio) < 0.025:
                        col = bianco
            if d < 0.055:
                col = bianco
            r += bytes(col)
        righe.append(bytes(r))
    raw = zlib.compress(b"".join(righe), 9)
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", raw) + chunk(b"IEND", b""))

web = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web")
for n in (180, 192, 512):
    png(os.path.join(web, f"icona-{n}.png"), n)
