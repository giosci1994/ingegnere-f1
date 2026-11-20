"""L'ingegnere di pista: legge lo stato e decide che cosa dire, e quando.

Un Ingegnere solo, per l'auto del giocatore (player_car_index): c'è sempre un giocatore solo
(scelta del 19/11/2026); `slot` resta solo come nome interno (vale 1). Produce Messaggi; li mette in fila e li fa parlare la Radio (radio.py).

Regole generali:
- priorità: sicurezza/bandiere (1) > box e penalità (2) > gomme, carburante, batteria,
  danni, meteo (3) > distacchi e posizioni (4) > il resto (5);
- ogni avviso ha una chiave e un tempo di attesa (in secondi di gioco) prima di ripetersi;
- verbosità: 1 essenziale, 2 normale, 3 tutto (ogni messaggio ha il suo livello minimo).
"""

import random
from dataclasses import dataclass, field

from . import pacchetti as P
from .impostazioni import CATEGORIE
from .stato import ms


@dataclass
class Messaggio:
    categoria: str
    chiave: str
    testo: str
    priorita: int = 0          # 0 = quella della categoria
    livello: int = 2           # verbosità minima per dirlo
    ttl: float = 12.0          # secondi di gioco dopo cui non ha più senso dirlo
    interrompe: bool = False   # può tagliare una frase meno importante
    creato: float = 0.0
    fisso: bool = False        # frase senza numeri: va nella cache all'avvio

    def __post_init__(self):
        if not self.priorita:
            self.priorita = CATEGORIE[self.categoria][1]


# ---------- come si dicono i numeri ----------
def dec(x):
    """1.24 → «1 virgola 2»; 12.3 → «12»."""
    if x is None:
        return ""
    if x < 0.1:
        return "meno di un decimo"
    if x >= 10:
        return f"{round(x)}"
    i, d = int(x), int(round((x - int(x)) * 10))
    if d == 10:
        i, d = i + 1, 0
    return f"{i}" if d == 0 else f"{i} virgola {d}"


def tempo_giro(millis):
    """92456 → «1, 32 e 4» (uno, trentadue e quattro)."""
    if not millis:
        return ""
    s = millis / 1000
    m = int(s // 60)
    resto = s - m * 60
    sec = int(resto)
    dec_ = int((resto - sec) * 10)
    if m:
        return f"{m}, {sec} e {dec_}" if dec_ else f"{m}, {sec}"
    return f"{sec} e {dec_}"


def pos(n):
    return f"P {n}"


def pct(x):
    return f"{int(round(x))} per cento"


def scegli(*frasi):
    return random.choice(frasi)


# frasi senza numeri: si preparano nella cache all'avvio
FRASI_FISSE = [
    "Bandiera gialla, bandiera gialla. Attenzione.",
    "Bandiera gialla. Occhio, piano.",
    "Bandiera blu. Fai passare.",
    "Bandiera verde, pista libera.",
    "Bandiera rossa, bandiera rossa. Rallenta e rientra ai box.",
    "Stai andando contromano! Girati.",
    "Safety car, safety car. Rallenta e tieni il delta positivo.",
    "Virtual safety car, virtual safety car. Rispetta il delta.",
    "La safety car rientra in questo giro. Preparati alla ripartenza.",
    "Pista libera, pista libera. Push, push!",
    "Fine virtual safety car. Push adesso!",
    "Delta negativo, rallenta.",
    "Limitatore! Limitatore!",
    "Box, box. Box, box.",
    "Via, via, via!",
    "Ultimo giro! Dai tutto.",
    "Contatto. Controllo i danni.",
    "Penalità scontata. Bene, testa giù.",
    "Giro cancellato. Limiti della pista.",
    "Overtake disponibile. Usalo.",
    "Batteria quasi scarica. Ricarica.",
    "Giro più veloce della gara! Grande.",
    "È anche il giro più veloce della gara. Grande.",
    "Pronti. Radio check. Ti sento forte e chiaro.",
    "Inizia a piovere. Valuta le intermedie.",
    "La pista si sta asciugando. Valuta le slick.",
    "Gomme surriscaldate. Gestisci, gestisci.",
    "Gomme fredde. Scaldale.",
    "Freni caldi. Gestisci in frenata.",
    "Guasto all'ERS. Ti diamo istruzioni.",
    "Guasto al DRS.",
    "Problema al cambio. Cambia marcia con delicatezza.",
    "Danno al motore. Gestisci.",
    "Bandiera a scacchi. Bel lavoro.",
    "Ali in modalità rettilineo!",
]


class Ingegnere:
    def __init__(self, slot):
        self.slot = slot
        self.nuova_sessione()

    def nuova_sessione(self):
        self.ultimo = {}          # chiave -> tempo di gioco in cui è stato detto
        self.salutato = False
        self.giro = None
        self.giro_invalido = False
        self.giro_box = False
        self.giro_sc = False
        self.inizio_giro_t = 0.0
        self.giri = []            # giri completati, per il riassunto
        self.pos_vista = None
        self.pos_dal = 0.0
        self.pos_detta = None
        self.ultimo_sorpasso = None
        self.flag = 0
        self.sc = 0
        self.pit = 0
        self.pit_entrata = None
        self.soste = []
        self.danni = None
        self.soglie_usura = set()
        self.best_ms = None
        self.finestra = None
        self.meteo_detto = set()
        self.meteo = None
        self.slick_bagnato_dal = None
        self.asciutto_dal = None
        self.overtake = 0
        self.tempo_rimasto_detto = set()
        self.distacco_davanti_prec = None
        self.fine = False
        self.penalita = []
        self.contatti = 0
        self.flashback = 0
        self.avvertimenti = 0
        self.giro1_detto = False
        self.ultima_t = 0.0
        self.arrivo_pos = None

    # ---------- utilità ----------
    def _puo(self, chiave, attesa, t):
        u = self.ultimo.get(chiave)
        if u is not None and u <= t and t - u < attesa:
            return False
        self.ultimo[chiave] = t
        return True

    def _m(self, out, t, categoria, chiave, testo, attesa=30.0, **kw):
        if self._puo(chiave, attesa, t):
            out.append(Messaggio(categoria, chiave, testo, creato=t, **kw))

    # ---------- ciclo ----------
    def valuta(self, st):
        idx = st.indice(self.slot)
        ses = st.sessione()
        lap = st.auto(P.LAP, idx)
        if idx is None or lap is None or ses is None:
            return []
        t = st.tempo()
        if t + 5 < self.ultima_t:          # il tempo torna indietro: flashback o riavvio
            self._indietro(t)
        self.ultima_t = t
        out = []
        if ses.game_paused:
            return out
        tel = st.auto(P.TELEMETRY, idx)
        sta = st.auto(P.STATUS, idx)
        dmg = st.auto(P.DAMAGE, idx)
        t2 = st.auto(P.TELEMETRY2, idx) if st.formato == 2026 else None
        gara = st.in_gara()

        if not self.salutato:
            self.salutato = True
            nome = P.NOMI_SESSIONE.get(ses.session_type, "sessione")
            pista = P.PISTE.get(ses.track_id, "")
            extra = f", {ses.total_laps} giri" if gara and ses.total_laps else ""
            self._m(out, t, "giri", "saluto",
                    f"Radio check. Ti sento forte e chiaro. {nome.capitalize()}"
                    f"{' a ' + pista if pista else ''}{extra}.", livello=2, ttl=60)

        if lap.driver_status == 0:          # in garage: niente avvisi di pista
            self.giro = lap.current_lap_num
            return out

        self._bandiere(out, t, st, ses, sta, t2, lap)
        self._safety_car(out, t, ses, lap)
        self._box(out, t, st, ses, lap, sta, tel, gara)
        self._giro(out, t, st, ses, lap, sta, dmg, gara, idx)
        if gara:
            self._posizioni(out, t, st, lap, idx)
            self._distacchi_vivi(out, t, st, idx, lap, sta, t2)
        self._gomme(out, t, st, lap, sta, tel, dmg, gara, ses)
        self._ers(out, t, sta, t2, gara, lap)
        self._danni(out, t, dmg)
        self._meteo(out, t, ses, sta, gara)
        self._tempo_sessione(out, t, ses, gara)
        return out

    def _indietro(self, t):
        for k in list(self.ultimo):
            if self.ultimo[k] > t:
                del self.ultimo[k]

    # ---------- bandiere e sicurezza ----------
    def _bandiere(self, out, t, st, ses, sta, t2, lap):
        if t2 is not None and t2.driving_wrong_way:
            self._m(out, t, "bandiere", "contromano", "Stai andando contromano! Girati.",
                    attesa=8, livello=1, ttl=4, interrompe=True, fisso=True)
        if sta is None:
            return
        f = sta.vehicle_fia_flags
        if f != self.flag:
            if f == 3:
                self._m(out, t, "bandiere", "gialla",
                        scegli("Bandiera gialla, bandiera gialla. Attenzione.",
                               "Bandiera gialla. Occhio, piano."),
                        attesa=20, livello=1, ttl=6, interrompe=True, fisso=True)
            elif f == 2 and st.in_gara():
                self._m(out, t, "bandiere", "blu", "Bandiera blu. Fai passare.",
                        attesa=40, livello=1, ttl=8, fisso=True)
            elif f == 1 and self.flag == 3:
                self._m(out, t, "bandiere", "verde", "Bandiera verde, pista libera.",
                        attesa=20, livello=2, ttl=6, fisso=True)
            self.flag = f

    def _safety_car(self, out, t, ses, lap):
        s = ses.safety_car_status
        if s != self.sc:
            if s == 1:
                self._m(out, t, "safety_car", "sc",
                        "Safety car, safety car. Rallenta e tieni il delta positivo.",
                        attesa=30, livello=1, ttl=10, interrompe=True, fisso=True)
            elif s == 2:
                self._m(out, t, "safety_car", "vsc",
                        "Virtual safety car, virtual safety car. Rispetta il delta.",
                        attesa=30, livello=1, ttl=10, interrompe=True, fisso=True)
            elif s == 0 and self.sc == 2:
                self._m(out, t, "safety_car", "vsc_fine", "Fine virtual safety car. Push adesso!",
                        attesa=30, livello=1, ttl=6, interrompe=True, fisso=True)
            self.sc = s
        if s in (1, 2):
            if t - self.inizio_giro_t > 3:      # il pacchetto sessione arriva in ritardo
                self.giro_sc = True
            if lap.safety_car_delta < -0.3 and lap.pit_status == 0:
                self._m(out, t, "safety_car", "delta", "Delta negativo, rallenta.",
                        attesa=12, livello=1, ttl=4, fisso=True)

    # ---------- box ----------
    def _box(self, out, t, st, ses, lap, sta, tel, gara):
        ps = lap.pit_status
        if ps:
            self.giro_box = True            # vale per il giro d'entrata e per quello d'uscita
        if ps and not self.pit:
            self.pit_entrata = (t, lap.current_lap_num)
        if ps and sta is not None and tel is not None and not sta.pit_limiter_status \
                and ps == 1 and tel.speed > ses.pit_speed_limit + 5 and ses.pit_speed_limit:
            self._m(out, t, "box", "limitatore", "Limitatore! Limitatore!",
                    attesa=10, livello=1, ttl=6, priorita=1, interrompe=True, fisso=True)
        if not ps and self.pit:
            secondi = lap.pit_lane_time_in_lane_in_ms / 1000 if lap.pit_lane_time_in_lane_in_ms else None
            if self.pit_entrata:
                self.soste.append({"giro": self.pit_entrata[1],
                                   "secondi_in_pit_lane": round(secondi, 1) if secondi else None,
                                   "sosta_secondi": round(lap.pit_stop_timer_in_ms / 1000, 1)
                                   if lap.pit_stop_timer_in_ms else None})
            if gara:
                testo = f"Fuori dai box. Rientri {pos(lap.car_position)}."
                if secondi:
                    testo += f" {dec(secondi)} secondi in pit lane."
                self._m(out, t, "box", "uscita_box", testo, attesa=20, livello=2, ttl=15)
            self.pos_detta = lap.car_position
        self.pit = ps

        if not gara:
            return
        ideale, ultimo = ses.pit_stop_window_ideal_lap, ses.pit_stop_window_latest_lap
        if ideale and lap.current_lap_num:
            chiave = (ideale, ultimo)
            if lap.current_lap_num == ideale and self.finestra != ("aperta", chiave):
                self.finestra = ("aperta", chiave)
                rientro = ses.pit_stop_rejoin_position
                testo = "Finestra box aperta."
                if ultimo and ultimo > ideale:
                    testo += f" Ultimo giro utile il {ultimo}."
                if rientro:
                    testo += f" Se ti fermi ora rientri {pos(rientro)}."
                self._m(out, t, "box", f"finestra{ideale}", testo, attesa=60, livello=1, ttl=20)
            elif ultimo and lap.current_lap_num == ultimo and self.finestra != ("ultimo", chiave) \
                    and lap.num_pit_stops == 0:
                self.finestra = ("ultimo", chiave)
                self._m(out, t, "box", f"ultimo_utile{ultimo}",
                        "Box, box. Box, box. Ultimo giro utile per la sosta.",
                        attesa=60, livello=1, ttl=20, interrompe=True)

    # ---------- fine giro ----------
    def _giro(self, out, t, st, ses, lap, sta, dmg, gara, idx):
        n = lap.current_lap_num
        if lap.current_lap_invalid:
            if not self.giro_invalido and not gara:
                self._m(out, t, "penalita", f"invalido{n}", "Giro cancellato. Limiti della pista.",
                        attesa=30, livello=2, ttl=6, fisso=True)
            self.giro_invalido = True
        if self.giro is None:
            self.giro = n
            return
        if n <= self.giro:
            if n < self.giro:                # flashback o sessione rifatta
                self.giro = n
                self.giri = [g for g in self.giri if g["giro"] < n]
            return
        # è finito il giro self.giro
        finito = self.giro
        self.giro = n
        tempo = lap.last_lap_time_in_ms
        valido = not self.giro_invalido
        usura = max(dmg.tyres_wear) if dmg is not None else None
        self.giri.append({
            "giro": finito, "tempo_ms": tempo, "valido": valido, "box": self.giro_box,
            "safety_car": self.giro_sc, "posizione": lap.car_position,
            "gomma": P.GOMME_VISIVE.get(sta.visual_tyre_compound) if sta is not None else None,
            "usura_max": round(usura, 1) if usura is not None else None,
            "carburante_giri": round(sta.fuel_remaining_laps, 2) if sta is not None else None,
        })
        era_box = self.giro_box
        self.giro_invalido = self.giro_box = False
        self.giro_sc = False
        self.inizio_giro_t = t
        parti = []

        # tempo e record
        nuovo_best = False
        if tempo and valido and (self.best_ms is None or tempo < self.best_ms):
            nuovo_best = self.best_ms is not None
            self.best_ms = tempo
        if tempo:
            if nuovo_best:
                self._m(out, t, "record", f"best{finito}",
                        f"Giro veloce personale! {tempo_giro(tempo)}.", attesa=5, livello=2, ttl=20)
            elif not gara and valido:
                self._m(out, t, "record", f"tempo{finito}",
                        f"{tempo_giro(tempo)}. Sei {pos(lap.car_position)}.",
                        attesa=5, livello=2, ttl=20)
            elif gara and valido:
                parti.append(("record", 3, f"{tempo_giro(tempo)}."))

        if not gara:
            return

        totali = ses.total_laps
        mancano = totali - n + 1 if totali else None
        if finito == 1 and not self.giro1_detto:
            self.giro1_detto = True
            griglia = lap.grid_position
            diff = griglia - lap.car_position if griglia else 0
            if diff > 0:
                extra = f" {'Guadagnata una posizione' if diff == 1 else f'Guadagnate {diff} posizioni'}."
            elif diff < 0:
                extra = f" {'Persa una posizione' if diff == -1 else f'Perse {-diff} posizioni'}."
            else:
                extra = ""
            self._m(out, t, "posizioni", "giro1", f"Fine primo giro, sei {pos(lap.car_position)}.{extra}",
                    attesa=60, livello=1, ttl=20)
            self.pos_detta = lap.car_position
        if mancano is not None and n <= totali:
            if mancano == 1:
                self._m(out, t, "giri", "ultimo_giro", "Ultimo giro! Dai tutto.",
                        attesa=60, livello=1, ttl=15, fisso=True)
            elif mancano in (5, 10) or (mancano == 3 and totali > 5):
                self._m(out, t, "giri", f"mancano{mancano}", f"Mancano {mancano} giri.",
                        attesa=60, livello=2, ttl=15)
            elif totali >= 10 and n == totali // 2 + 1:
                self._m(out, t, "giri", "meta", "Metà gara. Continua così.",
                        attesa=60, livello=3, ttl=15)

        # carburante, dopo il secondo giro
        if sta is not None and finito >= 2 and mancano and mancano > 1:
            fl = sta.fuel_remaining_laps
            if fl < -0.2:
                self._m(out, t, "carburante", "benzina_poca",
                        f"Carburante: meno {dec(-fl)} giri. Lift and coast.",
                        attesa=150, livello=1, ttl=30)
            elif fl > 1.0:
                parti.append(("carburante", 3, f"Carburante: più {dec(fl)} giri, puoi spingere."))

        # distacchi, a ogni giro (tutto) o ogni due (normale); non al primo giro (c'è già «Fine
        # primo giro»). «Recuperi/perdi» solo se davanti c'è la stessa macchina e niente box.
        davanti = st.distacco_davanti(idx)
        dietro, j = st.distacco_dietro(idx)
        j_av = st.auto_in_posizione(lap.car_position - 1) if davanti is not None else None
        frasi = []
        if davanti is not None:
            frasi.append(f"Davanti {st.nome(j_av)} a {dec(davanti)}")
            prec = self.distacco_davanti_prec
            if prec is not None and prec[0] == j_av and not era_box and not prec[2]:
                diff = prec[1] - davanti
                if abs(diff) >= 0.3:
                    frasi[-1] += f", {'recuperi' if diff > 0 else 'perdi'} {dec(abs(diff))}"
        if dietro is not None:
            frasi.append(f"Dietro {st.nome(j)} a {dec(dietro)}")
        self.distacco_davanti_prec = (j_av, davanti, era_box) if davanti is not None else None
        if frasi and finito > 1:
            livello = 2 if finito % 2 == 0 else 3
            parti.append(("distacchi", livello, ". ".join(frasi) + "."))

        # un messaggio solo per le informazioni del giro (niente frasi una sopra l'altra)
        self._riepilogo = parti

    def riepilogo_giro(self, imp, t):
        """Le parti del giro appena finito, filtrate per categoria e verbosità, in una frase."""
        parti = getattr(self, "_riepilogo", None)
        self._riepilogo = None
        if not parti:
            return None
        testo = " ".join(p for cat, liv, p in parti
                         if imp.acceso(cat) and imp["verbosita"] >= liv)
        if not testo:
            return None
        cat = next(cat for cat, liv, p in parti if imp.acceso(cat) and imp["verbosita"] >= liv)
        return Messaggio(cat, "riepilogo_giro", testo, priorita=4, livello=1, ttl=25, creato=t)

    # ---------- posizioni ----------
    def _posizioni(self, out, t, st, lap, idx):
        p = lap.car_position
        if not p:
            return
        if p != self.pos_vista:
            self.pos_vista, self.pos_dal = p, t
            return
        if lap.current_lap_num <= 1 or lap.pit_status or t - self.pos_dal < 2.0:
            return
        if self.pos_detta is None:
            self.pos_detta = p
            return
        if p == self.pos_detta:
            return
        guadagno = self.pos_detta - p
        self.pos_detta = p
        nome = ""
        if self.ultimo_sorpasso and t - self.ultimo_sorpasso[0] < 6:
            nome = st.nome(self.ultimo_sorpasso[2])
        if guadagno > 0:
            testo = (f"Bella mossa su {nome}! Sei {pos(p)}." if nome and guadagno == 1
                     else f"Bella mossa! Sei {pos(p)}.")
        else:
            testo = (f"{nome} ti ha passato. Sei {pos(p)}." if nome and guadagno == -1
                     else f"Hai perso {'una posizione' if guadagno == -1 else f'{-guadagno} posizioni'}. Sei {pos(p)}.")
        self._m(out, t, "posizioni", "posizione", testo, attesa=4, livello=2, ttl=8)

    def _distacchi_vivi(self, out, t, st, idx, lap, sta, t2):
        if lap.pit_status or lap.current_lap_num <= 1 or \
                (lap.current_lap_num == 2 and lap.lap_distance < 1000):
            return
        davanti = st.distacco_davanti(idx)
        if davanti is not None and 0 < davanti < 1.0:
            j = st.auto_in_posizione(lap.car_position - 1)
            if t2 is not None:
                arma = " Usa l'overtake." if t2.overtake_available else ""
            else:
                arma = " Usa il DRS." if sta is not None and sta.drs_allowed else ""
            self._m(out, t, "distacchi", "attacca",
                    f"Sei sotto il secondo da {st.nome(j)}. Attacca!{arma}",
                    attesa=120, livello=2, ttl=6)
        dietro, j = st.distacco_dietro(idx)
        if dietro is not None and 0 < dietro < 0.8:
            self._m(out, t, "distacchi", "difendi",
                    f"{st.nome(j)} è a {dec(dietro)} dietro. Difendi.",
                    attesa=120, livello=2, ttl=6)

    # ---------- gomme ----------
    def _gomme(self, out, t, st, lap, sta, tel, dmg, gara, ses):
        if dmg is not None:
            usura = max(dmg.tyres_wear)
            ruota = P.RUOTE[list(dmg.tyres_wear).index(usura)]
            mancano = (ses.total_laps - lap.current_lap_num + 1) if gara and ses.total_laps else None
            for soglia, liv in ((40, 3), (55, 2), (70, 1), (80, 1)):
                if usura >= soglia and soglia not in self.soglie_usura:
                    self.soglie_usura.add(soglia)
                    if usura >= soglia + 10:      # salto (gomma montata già usata, flashback)
                        continue
                    if soglia == 80 and gara and (mancano is None or mancano > 2):
                        self._m(out, t, "box", "box_gomme",
                                f"Box, box. Gomme finite, {pct(usura)} sulla {ruota}.",
                                attesa=90, livello=1, ttl=20, interrompe=True)
                    elif soglia == 70:
                        self._m(out, t, "gomme", "usura70",
                                f"Gomme al limite: {pct(usura)} sulla {ruota}. Pensiamo al box.",
                                attesa=60, livello=1, ttl=20)
                    elif soglia < 70:
                        self._m(out, t, "gomme", f"usura{soglia}",
                                f"Usura gomme {pct(usura)}, la più consumata è la {ruota}.",
                                attesa=60, livello=liv, ttl=20)
            if usura < 5 and self.soglie_usura:          # gomme nuove
                self.soglie_usura.clear()
            for i in range(4):
                if dmg.tyre_blisters[i] >= 40:
                    self._m(out, t, "gomme", "blister",
                            f"Blistering sulla {P.RUOTE[i]}. Gestisci le gomme.",
                            attesa=300, livello=2, ttl=15)
        if tel is not None and lap.current_lap_num >= 2 and not lap.pit_status and tel.speed > 80:
            interne = list(tel.tyres_inner_temperature)
            calde = max(interne)
            fredde = sum(interne) / 4
            if calde >= 112:
                self._m(out, t, "gomme", "gomme_calde",
                        f"Gomme surriscaldate, la {P.RUOTE[interne.index(calde)]} è a {calde} gradi. Gestisci.",
                        attesa=120, livello=2, ttl=10)
            elif 0 < fredde < 70 and sta is not None and sta.visual_tyre_compound in P.GOMME_SLICK \
                    and ses.weather < 3:
                self._m(out, t, "gomme", "gomme_fredde", "Gomme fredde. Scaldale.",
                        attesa=180, livello=3, ttl=10, fisso=True)
            # i freni caldi stanno in analisi.py (_freni): servono le curve e un orologio
            # che non torni indietro con i flashback

    # ---------- batteria e overtake ----------
    def _ers(self, out, t, sta, t2, gara, lap):
        if sta is not None and gara and lap.current_lap_num >= 2:
            pieno = 4_000_000.0
            perc = 100 * sta.ers_store_energy / pieno
            if perc < 10:
                self._m(out, t, "ers", "batteria", "Batteria quasi scarica. Ricarica.",
                        attesa=240, livello=2, ttl=10, fisso=True)
        if t2 is not None:
            if t2.overtake_available and not self.overtake and gara and lap.current_lap_num >= 2:
                self._m(out, t, "ers", "overtake", "Overtake disponibile. Usalo.",
                        attesa=45, livello=3, ttl=5, fisso=True)
            self.overtake = t2.overtake_available

    # ---------- danni ----------
    def _danni(self, out, t, dmg):
        if dmg is None:
            return
        attuali = {
            "ala anteriore sinistra": dmg.front_left_wing_damage,
            "ala anteriore destra": dmg.front_right_wing_damage,
            "ala posteriore": dmg.rear_wing_damage, "fondo": dmg.floor_damage,
            "diffusore": dmg.diffuser_damage, "pance": dmg.sidepod_damage,
            "cambio": dmg.gear_box_damage, "motore": dmg.engine_damage,
        }
        prima = self.danni
        self.danni = dict(attuali, ers=dmg.ers_fault, drs=dmg.drs_fault)
        if prima is None:
            return
        for parte, v in attuali.items():
            salto = v - prima.get(parte, 0)
            if salto >= 10 and v >= 15:
                if parte.startswith("ala anteriore") and v >= 40:
                    self._m(out, t, "box", "box_ala",
                            f"Danno pesante all'{parte}, {pct(v)}. Box, box per l'ala nuova.",
                            attesa=60, livello=1, ttl=20)
                elif parte in ("cambio", "motore"):
                    self._m(out, t, "danni", f"danno_{parte}",
                            "Problema al cambio. Cambia marcia con delicatezza." if parte == "cambio"
                            else "Danno al motore. Gestisci.",
                            attesa=60, livello=1, ttl=15, fisso=True)
                else:
                    art = "all'" if parte[0] in "aeiou" else ("alle " if parte == "pance" else "al ")
                    self._m(out, t, "danni", f"danno_{parte}",
                            f"Danno {art}{parte}, {pct(v)}.", attesa=30, livello=2, ttl=15)
        if dmg.ers_fault and not prima.get("ers"):
            self._m(out, t, "danni", "guasto_ers", "Guasto all'ERS. Ti diamo istruzioni.",
                    attesa=120, livello=1, ttl=15, fisso=True)
        if dmg.drs_fault and not prima.get("drs"):
            self._m(out, t, "danni", "guasto_drs", "Guasto al DRS.", attesa=120, livello=2,
                    ttl=15, fisso=True)

    # ---------- meteo ----------
    def _meteo(self, out, t, ses, sta, gara):
        w = ses.weather
        if self.meteo is not None and w != self.meteo:
            if w >= 3 > self.meteo:
                self._m(out, t, "meteo", "pioggia_ora",
                        f"Adesso {P.METEO[w]}.", attesa=120, livello=2, ttl=15)
        self.meteo = w
        # previsioni della sessione in corso
        n = min(ses.num_weather_forecast_samples, 64)
        for i in range(n):
            c = ses.weather_forecast_samples[i]
            if c.session_type != ses.session_type or c.time_offset == 0:
                continue
            if c.rain_percentage >= 50 and w < 3 and c.weather >= 3:
                chiave = ("pioggia", c.time_offset)
                if chiave not in self.meteo_detto and not any(k[0] == "pioggia" for k in self.meteo_detto):
                    self.meteo_detto.add(chiave)
                    self._m(out, t, "meteo", "previsione",
                            f"Pioggia in arrivo tra circa {c.time_offset} minuti, "
                            f"probabilità {pct(c.rain_percentage)}.", attesa=300, livello=1, ttl=30)
                break
        if sta is None:
            return
        slick = sta.visual_tyre_compound in P.GOMME_SLICK
        if w >= 3 and slick:
            self.slick_bagnato_dal = self.slick_bagnato_dal or t
            if t - self.slick_bagnato_dal > 20:
                self._m(out, t, "meteo", "intermedie", "Inizia a piovere. Valuta le intermedie.",
                        attesa=240, livello=1, ttl=20, priorita=2, fisso=True)
        else:
            self.slick_bagnato_dal = None
        if w <= 1 and not slick and sta.visual_tyre_compound in (7, 8):
            self.asciutto_dal = self.asciutto_dal or t
            if t - self.asciutto_dal > 120:
                self._m(out, t, "meteo", "slick", "La pista si sta asciugando. Valuta le slick.",
                        attesa=300, livello=1, ttl=20, priorita=2, fisso=True)
        else:
            self.asciutto_dal = None

    # ---------- tempo che resta (prove e qualifiche) ----------
    def _tempo_sessione(self, out, t, ses, gara):
        if gara or not ses.session_time_left:
            return
        for minuti in (5, 2):
            s = minuti * 60
            if s - 3 <= ses.session_time_left <= s and minuti not in self.tempo_rimasto_detto:
                self.tempo_rimasto_detto.add(minuti)
                self._m(out, t, "giri", f"tempo{minuti}",
                        f"{minuti} minuti alla fine della sessione.", attesa=60, livello=2, ttl=15)

    # ---------- eventi ----------
    def evento(self, st, pk):
        idx = st.indice(self.slot)
        if idx is None:
            return []
        out = []
        t = pk.header.session_time
        code = P.codice_evento(pk)
        d = pk.dati.details
        if code == "LGOT":
            self._m(out, t, "giri", "via", "Via, via, via!", attesa=60, livello=2, ttl=4,
                    priorita=1, interrompe=True, fisso=True)
        elif code == "RDFL":
            self._m(out, t, "bandiere", "rossa",
                    "Bandiera rossa, bandiera rossa. Rallenta e rientra ai box.",
                    attesa=60, livello=1, ttl=10, interrompe=True, fisso=True)
        elif code == "SCAR":
            tipo, ev = d.safety_car.safety_car_type, d.safety_car.event_type
            if tipo == 1 and ev == 1:
                self._m(out, t, "safety_car", "sc_rientra",
                        "La safety car rientra in questo giro. Preparati alla ripartenza.",
                        attesa=60, livello=1, ttl=15, fisso=True)
            elif tipo == 1 and ev == 3:
                self._m(out, t, "safety_car", "sc_via", "Pista libera, pista libera. Push, push!",
                        attesa=60, livello=1, ttl=8, interrompe=True, fisso=True)
        elif code == "CHQF":
            if not self.fine:
                self.fine = True
                lap = st.auto(P.LAP, idx)
                p = lap.car_position if lap else None
                self.arrivo_pos = p
                if st.in_gara() and p:
                    testo = {1: "Bandiera a scacchi! Hai vinto! Hai vinto! Che gara!",
                             2: f"Bandiera a scacchi. {pos(2)}, ottimo lavoro!",
                             3: f"Bandiera a scacchi. Podio! {pos(3)}!"}.get(
                        p, f"Bandiera a scacchi. Finisci {pos(p)}. Bel lavoro.")
                else:
                    testo = "Bandiera a scacchi. Bel lavoro."
                self._m(out, t, "giri", "arrivo", testo, attesa=600, livello=1, ttl=30,
                        priorita=2)
        elif code == "FTLP":
            if d.fastest_lap.vehicle_idx == idx and st.in_gara():
                appena = any(k.startswith("best") and 0 <= t - v < 10 for k, v in self.ultimo.items())
                testo = ("È anche il giro più veloce della gara. Grande." if appena else
                         f"Giro più veloce della gara! {tempo_giro(int(d.fastest_lap.lap_time * 1000))}. Grande.")
                self._m(out, t, "record", "giro_veloce", testo, attesa=30, livello=1, ttl=15)
        elif code == "PENA":
            pe = d.penalty
            if pe.vehicle_idx == idx:
                self._penalita(out, t, st, pe, idx)
        elif code in ("DTSV", "SGSV"):
            v = d.drive_through_served.vehicle_idx if code == "DTSV" else d.stop_go_served.vehicle_idx
            if v == idx:
                self._m(out, t, "penalita", "scontata", "Penalità scontata. Bene, testa giù.",
                        attesa=30, livello=2, ttl=10, fisso=True)
        elif code == "OVTK":
            o = d.overtake
            if o.overtaking_vehicle_idx == idx:
                self.ultimo_sorpasso = (t, "fatto", o.being_overtaken_vehicle_idx)
            elif o.being_overtaken_vehicle_idx == idx:
                self.ultimo_sorpasso = (t, "subito", o.overtaking_vehicle_idx)
        elif code == "COLL":
            c = d.collision
            if idx in (c.vehicle1_idx, c.vehicle2_idx):
                self.contatti += 1
                altro = c.vehicle2_idx if c.vehicle1_idx == idx else c.vehicle1_idx
                self._m(out, t, "danni", "contatto",
                        f"Contatto con {st.nome(altro)}. Controllo i danni.",
                        attesa=15, livello=2, ttl=10)
        elif code == "FLBK":
            self.flashback += 1
            self._indietro(d.flashback.flashback_session_time)
        return out

    def _penalita(self, out, t, st, pe, idx):
        tipo, secondi = pe.penalty_type, pe.time
        self.penalita.append({"tempo": round(t), "tipo": tipo, "infrazione": pe.infringement_type,
                              "secondi": secondi if secondi != 255 else None,
                              "giro": pe.lap_num})
        lap = st.auto(P.LAP, idx)
        if tipo == 4 and secondi and secondi != 255:
            self._m(out, t, "penalita", f"pen{t:.0f}", f"Penalità di {secondi} secondi.",
                    attesa=5, livello=1, ttl=15)
        elif tipo == 0:
            self._m(out, t, "penalita", f"pen{t:.0f}",
                    "Drive through. Devi scontarlo entro tre giri.", attesa=5, livello=1, ttl=15)
        elif tipo == 1:
            extra = f" di {secondi} secondi" if secondi and secondi != 255 else ""
            self._m(out, t, "penalita", f"pen{t:.0f}",
                    f"Stop and go{extra}. Devi scontarlo entro tre giri.", attesa=5, livello=1, ttl=15)
        elif tipo == 5:
            n = lap.corner_cutting_warnings if lap else 0
            self.avvertimenti = max(self.avvertimenti, n)
            testo = "Avvertimento per i limiti della pista."
            if n:
                testo += f" Sei a {n}."
            self._m(out, t, "penalita", "avvertimento", testo, attesa=10, livello=2, ttl=10)
        elif tipo == 6:
            self._m(out, t, "penalita", "squalifica", "Squalificati. Mi dispiace.",
                    attesa=600, livello=1, ttl=15)
