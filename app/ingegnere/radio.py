"""La radio: mette in fila i messaggi dell'ingegnere e li fa parlare uno alla volta.

- mai due frasi una sopra l'altra: la frase dopo parte quando la prima è finita (+ una pausa);
- prima le più importanti (priorità 1 → 5), a parità la più vecchia;
- una frase scaduta (ttl in secondi di gioco) non si dice più;
- la stessa chiave in fila una volta sola (vince il testo più nuovo); se la frase nuova
  annuncia il valore che la vecchia in fila aveva già trovato detto (`valore` == `da`: la
  posizione tornata quella di prima), si tolgono tutte e due e non si dice niente (0.6.3);
- al telefono ogni frase arriva con chiave, categoria, creazione, ttl e, per le categorie del
  momento (`DEL_MOMENTO`, non urgenti), i secondi che le restano (`scade_tra`): il telefono
  non legge una frase scaduta e, con la stessa chiave, toglie dalla sua fila quella vecchia;
- una frase di priorità 1 che «interrompe» taglia una frase di priorità 3 o più bassa;
- silenzio di 30 s dal tasto (`zitto()`): passano solo le priorità 1 (bandiere, safety car,
  spotter); le altre come nel silenzio della qualifica;
- silenzio radio (giro lanciato in qualifica, `silenzio()` vero): passano solo le priorità 1–2
  e il tempo del giro appena chiuso (categoria record, detto sul traguardo);
  le altre si tengono e, finito il giro, si dicono quelle ancora valide (categorie che non
  scadono con il momento: guida, gomme, danni, meteo, carburante, batteria, record, giri);
  se il silenzio finisce in pit lane, in garage o in pausa (`ai_box()`), si buttano (0.6.3);
"""

import asyncio
import logging
import time

log = logging.getLogger("radio")
PAUSA = 0.6
# quello che dopo il traguardo vale ancora (un «sei sotto il secondo, attacca» invece no)
VALE_DOPO = {"guida", "gomme", "danni", "meteo", "carburante", "ers", "record", "giri",
             "box", "strategia", "penalita"}   # le ultime tre contano solo per il tasto del silenzio
# quello che vale solo nel momento: se il telefono è indietro, non si legge più (0.6.3)
DEL_MOMENTO = {"posizioni", "distacchi", "spotter", "ali", "passo", "settori"}


class Radio:
    def __init__(self, slot, voce, imp, invia, ora_gioco, silenzio=None, ai_box=None):
        self.slot = slot
        self.voce = voce
        self.imp = imp
        self.invia = invia                # async (slot, dict)
        self.ora_gioco = ora_gioco        # () -> secondi di gioco
        self.coda = []
        self.occupato_fino = 0.0
        self.in_onda = None
        self._sveglia = asyncio.Event()
        self.detti = []                   # ultimi messaggi detti, per la pagina
        self._task = None
        self.silenzio = silenzio or (lambda: False)   # () -> True nel giro lanciato in qualifica
        self.ai_box = ai_box or (lambda: False)       # () -> True in pit lane, garage, pausa (0.6.3)
        self.tenuti = []                  # frasi tenute durante il silenzio radio
        self.in_silenzio = False
        self.zitto_fino = 0.0             # time.monotonic() fino a cui la radio sta zitta (tasto)

    def avvia(self):
        self._task = asyncio.create_task(self._ciclo())

    def ammesso(self, m):
        return self.imp.acceso(m.categoria) and self.imp["verbosita"] >= m.livello

    def metti(self, messaggi):
        for m in messaggi:
            if not self.ammesso(m):
                continue
            vecchio = next((x for x in self.coda if x.chiave == m.chiave), None)
            self.coda = [x for x in self.coda if x.chiave != m.chiave]
            if vecchio is not None and m.valore is not None and vecchio.da is not None:
                m.da = vecchio.da             # per chi ascolta vale ancora quello detto prima
                if m.valore == m.da:
                    log.info("ritirata %s: si torna a %s, già detto", m.chiave, m.valore)
                    continue
            self.coda.append(m)
        if messaggi:
            self._sveglia.set()

    def svuota(self):
        self.coda.clear()
        self.tenuti.clear()

    def svuota_categoria(self, categoria):
        self.coda = [m for m in self.coda if m.categoria != categoria]
        self.tenuti = [m for m in self.tenuti if m.categoria != categoria]

    def zitto(self, secondi=30.0):
        """Il tasto del silenzio: zitta per `secondi`; premuto di nuovo, riaccende. Restituisce i
        secondi di silenzio (0 = riaccesa)."""
        adesso = time.monotonic()
        if self.zitto_fino > adesso:
            self.zitto_fino = 0.0
        else:
            self.zitto_fino = adesso + secondi
        self._sveglia.set()
        return max(0.0, self.zitto_fino - adesso)

    def zitta(self):
        return time.monotonic() < self.zitto_fino

    def ultima_frase(self):
        return self.detti[-1]["testo"] if self.detti else None

    def _silenzio(self, t):
        """Tiene le frasi non urgenti durante il giro lanciato; alla fine rimette quelle valide."""
        muto = self.zitta()
        try:
            zitto = muto or bool(self.silenzio())
        except Exception:
            log.exception("silenzio")
            zitto = False
        if zitto:
            self.in_silenzio = True
            # qualifica: il tempo del giro appena chiuso (record) passa, è la chiamata del traguardo;
            # tasto del silenzio: passa solo la priorità 1
            tenere = [m for m in self.coda if (m.priorita >= 2 if muto else
                                               m.priorita >= 3 and m.categoria != "record")]
            if tenere:
                self.coda = [m for m in self.coda if m not in tenere]
                for m in tenere:
                    self.tenuti = [x for x in self.tenuti if x.chiave != m.chiave]
                    if m.categoria in VALE_DOPO:
                        self.tenuti.append(m)
                log.info("silenzio radio: tengo %s", ", ".join(m.chiave for m in tenere))
        elif self.in_silenzio:
            self.in_silenzio = False
            try:
                rientrato = bool(self.ai_box())
            except Exception:
                log.exception("ai_box")
                rientrato = False
            if rientrato and self.tenuti:     # 0.6.3: finito perché si è rientrati: non servono più
                log.info("silenzio finito ai box: butto %s", ", ".join(m.chiave for m in self.tenuti))
                self.tenuti = []
            for m in self.tenuti:
                m.creato = t                  # il ttl riparte da adesso, e più lungo: sono in fila
                m.ttl = max(m.ttl, 30.0)
                self.coda = [x for x in self.coda if x.chiave != m.chiave] + [m]
            self.tenuti = []

    async def _ciclo(self):
        while True:
            try:
                await self._giro()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("radio %s", self.slot)
                await asyncio.sleep(1)

    async def _giro(self):
        if not self.coda:
            if self.tenuti:               # silenzio radio: si guarda ogni mezzo secondo se è finito
                await asyncio.sleep(0.5)
                self._silenzio(self.ora_gioco())
                return
            self._sveglia.clear()
            await self._sveglia.wait()
            return
        adesso = time.monotonic()
        t = self.ora_gioco()
        self._silenzio(t)
        self.coda = [m for m in self.coda if t - m.creato <= m.ttl or t < m.creato - 5]
        if not self.coda:
            if self.in_silenzio:          # si ricontrolla: alla fine del giro escono le tenute
                await asyncio.sleep(0.5)
            return
        self.coda.sort(key=lambda m: (m.priorita, m.creato))
        m = self.coda[0]
        occupato = adesso < self.occupato_fino
        interrompi = False
        if occupato:
            # lo spotter taglia anche le frasi di priorità 2: un affiancamento detto tardi non serve
            soglia = 2 if m.categoria == "spotter" else 3
            if m.interrompe and m.priorita == 1 and self.in_onda and self.in_onda.priorita >= soglia:
                interrompi = True
            else:
                self._sveglia.clear()
                try:
                    await asyncio.wait_for(self._sveglia.wait(), self.occupato_fino - adesso)
                except asyncio.TimeoutError:
                    pass
                return
        self.coda.pop(0)
        await self.parla(m, interrompi)
        nato = getattr(m, "nato", None)
        if nato is not None:              # lo spotter: quanto ci ha messo dal pacchetto alla radio
            log.info("ritardo %s: %.3f s dal pacchetto all'invio ai telefoni", m.chiave, time.monotonic() - nato)

    def scade_tra(self, m):
        """Secondi che restano alla frase (per il telefono); None = non scade al telefono:
        le urgenti (priorità 1) e quelle che non sono del momento."""
        if m.priorita <= 1 or m.categoria not in DEL_MOMENTO:
            return None
        try:
            resta = m.ttl - (self.ora_gioco() - m.creato)
        except Exception:
            return None
        return round(max(0.0, resta), 2)

    async def parla(self, m, interrompi=False):
        v = self.imp
        loop = asyncio.get_running_loop()
        inizio = time.monotonic()
        chiave, durata = await loop.run_in_executor(
            None, self.voce.sintetizza, m.testo, v["voce"], v["velocita"], v["effetto_radio"])
        pronto = time.monotonic() - inizio
        self.in_onda = m
        self.occupato_fino = time.monotonic() + durata + PAUSA
        voce = {
            "tipo": "radio", "slot": self.slot, "testo": m.testo, "categoria": m.categoria,
            "priorita": m.priorita, "interrompi": interrompi, "durata": round(durata, 2),
            "url": f"/audio/{chiave}.wav?v={v['volume']}",
            "ora": time.strftime("%H:%M:%S"),
            "chiave": m.chiave, "creato": round(m.creato, 1), "ttl": m.ttl,
            "scade_tra": self.scade_tra(m),
        }
        self.detti.append({k: voce[k] for k in ("testo", "categoria", "priorita", "ora")})
        self.detti = self.detti[-30:]
        log.info("slot %s P%s [%s] %s (voce in %.2f s, dura %.1f s)", self.slot, m.priorita,
                 m.categoria, m.testo, pronto, durata)
        await self.invia(self.slot, voce)
