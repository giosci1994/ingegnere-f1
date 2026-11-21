"""Fase 2 e 3: tracce dei giri, consigli di guida in diretta (come migliorare in ogni curva),
strategia (undercut/overcut), ali mobili 2026, freni caldi, giro lanciato in qualifica, e i pezzi
del riassunto (guida, assetto, strategia, ali).

Una Analisi per sessione, per l'auto del giocatore (player_car_index).
"""

from bisect import bisect_left
import statistics

from . import assetto as A
from . import curve as C
from . import gara as G
from . import numeri_curve as N
from . import pacchetti as P
from .ingegnere import Messaggio, dec, pct, pos
from .pregara import StaccoPartenza
from .riassunto import fmt
from .riferimento import RiferimentoEsterno
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
        # fase 5 (gara.py)
        self.settore_prec = None
        self.settori_migliori = {}  # 1, 2 -> secondi (giri validi della sessione)
        self.benzina = []          # (giro finito, kg nel serbatoio)
        self.sc_prec = 0
        self.mescola_detta = -1    # numero di soste quando si è detto il set per la sosta
        # fase 6 (blocco 1)
        self._rif_d = []
        self._rif_t = []
        self.consigli_sessione = 0
        self.soste_coperte = {}
        self.blocchi_av_t = []
        self.blocchi_post_t = []
        self._blocco_av = False
        self._blocco_post = False
        self._bias_sbil_dal = None
        self._bias_consigliato = None
        self.gomme_calde_dal = None
        self.gomme_curve = {}
        self._gomme_giro = set()
        self._blister_max = 0
        self.settori_auto = {}
        self.settori_giro_car = {}
        self.settore_gara_prec = None
        self.ultimo_target_lap = None
        # fase 6 (blocco 2)
        self.rif_ext = RiferimentoEsterno()
        self.stacco = StaccoPartenza()
        self.piano_attivo = "A"
        self.piani_gara = None
        self._box_chiamato = None
        self._box_giro_stint = -1
        self._sc_soppresso = None

    def _puo(self, chiave, attesa, t):
        """Attesa prima di ripetere, sull'orologio che non torna indietro con i flashback
        (`self.ora`): prima un flashback faceva ridire subito le stesse cose."""
        u = self.ultimo.get(chiave)
        if u is not None and self.ora - u < attesa:
            return False
        self.ultimo[chiave] = self.ora
        return True

    # ---------- a ogni pacchetto di telemetria ----------
    def _rileva_bloccaggi(self, st, idx):
        lap = st.auto(P.LAP, idx)
        tel = st.auto(P.TELEMETRY, idx)
        mex = st.get(P.MOTIONEX)
        if lap is None or tel is None or mex is None or lap.driver_status == 0 or lap.pit_status \
                or tel.brake <= 0.2 or tel.speed <= 60:
            self._blocco_av = self._blocco_post = False
            return
        s = mex.wheel_slip_ratio
        av = min(s[2], s[3]) < -0.2
        post = min(s[0], s[1]) < -0.25
        if av and not self._blocco_av:
            if not self.blocchi_av_t or self.ora - self.blocchi_av_t[-1] >= 2.0:
                self.blocchi_av_t.append(self.ora)
        self._blocco_av = av
        if post and not self._blocco_post:
            if not self.blocchi_post_t or self.ora - self.blocchi_post_t[-1] >= 2.0:
                self.blocchi_post_t.append(self.ora)
        self._blocco_post = post

    def evento(self, st, pk):
        self.stacco.evento(st, pk)

    def campione(self, st):
        idx = st.indice()
        if idx is None:
            return
        self._rileva_bloccaggi(st, idx)
        self.stacco.campione(st, idx)
        self.rif_ext.campione(st, idx)
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
        idx_v = C._validi(c)
        self._rif_d = [c["d"][i] for i in idx_v]
        self._rif_t = [c["t"][i] for i in idx_v]
        self.curve = C.trova_curve(c)
        if lunghezza is None:
            lunghezza = max((d for d in c["d"] if d is not None), default=0)
        self.numerazione = N.assegna(self.curve, meta.get("pista"), lunghezza, c)
        self.rif_misure = {cu["n"]: C.misura(c, cu) for cu in self.curve}
        if self.fuoco is not None:        # la curva su cui si lavora resta la stessa
            cu = self._curva_vicina(self.fuoco["apice"])
            if cu is not None:
                self.fuoco["nome"] = cu["nome"]

    def delta_live(self, st):
        """Delta istantaneo (secondi, < 0 = più veloce del riferimento) rispetto a `self.rif`."""
        idx = st.indice()
        lap = st.auto(P.LAP, idx)
        if not self._rif_d or lap is None or lap.driver_status == 0 or lap.pit_status:
            return None
        d = lap.lap_distance
        if d < self._rif_d[0] or d > self._rif_d[-1]:
            return None
        t_cur = lap.current_lap_time_in_ms / 1000.0
        if t_cur <= 0:
            return None
        k = bisect_left(self._rif_d, d)
        if k <= 0:
            t_rif = self._rif_t[0]
        elif k >= len(self._rif_d):
            t_rif = self._rif_t[-1]
        else:
            d0, d1 = self._rif_d[k - 1], self._rif_d[k]
            t0, t1 = self._rif_t[k - 1], self._rif_t[k]
            t_rif = t1 if d1 == d0 else t0 + (t1 - t0) * (d - d0) / (d1 - d0)
        return round(t_cur - t_rif, 2)

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
        if idx is None or ses is None or lap is None or ses.game_paused:
            return []
        t = st.tempo()
        if lap.driver_status == 0:
            if st.in_gara():
                G.aggiorna_piani(self, [], t, st, ses, lap, idx, [])
            return []
        if self._t_prec is not None and 0 < t - self._t_prec < 2:
            self.ora += t - self._t_prec
        self._t_prec = t
        out = []
        giro_finito = self.giro_corrente is not None and lap.current_lap_num == self.giro_corrente + 1
        if giro_finito:
            sta = st.auto(P.STATUS, idx)
            if sta is not None:
                self.benzina.append((self.giro_corrente, sta.fuel_in_tank))
                self.benzina = self.benzina[-40:]
        if lap.current_lap_num != self.giro_corrente:
            self.giro_corrente = lap.current_lap_num
            self.valutate = set()
            self.dette_giro = 0
            self._freni_giro = set()
            self._gomme_giro = set()
        if self.rif is None and lap.current_lap_num <= 2:
            self.rif_da_biblioteca(st)
        self._rileva_bloccaggi(st, idx)
        if st.in_gara():
            G.aggiorna_settori_auto(self, st)
        self._guida(out, t, st, ses, lap)
        self._freni(out, t, st, lap, idx)
        self._gomme_calde(out, t, st, lap, idx)
        self._brake_bias(out, t, st, lap, idx)
        G.settori(self, out, t, st, ses, lap)
        if st.in_gara():
            self._strategia(out, t, st, ses, lap, idx, nuove_soste)
            G.aggiorna_piani(self, out, t, st, ses, lap, idx, nuove_soste)
            G.box_sc(self, out, t, st, ses, lap, idx)
            G.mescola(self, out, t, st, ses, lap, idx)
            G.passo(self, out, t, st, ses, lap, idx, giro_finito)
            G.settori_avversari(self, out, t, st, ses, lap, idx, giro_finito)
            G.target_lap_avviso(self, out, t, st, ses, lap, idx, giro_finito)
            G.previsioni(self, out, t, st, ses, lap, idx, giro_finito)
        if st.formato == 2026:
            self._ali(out, t, st, ses, lap, idx)
        return out

    def _guida(self, out, t, st, ses, lap):
        """Dopo ogni curva, sul rettilineo: che cosa fare per non perdere tempo lì, con il dato.
        Stesse soglie di prima: perdita ≥ 0,15 s con una causa, massimo 2 a giro, non in pit,
        safety car o primo giro di gara. In prova (impostazione «una curva alla volta») si parla
        di una curva sola, la peggiore, finché migliora; poi si passa alla successiva. Se c'è un
        compagno di squadra o riferimento più veloce, integra con il confronto curva per curva."""
        g = self.trac.giro
        if g is None or lap.pit_status or ses.safety_car_status in (1, 2):
            return
        if st.in_gara() and lap.current_lap_num <= 1:
            return
        idx = st.indice()
        mio_best = self.rif[0]["tempo_ms"] if self.rif is not None else None
        rif_ext = self.rif_ext.seleziona(st, idx, mio_best)
        curve_eff = self.curve
        if not curve_eff and rif_ext is not None:
            curve_eff, _ = self.rif_ext.curve_per_confronto(st, self.curve, self.numerazione, rif_ext)
        if not curve_eff:
            return
        fuoco_acceso = self.imp["una_curva_alla_volta"] and st.tipo_sessione() in P.SESSIONE_PROVE
        cap = self.imp.get("max_consigli_guida", 12)
        d = lap.lap_distance
        for cu in curve_eff:
            if cu["n"] in self.valutate or d < cu["fine"] + 60:
                continue
            self.valutate.add(cu["n"])
            if d > cu["fine"] + 600:          # siamo partiti a metà giro: niente confronto
                continue
            m = C.misura(g.c, cu)
            emesso_qui = False
            if self.rif is not None:
                r = self.rif_misure.get(cu["n"])
                if r and m.get("tempo") is not None and r.get("tempo") is not None:
                    delta = m["tempo"] - r["tempo"]
                    k, come = C.consiglio(m, r)
                    self.ultime_perdite[cu["nome"]] = (delta, come, cu["apice"])
                    if cap <= 0 or self.consigli_sessione < cap:
                        if fuoco_acceso:
                            self._fuoco(out, t, cu, delta, k, come)
                            emesso_qui = True
                        elif delta >= 0.15 and self.dette_giro < 2 and k and self._puo(f"curva{cu['nome']}", 120, t):
                            self.dette_giro += 1
                            self.consigli_sessione += 1
                            out.append(Messaggio("guida", f"curva{cu['nome']}",
                                                 f"{N.etichetta(cu)}, {come}. Perdi {C.decimi(delta)}.",
                                                 livello=2, ttl=6, creato=t))
                            emesso_qui = True
            if not emesso_qui and not fuoco_acceso and rif_ext is not None \
                    and self.dette_giro < 2 and (cap <= 0 or self.consigli_sessione < cap):
                frase_ext, _ = self.rif_ext.consiglio_curva(m, cu, rif_ext, curve_eff)
                if frase_ext and self._puo(f"confronto_ext{cu['nome']}", 150, t):
                    self.dette_giro += 1
                    self.consigli_sessione += 1
                    out.append(Messaggio("guida", f"confronto_ext{cu['nome']}", frase_ext,
                                         livello=2, ttl=8, creato=t))

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
                    self.consigli_sessione += 1
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
            self.consigli_sessione += 1
            out.append(Messaggio("guida", "fuoco", testo, livello=2, ttl=8, creato=t))
            return
        if delta >= 0.15 and k:
            self.consigli_sessione += 1
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

    def _frase_curve(self, conteggi, min_volte=2, attuale=None):
        """Le 1–2 curve dove un problema si ripete di più (o la curva corrente)."""
        top = [n for n, v in sorted(conteggi.items(), key=lambda x: -x[1]) if v >= min_volte][:2]
        c_list = [next((x for x in self.curve if x["nome"] == n), None) for n in top]
        c_list = [c for c in c_list if c is not None]
        if not c_list and attuale is not None:
            c_list = [attuale]
        if not c_list:
            return ""
        if len(c_list) == 1:
            return f" Soprattutto {N.etichetta(c_list[0], False, 'a')}."
        return f" Soprattutto {N.etichetta(c_list[0], False, 'a')} e {N.etichetta(c_list[1], False, 'a')}."

    def _gomme_calde(self, out, t, st, lap, idx):
        """Temperature gomme (superficie e carcassa) persistenti e blistering, con le curve."""
        tel = st.auto(P.TELEMETRY, idx)
        dmg = st.auto(P.DAMAGE, idx)
        mex = st.get(P.MOTIONEX)
        if lap.current_lap_num >= 2 and not lap.pit_status and tel is not None and tel.speed > 80:
            ts = list(tel.tyres_surface_temperature)
            ti = list(tel.tyres_inner_temperature)
            max_ts, max_ti = max(ts), max(ti)
            slip = max((abs(x) for x in mex.wheel_slip_ratio), default=0) if mex is not None else 0
            cu = self.curva_del_tratto(lap.lap_distance)
            if max_ts >= 115 or max_ti >= 110 or slip >= 0.25:
                if cu is not None and cu["nome"] not in self._gomme_giro:
                    self._gomme_giro.add(cu["nome"])
                    self.gomme_curve[cu["nome"]] = self.gomme_curve.get(cu["nome"], 0) + 1
            if max_ts >= 115 or max_ti >= 110:
                if self.gomme_calde_dal is None:
                    self.gomme_calde_dal = self.ora
                if self.ora - self.gomme_calde_dal >= 3.0 and self._puo("gomme_calde", 150, t):
                    if max_ti >= 110:
                        i_hot, tval, dove_t = ti.index(max_ti), max_ti, "carcassa"
                    else:
                        i_hot, tval, dove_t = ts.index(max_ts), max_ts, "superficie"
                    extra_cu = self._frase_curve(self.gomme_curve, attuale=cu)
                    out.append(Messaggio(
                        "gomme", "gomme_calde",
                        f"Gomme surriscaldate, {dove_t} {P.RUOTE[i_hot]} a {tval} gradi.{extra_cu} Gestisci.",
                        livello=2, ttl=12, creato=t))
            else:
                self.gomme_calde_dal = None
        else:
            self.gomme_calde_dal = None
        if dmg is not None:
            mb = max(dmg.tyre_blisters)
            if mb < 5:
                self._blister_max = 0
            elif mb >= 20 and (self._blister_max < 20 or mb >= self._blister_max + 20) \
                    and self._puo("blister", 240, t):
                self._blister_max = mb
                i_b = list(dmg.tyre_blisters).index(mb)
                extra_cu = self._frase_curve(self.gomme_curve, min_volte=1)
                out.append(Messaggio(
                    "gomme", "blister",
                    f"Blistering sulla {P.RUOTE[i_b]}, {pct(mb)}.{extra_cu} Gestisci le gomme.",
                    livello=2, ttl=15, creato=t))

    def _brake_bias(self, out, t, st, lap, idx):
        """Consiglia di spostare il brake bias indietro/avanti per bloccaggi ripetuti o sbilanciamento."""
        tel = st.auto(P.TELEMETRY, idx)
        sta = st.auto(P.STATUS, idx)
        dmg = st.auto(P.DAMAGE, idx)
        if lap.current_lap_num < 2 or lap.pit_status or tel is None or sta is None \
                or tel.speed <= 80 or sta.front_brake_bias <= 0:
            self._bias_sbil_dal = None
            return
        bias = sta.front_brake_bias
        self.blocchi_av_t = [x for x in self.blocchi_av_t if self.ora - x <= 120]
        self.blocchi_post_t = [x for x in self.blocchi_post_t if self.ora - x <= 120]
        if len(self.blocchi_av_t) >= 2 and bias > 45 and self._puo("brake_bias", 240, t):
            self.blocchi_av_t.clear()
            out.append(Messaggio(
                "gomme", "brake_bias",
                f"Bloccaggi ripetuti davanti: sposta il brake bias indietro di 1 o 2 punti, verso {max(40, bias - 2)}.",
                livello=2, ttl=12, creato=t))
            return
        if len(self.blocchi_post_t) >= 2 and bias < 68 and self._puo("brake_bias", 240, t):
            self.blocchi_post_t.clear()
            out.append(Messaggio(
                "gomme", "brake_bias",
                f"Bloccaggi dietro: sposta il brake bias avanti di 1 o 2 punti, verso {min(70, bias + 2)}.",
                livello=2, ttl=12, creato=t))
            return
        bt = list(tel.brakes_temperature)
        ti = list(tel.tyres_inner_temperature)
        b_ant, b_post = (bt[2] + bt[3]) / 2, (bt[0] + bt[1]) / 2
        t_ant, t_post = (ti[2] + ti[3]) / 2, (ti[0] + ti[1]) / 2
        w = list(dmg.tyres_wear) if dmg is not None else None
        w_ant, w_post, w_max = ((w[2] + w[3]) / 2, (w[0] + w[1]) / 2, max(w)) if w else (0, 0, 0)
        davanti_peso = (b_ant - b_post >= 200 and max(bt) >= 850) or (t_ant - t_post >= 14 and max(ti) >= 105) \
            or (w_max >= 25 and w_ant - w_post >= 12)
        dietro_peso = (b_post - b_ant >= 200 and max(bt) >= 850) or (t_post - t_ant >= 14 and max(ti) >= 105) \
            or (w_max >= 25 and w_post - w_ant >= 12)
        if davanti_peso and not dietro_peso and bias > 45 and self._bias_consigliato != ("av", bias):
            if not self._bias_sbil_dal or self._bias_sbil_dal[0] != "av":
                self._bias_sbil_dal = ("av", self.ora)
            elif self.ora - self._bias_sbil_dal[1] >= 4.0 and self._puo("brake_bias", 360, t):
                self._bias_consigliato = ("av", bias)
                out.append(Messaggio(
                    "gomme", "brake_bias",
                    f"Anteriore più sollecitato del posteriore: sposta il brake bias indietro di 1 o 2 punti, verso {max(40, bias - 2)}.",
                    livello=2, ttl=12, creato=t))
        elif dietro_peso and not davanti_peso and bias < 68 and self._bias_consigliato != ("post", bias):
            if not self._bias_sbil_dal or self._bias_sbil_dal[0] != "post":
                self._bias_sbil_dal = ("post", self.ora)
            elif self.ora - self._bias_sbil_dal[1] >= 4.0 and self._puo("brake_bias", 360, t):
                self._bias_consigliato = ("post", bias)
                out.append(Messaggio(
                    "gomme", "brake_bias",
                    f"Posteriore più sollecitato dell'anteriore: sposta il brake bias avanti di 1 o 2 punti, verso {min(70, bias + 2)}.",
                    livello=2, ttl=12, creato=t))
        else:
            self._bias_sbil_dal = None

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
    def eta_gomme(self, st, j):
        """(età delle gomme di j in giri equivalenti, usura vera o None). Se il gioco manda l'usura
        di j (offline sì), l'età si ricava dall'usura e dal tuo consumo per giro; se no, l'età vera
        del set (come prima della 0.5.0)."""
        sta_all = st.get(P.STATUS)
        eta = sta_all.cars[j].tyres_age_laps if sta_all is not None else 0
        usura = G.usura_altro(st, j)
        mio = self._usura_per_giro()
        if usura is None or not mio or max(mio) <= 0.2:
            return eta, None
        return usura / max(mio), usura

    def stima_undercut(self, st, idx):
        """(nome di chi è davanti, vantaggio stimato in s, distacco, usura sua o None) o None."""
        lap = st.auto(P.LAP, idx)
        sta_all = st.get(P.STATUS)
        if lap is None or sta_all is None or lap.car_position <= 1:
            return None
        davanti_i = st.auto_in_posizione(lap.car_position - 1)
        davanti_g = st.distacco_davanti(idx)
        deg = self.strategia.degrado(idx)
        if davanti_i is None or davanti_g is None or davanti_g >= 3.5 or not deg:
            return None
        eta, usura = self.eta_gomme(st, davanti_i)
        return st.nome(davanti_i), deg * eta - 0.8, davanti_g, usura

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
        ch = self._box_chiamato
        box_pioggia = ch is not None and ch.get("giro") == n and ch.get("motivo") == "pioggia"
        for i in nuove_soste:
            if i == idx or sosta_recente or mancano <= 3 or box_pioggia:
                continue
            if i == davanti_i and davanti_g is not None and davanti_g < 4:
                if self._puo(f"overcut{i}", 60, t):
                    self.soste_coperte[i] = self.ora
                    out.append(Messaggio("strategia", "sosta_altri",
                                         f"{st.nome(i)} si è fermato. Spingi due giri, proviamo l'overcut.",
                                         priorita=2, livello=1, ttl=15, creato=t))
            elif i == dietro_i and dietro_g is not None and dietro_g < 4:
                if not self._puo(f"copri{i}", 60, t):
                    continue
                self.soste_coperte[i] = self.ora
                if usura >= 60:
                    testo = f"{st.nome(i)} si è fermato. Copri l'undercut: box questo giro."
                    self._box_giro_stint = len(self.mie_soste)
                    self._box_chiamato = {"giro": n, "motivo": "copri", "bersaglio": i,
                                          "ora": self.ora, "piano": self.piano_attivo}
                else:
                    testo = f"{st.nome(i)} si è fermato. Spingi due giri, tieni il passo."
                out.append(Messaggio("strategia", "sosta_altri", testo, priorita=2, livello=1,
                                     ttl=15, creato=t))
        uscite = list(stg.uscite)
        stg.uscite.clear()
        lap_all = st.get(P.LAP)
        if lap_all is not None:
            for i in uscite:
                if i == idx or mancano <= 2 or i >= len(lap_all.cars):
                    continue
                if i in self.soste_coperte and self.ora - self.soste_coperte[i] < 120:
                    continue
                c_alt = lap_all.cars[i]
                if c_alt.car_position > 3 and abs(c_alt.car_position - lap.car_position) > 5:
                    continue
                if self.ora - self.ultimo.get(f"uscita_altro_{i}", -1e9) < 90 \
                        or self.ora - self.ultimo.get("uscita_altro", -1e9) < 15:
                    continue
                self._puo(f"uscita_altro_{i}", 90, t)
                self._puo("uscita_altro", 15, t)
                gomma = G.NOMI_MESCOLA.get(sta_all.cars[i].visual_tyre_compound) if sta_all is not None else None
                testo = (f"{st.nome(i)} si è fermato, monta le {gomma}." if gomma
                         else f"{st.nome(i)} è uscito dai box.")
                out.append(Messaggio("strategia", "sosta_gomma", testo, priorita=3, livello=2, ttl=12, creato=t))
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
        if ses.safety_car_status == 0 and davanti_i is not None and davanti_g is not None and davanti_g < 3.5 \
                and deg and deg >= 0.04 and sta_all is not None:
            sua_eta, sua_usura = self.eta_gomme(st, davanti_i)
            if sua_eta >= mia_eta - 1 and sua_eta >= 5:
                guadagno = deg * sua_eta - 0.8
                if guadagno > davanti_g + 0.3 and (r["margine_dietro"] is None or r["margine_dietro"] >= 1.0) \
                        and not box_pioggia and self._puo("undercut", 150, t):
                    self.soste_coperte[davanti_i] = self.ora
                    self._box_giro_stint = len(self.mie_soste)
                    self._box_chiamato = {"giro": n, "motivo": "undercut", "bersaglio": davanti_i,
                                          "ora": self.ora, "piano": self.piano_attivo}
                    sue = f" Ha le gomme al {pct(sua_usura)}." if sua_usura is not None else ""
                    out.append(Messaggio(
                        "strategia", "undercut",
                        f"Box per undercut su {st.nome(davanti_i)}.{sue} Stimiamo {dec(guadagno)} secondi "
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
        # confronto con compagno di squadra o riferimento più veloce
        player_c = self.rif[1] if self.rif is not None else (self.giri[-1][1] if self.giri else None)
        mio_best = self.rif[0]["tempo_ms"] if self.rif is not None else None
        conf_ext = self.rif_ext.riassunto(st, idx, player_c, self.curve, self.numerazione, mio_best)
        if conf_ext is not None:
            out["confronto_riferimento"] = conf_ext
        # stacco partenza
        stacco = self.stacco.chiudi()
        if stacco is not None:
            out["stacco_partenza"] = stacco
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
                                "degrado_s_per_giro": round(deg, 3) if deg is not None else None,
                                "piano_attivo": self.piano_attivo}
            if self.piani_gara and self.piani_gara.get("piani"):
                out["strategia"]["piani"] = self.piani_gara["piani"]
            if self.ultimo_target_lap is not None:
                out["strategia"]["target_lap_ms"] = self.ultimo_target_lap["target_ms"]
                out["strategia"]["target_lap"] = fmt(self.ultimo_target_lap["target_ms"])
                out["strategia"]["target_lap_giro"] = self.ultimo_target_lap["ideale"]
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
