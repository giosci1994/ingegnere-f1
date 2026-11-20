"""Fase 5 (0.5.0): le chiamate nuove che guardano la gara intorno.

Le chiama `Analisi.valuta` ogni 0,2 s; usano l'orologio di `Analisi` che non torna indietro con
i flashback (`an.ora`, `an._puo`), così niente si ripete dopo un flashback.

- settori: in prova e qualifica, il tempo di ogni settore contro il tuo migliore della sessione
  (giri validi); si dice solo il migliore personale o 2 decimi e più di ritardo;
- passo: in gara, ogni 3 giri al massimo, il passo degli ultimi 3 giri puliti contro chi è
  davanti e dietro (entro 3 s), tra 0,15 e 2 s a giro (oltre è pioggia, danni o box, non passo):
  «lo prendi in N giri», «ti recupera N decimi a giro»;
- previsioni: in gara, ogni 5 giri, usura (quando arriva all'80 per cento o con quanto finisci) e
  carburante (con quanti chili arrivi e il massimo a giro); se non basta (oltre 0,3 kg di meno),
  quanti grammi a giro risparmiare, al massimo ogni 5 minuti;
- box sotto safety car o VSC: quanto costa fermarsi adesso, stimato (tempo al box per 0,65 con la
  safety car, 0,7 con la VSC: rapporti del tempo al box di F1 con SC/VSC pubblicati da MultiViewer);
- mescola per la sosta: dai set di gomme del gioco (pacchetto tyre sets), quale montare e quanti
  giri dura.
"""

import statistics

from . import curve as C
from . import pacchetti as P
from .ingegnere import Messaggio, dec, pct

RAPPORTO_SC = {1: 0.65, 2: 0.70}          # safety car, VSC
NOMI_MESCOLA = {16: "soft", 17: "medie", 18: "dure", 7: "intermedie", 8: "gomme da bagnato",
                15: "gomme da bagnato", 19: "super soft", 20: "soft", 21: "dure", 22: "soft",
                23: "medie", 24: "dure"}


def _pendenza(punti):
    """Pendenza (minimi quadrati) di [(x, y)], o None con meno di 3 punti."""
    if len(punti) < 3:
        return None
    mx = sum(x for x, _ in punti) / len(punti)
    my = sum(y for _, y in punti) / len(punti)
    den = sum((x - mx) ** 2 for x, _ in punti)
    if not den:
        return None
    return sum((x - mx) * (y - my) for x, y in punti) / den


def _stint(storia):
    """Gli ultimi punti (giro, valore) dopo l'ultima sosta: storia = [(giro, valore, box)]."""
    out = []
    for g, v, box in storia:
        if box:
            out = []
            continue
        out.append((g, v))
    return out[-6:]


# ---------- settori (prove e qualifiche) ----------
def settori(an, out, t, st, ses, lap):
    if st.in_gara() or lap.pit_status or lap.driver_status == 3:
        an.settore_prec = lap.sector
        return
    prima, ora_s = an.settore_prec, lap.sector
    an.settore_prec = ora_s
    if prima is None or ora_s == prima:
        return
    if prima == 0 and ora_s == 1:
        k, ms = 1, lap.sector1_time_minutes_part * 60000 + lap.sector1_time_ms_part
        valido = not lap.current_lap_invalid
    elif prima == 1 and ora_s == 2:
        k, ms = 2, lap.sector2_time_minutes_part * 60000 + lap.sector2_time_ms_part
        valido = not lap.current_lap_invalid
    else:
        return                      # il terzo settore lo chiude il tempo sul giro
    if not ms or not valido:
        return
    s = ms / 1000
    best = an.settori_migliori.get(k)
    if best is None or s < best:
        an.settori_migliori[k] = s
        if best is not None and an._puo(f"settore{k}", 20, t):
            out.append(Messaggio("settori", f"settore{k}",
                                 f"Settore {k}, migliore personale: {C.decimi(best - s)} meglio.",
                                 livello=2, ttl=8, creato=t))
        return
    if s - best >= 0.2 and an._puo(f"settore{k}", 20, t):
        out.append(Messaggio("settori", f"settore{k}", f"Settore {k}, {C.decimi(s - best)} più lento.",
                             livello=2, ttl=8, creato=t))


# ---------- passo contro chi è davanti e dietro (gara) ----------
def _passo_di(an, i, n=3):
    t = [ms / 1000 for g, ms, pit, sc in an.strategia.tempi.get(i, []) if not pit and not sc and g > 1][-n:]
    if len(t) < n:
        return None
    med = statistics.median(t)
    t = [x for x in t if x < med * 1.03]
    return sum(t) / len(t) if len(t) >= 2 else None


def _quanto(x):
    """0,2 → «2 decimi», 1,0 → «un secondo», 2,3 → «2 virgola 3 secondi»."""
    x = abs(x)
    return C.decimi(x) if x < 1.25 else f"{dec(x)} secondi"


def passo(an, out, t, st, ses, lap, idx, giro_finito):
    if not giro_finito or lap.current_lap_num < 5 or ses.safety_car_status in (1, 2) or lap.pit_status:
        return
    mio = _passo_di(an, idx)
    if mio is None:
        return
    davanti = st.distacco_davanti(idx)
    j_av = st.auto_in_posizione(lap.car_position - 1) if davanti is not None else None
    dietro, j_di = st.distacco_dietro(idx)
    frasi = []
    if j_av is not None and davanti < 3.0:
        suo = _passo_di(an, j_av)
        if suo is not None and 0.15 <= abs(suo - mio) <= 2.0 and an._puo(f"passo{j_av}", 180, t):
            d = suo - mio
            if d > 0:
                giri = max(1, round(davanti / d))
                frasi.append(f"Sei {_quanto(d)} a giro più veloce di {st.nome(j_av)}: lo prendi in "
                             f"{giri} {'giro' if giri == 1 else 'giri'}.")
            else:
                frasi.append(f"{st.nome(j_av)} è {_quanto(d)} a giro più veloce di te.")
    if j_di is not None and dietro is not None and dietro < 3.0:
        suo = _passo_di(an, j_di)
        if suo is not None and 0.15 <= abs(suo - mio) <= 2.0 and an._puo(f"passo{j_di}", 180, t):
            d = mio - suo
            frasi.append(f"{st.nome(j_di)} ti recupera {_quanto(d)} a giro." if d > 0
                         else f"Su {st.nome(j_di)} guadagni {_quanto(d)} a giro.")
    if frasi:
        out.append(Messaggio("passo", "passo", " ".join(frasi), livello=2, ttl=20, creato=t))


# ---------- previsioni di usura e carburante (gara) ----------
def previsioni(an, out, t, st, ses, lap, idx, giro_finito):
    n = lap.current_lap_num
    totali = ses.total_laps
    if not giro_finito or not totali or n < 4 or lap.pit_status or ses.safety_car_status in (1, 2):
        return
    mancano = totali - n + 1                     # giri ancora da fare, compreso questo
    if mancano <= 2:
        return
    sta = st.auto(P.STATUS, idx)
    dmg = st.auto(P.DAMAGE, idx)
    # usura: ogni 5 giri
    if dmg is not None and n % 5 == 0 and an._puo("prev_usura", 200, t):
        punti = _stint([(g, max(w), b) for g, w, b in an.usure])
        r = _pendenza(punti)
        ora_u = max(dmg.tyres_wear)
        if r is not None and r >= 0.3:
            giri_80 = (80 - ora_u) / r
            fine = ora_u + r * mancano
            if ora_u < 80 and giri_80 < mancano:
                g80 = max(1, int(giri_80))
                out.append(Messaggio("gomme", "prev_usura",
                                     f"A questo ritmo le gomme arrivano all'80 per cento tra {g80} "
                                     f"{'giro' if g80 == 1 else 'giri'}, al giro {n + g80}.",
                                     livello=2, ttl=20, creato=t))
            elif ora_u < 80:
                out.append(Messaggio("gomme", "prev_usura",
                                     f"A questo ritmo finisci la gara con le gomme al {pct(fine)}.",
                                     livello=3, ttl=20, creato=t))
    # carburante: con quanto arrivi e il massimo a giro
    if sta is None:
        return
    punti = _stint([(g, f, False) for g, f in an.benzina])
    r = _pendenza(punti)
    if r is None or r >= -0.05:
        return
    consumo = -r                                  # kg a giro
    benzina = sta.fuel_in_tank
    arrivo = benzina - consumo * mancano
    obiettivo = benzina / mancano
    risparmio = round((consumo - obiettivo) * 100) * 10          # grammi a giro, a 10 g
    if arrivo < -0.3 and risparmio >= 20 and an._puo("prev_benzina_poca", 300, t):
        out.append(Messaggio("carburante", "prev_benzina",
                             f"Carburante: per arrivare in fondo risparmia {risparmio} grammi a giro. "
                             f"Lift and coast.", livello=1, ttl=20, creato=t))
    elif arrivo >= 0 and n % 5 == 0 and an._puo("prev_benzina", 200, t):
        quanto = f"con {dec(arrivo)} chili" if arrivo >= 0.5 else "giusto, senza margine"
        out.append(Messaggio("carburante", "prev_benzina",
                             f"Carburante: a questo ritmo arrivi {quanto}. "
                             f"Al massimo {dec(obiettivo)} chili a giro.",
                             livello=3, ttl=20, creato=t))


# ---------- box sotto safety car o VSC ----------
def box_sc(an, out, t, st, ses, lap, idx):
    s = ses.safety_car_status
    prima, an.sc_prec = an.sc_prec, s
    if s not in RAPPORTO_SC or s == prima or not st.in_gara():
        return
    n = lap.current_lap_num
    mancano = ses.total_laps - n + 1 if ses.total_laps else 99
    if lap.pit_status or n < 2 or mancano <= 3 or (an.mie_soste and n - an.mie_soste[-1] < 5):
        return
    dmg = st.auto(P.DAMAGE, idx)
    usura = max(dmg.tyres_wear) if dmg is not None else 0
    serve = lap.num_pit_stops == 0 or usura >= 40 or (
        ses.pit_stop_window_ideal_lap and n >= ses.pit_stop_window_ideal_lap - 5)
    if not serve or not an._puo("box_sc", 120, t):
        return
    perdita, misurata = an.strategia.piste.perdita_box(ses.track_id)
    sotto = perdita * RAPPORTO_SC[s]
    chi = "Safety car" if s == 1 else "Virtual safety car"
    out.append(Messaggio("strategia", "box_sc",
                         f"{chi}: fermarsi adesso costa circa {round(sotto)} secondi invece di "
                         f"{round(perdita)}, stima. Se vuoi, box questo giro.",
                         priorita=2, livello=1, ttl=15, creato=t))


# ---------- quale set montare al box ----------
def set_per_sosta(st, idx, mancano):
    """(nome della mescola, nuove, usura del set, giri che dura) o None, dai set del gioco."""
    ts = st.set_gomme.get(idx)
    ses = st.sessione()
    if ts is None or ses is None:
        return None
    bagnato = ses.weather >= 3
    adatte = {7, 8, 15} if bagnato else set(P.GOMME_SLICK)
    usate = set()
    storia = st.storia.get(idx)
    if storia is not None:
        usate = {storia.stints[k].tyre_visual_compound for k in range(min(storia.num_tyre_stints, 8))}
    cand = []
    for s in ts.sets:
        if not s.available or s.fitted or s.visual_tyre_compound not in adatte or not s.usable_life:
            continue
        dura = s.usable_life * (1 - s.wear / 100)
        cand.append((s, dura))
    if not cand:
        return None
    if not bagnato and len(usate & set(P.GOMME_SLICK)) < 2:      # in gara asciutta due mescole
        diverse = [c for c in cand if c[0].visual_tyre_compound not in usate]
        cand = diverse or cand
    bastano = [c for c in cand if c[1] >= mancano]
    if bastano:
        s, dura = min(bastano, key=lambda c: (c[0].lap_delta_time, c[0].wear))
    else:
        s, dura = max(cand, key=lambda c: (c[1], -c[0].lap_delta_time))
    return NOMI_MESCOLA.get(s.visual_tyre_compound, "gomme"), s.wear == 0, s.wear, int(dura)


def frase_set(scelta):
    nome, nuove, usura, dura = scelta
    stato = "nuove" if nuove else f"usate al {pct(usura)}"
    return f"Per la sosta: {nome} {stato}, durano circa {dura} giri."


def mescola(an, out, t, st, ses, lap, idx):
    """Una volta per stint, quando si avvicina il box: finestra aperta o usura al 65 per cento."""
    if not st.in_gara() or lap.pit_status:
        return
    n = lap.current_lap_num
    mancano = ses.total_laps - n + 1 if ses.total_laps else 99
    if mancano <= 3 or an.mescola_detta == len(an.mie_soste):
        return
    dmg = st.auto(P.DAMAGE, idx)
    usura = max(dmg.tyres_wear) if dmg is not None else 0
    ideale = ses.pit_stop_window_ideal_lap
    vicino = (ideale and lap.num_pit_stops == 0 and n >= ideale - 1) or usura >= 65
    if not vicino:
        return
    scelta = set_per_sosta(st, idx, mancano - 1)
    if scelta is None:
        return
    an.mescola_detta = len(an.mie_soste)
    out.append(Messaggio("strategia", "mescola", frase_set(scelta), priorita=3, livello=2, ttl=20, creato=t))


# ---------- usura gomme degli altri ----------
def usura_altro(st, j):
    """L'usura più alta delle gomme dell'auto j, se il gioco la manda (offline sì; online le auto
    con la telemetria privata no): None se non si sa."""
    par = st.get(P.PARTICIPANTS)
    if par is not None and j < len(par.cars) and not (par.cars[j].your_telemetry or par.cars[j].ai_controlled):
        return None
    dmg = st.auto(P.DAMAGE, j)
    if dmg is None:
        return None
    u = max(dmg.tyres_wear)
    return u if u > 0 else None
