"""Lo spotter: una macchina affiancata a sinistra o a destra (fase 5, 0.5.0).

Dal pacchetto motion (posizione di tutte le auto, 20 al secondo): per ogni altra auto la
distanza lungo la direzione del giocatore (avanti/indietro) e di lato (destra/sinistra). È
affiancata se è entro 5,5 m avanti o indietro e tra 0,8 e 4 m di lato. La direzione viene da
`world_forward_dir`/`world_right_dir` del giocatore (interi su 32767); se il pacchetto non li ha
(il simulatore), dal movimento tra due pacchetti.

Si dice solo all'inizio dell'affiancamento (due pacchetti di fila, sopra i 50 km/h, fuori dai
box), con un'attesa di 5 s per lato su un orologio che non torna indietro con i flashback; «Libero»
quando un affiancamento di almeno 2 s finisce. Priorità 1 e ttl di 1,5 s: se non si può dire
subito, non si dice più.
"""

import math
import time

from . import pacchetti as P
from .ingegnere import Messaggio

AVANTI_M = 5.5
LATO_MIN, LATO_MAX = 0.8, 4.0


class Spotter:
    def __init__(self):
        self.reset()

    def reset(self):
        self.lati = {"sinistra": 0, "destra": 0}     # pacchetti di fila con una macchina di lato
        self.dal = {"sinistra": None, "destra": None}
        self.detto = {"sinistra": -1e9, "destra": -1e9}
        self.prec = None             # (x, z) del giocatore al pacchetto prima
        self.ora = 0.0
        self._t = None

    def _direzioni(self, me):
        fx, fz = me.world_forward_dir_x / 32767.0, me.world_forward_dir_z / 32767.0
        rx, rz = me.world_right_dir_x / 32767.0, me.world_right_dir_z / 32767.0
        if abs(fx) + abs(fz) > 0.5 and abs(rx) + abs(rz) > 0.5:
            return (fx, fz), (rx, rz)
        if self.prec is None:
            return None
        dx, dz = me.world_position_x - self.prec[0], me.world_position_z - self.prec[1]
        lung = math.hypot(dx, dz)
        if lung < 0.05:
            return None
        fx, fz = dx / lung, dz / lung
        return (fx, fz), (-fz, fx)

    def valuta(self, st):
        """Da chiamare a ogni pacchetto motion. Restituisce i Messaggi (0 o 1)."""
        idx = st.indice()
        mot = st.get(P.MOTION)
        lap_all = st.get(P.LAP)
        tel = st.auto(P.TELEMETRY, idx)
        if idx is None or mot is None or lap_all is None:
            return []
        t = st.tempo()
        if self._t is not None and 0 < t - self._t < 2:
            self.ora += t - self._t
        self._t = t
        me = mot.cars[idx]
        dirz = self._direzioni(me)
        self.prec = (me.world_position_x, me.world_position_z)
        mio = lap_all.cars[idx]
        if dirz is None or mio.pit_status or (tel is not None and tel.speed < 50):
            self.lati = {"sinistra": 0, "destra": 0}
            self.dal = {"sinistra": None, "destra": None}
            return []
        (fx, fz), (rx, rz) = dirz
        lati = set()
        for j in range(min(st.n_auto or len(mot.cars), len(mot.cars))):
            if j == idx or lap_all.cars[j].result_status != 2 or lap_all.cars[j].pit_status:
                continue
            c = mot.cars[j]
            dx, dz = c.world_position_x - me.world_position_x, c.world_position_z - me.world_position_z
            avanti = dx * fx + dz * fz
            lato = dx * rx + dz * rz
            if abs(avanti) <= AVANTI_M and LATO_MIN <= abs(lato) <= LATO_MAX:
                lati.add("destra" if lato > 0 else "sinistra")
        out = []
        nuovi = []
        for lato in ("sinistra", "destra"):
            if lato in lati:
                self.lati[lato] += 1
                if self.lati[lato] == 2:
                    self.dal[lato] = self.ora
                    if self.ora - self.detto[lato] >= 5:
                        self.detto[lato] = self.ora
                        nuovi.append(lato)
            else:
                if self.lati[lato] >= 2 and self.dal[lato] is not None and self.ora - self.dal[lato] >= 2 \
                        and not any(self.lati[x] >= 2 for x in self.lati if x != lato):
                    out.append(self._msg("spotter_libero", "Libero.", t, livello=2))
                self.lati[lato] = 0
                self.dal[lato] = None
        if len(nuovi) == 2 or (nuovi and all(self.lati[x] >= 2 for x in self.lati)):
            out = [self._msg("spotter", "Macchine ai due lati.", t)]
        elif nuovi:
            out = [self._msg("spotter", f"Macchina a {nuovi[0]}.", t)]
        return out

    @staticmethod
    def _msg(chiave, testo, t, livello=1):
        m = Messaggio("spotter", chiave, testo, priorita=1, livello=livello, ttl=1.5, interrompe=True,
                      creato=t, fisso=True)
        m.nato = time.monotonic()        # per misurare il ritardo vero fino alla radio
        return m
