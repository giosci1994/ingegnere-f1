"""Fase 2: tracce dei giri, staccate e uscite in diretta, strategia (undercut/overcut),
ali mobili 2026, e i pezzi del riassunto (guida, assetto, strategia, ali).

Una Analisi per sessione, per l'auto del giocatore (player_car_index).
"""

import statistics

from . import assetto as A
from . import curve as C
from . import pacchetti as P
from .ingegnere import Messaggio, dec, pos
from .strategia import Strategia
from .traccia import Biblioteca, Tracciatore, copertura

MAX_IN_MEMORIA = 20


class Analisi:
    def __init__(self, imp, biblioteca: Biblioteca, piste):
        self.imp = imp
        self.bib = biblioteca
        self.strategia = Strategia(piste)
        self.nuova_sessione()

    def nuova_sessione(self):
        self.trac = Tracciatore()
        self.strategia.reset()
        self.giri = []             # [(meta, c)] giri della sessione con traccia (ultimi 20)
        self.rif = None            # (meta, c) giro di riferimento
        self.curve = []
        self.rif_misure = {}
        self.valutate = set()      # curve già guardate nel giro in corso
        self.dette_giro = 0
        self.giro_corrente = None
        self.ultimo = {}
        self.usure = []            # (giro, [4], box)
        self.rientro_detto = set()
        self.ali_rett_dal = None
        self.ali_avvisi = 0
        self.stato_ali = None
        self.mie_soste = []
        self.pista = None

    def _puo(self, chiave, attesa, t):
        u = self.ultimo.get(chiave)
        if u is not None and u <= t and t - u < attesa:
            return False
        self.ultimo[chiave] = t
        return True

    # ---------- a ogni pacchetto di telemetria ----------
    def campione(self, st):
        idx = st.indice()
        if idx is None:
            return
        finito = self.trac.campione(st, idx)
        if finito is None:
            return
        lap = st.auto(P.LAP, idx)
        ses = st.sessione()
        dmg = st.auto(P.DAMAGE, idx)
        self.pista = ses.track_id if ses else None
        if dmg is not None:
            self.usure.append((finito.numero, list(dmg.tyres_wear), finito.box))
        tempo = lap.last_lap_time_in_ms if lap else 0
        if not tempo or ses is None or copertura(finito, ses.track_length) < 0.9:
            return
        meta = {"pista": ses.track_id, "tempo_ms": tempo, "valido": not finito.invalido,
                "sessione": P.NOMI_SESSIONE.get(ses.session_type, "sessione"),
                "session_uid": st.session_uid or 0, "pilota": self.imp["pilota"],
                "formato": st.formato, "data": None}
        if self.imp["salva_giri"]:
            try:
                meta["id"] = self.bib.salva(finito, meta)
            except OSError:
                pass
        meta.update(giro=finito.numero, box=finito.box, safety_car=finito.sc, invalido=finito.invalido)
        self.giri.append((meta, finito.c))
        if len(self.giri) > MAX_IN_MEMORIA:
            self.giri.pop(0)
        pulito = meta["valido"] and not finito.box and not finito.sc and \
            not (st.in_gara() and finito.numero == 1)          # la partenza da fermo non fa da riferimento
        if pulito and (self.rif is None or tempo < self.rif[0]["tempo_ms"]
                       or self.rif[0].get("da_biblioteca")):
            self._imposta_rif(meta, finito.c)

    def _imposta_rif(self, meta, c):
        self.rif = (meta, c)
        self.curve = C.trova_curve(c)
        self.rif_misure = {cu["n"]: C.misura(c, cu) for cu in self.curve}

    def rif_da_biblioteca(self, st):
        """Prima del primo giro pulito: il giro migliore salvato su questa pista, di chi guida."""
        ses = st.sessione()
        if self.rif is not None or ses is None:
            return
        m = self.bib.migliore(ses.track_id, self.imp["pilota"])
        if m:
            g = self.bib.leggi(ses.track_id, m["id"])
            if g:
                self._imposta_rif(dict(g["meta"], da_biblioteca=True), g["c"])

    # ---------- ogni 0,2 s ----------
    def valuta(self, st, nuove_soste):
        idx = st.indice()
        ses = st.sessione()
        lap = st.auto(P.LAP, idx)
        if idx is None or ses is None or lap is None or ses.game_paused or lap.driver_status == 0:
            return []
        t = st.tempo()
        out = []
        if lap.current_lap_num != self.giro_corrente:
            self.giro_corrente = lap.current_lap_num
            self.valutate = set()
            self.dette_giro = 0
        if self.rif is None and lap.current_lap_num <= 2:
            self.rif_da_biblioteca(st)
        self._guida(out, t, st, ses, lap)
        if st.in_gara():
            self._strategia(out, t, st, ses, lap, idx, nuove_soste)
        if st.formato == 2026:
            self._ali(out, t, st, ses, lap, idx)
        return out

    def _guida(self, out, t, st, ses, lap):
        g = self.trac.giro
        if not self.curve or g is None or lap.pit_status or ses.safety_car_status in (1, 2):
            return
        if st.in_gara() and lap.current_lap_num <= 1:
            return
        d = lap.lap_distance
        for cu in self.curve:
            if cu["n"] in self.valutate or d < cu["fine"] + 60:
                continue
            self.valutate.add(cu["n"])
            if d > cu["fine"] + 600:          # siamo partiti a metà giro: niente confronto
                continue
            m = C.misura(g.c, cu)
            r = self.rif_misure.get(cu["n"])
            if not r or m.get("tempo") is None or r.get("tempo") is None:
                continue
            delta = m["tempo"] - r["tempo"]
            if delta < 0.15 or self.dette_giro >= 2:
                continue
            k, frase = C.causa(m, r)
            if not k or not self._puo(f"curva{cu['n']}", 120, t):
                continue
            self.dette_giro += 1
            out.append(Messaggio("guida", f"curva{cu['n']}",
                                 f"Curva {cu['n']}, perdi {C.decimi(delta)}: {frase}.",
                                 livello=2, ttl=6, creato=t))

    def _strategia(self, out, t, st, ses, lap, idx, nuove_soste):
        stg = self.strategia
        n = lap.current_lap_num
        mancano = ses.total_laps - n + 1 if ses.total_laps else 99
        if lap.pit_status:
            if not self.mie_soste or self.mie_soste[-1] < n - 1:
                self.mie_soste.append(n)
            return
        if n < 2 or mancano <= 2:
            return
        sosta_recente = self.mie_soste and n - self.mie_soste[-1] < 5
        dmg = st.auto(P.DAMAGE, idx)
        sta_all = st.get(P.STATUS)
        usura = max(dmg.tyres_wear) if dmg is not None else 0
        mia_eta = sta_all.cars[idx].tyres_age_laps if sta_all is not None else 0
        davanti_i = st.auto_in_posizione(lap.car_position - 1) if lap.car_position > 1 else None
        dietro_g, dietro_i = st.distacco_dietro(idx)
        davanti_g = st.distacco_davanti(idx)

        # le soste degli altri (all'entrata in pit lane): overcut o copertura
        for i in nuove_soste:
            if i == idx or sosta_recente or mancano <= 3:
                continue
            if i == davanti_i and davanti_g is not None and davanti_g < 4:
                if self._puo(f"overcut{i}", 60, t):
                    out.append(Messaggio("strategia", "sosta_altri",
                                         f"{st.nome(i)} si è fermato. Spingi due giri, proviamo l'overcut.",
                                         priorita=2, livello=1, ttl=15, creato=t))
            elif i == dietro_i and dietro_g is not None and dietro_g < 4:
                if not self._puo(f"copri{i}", 60, t):
                    continue
                if usura >= 60:
                    testo = f"{st.nome(i)} si è fermato. Copri l'undercut: box questo giro."
                else:
                    testo = f"{st.nome(i)} si è fermato. Spingi due giri, tieni il passo."
                out.append(Messaggio("strategia", "sosta_altri", testo, priorita=2, livello=1,
                                     ttl=15, creato=t))
        if sosta_recente:
            return

        finestra = ses.pit_stop_window_ideal_lap and \
            ses.pit_stop_window_ideal_lap - 1 <= n <= max(ses.pit_stop_window_latest_lap, ses.pit_stop_window_ideal_lap) + 1
        if not (finestra or usura >= 55):
            return
        fraz = lap.lap_distance / ses.track_length if ses.track_length else 0
        r = stg.rientro(st, idx)
        if r is None:
            return
        # undercut sulla macchina davanti
        deg = stg.degrado(idx)
        if davanti_i is not None and davanti_g is not None and davanti_g < 3.5 and deg and deg >= 0.04 \
                and sta_all is not None:
            sua_eta = sta_all.cars[davanti_i].tyres_age_laps
            ultima = stg.soste_viste.get(davanti_i, 0)
            if sua_eta >= mia_eta - 1 and sua_eta >= 5:
                guadagno = deg * sua_eta - 0.8
                if guadagno > davanti_g + 0.3 and (r["margine_dietro"] is None or r["margine_dietro"] >= 1.0) \
                        and self._puo("undercut", 150, t):
                    out.append(Messaggio(
                        "strategia", "undercut",
                        f"Undercut su {st.nome(davanti_i)}: box adesso. Stimiamo {dec(guadagno)} secondi "
                        f"di vantaggio con le gomme nuove.", priorita=2, livello=1, ttl=15, creato=t))
                    return
        # dove esci, una volta a giro a metà giro
        if 0.45 <= fraz <= 0.6 and n not in self.rientro_detto:
            self.rientro_detto.add(n)
            testo = f"Se rientri adesso esci {pos(r['posizione'])}"
            if r["davanti_a"] is not None and r["margine_dietro"] is not None:
                if r["margine_dietro"] < 1.0:
                    testo += f", con {st.nome(r['davanti_a'])} attaccato dietro"
                else:
                    testo += f", davanti a {st.nome(r['davanti_a'])} di {dec(r['margine_dietro'])}"
            if r["dietro_a"] is not None and r["margine_davanti"] is not None and r["margine_davanti"] < 1.0:
                testo += f", subito dietro a {st.nome(r['dietro_a'])}"
            testo += "." if r["misurata"] else ". Tempo del box stimato."
            out.append(Messaggio("strategia", "rientro", testo, priorita=3, livello=2, ttl=12, creato=t))

    def _ali(self, out, t, st, ses, lap, idx):
        t2 = st.auto(P.TELEMETRY2, idx)
        tel = st.auto(P.TELEMETRY, idx)
        if t2 is None or tel is None or not t2.regulations_2026:
            return
        stato = ses.active_aero_track_status
        if self.stato_ali is not None and stato != self.stato_ali and self._puo("ali_pista", 120, t):
            testo = ("Ali mobili: adesso solo le zone ridotte." if stato == 1
                     else "Ali mobili: di nuovo tutte le zone.")
            out.append(Messaggio("ali", "ali_pista", testo, livello=2, ttl=15, creato=t))
        self.stato_ali = stato
        if t2.active_aero_available and t2.active_aero_mode == 0 and tel.speed > 200 and tel.throttle > 0.9 \
                and not lap.pit_status:
            self.ali_rett_dal = self.ali_rett_dal or t
            if t - self.ali_rett_dal > 1.5 and self._puo("ali_rettilineo", 60, t):
                self.ali_avvisi += 1
                out.append(Messaggio("ali", "ali_rettilineo", "Ali in modalità rettilineo!",
                                     livello=2, ttl=4, fisso=True, creato=t))
        else:
            self.ali_rett_dal = None

    # ---------- riassunto ----------
    def riassunto(self, st):
        idx = st.indice()
        ses = st.sessione()
        out = {"chi_guida": self.imp["pilota"]}
        if self.rif is not None:
            rm, rc = self.rif
            out["riferimento"] = {"giro": rm.get("giro"), "tempo_ms": rm.get("tempo_ms"),
                                  "da_biblioteca": bool(rm.get("da_biblioteca")), "id": rm.get("id")}
            curve = []
            per_curva = {cu["n"]: [] for cu in self.curve}
            cause = {cu["n"]: [] for cu in self.curve}
            for meta, c in self.giri:
                if meta.get("box") or meta.get("safety_car") or meta.get("id") == rm.get("id") \
                        or meta.get("giro") == rm.get("giro") and not rm.get("da_biblioteca"):
                    continue
                for x in C.confronta(c, rc, self.curve):
                    if x["delta"] is not None:
                        per_curva[x["curva"]].append(x["delta"])
                        if x["causa"]:
                            cause[x["curva"]].append(x["frase"])
            for cu in self.curve:
                r = self.rif_misure.get(cu["n"], {})
                dl = per_curva[cu["n"]]
                curve.append({
                    "curva": cu["n"], "apice_m": round(cu["apice"]), "vmin_rif": r.get("vmin"),
                    "frenata_rif_m": round(r["frenata"]) if r.get("frenata") is not None else None,
                    "gas_rif_m": round(r["gas"]) if r.get("gas") is not None else None,
                    "perdita_media_s": round(statistics.mean(dl), 3) if dl else None,
                    "giri": len(dl),
                    "causa_frequente": max(set(cause[cu["n"]]), key=cause[cu["n"]].count) if cause[cu["n"]] else None,
                })
            peggiori = sorted((c for c in curve if c["perdita_media_s"]), key=lambda c: -c["perdita_media_s"])[:3]
            out["guida"] = {"curve": curve, "dove_perdi": peggiori}
        # assetto
        if self.imp["assetto"] and idx is not None:
            puliti = [c for m, c in self.giri if m["valido"] and not m.get("box") and not m.get("safety_car")]
            s = st.get(P.SETUPS)
            setup = A.leggi_assetto(s.cars[idx]) if s is not None else None
            out["assetto"] = A.analizza(puliti[-10:], setup, self._usura_per_giro(), self._speed_trap(st, idx),
                                        st.in_gara())
        # strategia
        if st.in_gara() and ses is not None:
            perdita, misurata = self.strategia.piste.perdita_box(ses.track_id)
            deg = self.strategia.degrado(idx, ultimo_stint=False) if idx is not None else None
            out["strategia"] = {"perdita_box_s": perdita, "misurata": misurata,
                                "misure_in_questa_gara": self.strategia.misure,
                                "degrado_s_per_giro": round(deg, 3) if deg is not None else None}
        # ali mobili
        if st.formato == 2026:
            giri_ali = []
            for meta, c in self.giri:
                disp = usate = 0
                for i in range(1, len(c["d"])):
                    if c["aa"][i] and c["d"][i] is not None and c["d"][i - 1] is not None:
                        passo = max(0.0, c["d"][i] - c["d"][i - 1])
                        disp += passo
                        if c["am"][i] == 1:
                            usate += passo
                if disp > 0:
                    giri_ali.append({"giro": meta.get("giro"), "metri_disponibili": round(disp),
                                     "uso_percento": round(100 * usate / disp)})
            if giri_ali or (ses and ses.num_active_aero_zones_full):
                out["ali"] = {"zone_complete": ses.num_active_aero_zones_full if ses else None,
                              "zone_ridotte": ses.num_active_aero_zones_partial if ses else None,
                              "avvisi": self.ali_avvisi, "giri": giri_ali}
        return out

    def _usura_per_giro(self):
        incrementi = [[], [], [], []]
        for (g0, w0, b0), (g1, w1, b1) in zip(self.usure, self.usure[1:]):
            if b0 or b1 or g1 != g0 + 1:
                continue
            for k in range(4):
                diff = w1[k] - w0[k]
                if 0 <= diff < 15:
                    incrementi[k].append(diff)
        if not all(incrementi):
            return None
        return [statistics.median(x) for x in incrementi]

    def _speed_trap(self, st, idx):
        lap = st.get(P.LAP)
        if lap is None or idx is None:
            return None
        mio = lap.cars[idx].speed_trap_fastest_speed
        altri = [lap.cars[i].speed_trap_fastest_speed for i in range(min(st.n_auto or 0, len(lap.cars)))
                 if i != idx and lap.cars[i].speed_trap_fastest_speed > 50]
        if mio <= 50 or len(altri) < 3:
            return None
        return mio, statistics.median(altri)
