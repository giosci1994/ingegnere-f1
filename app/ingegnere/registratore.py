"""Registratore delle sessioni vere: salva i datagrammi così come arrivano, con il tempo.

Formato del file (`.f1rec.gz`, gzip): l'intestazione b"F1REC1\\n", poi per ogni datagramma
`<d H` (secondi dall'inizio, lunghezza) e i byte. Un file per sessione (session_uid).
Il riproduttore è `python -m ingegnere.riproduci`.
"""

import gzip
import os
import struct
import time

MAGIA = b"F1REC1\n"
REC = struct.Struct("<dH")


class Registratore:
    def __init__(self, cartella, imp):
        self.cartella = cartella
        self.imp = imp
        os.makedirs(cartella, exist_ok=True)
        self.f = None
        self.nome = None
        self.uid = None
        self.t0 = 0.0
        self.ultimo = 0.0
        self.ultimo_flush = 0.0
        self.scritti = 0
        self.ultimo_motion = 0.0

    def scrivi(self, buf, uid, pid, nome_sessione="sessione"):
        if not self.imp["registra"]:
            self.chiudi()
            return
        now = time.monotonic()
        if pid == 0:
            # motion: pesante (1325 byte, tutte le auto). Se si registra, al massimo 10 al secondo
            if not self.imp["registra_motion"] or now - self.ultimo_motion < 0.095:
                return
            self.ultimo_motion = now
        if self.f is None or uid != self.uid:
            self.chiudi()
            self.uid = uid
            self.nome = time.strftime("%Y%m%d-%H%M%S") + f"-{nome_sessione}.f1rec.gz"
            self.f = gzip.open(os.path.join(self.cartella, self.nome), "wb", compresslevel=1)
            self.f.write(MAGIA)
            self.t0 = now
            self.scritti = 0
            self.ruota()
        self.f.write(REC.pack(now - self.t0, len(buf)))
        self.f.write(buf)
        self.scritti += 1
        self.ultimo = now
        if now - self.ultimo_flush > 5:
            self.f.flush()
            self.ultimo_flush = now

    def controlla(self):
        """Chiude il file dopo 60 s senza pacchetti (la PS5 ha smesso di mandare)."""
        if self.f is not None and time.monotonic() - self.ultimo > 60:
            self.chiudi()

    def chiudi(self):
        if self.f is not None:
            try:
                self.f.close()
            except OSError:
                pass
        self.f = None
        self.uid = None

    def elenco(self):
        out = []
        for n in sorted(os.listdir(self.cartella), reverse=True):
            if n.endswith(".f1rec.gz"):
                p = os.path.join(self.cartella, n)
                out.append({"nome": n, "mb": round(os.path.getsize(p) / 1e6, 1),
                            "in_corso": n == self.nome and self.f is not None})
        return out

    def ruota(self):
        """Tiene le registrazioni sotto il tetto in MB, togliendo le più vecchie."""
        tetto = self.imp["max_registrazioni_mb"] * 1e6
        file = sorted((os.path.join(self.cartella, n) for n in os.listdir(self.cartella)
                       if n.endswith(".f1rec.gz")), key=os.path.getmtime)
        totale = sum(os.path.getsize(f) for f in file)
        for f in file:
            if totale <= tetto or os.path.basename(f) == self.nome:
                break
            totale -= os.path.getsize(f)
            os.remove(f)


def leggi(percorso):
    """Genera (secondi, byte) da un file registrato. Un file tronco (container spento mentre
    registrava) si legge fino al punto in cui è arrivato."""
    with gzip.open(percorso, "rb") as f:
        if f.read(len(MAGIA)) != MAGIA:
            raise ValueError("non è una registrazione F1REC1")
        while True:
            try:
                testa = f.read(REC.size)
                if len(testa) < REC.size:
                    return
                t, n = REC.unpack(testa)
                dati = f.read(n)
            except (EOFError, gzip.BadGzipFile, OSError):
                return
            if len(dati) < n:
                return
            yield t, dati
