"""Simulatore: una sessione finta che fa scattare tutte le regole dell'ingegnere (fasi 1 e 2).

    python -m ingegnere.simulatore --uscita FILE [--formato 2026|2025] [--giri 8] [--seme 1]
                                   [--sessione gara|prove] [--pilota-lento]

Scrive una registrazione (formato di registratore.py) che si rimanda in UDP con
`python -m ingegnere.riproduci FILE`. Solo libreria standard.

La pista: 5793 m, 6 curve (apice, velocità minima, angolo), rettilinei a 320 km/h; la
geometria (x, z) si costruisce integrando la curvatura. Ogni auto segue lo stesso profilo di
velocità con un suo fattore; posizioni e distacchi vengono dalla distanza percorsa.
Il giocatore (indice 0) parte P8 e ha un copione:
- giro 1 guadagna; giro 2 giro non valido, bandiera gialla, contromano, avvertimento;
- giro 3 safety car, e in curva 4 frena 30 m prima e allarga la traiettoria;
- giro 4 contatto, danno all'ala, penalità; bloccaggio in curva 2; l'auto davanti si ferma;
- giro 5 l'auto dietro si ferma, finestra box, ali in modalità curva sul rettilineo, sosta a fine giro;
- giro 6 VSC, guasto ERS, freni caldi, pattinamento e gas tardi in curva 5;
- giro 7 pioggia, giro veloce; poi bandiera a scacchi, classifica finale, fine sessione;
- tasti (evento BUTN): UDP Action 2 al giro 3, 1 al giro 5, 7 al giro 6 (le domande).
Il giocatore sottosterza nelle curve lente, le posteriori scaldano più delle anteriori e lo
speed trap è più basso degli altri: servono a far scattare i consigli d'assetto.
`--sessione prove --pilota-lento` fa una sessione di prove più lenta, da confrontare.
`--pulita --giri 10` fa una gara senza safety car né incidenti, con gomme che calano di più e
la sosta al giro 7: serve a provare l'undercut.
"""

import argparse
import gzip
import math

from . import pacchetti as P
from .registratore import MAGIA, REC

PISTA = 5793.0
DT = 0.05                       # 20 Hz
VMAX = 320 / 3.6
FRENA, ACCEL = 38.0, 9.0        # m/s²
CURVE = [(900, 80, 90), (1500, 120, 60), (2300, 200, 45), (3000, 90, 90), (3900, 150, 45), (4800, 110, 30)]
ARCO = 120.0
PASSO = 3.6
NOMI = ["PILOTA", "ROSSI", "BIANCHI", "VERDI", "NERI", "GIALLI", "MARRONI", "BLU", "ROSA",
        "VIOLA", "ARANCIO", "GRIGI", "BRUNI", "FERRARI", "ESPOSITO", "ROMANO", "COLOMBO",
        "RICCI", "MARINO", "GRECO"]


def _wrap(x):
    x = x % PISTA
    return x - PISTA if x > PISTA / 2 else x


def curvatura(d):
    k = 0.0
    for ap, _, ang in CURVE:
        if abs(_wrap(d - ap)) <= ARCO / 2:
            k += math.radians(ang) / ARCO
    return k


def profilo(d, mod=None):
    """Velocità (m/s) alla distanza d; mod = {curva: (anticipo frenata m, delta vmin km/h, ritardo gas m)}."""
    v = VMAX
    for n, (ap, vmin, _) in enumerate(CURVE, start=1):
        anticipo, dv, ritardo = (mod or {}).get(n, (0, 0, 0))
        vc = (vmin + dv) / 3.6
        x = _wrap(d - ap)
        if x < 0:
            vb = math.sqrt(vc * vc + 2 * FRENA * (-x - anticipo)) if -x > anticipo else vc
        else:
            vb = math.sqrt(vc * vc + 2 * ACCEL * max(0.0, x - ritardo))
        v = min(v, vb)
    return v


def costruisci_pista():
    """(x, z) ogni metro, chiusa correggendo l'errore in modo lineare."""
    xs, zs, th, x, z = [], [], 0.0, 0.0, 0.0
    n = int(PISTA)
    for i in range(n + 1):
        xs.append(x)
        zs.append(z)
        th += curvatura(i)
        x += math.cos(th)
        z += math.sin(th)
    ex, ez = xs[-1] - xs[0], zs[-1] - zs[0]
    return [(xs[i] - ex * i / n, zs[i] - ez * i / n) for i in range(n + 1)]


TRACCIATO = costruisci_pista()


def posizione(d, offset=0.0):
    d = d % PISTA
    i = int(d)
    x0, z0 = TRACCIATO[i]
    x1, z1 = TRACCIATO[min(i + 1, len(TRACCIATO) - 1)]
    f = d - i
    x, z = x0 + (x1 - x0) * f, z0 + (z1 - z0) * f
    dx, dz = x1 - x0, z1 - z0
    nrm = math.hypot(dx, dz) or 1
    return x + offset * (-dz / nrm), z + offset * (dx / nrm)


def tempo_base():
    t, d = 0.0, 0.0
    while d < PISTA:
        d += profilo(d) * 0.01
        t += 0.01
    return t


T_BASE = tempo_base()
V_MEDIA = PISTA / T_BASE


def _zone_ali():
    """Rettilinei (zone delle ali mobili): più lontano di 300 m dagli apici."""
    zone, dentro, inizio = [], False, 0
    for d in range(0, int(PISTA), 10):
        ok = all(abs(_wrap(d - ap)) > 300 for ap, _, _ in CURVE)
        if ok and not dentro:
            dentro, inizio = True, d
        elif not ok and dentro:
            dentro = False
            zone.append((inizio, d))
    if dentro:
        zone.append((inizio, PISTA))
    return zone


ZONE_ALI = _zone_ali()


def in_zona_ali(d):
    d = d % PISTA
    for k, (a, b) in enumerate(ZONE_ALI):
        if a <= d < b:
            return k + 1
    return 0


class Sim:
    def __init__(self, o):
        self.o = o
        self.fmt = o.formato
        self.S = P.STRUTTURE[self.fmt]
        self.n = 20
        self.giri = o.giri
        self.gara = o.sessione == "gara"
        self.out = gzip.open(o.uscita, "wb", compresslevel=6)
        self.out.write(MAGIA)
        self.t_rec = 0.0
        self.t_gioco = 0.0
        self.frame = 0
        self.uid = 0x5EED0000 + o.seme + (0x100 if not self.gara else 0) + (0x200 if o.pilota_lento else 0)
        ordine = list(range(1, self.n))
        ordine.insert(7, 0)
        self.griglia = {idx: p + 1 for p, idx in enumerate(ordine)}
        self.fattore = {i: 1 - 0.0015 * (self.griglia[i] - 1) for i in range(self.n)}
        self.d = {i: -(self.griglia[i] - 1) * 8.0 for i in range(self.n)}
        self.passaggi = {i: [] for i in range(self.n)}
        self.finito = {i: None for i in range(self.n)}
        self.pit = {i: 0 for i in range(self.n)}
        self.pit_t = {i: None for i in range(self.n)}
        self.soste = {i: 0 for i in range(self.n)}
        self.vuole_box = set()
        self.cambio = {i: 0.0 for i in range(self.n)}
        self.mescola = {i: 17 for i in range(self.n)}
        self.pit_corsia = 14.0
        self.pos = {i: self.griglia[i] for i in range(self.n)}
        self.pos_prec = None
        self.flashback_fatto = False
        self.fatti = set()
        self.avvertimenti = 0
        self.sc = 0
        self.vel = {i: 0.0 for i in range(self.n)}
        self.pulita = o.pulita
        self.giro_box = 7 if o.pulita else 5
        self.degrado = 0.005 if o.pulita else 0.0025

    # ---------- scrittura ----------
    def h(self, x, pid):
        hd = x.header
        hd.packet_format, hd.game_year, hd.game_major_version, hd.game_minor_version = self.fmt, 25, 1, 10
        hd.packet_version, hd.packet_id, hd.session_uid = 1, pid, self.uid
        hd.session_time, hd.frame_identifier, hd.overall_frame_identifier = self.t_gioco, self.frame, self.frame
        hd.player_car_index, hd.secondary_player_car_index = 0, 255
        b = bytes(x)
        self.out.write(REC.pack(self.t_rec, len(b)))
        self.out.write(b)

    def evento(self, code, **campi):
        e = self.S[P.EVENT]()
        e.code[:] = list(code.encode())
        if campi:
            nome, valori = next(iter(campi.items()))
            d = getattr(e.details, nome)
            for k, v in valori.items():
                setattr(d, k, v)
        self.h(e, P.EVENT)

    def una_volta(self, k):
        if k in self.fatti:
            return False
        self.fatti.add(k)
        return True

    # ---------- copione ----------
    def giro_di(self, i):
        return int(self.d[i] // PISTA) + 1 if self.d[i] >= 0 else 1

    def giro_g(self):
        return self.giro_di(0)

    def frazione(self):
        return (self.d[0] % PISTA) / PISTA if self.d[0] >= 0 else 0.0

    def mod_giocatore(self):
        if self.o.pilota_lento:
            return {n: (25, -6, 20) for n in range(1, 7)}
        g = self.giro_g()
        if g == self.giri:
            return {4: (30, -4, 0)}     # ultimo giro: frena 30 m prima in curva 4 (e allarga)
        if g == 4:
            return {2: (0, -8, 0)}
        if g == 6:
            return {5: (0, -3, 30)}
        return {}

    def velocita(self, i, partito):
        if not partito or self.finito[i] is not None:
            return 0.0
        if self.pit[i]:
            return 0.0 if self.pit[i] == 2 else 80 / 3.6
        dist = self.d[i] % PISTA if self.d[i] >= 0 else 0
        eta = max(0.0, (self.d[i] - self.cambio[i]) / PISTA)
        f = self.fattore[i] * (1 - self.degrado * eta)
        if i == 0:
            f *= {1: 1.006, 2: 0.998, 7: 1.02}.get(self.giro_g(), 1.0)
            if self.o.pilota_lento:
                f *= 0.99
        if self.sc == 1:
            f *= 0.7
        return profilo(dist, self.mod_giocatore() if i == 0 else None) * f

    def davanti_a(self, i):
        return next((j for j in range(self.n) if self.pos[j] == self.pos[i] - 1), None)

    # ---------- passo ----------
    def passo(self):
        o = self
        partito = o.t_rec >= 11.0
        for k in range(1, 6):
            if abs(o.t_rec - (5 + k)) < DT / 2 and o.una_volta(f"luce{k}"):
                o.evento("STLG", start_lights={"num_lights": k})
        if partito and o.una_volta("via"):
            o.evento("LGOT")
        g, fr = o.giro_g(), o.frazione()

        if o.gara:
            if g == (6 if o.pulita else 4) and o.una_volta("box_davanti") and not o.pulita:
                av = o.davanti_a(0)
                if av is not None:
                    o.vuole_box.add(av)
            if g == 5 and o.una_volta("box_dietro"):
                di = next((j for j in range(o.n) if o.pos[j] == o.pos[0] + 1), None)
                if di is not None:
                    o.vuole_box.add(di)
            if g == o.giro_box and o.soste[0] == 0 and not o.pit[0] and o.una_volta("box_mio"):
                o.vuole_box.add(0)
        # soste: entrata a fine giro, 14 s in pit lane, 2,5 s fermi
        for i in range(o.n):
            fr_i = (o.d[i] % PISTA) / PISTA if o.d[i] >= 0 else 0
            if not o.pit[i] and i in o.vuole_box and fr_i > 0.965:
                o.pit[i], o.pit_t[i] = 1, o.t_rec
                o.vuole_box.discard(i)
            if o.pit[i]:
                dt = o.t_rec - o.pit_t[i]
                o.pit[i] = 2 if 6 <= dt < 8.5 else 1
                if dt >= o.pit_corsia:
                    o.pit[i] = 0
                    o.soste[i] += 1
                    o.mescola[i] = 18
                    o.cambio[i] = o.d[i]
        for i in range(o.n):
            v = o.velocita(i, partito)
            o.vel[i] = v
            prima = o.d[i]
            o.d[i] += v * DT
            if prima < 0 <= o.d[i] or (prima >= 0 and int(prima // PISTA) < int(o.d[i] // PISTA)):
                o.passaggi[i].append(o.t_rec)
                if int(o.d[i] // PISTA) >= o.giri and o.finito[i] is None:
                    o.finito[i] = o.t_rec
                    if i == 0 and o.gara:
                        o.evento("CHQF")

        def chiave(i):
            return (0, o.finito[i]) if o.finito[i] is not None else (1, -o.d[i])
        ordine = sorted(range(o.n), key=chiave)
        o.pos = {idx: p + 1 for p, idx in enumerate(ordine)}
        if o.pos_prec and partito and o.gara:
            p0, q0 = o.pos_prec[0], o.pos[0]
            if q0 < p0:
                altro = next(i for i in range(o.n) if o.pos[i] == q0 + 1)
                o.evento("OVTK", overtake={"overtaking_vehicle_idx": 0, "being_overtaken_vehicle_idx": altro})
            elif q0 > p0 and not o.pit[0]:
                altro = next(i for i in range(o.n) if o.pos[i] == q0 - 1)
                o.evento("OVTK", overtake={"overtaking_vehicle_idx": altro, "being_overtaken_vehicle_idx": 0})
        o.pos_prec = dict(o.pos)

        if not o.gara or o.pulita:
            o.sc = 0
            return
        sc = 0
        if g == 3:
            sc = 1
            if o.una_volta("sc_dentro"):
                o.evento("SCAR", safety_car={"safety_car_type": 1, "event_type": 0})
            if fr > 0.5 and o.una_volta("sc_rientra"):
                o.evento("SCAR", safety_car={"safety_car_type": 1, "event_type": 1})
        if g == 4 and o.una_volta("sc_via"):
            o.evento("SCAR", safety_car={"safety_car_type": 1, "event_type": 2})
            o.evento("SCAR", safety_car={"safety_car_type": 1, "event_type": 3})
        if g == 6 and 0.3 < fr < 0.4:
            sc = 2
        o.sc = sc
        if g == 2 and fr > 0.6 and o.una_volta("avvertimento"):
            o.avvertimenti = 2
            o.evento("PENA", penalty={"penalty_type": 5, "infringement_type": 7, "vehicle_idx": 0,
                                      "other_vehicle_idx": 255, "time": 255, "lap_num": 2,
                                      "places_gained": 255})
        if g == 4 and fr > 0.5 and o.una_volta("contatto"):
            altro = o.davanti_a(0)
            ev = {"vehicle1_idx": 0, "vehicle2_idx": altro if altro is not None else 1}
            if o.fmt == 2026:
                ev["severity"] = 2
            o.evento("COLL", collision=ev)
        if g == 4 and fr > 0.6 and o.una_volta("penalita"):
            o.evento("PENA", penalty={"penalty_type": 4, "infringement_type": 9, "vehicle_idx": 0,
                                      "other_vehicle_idx": 255, "time": 5, "lap_num": 4,
                                      "places_gained": 255})
        # domande dai tasti (fase 3): UDP Action 2 (gomme) al giro 3, 1 (strategia) al giro 5,
        # 7 (ripeti) al giro 6; con R2 (gas) tenuto premuto, per provare il fronte di salita
        for giro_t, frz, bit in ((3, 0.2, 0x00200000), (5, 0.3, 0x00100000), (6, 0.5, 0x00100000 << 6)):
            if g == giro_t and fr > frz and o.una_volta(f"tasto{giro_t}"):
                o.evento("BUTN", buttons={"button_status": 0x1000 | bit})
                o.evento("BUTN", buttons={"button_status": 0x1000 | bit})
                o.evento("BUTN", buttons={"button_status": 0x1000})
        if g == 6 and fr > 0.7 and not o.flashback_fatto:
            o.flashback_fatto = True
            o.evento("FLBK", flashback={"flashback_frame_identifier": o.frame - 80,
                                        "flashback_session_time": o.t_gioco - 4})
            o.t_gioco -= 4

    # ---------- pacchetti ----------
    def tempo_ultimo(self, i):
        p = self.passaggi[i]
        return int((p[-1] - p[-2]) * 1000) if len(p) >= 2 else 0

    def lap(self):
        o = self
        x = o.S[P.LAP]()
        capo = next(j for j in range(o.n) if o.pos[j] == 1)
        for i in range(o.n):
            c = x.cars[i]
            c.last_lap_time_in_ms = o.tempo_ultimo(i)
            c.current_lap_time_in_ms = int((o.t_rec - o.passaggi[i][-1]) * 1000) if o.passaggi[i] else 0
            c.current_lap_num = min(o.giro_di(i), o.giri) if o.finito[i] is None else o.giri
            dist = o.d[i] % PISTA if o.d[i] >= 0 else o.d[i]
            c.lap_distance, c.total_distance = dist, o.d[i]
            c.sector = 0 if dist < PISTA / 3 else (1 if dist < 2 * PISTA / 3 else 2)
            c.car_position = o.pos[i]
            c.grid_position = o.griglia[i]
            c.driver_status = 0 if o.t_rec < 3 else 4
            c.result_status = 3 if o.finito[i] is not None else 2
            c.pit_status = o.pit[i]
            c.num_pit_stops = o.soste[i]
            davanti = o.davanti_a(i)
            if davanti is not None and o.finito[i] is None:
                dd = max(0.0, (o.d[davanti] - o.d[i]) / V_MEDIA) * 1000
                c.delta_to_car_in_front_minutes_part, c.delta_to_car_in_front_ms_part = int(dd // 60000), int(dd % 60000)
            dl = max(0.0, (o.d[capo] - o.d[i]) / V_MEDIA) * 1000
            c.delta_to_race_leader_minutes_part, c.delta_to_race_leader_ms_part = int(dl // 60000), int(dl % 60000)
            c.safety_car_delta = 2.0
            if o.t_rec > 60:
                c.speed_trap_fastest_speed = 318.0 if i == 0 else 322.0 + (i % 5) * 2
        p = x.cars[0]
        g, fr = o.giro_g(), o.frazione()
        if o.pit[0]:
            p.pit_lane_timer_active = 1
            p.pit_lane_time_in_lane_in_ms = int((o.t_rec - o.pit_t[0]) * 1000)
            p.pit_stop_timer_in_ms = int(max(0, min(o.t_rec - o.pit_t[0] - 6, 2.5)) * 1000)
        elif o.soste[0]:
            p.pit_lane_time_in_lane_in_ms = int(o.pit_corsia * 1000)
            p.pit_stop_timer_in_ms = 2500
        if o.gara and g == 2 and fr > 0.55:
            p.current_lap_invalid = 1
        p.corner_cutting_warnings = p.total_warnings = o.avvertimenti
        if o.sc == 1 and 0.6 < fr < 0.65:
            p.safety_car_delta = -0.6
        o.h(x, P.LAP)

    def session(self):
        o = self
        x = o.S[P.SESSION]()
        g, fr = o.giro_g(), o.frazione()
        x.weather = 3 if (o.gara and g == 7 and 0.1 < fr < 0.9) else 0
        x.track_temperature, x.air_temperature = 32, 24
        x.total_laps, x.track_length, x.track_id = o.giri if o.gara else 0, int(PISTA), 11
        x.session_type = 15 if o.gara else 3
        x.session_duration = 3600
        x.session_time_left = max(0, int(3600 - o.t_rec))
        x.pit_speed_limit = 80
        x.safety_car_status = o.sc
        if o.gara:
            x.num_weather_forecast_samples = 5
            for k, (off, w, rain) in enumerate(((0, 0, 10), (5, 1, 20), (10, 3, 60), (15, 3, 70), (30, 2, 40))):
                s = x.weather_forecast_samples[k]
                s.session_type, s.time_offset, s.weather, s.rain_percentage = 15, off, w, rain
            x.pit_stop_window_ideal_lap, x.pit_stop_window_latest_lap = (6, 8) if o.pulita else (5, 6)
            x.pit_stop_rejoin_position = 10
        if o.fmt == 2026:
            x.active_aero_track_status = 0
            x.num_active_aero_zones_full = len(ZONE_ALI)
            for k, (a, b) in enumerate(ZONE_ALI[:8]):
                x.active_aero_zones_full[k].zone_start = a / PISTA
                x.active_aero_zones_full[k].zone_end = b / PISTA
        o.h(x, P.SESSION)

    def telemetry(self):
        o = self
        x = o.S[P.TELEMETRY]()
        g, fr = o.giro_g(), o.frazione()
        for i in range(o.n):
            c = x.cars[i]
            v = o.vel[i]
            c.speed = int(v * 3.6)
            dist = o.d[i] % PISTA if o.d[i] >= 0 else 0
            mod = o.mod_giocatore() if i == 0 else None
            qui = profilo(dist, mod)
            vprox = profilo(dist + 15, mod) * (v / qui if qui and v else o.fattore[i])
            if o.pit[i] or o.t_rec < 11:
                c.throttle, c.brake = 0.2, 0.0
            elif vprox < v - 0.3:
                c.throttle, c.brake = 0.0, 1.0
            elif abs(vprox - v) <= 0.3 and v < 0.95 * VMAX:
                c.throttle, c.brake = 0.4, 0.0
            else:
                c.throttle, c.brake = 1.0, 0.0
            k = curvatura(dist)
            c.steer = max(-1.0, min(1.0, k * PASSO * 6))
            c.gear = max(1, min(8, int(v * 3.6 / 40)))
            c.engine_rpm = 11000
            c.brakes_temperature[:] = [550] * 4
            c.tyres_surface_temperature[:] = [96] * 4
            c.tyres_inner_temperature[:] = [98] * 4
            c.tyres_pressure[:] = [22.5] * 4
        p = x.cars[0]
        p.tyres_surface_temperature[:] = [105, 104, 94, 95]
        if o.pit[0]:
            p.speed = 95 if o.t_rec - o.pit_t[0] < 1.5 else (0 if o.pit[0] == 2 else 80)
        if o.gara and g == 2 and 0.3 < fr < 0.42:
            p.tyres_inner_temperature[:] = [99, 101, 116, 104]
        if o.gara and g == 6 and 0.6 < fr < 0.66:
            p.brakes_temperature[:] = [700, 700, 1080, 1060]
        o.h(x, P.TELEMETRY)

    def motion(self):
        o = self
        x = o.S[P.MOTION]()
        g = o.giro_g()
        for i in range(o.n):
            dist = o.d[i] if o.d[i] >= 0 else PISTA + o.d[i]
            off = 0.0
            if i == 0 and o.gara and g == o.giri and abs(_wrap(dist - CURVE[3][0])) < 120:
                off = 3.0 * math.cos(_wrap(dist - CURVE[3][0]) / 120 * math.pi / 2)
            if i == 0 and o.o.pilota_lento:
                off = 1.5 * math.sin(dist / 300)
            x.cars[i].world_position_x, x.cars[i].world_position_z = posizione(dist, off)
        o.h(x, P.MOTION)

    def motionex(self):
        o = self
        x = o.S[P.MOTIONEX]()
        g = o.giro_g()
        dist = o.d[0] % PISTA if o.d[0] >= 0 else 0
        v = o.vel[0]
        k = curvatura(dist)
        x.angular_velocity_y = v * k
        wa = math.atan(PASSO * k)
        if v * 3.6 < 150 and k:
            wa /= 0.82                    # sottosterzo nelle curve lente
        x.front_wheels_angle = wa
        s = [0.02, 0.02, -0.01, -0.01]
        if o.gara and g == 4 and -70 < _wrap(dist - CURVE[1][0]) < 0:
            s[2] = s[3] = -0.3            # bloccaggio davanti, curva 2
        if o.gara and g == 6 and 0 < _wrap(dist - CURVE[4][0]) < 90:
            s[0] = s[1] = 0.3             # pattinamento in uscita, curva 5
        x.wheel_slip_ratio[:] = s
        x.wheel_speed[:] = [v] * 4
        o.h(x, P.MOTIONEX)

    def status(self):
        o = self
        x = o.S[P.STATUS]()
        g, fr = o.giro_g(), o.frazione()
        for i in range(o.n):
            c = x.cars[i]
            c.fuel_in_tank, c.fuel_capacity = 60 - 6 * (max(o.d[i], 0) / PISTA), 110
            c.fuel_remaining_laps = 0.3
            c.actual_tyre_compound = c.visual_tyre_compound = o.mescola[i]
            c.tyres_age_laps = max(0, int((o.d[i] - o.cambio[i]) // PISTA))
            c.vehicle_fia_flags = 1
            c.ers_store_energy = 3.0e6
            c.ers_deploy_mode = 1
            c.max_rpm, c.idle_rpm, c.max_gears = 13000, 4000, 8
            c.pit_limiter_status = 1 if o.pit[i] else 0
        p = x.cars[0]
        if o.gara:
            p.fuel_remaining_laps = {3: -0.4, 4: -0.1, 5: 0.6, 6: 1.2, 7: 1.3, 8: 1.3}.get(g, 0.3)
            if g == 2 and 0.45 < fr < 0.52:
                p.vehicle_fia_flags = 3
            if g == 7 and 0.95 < fr:
                p.ers_store_energy = 0.3e6
        p.pit_limiter_status = 1 if (o.pit[0] and o.t_rec - o.pit_t[0] >= 1.5) else 0
        o.h(x, P.STATUS)

    def telemetry2(self):
        if self.fmt != 2026:
            return
        o = self
        x = o.S[P.TELEMETRY2]()
        g, fr = o.giro_g(), o.frazione()
        for i in range(o.n):
            c = x.cars[i]
            c.regulations_2026 = 1
            dist = o.d[i] % PISTA if o.d[i] >= 0 else 0
            z = in_zona_ali(dist) if o.t_rec > 11 and not o.pit[i] and o.sc == 0 else 0
            c.active_aero_available = 1 if z else 0
            c.active_aero_mode = 1 if z else 0
            if i == 0 and o.gara and z == 2 and g == 5:
                c.active_aero_mode = 0            # il giocatore si dimentica le ali
            davanti = o.davanti_a(i)
            if davanti is not None and (o.d[davanti] - o.d[i]) / V_MEDIA < 1.0 and o.t_rec > 60:
                c.overtake_available = 1
        if o.gara and g == 2 and 0.8 < fr < 0.83:
            x.cars[0].driving_wrong_way = 1
        o.h(x, P.TELEMETRY2)

    def damage(self):
        o = self
        x = o.S[P.DAMAGE]()
        g, fr = o.giro_g(), o.frazione()
        for i in range(o.n):
            giri = max(0.0, (o.d[i] - o.cambio[i]) / PISTA)
            base = 82 * giri / 5.0
            x.cars[i].tyres_wear[:] = [base * 0.9, base * 0.92, base * 1.0, base * 0.95]
        p = x.cars[0]
        if o.gara and (g > 4 or (g == 4 and fr > 0.5)):
            p.front_left_wing_damage = 25
            p.floor_damage = 8
        if o.gara and (g >= 6 and fr > 0.2 or g >= 7):
            p.ers_fault = 1
        o.h(x, P.DAMAGE)

    def setups(self):
        o = self
        x = o.S[P.SETUPS]()
        for i in range(o.n):
            s = x.cars[i]
            s.front_wing, s.rear_wing, s.on_throttle, s.off_throttle = 25, 22, 60, 55
            s.front_camber, s.rear_camber, s.front_toe, s.rear_toe = -3.0, -1.5, 0.05, 0.2
            s.front_suspension, s.rear_suspension = 30, 10
            s.front_anti_roll_bar, s.rear_anti_roll_bar = 10, 8
            s.front_suspension_height, s.rear_suspension_height = 25, 50
            s.brake_pressure, s.brake_bias, s.engine_braking = 100, 56, 50
            s.front_left_tyre_pressure = s.front_right_tyre_pressure = 22.5
            s.rear_left_tyre_pressure = s.rear_right_tyre_pressure = 20.5
            s.fuel_load = 40.0
        o.h(x, P.SETUPS)

    def participants(self):
        o = self
        x = o.S[P.PARTICIPANTS]()
        x.num_active_cars = o.n
        for i in range(o.n):
            c = x.cars[i]
            c.ai_controlled = 0 if i == 0 else 1
            c.name = NOMI[i].encode()
            c.race_number, c.team_id, c.your_telemetry = i + 2, i // 2, 1
        o.h(x, P.PARTICIPANTS)

    def history(self):
        o = self
        x = o.S[P.HISTORY]()
        x.car_idx = 0
        p = o.passaggi[0]
        tempi = [int((p[k + 1] - p[k]) * 1000) for k in range(len(p) - 1)]
        x.num_laps = min(len(tempi) + (0 if o.finito[0] else 1), 100)
        validi = []
        for k, t in enumerate(tempi[:100]):
            g = x.laps[k]
            g.lap_time_in_ms = t
            s1, s2 = int(t * 0.33), int(t * 0.335)
            s3 = t - s1 - s2
            g.sector1_time_ms_part, g.sector2_time_ms_part, g.sector3_time_ms_part = s1 % 60000, s2 % 60000, s3 % 60000
            g.sector1_time_minutes_part, g.sector2_time_minutes_part, g.sector3_time_minutes_part = s1 // 60000, s2 // 60000, s3 // 60000
            ok = not (o.gara and k + 1 == 2)
            g.lap_valid_bit_flags = 0x0F if ok else 0x0E
            if ok:
                validi.append((t, k + 1))
        if validi:
            best = min(validi)[1]
            x.best_lap_time_lap_num = x.best_sector1_lap_num = x.best_sector2_lap_num = x.best_sector3_lap_num = best
        x.num_tyre_stints = 2 if o.soste[0] else 1
        x.stints[0].end_lap, x.stints[0].tyre_actual_compound, x.stints[0].tyre_visual_compound = (5 if o.soste[0] else 255), 17, 17
        if o.soste[0]:
            x.stints[1].end_lap, x.stints[1].tyre_actual_compound, x.stints[1].tyre_visual_compound = 255, 18, 18
        o.h(x, P.HISTORY)

    def finale(self):
        o = self
        x = o.S[P.FINAL]()
        x.num_cars = o.n
        for i in range(o.n):
            c = x.cars[i]
            c.position, c.num_laps, c.grid_position = o.pos[i], o.giri, o.griglia[i]
            c.points = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1][o.pos[i] - 1] if o.pos[i] <= 10 else 0
            c.result_status = 3
            p = o.passaggi[i]
            tempi = [p[k + 1] - p[k] for k in range(len(p) - 1)]
            c.best_lap_time_in_ms = int(min(tempi) * 1000) if tempi else 0
            c.total_race_time = (o.finito[i] or o.t_rec) - 11.0
            c.num_pit_stops = o.soste[i]
            c.num_tyre_stints = 1 + o.soste[i]
            c.tyre_stints_visual[0] = c.tyre_stints_actual[0] = 17
            c.tyre_stints_end_laps[0] = 5 if o.soste[i] else o.giri
            if o.soste[i]:
                c.tyre_stints_visual[1] = c.tyre_stints_actual[1] = 18
                c.tyre_stints_end_laps[1] = o.giri
            if i == 0:
                c.penalties_time, c.num_penalties = 5, 1
        o.h(x, P.FINAL)

    # ---------- ciclo ----------
    def gira(self):
        o = self
        k = 0
        fine = None
        ftlp = False
        while True:
            o.passo()
            o.motion()
            o.motionex()
            o.lap()
            o.telemetry()
            o.status()
            o.telemetry2()
            if k % 2 == 0:
                o.damage()
            if k % 10 == 0:
                o.session()
            if k % 20 == 0:
                o.history()
            if k % 40 == 0:
                o.setups()
            if k % 100 == 0:
                o.participants()
            if o.gara and not ftlp and o.giro_g() == 8 and o.frazione() > 0.01:
                ftlp = True
                o.evento("FTLP", fastest_lap={"vehicle_idx": 0, "lap_time": o.tempo_ultimo(0) / 1000})
            if o.finito[0] is not None and fine is None:
                fine = o.t_rec + 3
            if fine is not None and o.t_rec >= fine:
                if o.gara:
                    for i in range(o.n):
                        if o.finito[i] is None:
                            o.finito[i] = o.t_rec
                    o.finale()
                o.evento("SEND")
                break
            k += 1
            o.frame += 1
            o.t_rec += DT
            o.t_gioco += DT
            if o.t_rec > 60 + o.giri * T_BASE * 1.6:
                raise RuntimeError("la sessione non finisce: controlla il modello")
        o.out.close()
        return o.t_rec


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--uscita", required=True)
    a.add_argument("--formato", type=int, choices=(2026, 2025), default=2026)
    a.add_argument("--giri", type=int, default=8)
    a.add_argument("--sessione", choices=("gara", "prove"), default="gara")
    a.add_argument("--pilota-lento", action="store_true")
    a.add_argument("--pulita", action="store_true",
                   help="gara senza safety car, incidenti e soste degli altri, gomme che calano di più: per l'undercut")
    a.add_argument("--seme", type=int, default=1)
    o = a.parse_args(argv)
    if o.sessione == "gara" and o.giri < 8:
        a.error("servono almeno 8 giri per il copione della gara")
    durata = Sim(o).gira()
    print(f"scritta {o.uscita}: {durata:.0f} s di {o.sessione} finta, formato {o.formato}, "
          f"giro base {T_BASE:.1f} s")


if __name__ == "__main__":
    main()
