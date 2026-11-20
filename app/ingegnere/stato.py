"""Lo stato della sessione: l'ultimo pacchetto di ogni tipo, i nomi, la storia dei giri,
gli eventi. Lo aggiorna il ricevitore, lo leggono l'ingegnere e il riassunto."""

import time
from collections import Counter, deque

from . import pacchetti as P


def ms(minuti, millis):
    return minuti * 60000 + millis


class Stato:
    def __init__(self):
        self.reset(None)
        self.ultimo_pacchetto = 0.0          # time.monotonic() dell'ultimo datagramma
        self.mittente = None                 # ip della PS5
        self.ricevuti = Counter()            # per id
        self.scartati = Counter()            # per motivo
        self.taglie_scartate = Counter()     # (formato, id, len) dei pacchetti non decodificati
        self.formato = None
        self.versione_gioco = None
        self._finestra = deque(maxlen=400)   # tempi per calcolare i pacchetti al secondo

    def reset(self, session_uid):
        self.session_uid = session_uid
        self.inizio = time.time()
        self.p = {}                          # id -> ultimo Pacchetto
        self.storia = {}                     # car_idx -> pacchetto History
        self.eventi = []                     # (session_time, codice, dict) per il riassunto
        self.nomi = {}
        self.finale = None
        self.giocatore = 255
        self.n_auto = 0
        self.set_gomme = {}                  # car_idx -> pacchetto tyre sets (set di gomme)

    # ---- ingresso ----
    def aggiorna(self, pk, mittente=None):
        """Restituisce True se è cominciata una sessione nuova."""
        now = time.monotonic()
        self.ultimo_pacchetto = now
        self._finestra.append(now)
        self.mittente = mittente or self.mittente
        self.ricevuti[pk.id] += 1
        self.formato = pk.formato
        h = pk.header
        self.versione_gioco = f"{h.game_major_version}.{h.game_minor_version:02d}"
        nuova = False
        if h.session_uid and h.session_uid != self.session_uid:
            self.reset(h.session_uid)
            nuova = True
        self.giocatore = h.player_car_index
        if pk.dati is None:
            return nuova
        self.p[pk.id] = pk
        if pk.id == P.PARTICIPANTS:
            d = pk.dati
            self.n_auto = d.num_active_cars
            for i in range(min(d.num_active_cars, len(d.cars))):
                nome = d.cars[i].name.decode("utf-8", "replace").strip()
                self.nomi[i] = nome
        elif pk.id == P.HISTORY:
            self.storia[pk.dati.car_idx] = pk.dati
        elif pk.id == P.TYRESETS:
            self.set_gomme[pk.dati.car_idx] = pk.dati
        elif pk.id == P.FINAL:
            self.finale = pk.dati
        elif pk.id == P.EVENT:
            self.eventi.append((h.session_time, P.codice_evento(pk), pk))
            if len(self.eventi) > 5000:
                del self.eventi[:1000]
        return nuova

    # ---- lettura ----
    def pps(self):
        now = time.monotonic()
        return sum(1 for t in self._finestra if now - t < 1.0)

    def connesso(self, secondi=3.0):
        return self.ultimo_pacchetto and time.monotonic() - self.ultimo_pacchetto < secondi

    def get(self, pid):
        pk = self.p.get(pid)
        return pk.dati if pk else None

    def tempo(self):
        """Tempo di gioco della sessione (secondi), dall'ultimo pacchetto giri o telemetria."""
        for pid in (P.LAP, P.TELEMETRY, P.STATUS, P.SESSION):
            pk = self.p.get(pid)
            if pk:
                return pk.header.session_time
        return 0.0

    def indice(self, slot=1):
        """L'auto del giocatore (player_car_index). C'è sempre un giocatore solo (scelta del
        19/11/2026): lo schermo diviso e il secondo giocatore non si seguono."""
        i = self.giocatore
        if i is None or i == 255:
            return None
        n = P.STRUTTURE[self.formato]["n"] if self.formato else 22
        return i if i < n else None

    def auto(self, pid, idx):
        d = self.get(pid)
        if d is None or idx is None:
            return None
        return d.cars[idx]

    def nome(self, idx):
        n = self.nomi.get(idx) or ""
        if not n:
            return "la macchina"
        # «VERSTAPPEN» o «Max Verstappen» → «Verstappen»
        parte = n.split()[-1]
        return parte.capitalize() if parte.isupper() else parte

    def sessione(self):
        return self.get(P.SESSION)

    def tipo_sessione(self):
        s = self.sessione()
        return s.session_type if s else 0

    def in_gara(self):
        return self.tipo_sessione() in P.SESSIONE_GARA

    def auto_in_posizione(self, pos):
        lap = self.get(P.LAP)
        if lap is None:
            return None
        n = len(lap.cars)
        for i in range(n):
            c = lap.cars[i]
            if c.car_position == pos and c.result_status in (2, 3):  # attivo / finito
                return i
        for i in range(n):
            if lap.cars[i].car_position == pos and lap.cars[i].result_status != 0:
                return i
        return None

    def distacco_davanti(self, idx):
        """Secondi dalla macchina davanti (dal pacchetto giri), oppure None."""
        c = self.auto(P.LAP, idx)
        if c is None or c.car_position <= 1:
            return None
        v = ms(c.delta_to_car_in_front_minutes_part, c.delta_to_car_in_front_ms_part)
        return v / 1000 if v > 0 else None

    def distacco_dietro(self, idx):
        c = self.auto(P.LAP, idx)
        if c is None:
            return None, None
        j = self.auto_in_posizione(c.car_position + 1)
        if j is None:
            return None, None
        d = self.distacco_davanti(j)
        return d, j

    def riassunto_stato(self):
        s = self.sessione()
        return {
            "connesso": bool(self.connesso()),
            "mittente": self.mittente,
            "formato": self.formato,
            "versione_gioco": self.versione_gioco,
            "pacchetti_al_secondo": self.pps(),
            "ricevuti": sum(self.ricevuti.values()),
            "scartati": sum(self.scartati.values()),
            "taglie_scartate": [f"{f}/{i}/{n}B×{c}" for (f, i, n), c in
                                self.taglie_scartate.most_common(5)],
            "sessione": P.NOMI_SESSIONE.get(s.session_type, "?") if s else None,
            "pista": P.PISTE.get(s.track_id, f"pista {s.track_id}") if s else None,
            "giri_totali": s.total_laps if s else None,
            "in_pausa": bool(s.game_paused) if s else False,
        }
