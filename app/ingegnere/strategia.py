"""Strategia in diretta: undercut, overcut, dove esci dopo la sosta.

Che cosa si sa e che cosa no:
- di tutte le auto si sanno distacchi (dal leader e da chi è davanti), mescola, età delle gomme
  in giri, numero di soste e tempi sul giro. **L'usura delle altre auto non si sa**: non si
  inventa. Per il vantaggio delle gomme nuove si usa il degrado misurato sui giri del
  giocatore (secondi persi per giro di età), dichiarato come stima.
- il **tempo perso al box** si misura per pista: per ogni auto che si ferma,
  (giro di entrata + giro di uscita) − 2 × la mediana dei suoi ultimi giri puliti.
  Si salva in `dati/piste.json` (mediana delle ultime 15 misure). Finché non c'è una misura,
  si usa una stima generica di 22 s e lo si dice.
"""

import json
import os
import statistics

from . import pacchetti as P
from .stato import ms

PERDITA_STIMA = 22.0


class Piste:
    def __init__(self, percorso):
        self.percorso = percorso
        try:
            with open(percorso, encoding="utf-8") as f:
                self.dati = json.load(f)
        except (OSError, ValueError):
            self.dati = {}

    def perdita_box(self, pista):
        v = self.dati.get(str(pista), {}).get("perdita_box", [])
        if len(v) >= 1:
            return round(statistics.median(v), 1), True
        return PERDITA_STIMA, False

    def aggiungi_perdita(self, pista, secondi):
        if not 8 <= secondi <= 60:
            return
        p = self.dati.setdefault(str(pista), {})
        p.setdefault("perdita_box", []).append(round(secondi, 2))
        p["perdita_box"] = p["perdita_box"][-15:]
        p["nome"] = P.PISTE.get(int(pista), str(pista))
        tmp = self.percorso + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.dati, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.percorso)


class Strategia:
    def __init__(self, piste):
        self.piste = piste
        self.reset()

    def reset(self):
        self.giro_auto = {}       # idx -> ultimo giro visto
        self.tempi = {}           # idx -> [(giro, ms, pit, sc)]
        self.soste_viste = {}     # idx -> num_pit_stops
        self.in_pit = {}          # idx -> giro in cui è entrato
        self.misure = []          # perdite misurate in questa sessione
        self.sc_nel_giro = {}     # idx -> safety car vista durante il giro in corso

    # ---------- osservazione di tutte le auto (a ogni pacchetto giri) ----------
    def osserva(self, st):
        lap = st.get(P.LAP)
        ses = st.sessione()
        if lap is None or ses is None or not st.in_gara():
            return []
        sc_ora = ses.safety_car_status in (1, 2)
        entrate = []
        for i in range(min(st.n_auto or len(lap.cars), len(lap.cars))):
            c = lap.cars[i]
            if c.result_status not in (2, 3):
                continue
            g = c.current_lap_num
            prima = self.giro_auto.get(i)
            if sc_ora:
                self.sc_nel_giro[i] = True
            if c.pit_status and i not in self.in_pit:
                self.in_pit[i] = g
                if prima is not None:          # entra in pit lane adesso
                    entrate.append(i)
            if prima is not None and g == prima + 1 and c.last_lap_time_in_ms:
                pit = i in self.in_pit and self.in_pit[i] >= prima - 1
                sc = self.sc_nel_giro.pop(i, False) or sc_ora
                self.tempi.setdefault(i, []).append((prima, c.last_lap_time_in_ms, pit, sc))
                self._misura(st, i)
            self.giro_auto[i] = g
            self.soste_viste[i] = c.num_pit_stops
            if not c.pit_status and i in self.in_pit and g > self.in_pit[i] + 1:
                del self.in_pit[i]
        return entrate

    def _misura(self, st, i):
        """Dopo il giro di uscita: (entrata + uscita) − 2 × mediana dei giri puliti prima."""
        t = self.tempi.get(i, [])
        if len(t) < 5:
            return
        # cerca la coppia entrata/uscita appena finita: gli ultimi due giri marcati pit
        if not (t[-1][2] and t[-2][2]) or (len(t) >= 3 and t[-3][2]):
            return
        if t[-1][3] or t[-2][3]:
            return                      # con la safety car la misura non vale
        puliti = [x[1] for x in t[:-2] if not x[2] and not x[3] and x[0] > 1][-4:]
        if len(puliti) < 2:
            return
        perdita = (t[-1][1] + t[-2][1] - 2 * statistics.median(puliti)) / 1000
        if not 8 <= perdita <= 60:
            return
        ses = st.sessione()
        self.misure.append(round(perdita, 2))
        self.piste.aggiungi_perdita(ses.track_id, perdita)

    def degrado(self, idx, ultimo_stint=True):
        """Secondi persi per giro di età gomme, dai giri puliti di uno stint del giocatore:
        l'ultimo stint con almeno 3 giri puliti (in diretta: solo quello in corso)."""
        t = self.tempi.get(idx, [])
        stint, stints = [], []
        for g, tempo, pit, sc in t:
            if pit:
                if stint:
                    stints.append(stint)
                stint = []
                continue
            if not sc and g > 1:          # il primo giro (partenza da fermo) non conta
                stint.append((g, tempo / 1000))
        stints.append(stint)
        candidati = stints[-1:] if ultimo_stint else stints
        for st_ in reversed(candidati):
            d = self._pendenza(st_[-6:])
            if d is not None:
                return d
        return None

    @staticmethod
    def _pendenza(stint):
        if len(stint) < 3:
            return None
        xs = [g for g, _ in stint]
        ys = [y for _, y in stint]
        med = statistics.median(ys)
        punti = [(x, y) for x, y in zip(xs, ys) if y < med * 1.03]
        if len(punti) < 3:
            return None
        mx = sum(x for x, _ in punti) / len(punti)
        my = sum(y for _, y in punti) / len(punti)
        den = sum((x - mx) ** 2 for x, _ in punti)
        if not den:
            return None
        return sum((x - mx) * (y - my) for x, y in punti) / den

    # ---------- dove esci se ti fermi adesso ----------
    def rientro(self, st, idx):
        lap = st.get(P.LAP)
        ses = st.sessione()
        if lap is None or ses is None:
            return None
        perdita, misurata = self.piste.perdita_box(ses.track_id)
        mio = lap.cars[idx]
        mio_gap = ms(mio.delta_to_race_leader_minutes_part, mio.delta_to_race_leader_ms_part) / 1000
        if mio.car_position == 1:
            mio_gap = 0.0
        nuovo = mio_gap + perdita
        altri = []
        for i in range(min(st.n_auto or len(lap.cars), len(lap.cars))):
            c = lap.cars[i]
            if i == idx or c.result_status != 2:
                continue
            g = 0.0 if c.car_position == 1 else ms(c.delta_to_race_leader_minutes_part,
                                                   c.delta_to_race_leader_ms_part) / 1000
            altri.append((g, i))
        altri.sort()
        davanti = [x for x in altri if x[0] < nuovo]
        dietro = [x for x in altri if x[0] >= nuovo]
        return {
            "posizione": len(davanti) + 1,
            "dietro_a": davanti[-1][1] if davanti else None,
            "margine_davanti": round(nuovo - davanti[-1][0], 1) if davanti else None,
            "davanti_a": dietro[0][1] if dietro else None,
            "margine_dietro": round(dietro[0][0] - nuovo, 1) if dietro else None,
            "perdita": perdita, "misurata": misurata,
        }
