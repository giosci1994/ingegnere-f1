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
from .ingegnere import Messaggio, dec, pct, tempo_giro
from .strategia import NOMI_MESCOLA, calcola_piani

RAPPORTO_SC = {1: 0.65, 2: 0.70}          # safety car, VSC


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
    if getattr(an, "_sc_soppresso", None) == n:
        return
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
    an._box_giro_stint = len(an.mie_soste)
    an._box_chiamato = {"giro": n, "motivo": "sc", "bersaglio": None, "ora": an.ora, "piano": an.piano_attivo}
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


# ---------- confronto settori contro avversari (gara) ----------
def aggiorna_settori_auto(an, st):
    """Registra S1, S2 e S3 dai pacchetti LAP per tutte le auto attive."""
    lap_all = st.get(P.LAP)
    if lap_all is None or not st.in_gara():
        return
    for i in range(min(st.n_auto or len(lap_all.cars), len(lap_all.cars))):
        c = lap_all.cars[i]
        if c.result_status not in (2, 3):
            continue
        g = c.current_lap_num
        prev_g = an.settori_giro_car.get(i)
        if prev_g is not None and g == prev_g + 1 and c.last_lap_time_in_ms:
            d_prev = an.settori_auto.get(i, {}).get(prev_g)
            if d_prev and 1 in d_prev and 2 in d_prev:
                s3 = c.last_lap_time_in_ms / 1000.0 - d_prev[1] - d_prev[2]
                if s3 > 5.0:
                    d_prev[3] = s3
        an.settori_giro_car[i] = g
        d_car = an.settori_auto.setdefault(i, {})
        d_lap = d_car.setdefault(g, {})
        if c.pit_status:
            d_lap["pit"] = True
        if c.sector >= 1 and (c.sector1_time_minutes_part or c.sector1_time_ms_part):
            d_lap[1] = (c.sector1_time_minutes_part * 60000 + c.sector1_time_ms_part) / 1000.0
        if c.sector == 2 and (c.sector2_time_minutes_part or c.sector2_time_ms_part):
            d_lap[2] = (c.sector2_time_minutes_part * 60000 + c.sector2_time_ms_part) / 1000.0
        for old_g in [x for x in d_car if x < g - 2]:
            del d_car[old_g]


def _ottieni_settore(an, st, i, g, k):
    d = an.settori_auto.get(i, {}).get(g)
    if d is not None:
        if d.get("pit"):
            return None
        if k in d:
            return d[k]
    h = st.storia.get(i)
    if h is not None and 1 <= g <= min(h.num_laps, len(h.laps)):
        gl = h.laps[g - 1]
        v = getattr(gl, f"sector{k}_time_minutes_part") * 60000 + getattr(gl, f"sector{k}_time_ms_part")
        if v > 0:
            return v / 1000.0
    return None


def _frase_settore(st, j, k, diff):
    if diff > 0:
        return f"{st.nome(j)} guadagna {_quanto(diff)} nel settore {k}."
    return f"Guadagni {_quanto(diff)} su {st.nome(j)} nel settore {k}."


def settori_avversari(an, out, t, st, ses, lap, idx, giro_finito):
    """Segnala differenze significative (>= 0,2 s) sui singoli settori contro chi precede/segue."""
    if not st.in_gara() or lap.pit_status or ses.safety_car_status in (1, 2) or lap.current_lap_num < 2:
        an.settore_gara_prec = lap.sector
        return
    prima, ora_s = an.settore_gara_prec, lap.sector
    an.settore_gara_prec = ora_s
    davanti = st.distacco_davanti(idx)
    j_av = st.auto_in_posizione(lap.car_position - 1) if (davanti is not None and davanti < 3.5) else None
    dietro, j_di = st.distacco_dietro(idx)
    j_di = j_di if (dietro is not None and dietro < 3.5) else None

    if prima in (0, 1) and ora_s == prima + 1 and j_av is not None:
        k = prima + 1
        mio_s = _ottieni_settore(an, st, idx, lap.current_lap_num, k)
        suo_s = _ottieni_settore(an, st, j_av, lap.current_lap_num, k)
        if mio_s and suo_s:
            diff = mio_s - suo_s
            if 0.2 <= abs(diff) <= 2.0 and an.ora - an.ultimo.get("settore_altro", -1e9) >= 180 \
                    and an.ora - an.ultimo.get(f"settore_altro_{j_av}", -1e9) >= 240:
                an._puo("settore_altro", 180, t)
                an._puo(f"settore_altro_{j_av}", 240, t)
                out.append(Messaggio("passo", "settore_altro", _frase_settore(st, j_av, k, diff),
                                     livello=2, ttl=12, creato=t))
                return

    if giro_finito and lap.current_lap_num >= 3 and not any(m.chiave == "passo" for m in out):
        finito = lap.current_lap_num - 1
        migliore = None
        for j in (j_av, j_di):
            if j is None:
                continue
            if an.ora - an.ultimo.get(f"settore_altro_{j}", -1e9) < 240:
                continue
            for k in (1, 2, 3):
                mio_s = _ottieni_settore(an, st, idx, finito, k)
                suo_s = _ottieni_settore(an, st, j, finito, k)
                if mio_s and suo_s:
                    diff = mio_s - suo_s
                    if 0.2 <= abs(diff) <= 2.0:
                        if migliore is None or abs(diff) > migliore[0]:
                            migliore = (abs(diff), diff, k, j)
        if migliore is not None and an.ora - an.ultimo.get("settore_altro", -1e9) >= 180:
            _, diff, k, j = migliore
            an._puo("settore_altro", 180, t)
            an._puo(f"settore_altro_{j}", 240, t)
            out.append(Messaggio("passo", "settore_altro", _frase_settore(st, j, k, diff),
                                 livello=2, ttl=12, creato=t))


# ---------- tempo obiettivo (Target Lap) ----------
def target_lap(an, st, ses, lap, idx):
    """Calcola un tempo obiettivo realistico per portare le gomme alla finestra pit."""
    if not st.in_gara() or ses is None or lap is None or not ses.pit_stop_window_ideal_lap:
        return None
    ideale = ses.pit_stop_window_ideal_lap
    n = lap.current_lap_num
    if lap.num_pit_stops > 0 or n < 2 or n >= ideale:
        return None
    puliti = [ms for g, ms, pit, sc in an.strategia.tempi.get(idx, []) if not pit and not sc and g > 1]
    if puliti:
        base_ms = statistics.median(puliti[-5:])
    elif an.rif is not None and an.rif[0].get("tempo_ms"):
        base_ms = an.rif[0]["tempo_ms"]
    else:
        return None
    dmg = st.auto(P.DAMAGE, idx)
    sta = st.auto(P.STATUS, idx)
    usura_g = an._usura_per_giro()
    per_giro = max(usura_g) if usura_g else (
        max(dmg.tyres_wear) / max(1, sta.tyres_age_laps)
        if dmg is not None and sta is not None and sta.tyres_age_laps >= 2 and max(dmg.tyres_wear) > 2
        else None)
    ora_u = max(dmg.tyres_wear) if dmg is not None else 0.0
    prev_u = ora_u + per_giro * (ideale - n) if per_giro is not None else None
    spingendo = prev_u is not None and prev_u > 72
    if spingendo:
        extra_s = min(1.2, max(0.3, (prev_u - 70) * 0.04))
        target_ms = int(round(base_ms + extra_s * 1000))
    else:
        target_ms = int(round(base_ms))
    return {"target_ms": target_ms, "ideale": ideale,
            "usura_prevista": round(prev_u, 1) if prev_u is not None else None,
            "spingendo_troppo": spingendo}


def target_lap_avviso(an, out, t, st, ses, lap, idx, giro_finito):
    tl = target_lap(an, st, ses, lap, idx)
    if tl is not None:
        an.ultimo_target_lap = tl
    if not giro_finito or tl is None or not tl["spingendo_troppo"]:
        return
    if lap.pit_status or ses.safety_car_status in (1, 2) or lap.current_lap_num < 3:
        return
    if lap.last_lap_time_in_ms and lap.last_lap_time_in_ms < tl["target_ms"] - 150:
        if an._puo("target_lap", 240, t):
            out.append(Messaggio("strategia", "target_lap",
                                 f"Stai spingendo troppo sulle gomme. Per arrivare al giro {tl['ideale']} "
                                 f"gira sul {tempo_giro(tl['target_ms'])}.",
                                 priorita=3, livello=2, ttl=15, creato=t))


# ---------- piano A/B/C e chiamate box / resta fuori ----------
def aggiorna_piani(an, out, t, st, ses, lap, idx, nuove_soste):
    """Calcola Piano A/B/C in sessione, gestisce i cambi di piano e le chiamate box / resta fuori."""
    if not st.in_gara() or ses is None or lap is None:
        return
    sta = st.auto(P.STATUS, idx)
    dmg = st.auto(P.DAMAGE, idx)
    storia = st.storia.get(idx)
    usati = set()
    if storia is not None:
        usati = {storia.stints[k].tyre_visual_compound for k in range(min(storia.num_tyre_stints, 8))}
    previsioni = []
    for k in range(min(ses.num_weather_forecast_samples, 64)):
        c = ses.weather_forecast_samples[k]
        if c.session_type == ses.session_type and c.time_offset > 0:
            previsioni.append((c.time_offset, c.weather, c.rain_percentage))
    deg = an.strategia.degrado(idx)
    usura_g = an._usura_per_giro()
    per_giro = max(usura_g) if usura_g else None
    perdita, misurata = an.strategia.piste.perdita_box(ses.track_id)
    piani_dati = calcola_piani(
        totali=ses.total_laps,
        ideale=ses.pit_stop_window_ideal_lap,
        ultimo=ses.pit_stop_window_latest_lap,
        mescola_attuale=sta.visual_tyre_compound if sta is not None else None,
        set_gomme=st.set_gomme.get(idx),
        usati=usati,
        degrado_s=deg,
        usura_per_giro=per_giro,
        meteo_ora=ses.weather,
        previsioni=previsioni,
        giro_corrente=lap.current_lap_num,
        perdita_box=perdita,
        fonte="sessione",
    )
    piani_dati["misurata"] = misurata
    piani_dati["attivo"] = an.piano_attivo
    an.piani_gara = piani_dati

    n = lap.current_lap_num
    totali = ses.total_laps
    mancano = (totali - n + 1) if totali else 99
    if lap.pit_status:
        an._box_chiamato = None
        return

    # 1. Controlla «Resta fuori» su chiamata box già aperta
    ch = getattr(an, "_box_chiamato", None)
    if ch is not None and ch.get("giro") == n:
        if ch.get("motivo") == "undercut" and ch.get("bersaglio") is not None:
            j = ch["bersaglio"]
            c_alt = st.auto(P.LAP, j)
            if j in nuove_soste or (c_alt is not None and c_alt.pit_status):
                an._box_chiamato = None
                if an._puo("resta_fuori", 25, t):
                    out.append(Messaggio(
                        "strategia", "resta_fuori",
                        f"Resta fuori, {st.nome(j)} è rientrato proprio ora.",
                        priorita=1, livello=1, ttl=12, interrompe=True, creato=t))
                    return
        if ses.safety_car_status in (1, 2) and an.sc_prec == 0 and ch.get("motivo") in ("undercut", "piano", "copri"):
            if ch.get("motivo") == "undercut" or mancano <= 3 or (an.mie_soste and n - an.mie_soste[-1] < 5):
                chi = "safety car" if ses.safety_car_status == 1 else "virtual safety car"
                an._box_chiamato = None
                an._sc_soppresso = n
                if an._puo("resta_fuori", 25, t):
                    out.append(Messaggio(
                        "strategia", "resta_fuori",
                        f"Resta fuori, {chi} in pista: cambia il piano.",
                        priorita=1, livello=1, ttl=12, interrompe=True, creato=t))
                    return

    # 2. Valuta cambi di piano (A -> B o C)
    if not totali or mancano <= 2 or n < 2:
        return
    usura_ora = max(dmg.tyres_wear) if dmg is not None else 0.0
    ideale = ses.pit_stop_window_ideal_lap
    ultimo = ses.pit_stop_window_latest_lap
    attivo = an.piano_attivo
    nuovo, motivo = attivo, None

    pioggia_ora = ses.weather >= 3
    pioggia_arr = piani_dati.get("pioggia_in_arrivo")
    slick_ora = sta is None or sta.visual_tyre_compound in P.GOMME_SLICK

    if pioggia_ora and slick_ora:
        if attivo != "C":
            nuovo, motivo = "C", "inizia a piovere, valutiamo le intermedie"
    elif pioggia_arr and pioggia_arr[0] <= 12 and pioggia_arr[2] >= 60 and lap.num_pit_stops == 0:
        if attivo != "C" and (not ideale or n >= max(2, ideale - 2)):
            nuovo, motivo = "C", f"pioggia in arrivo tra {pioggia_arr[0]} minuti"
    elif attivo == "A" and lap.num_pit_stops == 0 and ideale and n < ideale:
        tasso = per_giro or (usura_ora / max(1, sta.tyres_age_laps)
                             if sta is not None and sta.tyres_age_laps >= 2 and usura_ora > 2 else None)
        prev_u = usura_ora + tasso * (ideale - n) if tasso is not None else None
        if (prev_u is not None and prev_u >= 78) or (deg is not None and deg >= 0.45 and n >= 3) \
                or (usura_ora >= 65 and n <= ideale - 2):
            nuovo, motivo = "B", "degrado più alto del previsto, anticipiamo la sosta"
    elif attivo == "A" and not pioggia_ora and not pioggia_arr and lap.num_pit_stops == 0 \
            and ultimo and n > ultimo and mancano > 3:
        nuovo, motivo = "C", "allunghiamo lo stint"

    if nuovo != attivo:
        an.piano_attivo = nuovo
        piani_dati["attivo"] = nuovo
        if ch is not None and ch.get("giro") == n and nuovo == "C" and piani_dati["piani"]["C"].get("pioggia"):
            an._box_chiamato = None
            if an._puo("resta_fuori", 25, t):
                out.append(Messaggio(
                    "strategia", "resta_fuori",
                    f"Resta fuori, passiamo al Piano C: {motivo}.",
                    priorita=1, livello=1, ttl=12, interrompe=True, creato=t))
                return
        if an._puo(f"piano_{nuovo}", 180, t):
            out.append(Messaggio(
                "strategia", "piano_strategia",
                f"Passiamo al Piano {nuovo}, {motivo}.",
                priorita=2, livello=2, ttl=15, creato=t))

    # 3. Chiamata esplicita «Box questo giro» sul giro target del piano attivo
    piano = piani_dati["piani"].get(an.piano_attivo) or {}
    target = piano.get("target_giro")
    fraz = lap.lap_distance / ses.track_length if ses.track_length else 0.0
    gia_chiamato = (
        getattr(an, "_box_giro_stint", -1) == len(an.mie_soste)
        or an._box_chiamato is not None
        or any(m.chiave in ("undercut", "box_sc", "sosta_altri", "box_gomme") for m in out)
    )
    if target and n == target and target != ultimo and fraz >= 0.50 and ses.safety_car_status == 0 and not gia_chiamato:
        an._box_giro_stint = len(an.mie_soste)
        an._box_chiamato = {"giro": n, "motivo": "piano", "bersaglio": None, "ora": an.ora, "piano": an.piano_attivo}
        out.append(Messaggio(
            "box", "box_questo_giro",
            f"Box questo giro, Piano {an.piano_attivo}.",
            priorita=2, livello=1, ttl=12, creato=t))
