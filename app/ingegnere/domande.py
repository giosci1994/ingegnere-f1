"""Le domande all'ingegnere con i tasti della PS5 (evento BUTN, UDP Action 1–12).

Nei controlli di F1 25 un tasto del volante o del controller si può assegnare a «UDP Action 1…12»:
quando lo premi il gioco manda l'evento BUTN con il bit acceso. Si reagisce solo al **fronte di
salita** (il tasto che passa da su a giù), non a ogni pacchetto mentre è tenuto premuto.

Bit dei tasti [extra · appendice «Button flags» della specifica EA]: lo `spec.h` ufficiale
(«(c) 2026 Electronic Arts», nel pacchetto sorgente di `f1-packets` 2026.1.1) dice solo
«Bit flags specifying which buttons are being pressed currently - see appendices»; la pagina EA
con le appendici non si legge in automatico (403). La tabella qui sotto è quella dell'appendice
ricopiata nel README di `MacManley/f1-25-udp` (GitHub), e coincide con i tasti veri registrati
il 20/11/2026: R2 (0x1000) e L2 (0x0800) sono i più frequenti (gas e freno), poi le frecce.
UDP Action 1 = 0x00100000 … UDP Action 12 = 0x80000000.
"""

import time

from . import pacchetti as P
from .impostazioni import DOMANDE, TASTI_PREDEFINITI  # noqa: F401
from .ingegnere import Messaggio, dec, pct, pos, tempo_giro

TASTI = {
    0x00000001: "Croce", 0x00000002: "Triangolo", 0x00000004: "Cerchio", 0x00000008: "Quadrato",
    0x00000010: "Freccia sinistra", 0x00000020: "Freccia destra", 0x00000040: "Freccia su",
    0x00000080: "Freccia giù", 0x00000100: "Options", 0x00000200: "L1", 0x00000400: "R1",
    0x00000800: "L2", 0x00001000: "R2", 0x00002000: "Levetta sinistra premuta",
    0x00004000: "Levetta destra premuta", 0x00008000: "Levetta destra a sinistra",
    0x00010000: "Levetta destra a destra", 0x00020000: "Levetta destra su",
    0x00040000: "Levetta destra giù", 0x00080000: "Speciale",
}
for _n in range(1, 13):
    TASTI[0x00100000 << (_n - 1)] = f"UDP Action {_n}"


def azione(bit):
    """0x00100000 → 1 … 0x80000000 → 12; None per gli altri tasti."""
    for n in range(1, 13):
        if bit == 0x00100000 << (n - 1):
            return n
    return None


class Tasti:
    """Il fronte di salita dei tasti, l'ultima UDP Action e l'ultimo tasto qualsiasi (per la pagina)."""

    def __init__(self):
        self.prima = 0
        self.ultima_azione = None    # {"nome", "ora", "azione", "domanda"}
        self.ultimo_tasto = None     # {"nome", "ora"}: anche gas e freno, per vedere che arrivano

    def premuti(self, stato_tasti, imp=None):
        """Restituisce le UDP Action appena premute (numeri 1–12), in ordine."""
        nuovi = stato_tasti & ~self.prima
        self.prima = stato_tasti
        azioni = []
        ora = time.strftime("%H:%M:%S")
        for bit in sorted(TASTI):
            if not nuovi & bit:
                continue
            self.ultimo_tasto = {"nome": TASTI[bit], "ora": ora}
            n = azione(bit)
            if n:
                domanda = (imp["tasti"].get(str(n)) or None) if imp is not None else None
                self.ultima_azione = {"nome": TASTI[bit], "ora": ora, "azione": n, "domanda": domanda}
                azioni.append(n)
        return azioni


def rispondi(domanda, st, ing, an, ultima_frase=None):
    """Il Messaggio con la risposta (priorità 2: passa davanti al resto), o None."""
    idx = st.indice()
    ses = st.sessione()
    lap = st.auto(P.LAP, idx)
    t = st.tempo()
    if domanda == "ripeti":
        testo = ultima_frase or "Niente da ripetere."
        return Messaggio("domande", "domanda_ripeti", testo, priorita=2, livello=1, ttl=10, creato=t)
    if idx is None or ses is None or lap is None:
        return None
    f = {"strategia": _strategia, "gomme": _gomme, "distacchi": _distacchi,
         "carburante": _carburante, "danni": _danni, "passo": _passo}.get(domanda)
    if f is None:
        return None
    testo = f(st, ing, an, idx, ses, lap)
    if not testo:
        return None
    return Messaggio("domande", f"domanda_{domanda}", testo, priorita=2, livello=1, ttl=10, creato=t)


def _strategia(st, ing, an, idx, ses, lap):
    if not st.in_gara():
        if ses.session_time_left:
            m = ses.session_time_left // 60
            return f"Niente strategia di gara in questa sessione. Mancano {m} minuti." if m else \
                "Niente strategia di gara in questa sessione. Ultimo minuto."
        return "Niente strategia di gara in questa sessione."
    n = lap.current_lap_num
    parti = []
    ideale, ultimo = ses.pit_stop_window_ideal_lap, ses.pit_stop_window_latest_lap
    if lap.num_pit_stops and ideale and n > max(ideale, ultimo):
        parti.append("Sosta fatta.")
    elif ideale:
        if n < ideale:
            parti.append(f"Finestra box dal giro {ideale}" + (f" al {ultimo}." if ultimo and ultimo > ideale else "."))
        elif ultimo and n <= ultimo:
            parti.append(f"Sei in finestra box, ultimo giro utile il {ultimo}.")
        else:
            parti.append("Finestra box chiusa.")
    u = an.stima_undercut(st, idx)
    if u is not None:
        nome, guadagno, distacco = u
        if guadagno > distacco + 0.3:
            parti.append(f"Undercut su {nome} possibile: stimiamo {dec(guadagno)} secondi, sei a {dec(distacco)}.")
        else:
            parti.append(f"Undercut su {nome} non basta: sei a {dec(distacco)}, stimiamo {dec(max(guadagno, 0))}.")
    r = an.strategia.rientro(st, idx)
    if r is not None:
        parti.append(an.frase_rientro(st, r))
    return " ".join(parti) or "Per la strategia mi servono ancora un paio di giri."


def _gomme(st, ing, an, idx, ses, lap):
    sta = st.auto(P.STATUS, idx)
    dmg = st.auto(P.DAMAGE, idx)
    tel = st.auto(P.TELEMETRY, idx)
    parti = []
    if sta is not None:
        g = P.GOMME_VISIVE.get(sta.visual_tyre_compound, "gomme")
        parti.append(f"{g.capitalize()}, {sta.tyres_age_laps} {'giro' if sta.tyres_age_laps == 1 else 'giri'}.")
    if dmg is not None:
        w = list(dmg.tyres_wear)
        usura = max(w)
        parti.append(f"Usura {pct(usura)}, la più consumata è la {P.RUOTE[w.index(usura)]}.")
    if tel is not None:
        ti = list(tel.tyres_inner_temperature)
        if max(ti) > 0:
            parti.append(f"Temperature: davanti {round((ti[2] + ti[3]) / 2)}, dietro {round((ti[0] + ti[1]) / 2)} gradi.")
    return " ".join(parti)


def _distacchi(st, ing, an, idx, ses, lap):
    if st.in_gara():
        davanti = st.distacco_davanti(idx)
        dietro, j = st.distacco_dietro(idx)
        parti = [f"Sei {pos(lap.car_position)}."]
        if davanti is not None:
            parti.append(f"Davanti {st.nome(st.auto_in_posizione(lap.car_position - 1))} a {dec(davanti)}.")
        if dietro is not None:
            parti.append(f"Dietro {st.nome(j)} a {dec(dietro)}.")
        return " ".join(parti)
    # prove e qualifiche: il distacco dal giro migliore della sessione
    migliori = {}
    for i, h in st.storia.items():
        if 1 <= h.best_lap_time_lap_num <= len(h.laps):
            v = h.laps[h.best_lap_time_lap_num - 1].lap_time_in_ms
            if v:
                migliori[i] = v
    mio = migliori.get(idx)
    if not mio:
        return f"Sei {pos(lap.car_position)}. Ancora nessun tuo giro cronometrato."
    primo = min(migliori.values())
    if mio <= primo:
        return f"Sei {pos(lap.car_position)}, hai il giro più veloce."
    return f"Sei {pos(lap.car_position)}, a {dec((mio - primo) / 1000)} dal migliore."


def _carburante(st, ing, an, idx, ses, lap):
    sta = st.auto(P.STATUS, idx)
    if sta is None:
        return None
    fl = sta.fuel_remaining_laps
    if fl < -0.2:
        return f"Carburante: meno {dec(-fl)} giri. Lift and coast."
    if fl < 0.2:
        return "Carburante giusto per finire. Non sprecare."
    return f"Carburante: più {dec(fl)} giri."


def _danni(st, ing, an, idx, ses, lap):
    dmg = st.auto(P.DAMAGE, idx)
    if dmg is None:
        return None
    parti = {
        "ala anteriore sinistra": dmg.front_left_wing_damage, "ala anteriore destra": dmg.front_right_wing_damage,
        "ala posteriore": dmg.rear_wing_damage, "fondo": dmg.floor_damage, "diffusore": dmg.diffuser_damage,
        "pance": dmg.sidepod_damage, "cambio": dmg.gear_box_damage, "motore": dmg.engine_damage,
    }
    rotti = sorted(((v, k) for k, v in parti.items() if v >= 5), reverse=True)[:3]
    extra = []
    if dmg.drs_fault:
        extra.append("guasto al DRS")
    if dmg.ers_fault:
        extra.append("guasto all'ERS")
    if not rotti and not extra:
        return "Nessun danno. Macchina a posto."
    testo = ", ".join(f"{k} {pct(v)}" for v, k in rotti)
    testo = (testo[0].upper() + testo[1:]) if testo else ""
    if extra:
        testo = (testo + ", " if testo else "") + ", ".join(extra)
        testo = testo[0].upper() + testo[1:]
    return testo + "."


def _passo(st, ing, an, idx, ses, lap):
    ultimo = lap.last_lap_time_in_ms
    if not ultimo:
        return "Ancora nessun giro completo."
    testo = f"Ultimo giro {tempo_giro(ultimo)}."
    best = ing.best_ms
    if best and ultimo > best:
        testo += f" Il migliore {tempo_giro(best)}: sei a {dec((ultimo - best) / 1000)}."
    elif best and ultimo == best:
        testo += " È il tuo migliore."
    if st.in_gara() and lap.car_position > 1:
        j = st.auto_in_posizione(lap.car_position - 1)
        h = st.storia.get(j)
        if h is not None and 1 <= h.num_laps <= len(h.laps):
            # num_laps conta anche il giro in corso: l'ultimo finito è quello prima
            k = h.num_laps - 2 if h.num_laps >= 2 and not h.laps[h.num_laps - 1].lap_time_in_ms else h.num_laps - 1
            v = h.laps[k].lap_time_in_ms if k >= 0 else 0
            if v:
                testo += f" {st.nome(j)} ha fatto {tempo_giro(v)}."
    return testo
