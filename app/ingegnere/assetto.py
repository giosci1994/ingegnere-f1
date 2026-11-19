"""Assetto: lettura dell'assetto del giocatore e consigli INDICATIVI dopo la sessione.

Ogni consiglio porta il dato che lo sostiene. Sono regole di buon senso dei giochi di F1,
non una verità: si provano una alla volta, in prova libera.

Che cosa non si può sapere dalla telemetria (e quindi non si consiglia):
- le temperature del bordo interno ed esterno della gomma (arrivano solo superficie e
  carcassa): la campanatura si consiglia solo dall'usura anteriore/posteriore;
- i cordoli e il fondo che tocca: niente consigli su sospensioni e altezze.

Sottosterzo e sovrasterzo stimati: rapporto tra l'imbardata vera (motion ex) e quella che
darebbe l'angolo delle ruote con il modello a bicicletta (passo 3,6 m). Il valore assoluto
dipende dal gioco: conta il confronto tra curve lente e veloci, e tra entrata e uscita.
"""

import math
import statistics

from . import pacchetti as P

PASSO = 3.6


def _mediana(x):
    return round(statistics.median(x), 2) if x else None


def leggi_assetto(s):
    if s is None:
        return None
    return {
        "ala_anteriore": s.front_wing, "ala_posteriore": s.rear_wing,
        "differenziale_in_trazione": s.on_throttle, "differenziale_in_rilascio": s.off_throttle,
        "campanatura_anteriore": round(s.front_camber, 2), "campanatura_posteriore": round(s.rear_camber, 2),
        "convergenza_anteriore": round(s.front_toe, 2), "convergenza_posteriore": round(s.rear_toe, 2),
        "sospensione_anteriore": s.front_suspension, "sospensione_posteriore": s.rear_suspension,
        "barra_anteriore": s.front_anti_roll_bar, "barra_posteriore": s.rear_anti_roll_bar,
        "altezza_anteriore": s.front_suspension_height, "altezza_posteriore": s.rear_suspension_height,
        "pressione_freni": s.brake_pressure, "ripartizione_freni": s.brake_bias,
        "freno_motore": s.engine_braking,
        "pressioni_gomme": [round(s.front_left_tyre_pressure, 1), round(s.front_right_tyre_pressure, 1),
                            round(s.rear_left_tyre_pressure, 1), round(s.rear_right_tyre_pressure, 1)],
        "zavorra": s.ballast, "carburante": round(s.fuel_load, 1),
    }


def _bilanciamento(giri):
    """Rapporti imbardata vera / attesa, per fase e per velocità."""
    fasi = {"entrata": [], "centro": [], "uscita": [], "lente": [], "veloci": []}
    for c in giri:
        n = len(c["d"])
        for i in range(n):
            v, wa, yr = c["v"][i], c["wa"][i], c["yr"][i]
            if v is None or wa is None or yr is None or v < 60 or abs(wa) < 0.01:
                continue
            atteso = (v / 3.6) * math.tan(abs(wa)) / PASSO
            if atteso < 0.05:
                continue
            r = abs(yr) / atteso
            if r > 3:
                continue
            br, th = c["br"][i] or 0, c["th"][i] or 0
            if v < 150:                   # le fasi si confrontano a parità di velocità (curve lente)
                if br > 0.2:
                    fasi["entrata"].append(r)
                elif th > 0.6:
                    fasi["uscita"].append(r)
                else:
                    fasi["centro"].append(r)
            if v < 150:
                fasi["lente"].append(r)
            elif v > 200:
                fasi["veloci"].append(r)
    return {k: _mediana(x) for k, x in fasi.items()}


def analizza(giri, assetto, usura_per_giro, speed_trap, gara):
    """giri: tracce (dict c) dei giri puliti del giocatore.
    usura_per_giro: [RL, RR, FL, FR] % per giro (o None). speed_trap: (mio, mediana altri)."""
    if not giri:
        return {"assetto": assetto, "consigli": [], "nota": "Nessun giro pulito con la traccia completa."}
    dati = {}
    consigli = []

    def consiglia(cosa, perche):
        consigli.append({"consiglio": cosa, "dato": perche})

    # temperature
    sup = [[], [], [], []]
    car = [[], [], [], []]
    freni_alti = 0
    campioni = 0
    for c in giri:
        for i in range(len(c["d"])):
            if (c["v"][i] or 0) < 80:
                continue
            campioni += 1
            for k in range(4):
                if c["ts"][i]:
                    sup[k].append(c["ts"][i][k])
                    car[k].append(c["ti"][i][k])
            if c["bt"][i] and max(c["bt"][i]) > 1000:
                freni_alti += 1
    s = [_mediana(x) for x in sup]
    dati["gomme_superficie"] = dict(zip(("PS", "PD", "AS", "AD"), s))
    dati["gomme_carcassa"] = dict(zip(("PS", "PD", "AS", "AD"), [_mediana(x) for x in car]))
    if all(x is not None for x in s):
        ant, post = (s[2] + s[3]) / 2, (s[0] + s[1]) / 2
        if post - ant > 8:
            consiglia("Posteriore che scalda troppo: differenziale in trazione più aperto (-5/-10%) "
                      "o pressioni posteriori un po' più basse.",
                      f"superficie posteriori {post:.0f} °C contro anteriori {ant:.0f} °C")
        elif ant - post > 8:
            consiglia("Anteriore che scalda troppo (scivola davanti): ala anteriore -1 o barra anteriore più morbida.",
                      f"superficie anteriori {ant:.0f} °C contro posteriori {post:.0f} °C")
        media = sum(s) / 4
        if media > 105:
            consiglia("Gomme calde in generale: pressioni più basse (-0,4 psi) e guida più pulita in uscita.",
                      f"superficie media {media:.0f} °C")
        elif media < 85:
            consiglia("Gomme fredde: pressioni un po' più alte (+0,4 psi).", f"superficie media {media:.0f} °C")

    # freni
    if campioni:
        quota = freni_alti / campioni
        dati["freni_oltre_1000_percento"] = round(100 * quota, 1)
        if quota > 0.03:
            consiglia("Freni molto caldi: pressione freni più bassa (-2/-5%).",
                      f"freni sopra 1000 °C nel {100 * quota:.0f}% dei campioni")

    # bloccaggi e pattinamenti (contati per giro)
    blocchi_av = blocchi_post = pattina = 0
    for c in giri:
        prev_a = prev_p = prev_s = False
        for i in range(len(c["d"])):
            br, th = c["br"][i] or 0, c["th"][i] or 0
            a = br > 0.2 and c["sf"][i] is not None and c["sf"][i] < -0.2
            p = br > 0.2 and c["sb"][i] is not None and c["sb"][i] < -0.25
            w = th > 0.5 and c["sr"][i] is not None and c["sr"][i] > 0.2
            blocchi_av += a and not prev_a
            blocchi_post += p and not prev_p
            pattina += w and not prev_s
            prev_a, prev_p, prev_s = a, p, w
    n = len(giri)
    dati["bloccaggi_anteriori_per_giro"] = round(blocchi_av / n, 1)
    dati["bloccaggi_posteriori_per_giro"] = round(blocchi_post / n, 1)
    dati["pattinamenti_per_giro"] = round(pattina / n, 1)
    if blocchi_av / n >= 2:
        consiglia("Bloccaggi davanti: ripartizione di frenata più indietro (-1/-2%) o pressione freni più bassa.",
                  f"{blocchi_av / n:.1f} bloccaggi anteriori per giro")
    if blocchi_post / n >= 1.5:
        consiglia("Bloccaggi dietro: ripartizione di frenata più avanti (+1/+2%) o freno motore più basso.",
                  f"{blocchi_post / n:.1f} bloccaggi posteriori per giro")
    if pattina / n >= 2:
        consiglia("Pattinamento in uscita: differenziale in trazione più aperto (-5/-10%) o barra posteriore più morbida.",
                  f"{pattina / n:.1f} pattinamenti per giro")

    # bilanciamento
    b = _bilanciamento(giri)
    dati["bilanciamento"] = b
    if b["lente"] and b["veloci"]:
        if b["lente"] < b["veloci"] * 0.88:
            consiglia("Più sottosterzo nelle curve lente che in quelle veloci: barra anteriore più morbida "
                      "o differenziale in rilascio più aperto.",
                      f"imbardata/attesa lente {b['lente']} contro veloci {b['veloci']}")
        elif b["veloci"] < b["lente"] * 0.88:
            consiglia("Sottosterzo nelle curve veloci: ala anteriore +1.",
                      f"imbardata/attesa veloci {b['veloci']} contro lente {b['lente']}")
    if b["uscita"] and b["centro"] and b["uscita"] > b["centro"] * 1.15:
        consiglia("La macchina gira troppo in uscita (sovrasterzo in trazione): differenziale in trazione "
                  "più aperto o barra posteriore più morbida.",
                  f"imbardata/attesa in uscita {b['uscita']} contro centro curva {b['centro']}")
    if b["entrata"] and b["centro"] and b["entrata"] > b["centro"] * 1.15:
        consiglia("Posteriore nervoso in frenata: ripartizione più avanti o freno motore più basso.",
                  f"imbardata/attesa in frenata {b['entrata']} contro centro curva {b['centro']}")

    # usura
    if usura_per_giro and all(x is not None for x in usura_per_giro):
        ant = (usura_per_giro[2] + usura_per_giro[3]) / 2
        post = (usura_per_giro[0] + usura_per_giro[1]) / 2
        dati["usura_per_giro"] = {"anteriori": round(ant, 2), "posteriori": round(post, 2)}
        if ant > post * 1.3 and ant > 0.5:
            consiglia("Le anteriori si consumano più delle posteriori: campanatura anteriore un po' meno negativa "
                      "o convergenza anteriore più vicina a zero.",
                      f"usura {ant:.1f}%/giro davanti contro {post:.1f}% dietro")
        elif post > ant * 1.3 and post > 0.5:
            consiglia("Le posteriori si consumano di più: differenziale in trazione più aperto, "
                      "campanatura posteriore un po' meno negativa.",
                      f"usura {post:.1f}%/giro dietro contro {ant:.1f}% davanti")

    # velocità di punta
    if speed_trap and speed_trap[0] and speed_trap[1]:
        mio, altri = speed_trap
        dati["speed_trap"] = {"tuo": round(mio), "mediana_altri": round(altri)}
        if mio < altri - 6:
            consiglia("Meno ala posteriore (-1/-2) per la velocità sul dritto.",
                      f"speed trap {mio:.0f} km/h contro {altri:.0f} della mediana degli altri")
        elif mio > altri + 6 and b.get("veloci") and b.get("lente") and b["veloci"] < b["lente"]:
            consiglia("Sei veloce sul dritto: puoi permetterti più ala (+1) per le curve.",
                      f"speed trap {mio:.0f} km/h contro {altri:.0f}")

    nota = ("Consigli indicativi: provane uno alla volta in prova libera. "
            "Niente consigli su sospensioni e altezze: la telemetria non dice dei cordoli né del fondo.")
    if gara:
        nota += " In gara l'assetto è bloccato: valgono per la prossima sessione."
    return {"assetto": assetto, "dati": dati, "consigli": consigli, "nota": nota}
