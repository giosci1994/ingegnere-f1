"""La traccia di ogni giro del giocatore: un campione per ogni pacchetto di telemetria (20 Hz).

Campo per campo (liste parallele, numeri arrotondati):
  t  tempo nel giro (s)          d  distanza nel giro (m)       x, z  posizione (m, dal motion)
  v  velocità (km/h)             th gas 0..1    br freno 0..1   st sterzo -1..1   g marcia
  sf slittamento anteriore più negativo (bloccaggio in frenata)
  sr slittamento posteriore più positivo (pattinamento in trazione)
  sb slittamento posteriore più negativo (bloccaggio dietro)
  yr velocità d'imbardata (rad/s)   wa angolo delle ruote anteriori (rad)   (dal motion ex)
  ts temperature di superficie [RL, RR, FL, FR]   ti temperature interne   bt freni (°C)
  am ali mobili 2026 (0 curva, 1 rettilineo, -1 non c'è)   aa ali disponibili (0/1)

I giri finiti si salvano in `dati/giri/<pista>/<id>.json.gz` (la «biblioteca» dei giri, anche
di sessioni diverse e di chi guida), per la traiettoria e i confronti.
"""

import gzip
import json
import os
import time

from . import pacchetti as P

CAMPI = ("t", "d", "x", "z", "v", "th", "br", "st", "g", "sf", "sr", "sb", "yr", "wa",
         "ts", "ti", "bt", "am", "aa")
MAX_GIRI_PER_PISTA = 300


class Giro:
    def __init__(self, numero):
        self.numero = numero
        self.c = {k: [] for k in CAMPI}
        self.invalido = False
        self.box = False
        self.sc = False

    def __len__(self):
        return len(self.c["d"])


class Tracciatore:
    """Riempie la traccia del giro in corso; alla fine del giro la consegna."""

    def __init__(self):
        self.giro = None
        self.ultimo_t = None

    def reset(self):
        self.giro = None
        self.ultimo_t = None

    def campione(self, st, idx):
        """Da chiamare a ogni pacchetto di telemetria. Restituisce il Giro appena finito, o None."""
        lap = st.auto(P.LAP, idx)
        tel = st.auto(P.TELEMETRY, idx)
        if lap is None or tel is None or lap.driver_status == 0:
            return None
        finito = None
        n = lap.current_lap_num
        if lap.result_status == 3:            # traguardo: l'ultimo giro si chiude qui (il numero non cambia più)
            if self.giro is not None and not getattr(self.giro, "chiuso", False) and len(self.giro):
                self.giro.chiuso = True
                return self.giro
            return None
        if self.giro is None or n != self.giro.numero:
            if self.giro is not None and n == self.giro.numero + 1:
                finito = self.giro
            self.giro = Giro(n)
        g = self.giro
        t = lap.current_lap_time_in_ms / 1000
        if g.c["t"] and t < g.c["t"][-1] - 0.5:      # flashback nel giro: si taglia la coda
            while g.c["t"] and g.c["t"][-1] > t:
                for k in CAMPI:
                    g.c[k].pop()
        if lap.current_lap_invalid:
            g.invalido = True
        if lap.pit_status:
            g.box = True
        ses = st.sessione()
        if ses is not None and ses.safety_car_status in (1, 2) and t > 3:   # il pacchetto sessione arriva in ritardo
            g.sc = True
        mot = st.auto(P.MOTION, idx)
        mex = st.get(P.MOTIONEX)
        t2 = st.auto(P.TELEMETRY2, idx) if st.formato == 2026 else None
        c = g.c
        c["t"].append(round(t, 3))
        c["d"].append(round(lap.lap_distance, 1))
        c["x"].append(round(mot.world_position_x, 1) if mot is not None else None)
        c["z"].append(round(mot.world_position_z, 1) if mot is not None else None)
        c["v"].append(tel.speed)
        c["th"].append(round(tel.throttle, 2))
        c["br"].append(round(tel.brake, 2))
        c["st"].append(round(tel.steer, 3))
        c["g"].append(tel.gear)
        if mex is not None:
            s = mex.wheel_slip_ratio
            c["sf"].append(round(min(s[2], s[3]), 3))
            c["sr"].append(round(max(s[0], s[1]), 3))
            c["sb"].append(round(min(s[0], s[1]), 3))
            c["yr"].append(round(mex.angular_velocity_y, 4))
            c["wa"].append(round(mex.front_wheels_angle, 4))
        else:
            for k in ("sf", "sr", "sb", "yr", "wa"):
                c[k].append(None)
        c["ts"].append(list(tel.tyres_surface_temperature))
        c["ti"].append(list(tel.tyres_inner_temperature))
        c["bt"].append(list(tel.brakes_temperature))
        c["am"].append(t2.active_aero_mode if t2 is not None else -1)
        c["aa"].append(t2.active_aero_available if t2 is not None else 0)
        return finito


def copertura(giro, lunghezza):
    """Quanta parte del giro è coperta dai campioni (0..1)."""
    d = [x for x in giro.c["d"] if x is not None and x >= 0]
    if not d or not lunghezza:
        return 0.0
    return min(1.0, (max(d) - min(d)) / lunghezza)


class Biblioteca:
    def __init__(self, cartella):
        self.cartella = cartella

    def salva(self, giro, meta):
        """meta: pista, tempo_ms, valido, sessione, pilota, session_uid, ..."""
        cart = os.path.join(self.cartella, str(meta["pista"]))
        os.makedirs(cart, exist_ok=True)
        gid = f"{time.strftime('%Y%m%d-%H%M%S')}-{meta['session_uid'] & 0xffffff:06x}-g{giro.numero}"
        meta = dict(meta, id=gid, giro=giro.numero, box=giro.box, safety_car=giro.sc,
                    invalido=giro.invalido, campioni=len(giro))
        p = os.path.join(cart, gid + ".json.gz")
        with gzip.open(p + ".tmp", "wt", encoding="utf-8", compresslevel=6) as f:
            json.dump({"meta": meta, "c": giro.c}, f, separators=(",", ":"))
        os.replace(p + ".tmp", p)
        self._indice_aggiungi(cart, meta)
        self._pulisci(cart)
        return gid

    def _indice(self, cart):
        p = os.path.join(cart, "indice.json")
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return []

    def _indice_aggiungi(self, cart, meta):
        ind = [m for m in self._indice(cart) if m["id"] != meta["id"]]
        ind.append(meta)
        with open(os.path.join(cart, "indice.json.tmp"), "w", encoding="utf-8") as f:
            json.dump(ind, f, ensure_ascii=False)
        os.replace(os.path.join(cart, "indice.json.tmp"), os.path.join(cart, "indice.json"))

    def _pulisci(self, cart):
        ind = self._indice(cart)
        if len(ind) <= MAX_GIRI_PER_PISTA:
            return
        # si tengono i migliori 20 validi e i più recenti
        validi = sorted((m for m in ind if m.get("valido")), key=lambda m: m["tempo_ms"])[:20]
        tieni = {m["id"] for m in validi}
        recenti = sorted(ind, key=lambda m: m["id"], reverse=True)
        for m in recenti:
            if len(tieni) >= MAX_GIRI_PER_PISTA:
                break
            tieni.add(m["id"])
        for m in ind:
            if m["id"] not in tieni:
                try:
                    os.remove(os.path.join(cart, m["id"] + ".json.gz"))
                except OSError:
                    pass
        nuovo = [m for m in ind if m["id"] in tieni]
        with open(os.path.join(cart, "indice.json"), "w", encoding="utf-8") as f:
            json.dump(nuovo, f, ensure_ascii=False)

    def piste(self):
        if not os.path.isdir(self.cartella):
            return []
        out = []
        for n in sorted(os.listdir(self.cartella)):
            ind = self._indice(os.path.join(self.cartella, n))
            if ind:
                out.append({"pista": int(n), "nome": P.PISTE.get(int(n), f"pista {n}"), "giri": len(ind)})
        return out

    def giri(self, pista):
        ind = self._indice(os.path.join(self.cartella, str(int(pista))))
        return sorted(ind, key=lambda m: m["id"], reverse=True)

    def leggi(self, pista, gid):
        if not all(ch.isalnum() or ch == "-" for ch in gid):
            return None
        p = os.path.join(self.cartella, str(int(pista)), gid + ".json.gz")
        if not os.path.exists(p):
            return None
        with gzip.open(p, "rt", encoding="utf-8") as f:
            return json.load(f)

    def migliore(self, pista, pilota=None, escludi_sessione=None):
        cand = [m for m in self.giri(pista) if m.get("valido") and not m.get("box")
                and not m.get("safety_car") and (pilota is None or m.get("pilota") == pilota)
                and m.get("session_uid") != escludi_sessione]
        return min(cand, key=lambda m: m["tempo_ms"]) if cand else None
