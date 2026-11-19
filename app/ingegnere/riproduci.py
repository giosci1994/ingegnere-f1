"""Riproduttore: rimanda in UDP una sessione registrata, con i suoi tempi.

    python -m ingegnere.riproduci FILE [--host 127.0.0.1] [--porta 20777] [--velocita 1]
                                       [--da SECONDI] [--fino SECONDI]

Si prova l'ingegnere senza giocare: dentro il container la destinazione è 127.0.0.1:20777.
"""

import argparse
import socket
import sys
import time

from .registratore import leggi


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument("file")
    a.add_argument("--host", default="127.0.0.1")
    a.add_argument("--porta", type=int, default=20777)
    a.add_argument("--velocita", type=float, default=1.0, help="2 = due volte più veloce")
    a.add_argument("--da", type=float, default=0.0)
    a.add_argument("--fino", type=float, default=None)
    o = a.parse_args(argv)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    inizio = time.monotonic()
    n = 0
    for t, dati in leggi(o.file):
        if t < o.da:
            continue
        if o.fino is not None and t > o.fino:
            break
        quando = (t - o.da) / o.velocita
        attesa = quando - (time.monotonic() - inizio)
        if attesa > 0:
            time.sleep(attesa)
        s.sendto(dati, (o.host, o.porta))
        n += 1
    print(f"mandati {n} pacchetti in {time.monotonic() - inizio:.1f} s", file=sys.stderr)


if __name__ == "__main__":
    main()
