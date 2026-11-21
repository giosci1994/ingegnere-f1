"""Analisi pre-gara e stacco partenza.

- `StaccoPartenza`: rileva lo spegnimento dei semafori (`LGOT`) e i primi secondi di gara
  (tempo di reazione da `SESSION.start_reaction_time`, uso frizione `clutch`, gas, giri motore,
  pattinamento `wheel_slip_ratio`, 0–100 km/h, posizioni) e produce il consiglio per il via.
- `dati_pregara`: aggrega per una pista il piano di gara A/B/C (live o da storico), i consigli
  d'assetto da `assetto.py`, la mappa frenate per curva dal miglior giro salvato e lo storico
  degli stacchi partenza.
"""

import json
import os
import statistics

from . import assetto as A
from . import curve as C
from . import numeri_curve as N
from . import pacchetti as P
from .riassunto import fmt
from .strategia import PERDITA_STIMA, calcola_piani


class StaccoPartenza:
    """Cattura e analisi dello stacco alla partenza della gara."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.semaforo = False
        self.via_t = None
        self.attivo = False
        self.chiuso = False
        self.reaction_time = None
        self.griglia = None
        self.pre_frizione = None
        self.pre_gas = None
        self.pre_rpm = None
        self._campioni = []
        self.risultato = None

    def evento(self, st, pk):
        if not st.in_gara():
            return
        code = P.codice_evento(pk)
        if code == "STLG":
            self.semaforo = True
            lap = st.auto(P.LAP, st.indice())
            if lap is not None and (lap.grid_position or lap.car_position):
                self.griglia = lap.grid_position or lap.car_position
        elif code == "LGOT":
            self.via_t = pk.header.session_time
            self.attivo = True
            self.chiuso = False
            self._campioni = []
            self.risultato = None
            lap = st.auto(P.LAP, st.indice())
            if lap is not None and (lap.grid_position or lap.car_position):
                self.griglia = lap.grid_position or lap.car_position

    def campione(self, st, idx):
        if not st.in_gara() or idx is None:
            return
        lap = st.auto(P.LAP, idx)
        tel = st.auto(P.TELEMETRY, idx)
        ses = st.sessione()
        if lap is None or tel is None or ses is None or lap.driver_status == 0:
            return
        t = st.tempo()

        # Se ci siamo persi LGOT ma siamo fermi in griglia al giro 1, cattura lo stato pre-via
        if not self.attivo and not self.chiuso and lap.current_lap_num == 1:
            if tel.speed <= 5 and lap.lap_distance <= 15:
                self.pre_frizione = tel.clutch
                self.pre_gas = round(tel.throttle, 2)
                self.pre_rpm = tel.engine_rpm
                if lap.grid_position or lap.car_position:
                    self.griglia = lap.grid_position or lap.car_position
                return
            if self.pre_frizione is not None and tel.speed >= 8 and lap.lap_distance < 80:
                self.via_t = t
                self.attivo = True

        if not self.attivo or self.chiuso or self.via_t is None:
            return

        dt = t - self.via_t
        if dt < -0.5:
            # flashback prima del via
            self.via_t = None
            self.attivo = False
            self._campioni = []
            return

        rt = getattr(ses, "start_reaction_time", 0.0)
        if 0.0 < rt < 10.0:
            self.reaction_time = round(float(rt), 3)

        mex = st.get(P.MOTIONEX)
        slip_post = round(max(mex.wheel_slip_ratio[0], mex.wheel_slip_ratio[1]), 3) if mex is not None else 0.0
        self._campioni.append({
            "dt": round(dt, 3),
            "v": int(tel.speed),
            "cl": int(tel.clutch),
            "th": round(float(tel.throttle), 2),
            "rpm": int(tel.engine_rpm),
            "g": int(tel.gear),
            "slip": slip_post,
            "pos": int(lap.car_position),
            "d": float(lap.lap_distance),
        })
        if lap.grid_position and not self.griglia:
            self.griglia = int(lap.grid_position)

        if dt >= 6.0 or lap.lap_distance >= 250 or lap.current_lap_num > 1:
            self.risultato = self._elabora()
            self.chiuso = True
            self.attivo = False

    def chiudi(self):
        if self.risultato is None and len(self._campioni) >= 10:
            self.risultato = self._elabora()
        return self.risultato

    def _elabora(self):
        camp = self._campioni
        if not camp:
            return None
        friz_max = max(max(c["cl"] for c in camp), self.pre_frizione or 0)
        friz_usata = friz_max >= 50

        # Primo istante di stacco (frizione rilasciata o movimento)
        i_mov = next((i for i, c in enumerate(camp) if (friz_usata and c["cl"] < 85) or c["v"] >= 3), 0)
        t_stacco = camp[i_mov]["dt"]

        rt = self.reaction_time
        if rt is None and self.semaforo and t_stacco > 0:
            rt = round(t_stacco, 3)

        # Tempo di rilascio frizione (da < 90 a <= 10)
        rilascio_s = None
        if friz_usata:
            t_in = next((c["dt"] for c in camp if c["cl"] < 90), None)
            t_out = next((c["dt"] for c in camp if c["cl"] <= 10 and (t_in is None or c["dt"] >= t_in)), None)
            if t_in is not None and t_out is not None:
                rilascio_s = round(max(0.0, t_out - t_in), 2)

        fin_lancio = [c for c in camp[i_mov:] if c["dt"] <= t_stacco + 0.8] or camp[i_mov:i_mov + 10]
        gas_lancio = round(max((c["th"] for c in fin_lancio), default=camp[0]["th"]) * 100)
        rpm_lancio = camp[i_mov]["rpm"]

        dopo_lancio = [c for c in camp[i_mov:] if t_stacco + 0.4 <= c["dt"] <= t_stacco + 2.2 and c["g"] == 1]
        rpm_min_dopo = min((c["rpm"] for c in dopo_lancio), default=None)

        slip_max = round(max(c["slip"] for c in camp), 2)
        camp_patt = sum(1 for c in camp if c["slip"] > 0.25 and c["v"] < 140)
        t_100 = next((c["dt"] for c in camp if c["v"] >= 100), None)
        pos_dopo = camp[-1]["pos"]
        pos_guad = (self.griglia - pos_dopo) if (self.griglia and pos_dopo) else None

        consiglio = _consiglio_singolo(rt, friz_usata, rilascio_s, gas_lancio, slip_max, camp_patt, rpm_min_dopo)
        return {
            "tempo_reazione_s": rt,
            "frizione_usata": friz_usata,
            "rilascio_frizione_s": rilascio_s,
            "gas_partenza_percento": gas_lancio,
            "rpm_lancio": rpm_lancio,
            "rpm_min_dopo": rpm_min_dopo,
            "pattinamento_max": slip_max,
            "campioni_pattinamento": camp_patt,
            "tempo_0_100_s": round(t_100, 2) if t_100 is not None else None,
            "griglia": self.griglia,
            "posizione_dopo_stacco": pos_dopo,
            "posizioni_guadagnate": pos_guad,
            "consiglio": consiglio,
        }


def _consiglio_singolo(rt, friz_usata, rilascio_s, gas_pct, slip_max, camp_patt, rpm_min_dopo):
    note = []
    if rt is not None:
        if rt > 0.45:
            note.append(f"Tempo di reazione lento ({rt:.2f} s): anticipa il rilascio allo spegnimento.")
        elif rt <= 0.25:
            note.append(f"Ottimo riflesso ({rt:.2f} s).")
    if slip_max > 0.6 or camp_patt >= 4:
        note.append(f"Forte pattinamento ({slip_max:.2f}) con gas al {gas_pct}%: modula il gas al 65–75% fino alla 2ª marcia.")
    elif rpm_min_dopo is not None and rpm_min_dopo < 5500:
        note.append(f"Calo di giri dopo lo stacco ({rpm_min_dopo} rpm): tieni giri più alti allo stacco.")
    if not friz_usata:
        note.append("Frizione non usata: tieni la frizione premuta in griglia per uno stacco più rapido.")
    elif rilascio_s is not None and rilascio_s <= 0.05 and slip_max > 0.4:
        note.append("Rilascio frizione a scatto: prova un rilascio più progressivo.")
    return " ".join(note) if note else "Stacco pulito e buona trazione."


def consiglio_partenza(storico):
    """Consiglio sintetico per la partenza successiva, basato sullo storico degli stacchi."""
    if not storico:
        return "Nessuno stacco partenza registrato su questa pista: i dati arriveranno dopo la prossima gara."
    rts = [s["tempo_reazione_s"] for s in storico if s.get("tempo_reazione_s") is not None]
    slips = [s["pattinamento_max"] for s in storico if s.get("pattinamento_max") is not None]
    gases = [s["gas_partenza_percento"] for s in storico if s.get("gas_partenza_percento") is not None]
    friz = [s.get("frizione_usata") for s in storico if s.get("frizione_usata") is not None]
    parti = []
    if rts:
        med_rt = statistics.median(rts)
        if med_rt > 0.45:
            parti.append(f"Reazione media {med_rt:.2f} s: prova ad anticipare leggermente lo stacco.")
        else:
            parti.append(f"Reazione media buona ({med_rt:.2f} s).")
    if slips and statistics.median(slips) > 0.5:
        med_g = round(statistics.median(gases)) if gases else 100
        parti.append(f"Pattinamento frequente in partenza (mediana {statistics.median(slips):.2f}, gas {med_g}%): "
                     "dosa il gas al 65–75% nei primi metri.")
    elif friz and not any(friz):
        parti.append("Usa la frizione in griglia prima dello spegnimento dei semafori.")
    else:
        parti.append("Trazione in partenza sotto controllo: mantieni questa modulazione.")
    return " ".join(parti)


def riassunti_pista(cartella_riassunti, track_id):
    """Legge i riassunti salvati (dal più recente) che appartengono a `track_id`."""
    if not cartella_riassunti or not os.path.isdir(cartella_riassunti):
        return []
    nome_pista = P.PISTE.get(int(track_id))
    out = []
    files = sorted(
        (n for n in os.listdir(cartella_riassunti) if n.endswith(".json")),
        key=lambda n: os.path.getmtime(os.path.join(cartella_riassunti, n)),
        reverse=True,
    )
    for n in files:
        try:
            with open(os.path.join(cartella_riassunti, n), encoding="utf-8") as f:
                r = json.load(f)
        except (OSError, ValueError):
            continue
        if r.get("pista_id") == int(track_id) or (nome_pista and r.get("pista") == nome_pista):
            out.append(r)
    return out


def mappa_frenate(bib, pista, pilota=None):
    """Mappa frenate per curva dal miglior giro salvato del giocatore su questa pista."""
    pista = int(pista)
    m = bib.migliore(pista, pilota) if pilota else None
    if m is None:
        m = bib.migliore(pista)
    if m is None:
        giri = bib.giri(pista)
        validi = [x for x in giri if x.get("tempo_ms")]
        m = min(validi, key=lambda x: x["tempo_ms"]) if validi else None
    if m is None:
        return None
    g = bib.leggi(pista, m["id"])
    if not g or not g.get("c"):
        return None
    c = g["c"]
    curve = C.trova_curve(c)
    lung = max((d for d in c["d"] if d is not None), default=0)
    numerazione = N.assegna(curve, pista, lung, c)
    righe = []
    for cu in curve:
        meas = C.misura(c, cu)
        righe.append({
            "n": cu["n"],
            "curva": cu["nome"],
            "apice_m": round(cu["apice"]),
            "frenata_m": round(meas["frenata"]) if meas.get("frenata") is not None else None,
            "vingresso": meas.get("vingresso"),
            "vmin": meas.get("vmin"),
            "marcia_min": meas.get("marcia_min"),
            "gas_m": round(meas["gas"]) if meas.get("gas") is not None else None,
        })
    return {
        "giro": {
            "id": m["id"],
            "tempo": fmt(m.get("tempo_ms")),
            "tempo_ms": m.get("tempo_ms"),
            "pilota": m.get("pilota"),
            "sessione": m.get("sessione"),
        },
        "numerazione": numerazione,
        "curve": righe,
    }


def _usura_storica_gara(riassunti_gara):
    vals = []
    for r in riassunti_gara:
        u = ((r.get("assetto") or {}).get("dati") or {}).get("usura_per_giro")
        if u and u.get("anteriori") is not None and u.get("posteriori") is not None:
            vals.append(max(u["anteriori"], u["posteriori"]))
    return round(statistics.median(vals), 2) if vals else None


def _piani_da_storico(pista, piste_obj, riassunti):
    perdita_box, misurata = piste_obj.perdita_box(pista)
    gare = [r for r in riassunti if "gara" in (r.get("sessione") or "").lower()]
    totali = None
    mescola_attuale = None
    if gare:
        g0 = gare[0]
        totali = (g0.get("finale") or {}).get("giri") or len(g0.get("giri") or ()) or None
        for r in gare:
            stint = (r.get("finale") or {}).get("stint") or []
            if stint:
                gm = stint[0].get("gomma")
                if gm and gm not in ("intermedie", "da bagnato", "gomme da bagnato"):
                    mescola_attuale = gm
                    break
    degr_list = [
        (r.get("strategia") or {}).get("degrado_s_per_giro")
        for r in gare
        if (r.get("strategia") or {}).get("degrado_s_per_giro") is not None
    ]
    degrado_s = round(statistics.median(degr_list), 3) if degr_list else None
    usura_giro = _usura_storica_gara(gare or riassunti)
    piani = calcola_piani(
        totali=totali,
        mescola_attuale=mescola_attuale,
        degrado_s=degrado_s,
        usura_per_giro=usura_giro,
        perdita_box=perdita_box,
        fonte="storico" if gare else "stima",
    )
    piani["misurata"] = misurata
    return piani


def piste_disponibili(bib, piste_obj, cartella_riassunti, sessione_live=None):
    """Elenco delle piste che hanno giri, riassunti, tempi box o la sessione in corso."""
    mappa = {}
    for p in bib.piste():
        mappa[int(p["pista"])] = {"pista": int(p["pista"]), "nome": p["nome"], "giri": p["giri"]}
    for pid_str, d in (piste_obj.dati or {}).items():
        if pid_str.lstrip("-").isdigit():
            pid = int(pid_str)
            mappa.setdefault(pid, {"pista": pid, "nome": d.get("nome") or P.PISTE.get(pid, f"pista {pid}"), "giri": 0})
    nomi_inv = {v: k for k, v in P.PISTE.items()}
    if cartella_riassunti and os.path.isdir(cartella_riassunti):
        for fn in os.listdir(cartella_riassunti):
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(cartella_riassunti, fn), encoding="utf-8") as f:
                    r = json.load(f)
            except (OSError, ValueError):
                continue
            pid = r.get("pista_id")
            if pid is None and r.get("pista") in nomi_inv:
                pid = nomi_inv[r["pista"]]
            if pid is not None:
                mappa.setdefault(int(pid), {"pista": int(pid), "nome": P.PISTE.get(int(pid), r.get("pista", str(pid))), "giri": 0})
    if sessione_live and sessione_live.get("pista_id") is not None:
        pid = int(sessione_live["pista_id"])
        mappa.setdefault(pid, {"pista": pid, "nome": P.PISTE.get(pid, f"pista {pid}"), "giri": 0})
    return sorted(mappa.values(), key=lambda x: x["nome"])


def dati_pregara(pista, bib, piste_obj, cartella_riassunti, pilota=None, sessione_live=None):
    """Payload completo per la scheda Pre-gara e `/api/pregara/<pista>`."""
    pista = int(pista)
    riass = riassunti_pista(cartella_riassunti, pista)

    # 1. Piano di gara (live se siamo in sessione su questa pista, altrimenti da storico)
    if sessione_live and sessione_live.get("pista_id") == pista and sessione_live.get("piani"):
        piani = dict(sessione_live["piani"])
    else:
        piani = _piani_da_storico(pista, piste_obj, riass)

    # 2. Setup consigliato (via assetto.py)
    giri_puliti = []
    if not any((r.get("assetto") or {}).get("dati") for r in riass):
        for m in bib.giri(pista):
            if m.get("valido") and not m.get("box") and not m.get("safety_car"):
                g = bib.leggi(pista, m["id"])
                if g and g.get("c"):
                    giri_puliti.append(g["c"])
                if len(giri_puliti) >= 10:
                    break
    setup = A.pregara(riass, giri_bib=giri_puliti)

    # 3. Mappa frenate per curva
    frenate = mappa_frenate(bib, pista, pilota=pilota)

    # 4. Storico stacchi partenza e consiglio
    stacchi = []
    for r in riass:
        sp = r.get("stacco_partenza")
        if sp:
            stacchi.append({
                "id": r.get("id"),
                "creato": r.get("creato"),
                "sessione": r.get("sessione"),
                "pilota": r.get("pilota"),
                **sp,
            })
    partenza = {
        "consiglio": consiglio_partenza(stacchi),
        "storico": stacchi[:10],
    }

    return {
        "pista": pista,
        "nome": P.PISTE.get(pista, f"pista {pista}"),
        "piani": piani,
        "setup": setup,
        "frenate": frenate,
        "partenza": partenza,
    }
