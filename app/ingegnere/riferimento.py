"""Confronto in memoria con il compagno di squadra o l'auto di riferimento più veloce.

Traccia i giri puliti delle altre auto (con telemetria visibile: offline tutte, online solo
se `your_telemetry` è pubblico) senza mai salvarli nella biblioteca del giocatore (`dati/giri/`).
"""

from . import curve as C
from . import numeri_curve as N
from . import pacchetti as P
from .riassunto import fmt


def _nuovo_giro(numero):
    return {
        "numero": numero,
        "invalido": False,
        "box": False,
        "sc": False,
        "chiuso": False,
        "c": {"t": [], "d": [], "v": [], "th": [], "br": [], "st": []},
    }


def _copertura(c, lunghezza):
    d = [x for x in c["d"] if x is not None and x >= 0]
    if not d or not lunghezza:
        return 0.0
    return min(1.0, (max(d) - min(d)) / lunghezza)


class RiferimentoEsterno:
    def __init__(self):
        self.reset()

    def reset(self):
        self.correnti = {}      # car_idx -> giro in corso
        self.migliori = {}      # car_idx -> {"tempo_ms", "giro", "c"}
        self._cache_curve = None
        self._cache_num = "nostra"
        self._cache_misure = {}  # (idx, tempo_ms, n_curve) -> {cu["n"]: misura}

    def campione(self, st, idx_giocatore):
        """Aggiorna le tracce in memoria delle auto attive con telemetria accessibile."""
        lap_all = st.get(P.LAP)
        tel_all = st.get(P.TELEMETRY)
        ses = st.sessione()
        if lap_all is None or tel_all is None or ses is None:
            return
        par = st.get(P.PARTICIPANTS)
        n_auto = min(st.n_auto or len(lap_all.cars), len(lap_all.cars), len(tel_all.cars))
        gara = st.in_gara()
        sc_ora = ses.safety_car_status in (1, 2)

        for j in range(n_auto):
            if j == idx_giocatore:
                continue
            if par is not None and j < len(par.cars):
                pc = par.cars[j]
                if not (pc.your_telemetry or pc.ai_controlled):
                    continue
            l = lap_all.cars[j]
            if l.driver_status == 0 or l.result_status in (0, 1, 4, 5, 6, 7):
                continue
            g = self.correnti.get(j)
            n = l.current_lap_num
            if l.result_status == 3:
                if g is not None and not g["chiuso"] and len(g["c"]["d"]) >= 50:
                    g["chiuso"] = True
                    self._chiudi_giro(j, g, l.last_lap_time_in_ms, ses.track_length, gara)
                continue
            if g is None or n != g["numero"]:
                if g is not None and n == g["numero"] + 1:
                    self._chiudi_giro(j, g, l.last_lap_time_in_ms, ses.track_length, gara)
                g = self.correnti[j] = _nuovo_giro(n)
            if l.result_status != 2:
                continue
            t_lap = l.current_lap_time_in_ms / 1000.0
            c = g["c"]
            if c["t"] and t_lap < c["t"][-1] - 0.5:
                while c["t"] and c["t"][-1] > t_lap:
                    for k in c:
                        c[k].pop()
            if l.current_lap_invalid:
                g["invalido"] = True
            if l.pit_status:
                g["box"] = True
            if sc_ora and t_lap > 3:
                g["sc"] = True
            tel = tel_all.cars[j]
            c["t"].append(round(t_lap, 3))
            c["d"].append(round(l.lap_distance, 1))
            c["v"].append(tel.speed)
            c["th"].append(round(tel.throttle, 2))
            c["br"].append(round(tel.brake, 2))
            c["st"].append(round(tel.steer, 3))

    def _chiudi_giro(self, j, g, tempo_ms, lunghezza, gara):
        if g["invalido"] or g["box"] or g["sc"]:
            return
        if gara and g["numero"] == 1:
            return
        if not tempo_ms or _copertura(g["c"], lunghezza) < 0.9:
            return
        v = g["c"]["v"]
        if len(v) < 50 or max(v) <= 100:
            return
        if max(g["c"]["br"]) <= 0.1 and max(g["c"]["th"]) <= 0.5:
            return
        prec = self.migliori.get(j)
        if prec is None or tempo_ms < prec["tempo_ms"]:
            self.migliori[j] = {"tempo_ms": tempo_ms, "giro": g["numero"], "c": g["c"]}

    def seleziona(self, st, idx_giocatore, mio_best_ms=None):
        """Sceglie il compagno di squadra se attivo e competitivo, altrimenti il riferimento più veloce."""
        if not self.migliori or idx_giocatore is None:
            return None
        par = st.get(P.PARTICIPANTS)
        lap_all = st.get(P.LAP)
        mio_team = par.cars[idx_giocatore].team_id if (par is not None and idx_giocatore < len(par.cars)) else None
        mio_pos = lap_all.cars[idx_giocatore].car_position if (lap_all is not None and idx_giocatore < len(lap_all.cars)) else 99

        def _attivo(j):
            if lap_all is None or j >= len(lap_all.cars):
                return True
            return lap_all.cars[j].result_status in (2, 3)

        def _pos(j):
            if lap_all is None or j >= len(lap_all.cars):
                return 99
            return lap_all.cars[j].car_position or 99

        attivi = [(self.migliori[j]["tempo_ms"], _pos(j), j)
                  for j in self.migliori if _attivo(j)]
        if not attivi:
            attivi = [(self.migliori[j]["tempo_ms"], _pos(j), j) for j in self.migliori]
        if not attivi:
            return None
        attivi.sort()
        veloce_ms, _, veloce_j = attivi[0]

        scelto_j = None
        tipo = "riferimento"
        if mio_team is not None and par is not None:
            compagni = [
                (self.migliori[j]["tempo_ms"], _pos(j), j)
                for j in self.migliori
                if j < len(par.cars) and par.cars[j].team_id == mio_team and _attivo(j)
            ]
            if compagni:
                compagni.sort()
                mate_ms, mate_pos, mate_j = compagni[0]
                if mio_best_ms:
                    ok_mate = mate_ms <= mio_best_ms * 1.005
                else:
                    ok_mate = mate_pos <= mio_pos or mate_ms <= veloce_ms * 1.015
                if ok_mate:
                    scelto_j, tipo = mate_j, "compagno"

        if scelto_j is None:
            scelto_j, tipo = veloce_j, "riferimento"

        dati = self.migliori[scelto_j]
        return {
            "idx": scelto_j,
            "tipo": tipo,
            "nome": st.nome(scelto_j),
            "nome_intero": st.nomi.get(scelto_j) or st.nome(scelto_j),
            "tempo_ms": dati["tempo_ms"],
            "giro": dati["giro"],
            "c": dati["c"],
        }

    def curve_per_confronto(self, st, curve_giocatore, numerazione_giocatore, rif_ext):
        """Usa le curve del giocatore se presenti, altrimenti le ricava dal riferimento esterno."""
        if curve_giocatore:
            return curve_giocatore, numerazione_giocatore
        key = (rif_ext["idx"], rif_ext["tempo_ms"])
        if self._cache_curve is not None and getattr(self, "_cache_ext_key", None) == key:
            return self._cache_curve, self._cache_num
        ses = st.sessione()
        cu = C.trova_curve(rif_ext["c"])
        lung = ses.track_length if ses and ses.track_length else max(
            (d for d in rif_ext["c"]["d"] if d is not None), default=0)
        num = N.assegna(cu, ses.track_id if ses else None, lung, rif_ext["c"])
        self._cache_curve = cu
        self._cache_num = num
        self._cache_ext_key = key
        return cu, num

    def misure_rif(self, rif_ext, curve):
        key = (rif_ext["idx"], rif_ext["tempo_ms"], len(curve))
        if key not in self._cache_misure:
            self._cache_misure[key] = {cu["n"]: C.misura(rif_ext["c"], cu) for cu in curve}
        return self._cache_misure[key]

    def consiglio_curva(self, m_giro, cu, rif_ext, curve):
        """Restituisce (frase, delta_s) se il giocatore perde >= 0,15 s rispetto al riferimento."""
        r_ext = self.misure_rif(rif_ext, curve).get(cu["n"])
        if not r_ext or m_giro.get("tempo") is None or r_ext.get("tempo") is None:
            return None, None
        delta = m_giro["tempo"] - r_ext["tempo"]
        if delta < 0.15:
            return None, delta
        chi = "il compagno" if rif_ext["tipo"] == "compagno" else rif_ext["nome"]
        dove = f"Alle curve {cu['nome']}" if " e " in str(cu["nome"]) else f"In curva {cu['nome']}"

        if m_giro.get("frenata") is not None and r_ext.get("frenata") is not None:
            diff = r_ext["frenata"] - m_giro["frenata"]
            if 12 <= diff <= 80:
                return f"{dove} {chi} frena {C._metri(diff)} metri più tardi, perdi {C.decimi(delta)}.", delta
        if m_giro.get("vmin") is not None and r_ext.get("vmin") is not None:
            dv = r_ext["vmin"] - m_giro["vmin"]
            if dv >= 5:
                k = int(round(dv))
                return (f"{dove} {chi} porta {k} chilometri orari in più a centro curva, "
                        f"perdi {C.decimi(delta)}."), delta
        if m_giro.get("gas") is not None and r_ext.get("gas") is not None:
            dg = m_giro["gas"] - r_ext["gas"]
            if 15 <= dg <= 120:
                return f"{dove} {chi} dà gas pieno {C._metri(dg)} metri prima in uscita, perdi {C.decimi(delta)}.", delta
        if delta >= 0.25:
            return f"{dove} {chi} è più veloce di {C.decimi(delta)}.", delta
        return None, delta

    def riassunto(self, st, idx, player_c, curve, numerazione, mio_best_ms):
        rif_ext = self.seleziona(st, idx, mio_best_ms)
        if rif_ext is None or player_c is None:
            return None
        curve_eff, num_eff = self.curve_per_confronto(st, curve, numerazione, rif_ext)
        if not curve_eff:
            return None
        misure_ext = self.misure_rif(rif_ext, curve_eff)
        righe = []
        for cu in curve_eff:
            m = C.misura(player_c, cu)
            r = misure_ext.get(cu["n"], {})
            if m.get("tempo") is None or r.get("tempo") is None:
                continue
            delta = round(m["tempo"] - r["tempo"], 3)
            fren_diff = round(r["frenata"] - m["frenata"]) if (m.get("frenata") is not None and r.get("frenata") is not None) else None
            vmin_diff = round(r["vmin"] - m["vmin"]) if (m.get("vmin") is not None and r.get("vmin") is not None) else None
            gas_diff = round(m["gas"] - r["gas"]) if (m.get("gas") is not None and r.get("gas") is not None) else None
            frase, _ = self.consiglio_curva(m, cu, rif_ext, curve_eff)
            righe.append({
                "curva": cu["nome"],
                "n": cu["n"],
                "delta_s": delta,
                "frenata_diff_m": fren_diff,
                "vmin_diff_kmh": vmin_diff,
                "gas_diff_m": gas_diff,
                "nota": frase,
            })
        peggiori = sorted((x for x in righe if x["delta_s"] > 0), key=lambda x: -x["delta_s"])[:3]
        return {
            "tipo": rif_ext["tipo"],
            "pilota": rif_ext["nome_intero"],
            "pilota_radio": rif_ext["nome"],
            "giro": rif_ext["giro"],
            "tempo_ms": rif_ext["tempo_ms"],
            "tempo": fmt(rif_ext["tempo_ms"]),
            "numerazione": num_eff,
            "curve": righe,
            "peggiori": peggiori,
        }
