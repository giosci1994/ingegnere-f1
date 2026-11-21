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
NOMI_MESCOLA = {16: "soft", 17: "medie", 18: "dure", 7: "intermedie", 8: "gomme da bagnato",
                15: "gomme da bagnato", 19: "super soft", 20: "soft", 21: "dure", 22: "soft",
                23: "medie", 24: "dure"}


def _leggi_set(set_gomme):
    """Normalizza i set di gomme da TYRESETS o lista di dict in una lista uniforme."""
    if not set_gomme:
        return []
    raw = getattr(set_gomme, "sets", set_gomme)
    out = []
    for s in raw:
        if isinstance(s, dict):
            comp = s.get("visual_tyre_compound", 0)
            disp = bool(s.get("available", True))
            montata = bool(s.get("fitted", False))
            usura = float(s.get("wear", 0))
            vita_tot = float(s.get("usable_life", 0))
            delta = float(s.get("lap_delta_time", 0))
        else:
            comp = getattr(s, "visual_tyre_compound", 0)
            disp = bool(getattr(s, "available", 0))
            montata = bool(getattr(s, "fitted", 0))
            usura = float(getattr(s, "wear", 0))
            vita_tot = float(getattr(s, "usable_life", 0))
            delta = float(getattr(s, "lap_delta_time", 0))
        if not comp:
            continue
        out.append({
            "comp": comp,
            "nome": NOMI_MESCOLA.get(comp, P.GOMME_VISIVE.get(comp, "gomme")),
            "disp": disp,
            "montata": montata,
            "usura": usura,
            "vita": vita_tot * (1.0 - usura / 100.0) if vita_tot else 0.0,
            "delta": delta,
        })
    return out


def calcola_piani(totali=None, ideale=0, ultimo=0, mescola_attuale=None, set_gomme=None,
                  usati=None, degrado_s=None, usura_per_giro=None, meteo_ora=0,
                  previsioni=None, giro_corrente=1, perdita_box=PERDITA_STIMA, fonte="sessione"):
    """Calcola i piani alternativi A (standard), B (aggressivo), C (conservativo / pioggia)."""
    usati = set(usati or ())
    sets = _leggi_set(set_gomme)
    if mescola_attuale is None:
        mont = next((s for s in sets if s["montata"]), None)
        mescola_attuale = mont["comp"] if mont else 17
    if isinstance(mescola_attuale, str):
        nome_attuale = mescola_attuale
    else:
        nome_attuale = NOMI_MESCOLA.get(mescola_attuale, P.GOMME_VISIVE.get(mescola_attuale, "medie"))

    dry_cand = [s for s in sets if s["disp"] and not s["montata"] and s["comp"] in P.GOMME_SLICK and s["vita"] > 0]
    dry_div = [s for s in dry_cand if s["comp"] not in usati]
    pool_dry = dry_div or dry_cand

    pioggia_arrivo = None
    for off, w, prob in (previsioni or ()):
        if 0 < off <= 20 and (w >= 3 or prob >= 55):
            pioggia_arrivo = (int(off), int(w), int(prob))
            break

    if not totali or totali < 4:
        nome_a = min(pool_dry, key=lambda s: (s["delta"], s["usura"]))["nome"] if pool_dry else (
            "dure" if nome_attuale != "dure" else "medie")
        nome_b = min(dry_cand, key=lambda s: (s["delta"], s["usura"]))["nome"] if dry_cand else (
            "soft" if nome_attuale != "soft" else "medie")
        nome_c = max(pool_dry, key=lambda s: (s["vita"], -s["delta"]))["nome"] if pool_dry else (
            "dure" if nome_attuale != "dure" else "medie")
        deg_txt = f", degrado stimato {degrado_s:.2f} s/giro" if degrado_s is not None else ""
        return {
            "attivo": "A",
            "fonte": fonte,
            "perdita_box_s": round(perdita_box, 1),
            "pioggia_in_arrivo": pioggia_arrivo,
            "piani": {
                "A": {"codice": "A", "nome": "Piano A", "stile": "Standard (1 sosta)", "soste": 1,
                      "finestra": None, "target_giro": None, "mescole": [nome_attuale, nome_a],
                      "pioggia": False, "motivo": "strategia bilanciata sulla durata gara",
                      "descrizione": f"1 sosta standard ({nome_attuale} → {nome_a}), perdita box ~{round(perdita_box)} s{deg_txt}."},
                "B": {"codice": "B", "nome": "Piano B", "stile": "Aggressivo (2 soste / undercut)", "soste": 2,
                      "finestra": None, "target_giro": None, "mescole": [nome_attuale, nome_b, nome_b],
                      "pioggia": False, "motivo": "degrado alto o tentativo di undercut",
                      "descrizione": f"Strategia aggressiva a 2 soste o anticipata su {nome_b}."},
                "C": {"codice": "C", "nome": "Piano C", "stile": "Conservativo / Pioggia", "soste": 1,
                      "finestra": None, "target_giro": None, "mescole": [nome_attuale, nome_c],
                      "pioggia": False, "motivo": "stint lungo o attesa meteo / safety car",
                      "descrizione": f"Stint allungato su {nome_c} (o intermedie in caso di pioggia)."},
            },
        }

    # Con numero di giri totali noto (in gara o da storico gare sulla pista)
    if ideale and 2 <= ideale < totali:
        g_a = int(ideale)
    elif usura_per_giro and usura_per_giro > 0.5:
        g_a = min(totali - 2, max(2, int(round(75.0 / usura_per_giro))))
    else:
        g_a = max(2, int(round(totali * 0.45)))
    g_a_fine = int(ultimo) if (ultimo and g_a <= ultimo < totali) else min(totali - 1, g_a + 2)
    mancano_a = max(1, totali - g_a)

    bastano_a = [s for s in pool_dry if s["vita"] >= mancano_a]
    if bastano_a:
        set_a = min(bastano_a, key=lambda s: (s["delta"], s["usura"]))
    elif pool_dry:
        set_a = max(pool_dry, key=lambda s: (s["vita"], -s["delta"]))
    else:
        set_a = None
    nome_a = set_a["nome"] if set_a else ("dure" if nome_attuale != "dure" else "medie")

    max_vita = max((s["vita"] for s in pool_dry), default=0.0)
    soste_a = 2 if (totali >= 30 and max_vita and max_vita < totali * 0.52) else 1
    if soste_a == 2:
        g_a1 = max(2, min(g_a, totali // 3))
        g_a2 = min(totali - 2, g_a1 + max(4, (totali - g_a1) // 2))
        finestra_a = [g_a1, g_a2]
        target_a = g_a1
        nome_a2 = max(dry_cand, key=lambda s: s["vita"])["nome"] if dry_cand else nome_a
        mescole_a = [nome_attuale, nome_a, nome_a2]
        desc_a = f"2 soste (giri {g_a1} e {g_a2}): {nome_attuale} → {nome_a} → {nome_a2}."
    else:
        finestra_a = [g_a, g_a_fine]
        target_a = g_a
        mescole_a = [nome_attuale, nome_a]
        win_txt = f"giro {g_a}" if g_a == g_a_fine else f"giri {g_a}–{g_a_fine}"
        desc_a = f"1 sosta standard ({win_txt}): {nome_attuale} → {nome_a}."

    # Piano B: aggressivo (2 soste o sosta anticipata per undercut / degrado alto)
    g_b1 = max(2, target_a - 2)
    set_aggr = min(dry_cand, key=lambda s: (s["delta"], s["usura"])) if dry_cand else None
    nome_aggr = set_aggr["nome"] if set_aggr else ("soft" if nome_attuale != "soft" else "medie")
    if totali >= 14 and len(dry_cand) >= 2 and soste_a == 1:
        soste_b = 2
        g_b2 = min(totali - 2, g_b1 + max(5, (totali - g_b1) // 2))
        finestra_b = [g_b1, g_b2]
        set_b2 = min([s for s in dry_cand if s is not set_aggr], key=lambda s: (s["delta"], s["usura"]))
        mescole_b = [nome_attuale, nome_aggr, set_b2["nome"]]
        stile_b = "Aggressivo (2 soste)"
        desc_b = f"2 soste aggressive (giri {g_b1} e {g_b2}): {nome_attuale} → {nome_aggr} → {set_b2['nome']}."
    else:
        soste_b = 1
        g_b_fine = max(g_b1, target_a - 1)
        finestra_b = [g_b1, g_b_fine]
        # in gara asciutta con 1 sosta cerchiamo una mescola diversa che arrivi in fondo, preferendo la più rapida
        bastano_b = [s for s in pool_dry if s["vita"] >= max(1, totali - g_b1)]
        set_b = min(bastano_b, key=lambda s: (s["delta"], s["usura"])) if bastano_b else set_aggr
        nome_b = set_b["nome"] if set_b else nome_aggr
        mescole_b = [nome_attuale, nome_b]
        stile_b = "Aggressivo (sosta anticipata)"
        desc_b = f"1 sosta anticipata al giro {g_b1} per undercut o degrado alto: {nome_attuale} → {nome_b}."

    # Piano C: conservativo (allunga / gomma dura) o pioggia in arrivo / in atto
    if meteo_ora >= 3:
        g_c = max(2, min(totali - 1, giro_corrente))
        mesc_w = "gomme da bagnato" if meteo_ora >= 4 else "intermedie"
        stile_c = "Pioggia in pista"
        finestra_c = [g_c, min(totali - 1, g_c + 1)]
        target_c = g_c
        mescole_c = [nome_attuale, mesc_w]
        pioggia_c = True
        motivo_c = "pista bagnata"
        desc_c = f"Pioggia attiva: passaggio alle {mesc_w}."
    elif pioggia_arrivo is not None:
        off, w_arr, prob = pioggia_arrivo
        g_c = min(totali - 2, max(g_a_fine + 1, target_a + 2))
        mesc_w = "gomme da bagnato" if w_arr >= 4 else "intermedie"
        stile_c = "Pioggia in arrivo"
        finestra_c = [g_a_fine, g_c]
        target_c = None
        mescole_c = [nome_attuale, mesc_w]
        pioggia_c = True
        motivo_c = f"pioggia prevista tra {off} minuti ({prob}%)"
        desc_c = f"Pioggia prevista tra {off} min ({prob}%): allunga lo stint fino al giro {g_c} per montare {mesc_w}."
    else:
        set_cons = max(pool_dry, key=lambda s: (s["vita"], -s["delta"])) if pool_dry else None
        nome_cons = set_cons["nome"] if set_cons else ("dure" if nome_attuale != "dure" else "medie")
        g_c = min(totali - 2, max(g_a_fine + 2, target_a + 4))
        stile_c = "Conservativo (stint lungo)"
        finestra_c = [g_a_fine, max(g_a_fine, g_c)]
        target_c = g_c
        mescole_c = [nome_attuale, nome_cons]
        pioggia_c = False
        motivo_c = "gomma più dura o attesa safety car"
        desc_c = f"1 sosta conservativa al giro {g_c}: {nome_attuale} → {nome_cons}."

    return {
        "attivo": "A",
        "fonte": fonte,
        "perdita_box_s": round(perdita_box, 1),
        "pioggia_in_arrivo": pioggia_arrivo,
        "piani": {
            "A": {"codice": "A", "nome": "Piano A", "stile": "Standard" if soste_a == 1 else "Standard (2 soste)",
                  "soste": soste_a, "finestra": finestra_a, "target_giro": target_a,
                  "mescole": mescole_a, "pioggia": False,
                  "motivo": "finestra ideale e degrado regolare", "descrizione": desc_a},
            "B": {"codice": "B", "nome": "Piano B", "stile": stile_b,
                  "soste": soste_b, "finestra": finestra_b, "target_giro": g_b1,
                  "mescole": mescole_b, "pioggia": False,
                  "motivo": "degrado più alto o undercut aggressivo", "descrizione": desc_b},
            "C": {"codice": "C", "nome": "Piano C", "stile": stile_c,
                  "soste": 1, "finestra": finestra_c, "target_giro": target_c,
                  "mescole": mescole_c, "pioggia": pioggia_c,
                  "motivo": motivo_c, "descrizione": desc_c},
        },
    }


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
        self.in_pit_live = {}     # idx -> num_pit_stops all'ingresso ai box
        self.uscite = []          # idx usciti dai box con sosta fatta
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
            if c.pit_status and i not in self.in_pit_live:
                self.in_pit_live[i] = c.num_pit_stops
            elif not c.pit_status and i in self.in_pit_live:
                soste_prima = self.in_pit_live.pop(i)
                if c.result_status == 2 and c.num_pit_stops > soste_prima and i not in self.uscite:
                    self.uscite.append(i)
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
