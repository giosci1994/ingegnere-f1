"""La radio: mette in fila i messaggi dell'ingegnere e li fa parlare uno alla volta.

- mai due frasi una sopra l'altra: la frase dopo parte quando la prima è finita (+ una pausa);
- prima le più importanti (priorità 1 → 5), a parità la più vecchia;
- una frase scaduta (ttl in secondi di gioco) non si dice più;
- la stessa chiave in fila una volta sola (vince il testo più nuovo);
- una frase di priorità 1 che «interrompe» taglia una frase di priorità 3 o più bassa.
"""

import asyncio
import logging
import time

log = logging.getLogger("radio")
PAUSA = 0.6


class Radio:
    def __init__(self, slot, voce, imp, invia, ora_gioco):
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

    def avvia(self):
        self._task = asyncio.create_task(self._ciclo())

    def ammesso(self, m):
        return self.imp.acceso(m.categoria) and self.imp["verbosita"] >= m.livello

    def metti(self, messaggi):
        for m in messaggi:
            if not self.ammesso(m):
                continue
            self.coda = [x for x in self.coda if x.chiave != m.chiave]
            self.coda.append(m)
        if messaggi:
            self._sveglia.set()

    def svuota(self):
        self.coda.clear()

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
            self._sveglia.clear()
            await self._sveglia.wait()
            return
        adesso = time.monotonic()
        t = self.ora_gioco()
        self.coda = [m for m in self.coda if t - m.creato <= m.ttl or t < m.creato - 5]
        if not self.coda:
            return
        self.coda.sort(key=lambda m: (m.priorita, m.creato))
        m = self.coda[0]
        occupato = adesso < self.occupato_fino
        interrompi = False
        if occupato:
            if m.interrompe and m.priorita == 1 and self.in_onda and self.in_onda.priorita >= 3:
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
        }
        self.detti.append({k: voce[k] for k in ("testo", "categoria", "priorita", "ora")})
        self.detti = self.detti[-30:]
        log.info("slot %s P%s [%s] %s (voce in %.2f s, dura %.1f s)", self.slot, m.priorita,
                 m.categoria, m.testo, pronto, durata)
        await self.invia(self.slot, voce)
