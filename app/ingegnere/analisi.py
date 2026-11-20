"""Fase 2 e 3: tracce dei giri, consigli di guida in diretta (come migliorare in ogni curva),
strategia (undercut/overcut), ali mobili 2026, freni caldi, giro lanciato in qualifica, e i pezzi
del riassunto (guida, assetto, strategia, ali).

Una Analisi per sessione, per l'auto del giocatore (player_car_index).
"""

import statistics

from . import assetto as A
from . import curve as C
from . import numeri_curve as N
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
        self.numerazione = "nostra"
        # una curva alla volta (prove libere)
        self.fuoco = None          # {"nome", "apice", "perdita", "giri"}
        self.sistemate = set()
        self.ultime_perdite = {}   # nome -> (delta, consiglio) dell'ultimo passaggio
        # freni caldi
        self.ora = 0.0             # orologio di gioco che non torna indietro con i flashback
        self._t_prec = None
        self.freni = None          # {"ora", "max"} dell'ultimo avviso
        self.freni_curve = {}      # nome della curva -> giri con i freni sopra soglia lì
        self._freni_giro = set()

    def _puo(self, chiave, attesa, t):
        """Attesa prima di ripetere, sull'orologio che non torna indietro con i flashback
        (`self.ora`): prima un flashback faceva ridire subito le stesse cose."""
        u = self.ultimo.get(chiave)
        if u is not None and self.ora - u < attesa:
            return False
        self.ultimo[chiave] = self.ora
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
            self._imposta_rif(meta, finito.c, ses.track_length)

    def _imposta_rif(self, meta, c, lunghezza=None):
        self.rif = (meta, c)
        self.curve = C.trova_curve(c)
        if lunghezza is None:
            lunghezza = max((d for d in c["d"] if d is not None), default=0)
        self.numerazione = N.assegna(self.curve, meta.get("pista"), lunghezza, c)
        self.rif_misure = {cu["n"]: C.misura(c, cu) for cu in self.curve}
        if self.fuoco is not None:        # la curva su cui si lavora resta la stessa
            cu = self._curva_vicina(self.fuoco["apice"])
            if cu is not None:
                self.fuoco["nome"] = cu["nome"]

    def _curva_vicina(self, d, entro=150):
        if not self.curve:
            return None
        cu = min(self.curve, key=lambda x: abs(x["apice"] - d))
        return cu if abs(cu["apice"] - d) <= entro else None

    def curva_del_tratto(self, d):
        """La curva in cui si trova la distanza d (dall'inizio della frenata all'uscita)."""
        for cu in self.curve:
            if cu["inizio"] - 50 <= d <= cu["fine"]:
                return cu
        return None

    def rif_da_biblioteca(self, st):
        """Prima del primo giro pulito: il giro migliore salvato su questa pista, di chi guida."""
        ses = st.sessione()
        if self.rif is not None or ses is None:
            return
        m = self.bib.migliore(ses.track_id, self.imp["pilota"])
        if m:
            g = self.bib.leggi(ses.track_id, m["id"])
            if g:
                self._imposta_rif(dict(g["meta"], da_biblioteca=True), g["c"], ses.track_length)

    # ---------- ogni 0,2 s ----------
    def valuta(self, st, nuove_soste):
        idx = st.indice()
        ses = st.sessione()
        lap = st.auto(P.LAP, idx)
        if idx is None or ses is None or lap is None or ses.game_paused or lap.driver_status == 0:
            return []
        t = st.tempo()
        if self._t_prec is not None and 0 < t - self._t_prec < 2:
            self.ora += t - self._t_prec
        self._t_prec = t
        out = []
        if lap.current_lap_num != self.giro_corrente:
            self.giro_corrente = lap.current_lap_num
            self.valutate = set()
            self.dette_giro = 0
            self._freni_giro = set()
        if self.rif is None and lap.current_lap_num <= 2:
            self.rif_da_biblioteca(st)
        self._guida(out, t, st, ses, lap)
        self._freni(out, t, st, lap, idx)
        if st.in_gara():
            self._strategia(out, t, st, ses, lap, idx, nuove_soste)
        if st.formato == 2026:
            self._ali(out, t, st, ses, lap, idx)
        return out

    def _guida(self, out, t, st, ses, lap):
        """Dopo ogni curva, sul rettilineo: che cosa fare per non perdere tempo lì, con il dato.
        Stesse soglie di prima: perdita ≥ 0,15 s con una causa, massimo 2 a giro, non in pit,
        safety car o primo giro di gara. In prova (impostazione «una curva alla volta») si parla
        di una curva sola, la peggiore, finché migliora; poi si passa alla successiva."""
        g = self.trac.giro
        if not self.curve or g is None or lap.pit_status or ses.safety_car_status in (1, 2):
            return
        if st.in_gara() and lap.current_lap_num <= 1:
            return
        fuoco_acceso = self.imp["una_curva_alla_volta"] and st.tipo_sessione() in P.SESSIONE_PROVE
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
            k, come = C.consiglio(m, r)
            self.ultime_perdite[cu["nome"]] = (delta, come, cu["apice"])
            if fuoco_acceso:
                self._fuoco(out, t, cu, delta, k, come)
                continue
            if delta < 0.15 or self.dette_giro >= 2:
                continue
            if not k or not self._puo(f"curva{cu['nome']}", 120, t):
                continue
            self.dette_giro += 1
            out.append(Messaggio("guida", f"curva{cu['nome']}",
                                 f"{N.etichetta(cu)}, {come}. Perdi {C.decimi(delta)}.",
                                 livello=2, ttl=6, creato=t))

    def _prossima(self, esclusa):
        """La curva peggiore dell'ultimo giro (con un consiglio), tra quelle non ancora sistemate."""
        cand = [(dl, nome, ap) for nome, (dl, come, ap) in self.ultime_perdite.items()
                if nome != esclusa and nome not in self.sistemate and come and dl >= 0.15]
        if not cand:
            return None
        dl, nome, ap = max(cand)
        return {"nome": nome, "apice": ap, "perdita": dl, "giri": 0}

    def _fuoco(self, out, t, cu, delta, k, come):
        f = self.fuoco
        if f is None:
            # si sceglie dopo un giro intero misurato: la peggiore
            if len(self.ultime_perdite) < len(self.curve):
                return
            self.fuoco = f = self._prossima(None)
            if f is None:
                return
            if cu["nome"] != f["nome"]:
                c2 = next((x for x in self.curve if x["nome"] == f["nome"]), None)
                testo = (f"Lavoriamo su una curva alla volta. Cominciamo {N.etichetta(c2, False, 'da')}: "
                         f"lì perdi {C.decimi(f['perdita'])}.") if c2 else None
                if testo and self.dette_giro < 2:
                    self.dette_giro += 1
                    out.append(Messaggio("guida", "fuoco", testo, livello=2, ttl=8, creato=t))
                return
        if cu["nome"] != f["nome"]:
            return
        f["giri"] += 1
        migliorata = delta < max(0.1, 0.4 * f["perdita"])
        if migliorata or f["giri"] >= 6:
            self.sistemate.add(f["nome"])
            dopo = self._prossima(f["nome"])
            if migliorata:
                testo = f"{N.etichetta(cu)} meglio: adesso perdi solo {C.decimi(max(delta, 0))}."
            else:
                testo = f"Lasciamo {N.etichetta(cu, False, 'la')} per ora."
            if dopo is not None:
                c2 = next((x for x in self.curve if x["nome"] == dopo["nome"]), None)
                if c2 is not None:
                    testo += f" Passiamo {N.etichetta(c2, False, 'a')}: lì perdi {C.decimi(dopo['perdita'])}."
            self.fuoco = dopo
            out.append(Messaggio("guida", "fuoco", testo, livello=2, ttl=8, creato=t))
            return
        if delta >= 0.15 and k:
            out.append(Messaggio("guida", "fuoco", f"{N.etichetta(cu)}, {come}. Perdi {C.decimi(delta)}.",
                                 livello=2, ttl=8, creato=t))

    def _freni(self, out, t, st, lap, idx):
        """Freni caldi: si dice una volta; poi solo se peggiorano (50 °C in più) o dopo 10 minuti
        di gioco (che non tornano indietro con i flashback), e allora con la causa se c'è."""
        tel = st.auto(P.TELEMETRY, idx)
        if tel is None or lap.current_lap_num < 2 or lap.pit_status or tel.speed <= 80:
            return
        bt = list(tel.brakes_temperature)
        caldo = max(bt)
        if caldo < 1050:
            return
        cu = self.curva_del_tratto(lap.lap_distance)
        if cu is not None and cu["nome"] not in self._freni_giro:
            self._freni_giro.add(cu["nome"])
            self.freni_curve[cu["nome"]] = self.freni_curve.get(cu["nome"], 0) + 1
        f = self.freni
        if f is None:
            self.freni = {"ora": self.ora, "max": caldo}
            out.append(Messaggio("gomme", "freni", "Freni caldi. Gestisci in frenata.",
                                 livello=2, ttl=10, fisso=True, creato=t))
            return
        peggio = caldo >= f["max"] + 50
        if not peggio and self.ora - f["ora"] < 600:
            return
        self.freni = {"ora": self.ora, "max": max(caldo, f["max"] if peggio else 0)}
        davanti = (bt[2] + bt[3]) / 2 - (bt[0] + bt[1]) / 2
        dove = " davanti" if davanti >= 100 else (" dietro" if davanti <= -100 else "")
        testo = f"Freni{dove} {'sempre più' if peggio else 'ancora'} caldi, {int(round(caldo, -1))} gradi."
        if self.freni_curve:
            nome, volte = max(self.freni_curve.items(), key=lambda x: x[1])
            c2 = next((x for x in self.curve if x["nome"] == nome), None)
            if volte >= 2 and c2 is not None:
                testo += f" Soprattutto {N.etichetta(c2, False, 'a')}."
        testo += " Alza il piede un attimo prima di frenare."
        out.append(Messaggio("gomme", "freni", testo, livello=2, ttl=10, creato=t))

    # ---------- giro lanciato in qualifica ----------
    def giro_lanciato(self, st):
        """Vero durante un giro lanciato in qualifica (non out-lap, non in-lap): driver_status 1
        della specifica («flying lap»), fuori dai box, giro ancora valido."""
        if not self.imp["silenzio_qualifica"] or st.tipo_sessione() not in P.SESSIONE_QUALIFICA:
            return False
        lap = st.auto(P.LAP, st.indice())
        ses = st.sessione()
        if lap is None or ses is None or ses.game_paused:
            return False
        return lap.driver_status == 1 and not lap.pit_status and not lap.current_lap_invalid

    # ---------- strategia: pezzi usati anche dalle domande ----------
    def stima_undercut(self, st, idx):
        """(nome di chi è davanti, vantaggio stimato in s, distacco) o None."""
        lap = st.auto(P.LAP, idx)
        sta_all = st.get(P.STATUS)
        if lap is None or sta_all is None or lap.car_position <= 1:
            return None
        davanti_i = st.auto_in_posizione(lap.car_position - 1)
        davanti_g = st.distacco_davanti(idx)
        deg = self.strategia.degrado(idx)
        if davanti_i is None or davanti_g is None or davanti_g >= 3.5 or not deg:
            return None
        sua_eta = sta_all.cars[davanti_i].tyres_age_laps
        return st.nome(davanti_i), deg * sua_eta - 0.8, davanti_g

    def frase_rientro(self, st, r):
        testo = f"Se rientri adesso esci {pos(r['posizione'])}"
        if r["davanti_a"] is not None and r["margine_dietro"] is not None:
            if r["margine_dietro"] < 1.0:
                testo += f", con {st.nome(r['davanti_a'])} attaccato dietro"
            else:
                testo += f", davanti a {st.nome(r['davanti_a'])} di {dec(r['margine_dietro'])}"
        if r["dietro_a"] is not None and r["margine_davanti"] is not None and r["margine_davanti"] < 1.0:
            testo += f", subito dietro a {st.nome(r['dietro_a'])}"
        return testo + ("." if r["misurata"] else ". Tempo del box stimato.")

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
            testo = self.frase_rientro(st, r)
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
            consigli = {cu["n"]: [] for cu in self.curve}
            for meta, c in self.giri:
                if meta.get("box") or meta.get("safety_car") or meta.get("id") == rm.get("id") \
                        or meta.get("giro") == rm.get("giro") and not rm.get("da_biblioteca"):
                    continue
                for x in C.confronta(c, rc, self.curve):
                    if x["delta"] is not None:
                        per_curva[x["curva"]].append(x["delta"])
                        if x["causa"]:
                            cause[x["curva"]].append(x["frase"])
                        if x["consiglio"]:
                            consigli[x["curva"]].append((x["causa"], x["consiglio"]))
            for cu in self.curve:
                r = self.rif_misure.get(cu["n"], {})
                dl = per_curva[cu["n"]]
                cc = consigli[cu["n"]]
                kk = max(set(k for k, _ in cc), key=[k for k, _ in cc].count) if cc else None
                curve.append({
                    "curva": cu["nome"], "n": cu["n"], "apice_m": round(cu["apice"]), "vmin_rif": r.get("vmin"),
                    "frenata_rif_m": round(r["frenata"]) if r.get("frenata") is not None else None,
                    "gas_rif_m": round(r["gas"]) if r.get("gas") is not None else None,
                    "perdita_media_s": round(statistics.mean(dl), 3) if dl else None,
                    "giri": len(dl),
                    "causa_frequente": max(set(cause[cu["n"]]), key=cause[cu["n"]].count) if cause[cu["n"]] else None,
                    "consiglio": next((f for k, f in reversed(cc) if k == kk), None),
                })
            peggiori = sorted((c for c in curve if c["perdita_media_s"]), key=lambda c: -c["perdita_media_s"])[:3]
            out["guida"] = {"curve": curve, "dove_perdi": peggiori, "numerazione": self.numerazione,
                            "sistemate": sorted(self.sistemate)}
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
