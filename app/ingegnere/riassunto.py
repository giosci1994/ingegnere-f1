"""Il riassunto dopo la sessione: giri, passo, settori migliori, soste, errori."""

import json
import os
import statistics
import time

from . import pacchetti as P
from .stato import ms

ESITI = {0: "non valido", 1: "inattivo", 2: "attivo", 3: "finito", 4: "non finito",
         5: "squalificato", 6: "non classificato", 7: "ritirato"}
TIPI_PENALITA = {0: "drive through", 1: "stop and go", 2: "penalità in griglia",
                 3: "promemoria penalità", 4: "penalità di tempo", 5: "avvertimento",
                 6: "squalifica", 7: "tolto dal giro di formazione", 8: "fermo troppo a lungo",
                 9: "regole delle gomme", 10: "giro cancellato", 11: "giro e successivo cancellati",
                 12: "giro cancellato", 13: "giro e successivo cancellati",
                 14: "giro e precedente cancellati", 15: "giro e precedente cancellati",
                 16: "ritirato", 17: "bandiera nera"}


def fmt(millis):
    if not millis:
        return None
    s = millis / 1000
    m = int(s // 60)
    return f"{m}:{s - m * 60:06.3f}" if m else f"{s:.3f}"


def costruisci(st, ing, analisi=None):
    idx = st.indice(ing.slot)
    if idx is None:
        return None
    ses = st.sessione()
    storia = st.storia.get(idx)
    extra = {g["giro"]: g for g in ing.giri}
    giri = []
    if storia is not None:
        for i in range(min(storia.num_laps, 100)):
            g = storia.laps[i]
            if not g.lap_time_in_ms:
                continue
            n = i + 1
            e = extra.get(n, {})
            if not e and n == storia.num_laps and ing.arrivo_pos:   # l'ultimo giro finisce col traguardo
                e = {"posizione": ing.arrivo_pos}
            giri.append({
                "giro": n, "tempo_ms": g.lap_time_in_ms, "tempo": fmt(g.lap_time_in_ms),
                "s1": fmt(ms(g.sector1_time_minutes_part, g.sector1_time_ms_part)),
                "s2": fmt(ms(g.sector2_time_minutes_part, g.sector2_time_ms_part)),
                "s3": fmt(ms(g.sector3_time_minutes_part, g.sector3_time_ms_part)),
                "valido": bool(g.lap_valid_bit_flags & 1),
                "box": e.get("box", False), "safety_car": e.get("safety_car", False),
                "posizione": e.get("posizione"), "gomma": e.get("gomma"),
                "usura_max": e.get("usura_max"),
            })
    else:   # senza il pacchetto della storia: i giri visti dall'ingegnere
        for e in ing.giri:
            if e["tempo_ms"]:
                giri.append(dict(e, tempo=fmt(e["tempo_ms"]), s1=None, s2=None, s3=None))
    if not giri:
        return None

    validi = [g for g in giri if g["valido"]]
    migliore = min(validi or giri, key=lambda g: g["tempo_ms"])
    # passo: giri validi, niente primo giro, box o safety car, niente giri oltre il 107%
    puliti = [g["tempo_ms"] for g in validi if g["giro"] > 1 and not g["box"] and not g["safety_car"]]
    if puliti:
        med = statistics.median(puliti)
        puliti = [x for x in puliti if x <= med * 1.07]
    passo = None
    if puliti:
        passo = {"media": fmt(int(statistics.mean(puliti))),
                 "mediana": fmt(int(statistics.median(puliti))),
                 "costanza_s": round(statistics.pstdev(puliti) / 1000, 3) if len(puliti) > 1 else 0,
                 "giri_usati": len(puliti)}

    settori = None
    if storia is not None:
        settori = []
        ideale = 0
        for k, num in enumerate((storia.best_sector1_lap_num, storia.best_sector2_lap_num,
                                 storia.best_sector3_lap_num), start=1):
            if 1 <= num <= len(storia.laps):
                g = storia.laps[num - 1]
                v = ms(getattr(g, f"sector{k}_time_minutes_part"), getattr(g, f"sector{k}_time_ms_part"))
                settori.append({"settore": k, "tempo": fmt(v), "giro": num})
                ideale += v
        if len(settori) == 3:
            settori.append({"settore": "ideale", "tempo": fmt(ideale), "giro": None})

    finale = None
    if st.finale is not None and idx < len(st.finale.cars):
        f = st.finale.cars[idx]
        stint = [{"gomma": P.GOMME_VISIVE.get(f.tyre_stints_visual[i], str(f.tyre_stints_visual[i])),
                  "fino_al_giro": f.tyre_stints_end_laps[i] if f.tyre_stints_end_laps[i] != 255 else None}
                 for i in range(min(f.num_tyre_stints, 8))]
        finale = {"posizione": f.position, "griglia": f.grid_position, "punti": f.points,
                  "giri": f.num_laps, "soste": f.num_pit_stops,
                  "esito": ESITI.get(f.result_status, str(f.result_status)),
                  "tempo_totale": fmt(int(f.total_race_time * 1000)) if f.total_race_time else None,
                  "secondi_di_penalita": f.penalties_time, "stint": stint}
    elif storia is not None and storia.num_tyre_stints:
        finale = {"stint": [{"gomma": P.GOMME_VISIVE.get(s.tyre_visual_compound),
                             "fino_al_giro": s.end_lap if s.end_lap != 255 else None}
                            for s in storia.stints[:storia.num_tyre_stints]]}

    lap = st.auto(P.LAP, idx)
    extra2 = {}
    if analisi is not None:
        try:
            extra2 = analisi.riassunto(st)
        except Exception as e:    # il riassunto base non deve saltare per la fase 2
            extra2 = {"errore_analisi": str(e)}
    return {
        **extra2,
        "id": f"{time.strftime('%Y%m%d', time.localtime(st.inizio))}-{(st.session_uid or 0) & 0xffffff:06x}-{ing.slot}",
        "creato": time.strftime("%d/%m/%Y %H:%M"),
        "sessione": P.NOMI_SESSIONE.get(ses.session_type, "sessione") if ses else "sessione",
        "pista": P.PISTE.get(ses.track_id, "") if ses else "",
        "pista_id": ses.track_id if ses else None,
        "pilota": st.nomi.get(idx, ""),
        "giocatore": ing.slot,
        "formato": st.formato,
        "posizione": (finale or {}).get("posizione") or ing.arrivo_pos or (lap.car_position if lap else None),
        "griglia": (finale or {}).get("griglia") or (lap.grid_position if lap else None),
        "migliore": {"tempo": fmt(migliore["tempo_ms"]), "giro": migliore["giro"]},
        "passo": passo,
        "settori_migliori": settori,
        "finale": finale,
        "soste": ing.soste,
        "giri": giri,
        "errori": {
            "giri_non_validi": [g["giro"] for g in giri if not g["valido"]],
            "avvertimenti_limiti": max(ing.avvertimenti,
                                       lap.corner_cutting_warnings if lap else 0),
            "penalita": [dict(p, nome=TIPI_PENALITA.get(p["tipo"], str(p["tipo"])))
                         for p in ing.penalita],
            "contatti": ing.contatti,
            "flashback": ing.flashback,
        },
    }


def salva(cartella, r):
    os.makedirs(cartella, exist_ok=True)
    p = os.path.join(cartella, r["id"] + ".json")
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)
    return p


def elenco(cartella):
    if not os.path.isdir(cartella):
        return []
    out = []
    for n in sorted(os.listdir(cartella), key=lambda n: os.path.getmtime(os.path.join(cartella, n)),
                    reverse=True):
        if not n.endswith(".json"):
            continue
        try:
            with open(os.path.join(cartella, n), encoding="utf-8") as f:
                r = json.load(f)
        except (OSError, ValueError):
            continue
        out.append({k: r.get(k) for k in ("id", "creato", "sessione", "pista", "posizione",
                                          "giocatore", "migliore", "pilota")})
    return out[:50]
