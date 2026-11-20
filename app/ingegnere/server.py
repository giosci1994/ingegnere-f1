"""Il servizio: riceve la telemetria UDP, fa lavorare l'ingegnere e serve la web app.

    python -m ingegnere.server     (variabili: PORTA_UDP=20777, PORTA_WEB=8777, DATI=/dati)
"""

import asyncio
import json
import logging
import os
import time

from aiohttp import web, WSMsgType

from . import domande as D
from . import numeri_curve as N
from . import pacchetti as P
from . import riassunto as R
from .impostazioni import Impostazioni
from .analisi import Analisi
from .ingegnere import FRASI_FISSE, Ingegnere, Messaggio
from .pronuncia import Pronuncia
from .radio import Radio
from .spotter import Spotter
from .registratore import Registratore
from .stato import Stato
from .strategia import Piste
from .traccia import Biblioteca
from . import curve as C
from .voce import Voce, scala_volume

log = logging.getLogger("ingegnere")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.environ.get("WEB", os.path.join(os.path.dirname(BASE), "web"))
DATI = os.environ.get("DATI", os.path.join(os.path.dirname(BASE), "dati"))
VOCI = os.environ.get("VOCI", os.path.join(os.path.dirname(BASE), "voci"))
PORTA_UDP = int(os.environ.get("PORTA_UDP", "20777"))
PORTA_WEB = int(os.environ.get("PORTA_WEB", "8777"))
DA_DECODIFICARE = {P.SESSION, P.LAP, P.EVENT, P.PARTICIPANTS, P.TELEMETRY, P.STATUS, P.FINAL,
                   P.DAMAGE, P.HISTORY, P.TELEMETRY2, P.MOTION, P.MOTIONEX, P.SETUPS, P.TYRESETS}


class App:
    def __init__(self):
        os.makedirs(DATI, exist_ok=True)
        self.imp = Impostazioni(os.path.join(DATI, "impostazioni.json"))
        self.stato = Stato()
        self.pronuncia = Pronuncia(os.path.join(DATI, "pronuncia.json"))
        self.voce = Voce(VOCI, os.path.join(DATI, "cache"), self.pronuncia)
        self.tasti = D.Tasti()
        self.spotter = Spotter()
        self.finale_salvata = None   # session_uid della classifica finale già messa nel riassunto
        self.reg = Registratore(os.path.join(DATI, "registrazioni"), self.imp)
        self.cartella_riassunti = os.path.join(DATI, "riassunti")
        self.ing = {1: Ingegnere(1)}   # un giocatore solo: l'auto di player_car_index
        self.bib = Biblioteca(os.path.join(DATI, "giri"))
        self.analisi = Analisi(self.imp, self.bib, Piste(os.path.join(DATI, "piste.json")))
        self.nuove_soste = []
        self.radio = {}
        self.clienti = set()         # i telefoni collegati: sentono tutti la stessa radio
        self.ultimo_riassunto = {}
        self.cache_pronta = 0
        self.giro_cache = 0          # cresce a ogni giro della cache: solo l'ultimo scrive cache_pronta

    # ---------- UDP ----------
    def datagramma(self, buf, addr):
        h = P.intestazione(buf)
        if h is None:
            self.stato.scartati["corto"] += 1
            return
        if h.packet_format not in P.STRUTTURE:
            self.stato.scartati[f"formato {h.packet_format}"] += 1
            self.stato.taglie_scartate[(h.packet_format, h.packet_id, len(buf))] += 1
            return
        if self.stato.session_uid and h.session_uid and h.session_uid != self.stato.session_uid:
            self.chiudi_sessione("nuova sessione")
        pk = P.decodifica(buf, DA_DECODIFICARE)
        if pk is None:
            self.stato.scartati["taglia"] += 1
            self.stato.taglie_scartate[(h.packet_format, h.packet_id, len(buf))] += 1
            return
        nuova = self.stato.aggiorna(pk, addr[0])
        if nuova:
            for i in self.ing.values():
                i.nuova_sessione()
            self.analisi.nuova_sessione()
            self.spotter.reset()
            for r in self.radio.values():
                r.svuota()
        try:
            nome = P.NOMI_SESSIONE.get(self.stato.tipo_sessione(), "sessione").replace(" ", "-")
            self.reg.scrivi(buf, h.session_uid, h.packet_id, nome)
        except OSError:
            log.exception("registratore")
        if pk.id == P.TELEMETRY and pk.dati is not None:
            try:
                self.analisi.campione(self.stato)
            except Exception:
                log.exception("traccia")
        elif pk.id == P.LAP and pk.dati is not None:
            self.nuove_soste += self.analisi.strategia.osserva(self.stato)
        elif pk.id == P.MOTION and pk.dati is not None and self.imp.acceso("spotter"):
            try:                       # subito, non nel ciclo di 0,2 s: lo spotter deve arrivare in tempo
                for slot in self.radio:
                    self.radio[slot].metti(self.spotter.valuta(self.stato))
            except Exception:
                log.exception("spotter")
        if pk.id == P.EVENT and pk.dati is not None:
            code = P.codice_evento(pk)
            if code == "BUTN":
                self.domande(pk.dati.details.buttons.button_status)
                return
            for slot, ing in self.ing.items():
                self.radio[slot].metti(ing.evento(self.stato, pk))
            if code == "SEND":
                self.chiudi_sessione("fine sessione")
        elif pk.id == P.FINAL and pk.dati is not None:
            # nei menu la classifica arriva ogni 5 secondi: nel riassunto una volta sola
            if self.finale_salvata != self.stato.session_uid:
                self.finale_salvata = self.stato.session_uid
                self.chiudi_sessione("classifica finale")

    def domande(self, stato_tasti):
        """UDP Action 1–12 appena premute → la risposta alla domanda assegnata a quel tasto."""
        for n in self.tasti.premuti(stato_tasti, self.imp):
            domanda = self.imp["tasti"].get(str(n))
            if not domanda or not self.stato.connesso(5):
                continue
            if domanda == "silenzio":
                for slot, r in self.radio.items():
                    secondi = r.zitto(30)
                    log.info("tasto UDP Action %s: silenzio %s", n, f"per {secondi:.0f} s" if secondi else "finito")
                    asyncio.get_running_loop().create_task(
                        self.invia_radio(slot, {"tipo": "zitto", "secondi": round(secondi)}))
                continue
            for slot, ing in self.ing.items():
                try:
                    m = D.rispondi(domanda, self.stato, ing, self.analisi, self.radio[slot].ultima_frase())
                except Exception:
                    log.exception("domanda %s", domanda)
                    continue
                if m is not None:
                    log.info("tasto UDP Action %s: %s", n, domanda)
                    self.radio[slot].metti([m])

    def chiudi_sessione(self, motivo):
        for slot, ing in self.ing.items():
            if self.stato.indice(slot) is None:
                continue
            try:
                r = R.costruisci(self.stato, ing, self.analisi)
            except Exception:
                log.exception("riassunto")
                continue
            if not r:
                continue
            R.salva(self.cartella_riassunti, r)
            log.info("riassunto %s salvato (%s)", r["id"], motivo)
            if self.ultimo_riassunto.get(slot) != r["id"]:
                self.ultimo_riassunto[slot] = r["id"]
                self.radio[slot].metti([Messaggio("giri", "riassunto",
                                                  "Il riassunto della sessione è sull'app.",
                                                  priorita=5, livello=2, ttl=60,
                                                  creato=self.stato.tempo())])

    # ---------- cicli ----------
    async def ciclo_ingegnere(self):
        while True:
            await asyncio.sleep(0.2)
            try:
                if not self.stato.connesso(5):
                    continue
                for slot, ing in self.ing.items():
                    msgs = ing.valuta(self.stato)
                    rie = ing.riepilogo_giro(self.imp, self.stato.tempo())
                    if rie:
                        msgs.append(rie)
                    soste, self.nuove_soste = self.nuove_soste, []
                    msgs += self.analisi.valuta(self.stato, soste)
                    self.radio[slot].metti(msgs)
            except Exception:
                log.exception("ingegnere")

    async def ciclo_stato(self):
        n = 0
        while True:
            await asyncio.sleep(1)
            n += 1
            self.reg.controlla()
            if n % 600 == 0:
                await asyncio.get_running_loop().run_in_executor(None, self.voce.pulisci_cache)
            if self.clienti:
                stato = {"tipo": "stato", **self.stato_per()}
                for ws in list(self.clienti):
                    await self.manda(ws, stato)

    def stato_per(self, slot=1):
        s = self.stato.riassunto_stato()
        idx = self.stato.indice(slot)
        auto = {}
        if idx is not None and self.stato.connesso(5):
            lap = self.stato.auto(P.LAP, idx)
            sta = self.stato.auto(P.STATUS, idx)
            dmg = self.stato.auto(P.DAMAGE, idx)
            ses = self.stato.sessione()
            if lap is not None:
                auto.update(posizione=lap.car_position, giro=lap.current_lap_num,
                            giri_totali=ses.total_laps if ses else None,
                            davanti=self.stato.distacco_davanti(idx),
                            dietro=self.stato.distacco_dietro(idx)[0],
                            box=bool(lap.pit_status))
            if sta is not None:
                auto.update(gomma=P.GOMME_VISIVE.get(sta.visual_tyre_compound),
                            eta_gomme=sta.tyres_age_laps,
                            carburante=round(sta.fuel_remaining_laps, 1),
                            batteria=round(100 * sta.ers_store_energy / 4e6))
            if dmg is not None:
                auto["usura"] = round(max(dmg.tyres_wear))
            auto["pilota"] = self.stato.nomi.get(idx)
        s.update(tasti={"azione": self.tasti.ultima_azione, "tasto": self.tasti.ultimo_tasto},
                 silenzio=bool(self.radio[slot].in_silenzio) if slot in self.radio else False,
                 zitta=round(max(0.0, self.radio[slot].zitto_fino - time.monotonic())) if slot in self.radio else 0,
                 auto=auto, cache_pronta=self.cache_pronta,
                 frasi=self.radio[slot].detti[-6:], clienti=len(self.clienti),
                 registrazione=self.reg.nome if self.reg.f else None)
        return s

    async def prepara_cache(self):
        loop = asyncio.get_running_loop()
        v = self.imp
        firma = (v["voce"], v["velocita"], v["effetto_radio"])
        self.giro_cache += 1
        giro = self.giro_cache
        self.cache_pronta = 0
        t0 = time.monotonic()
        for i, frase in enumerate(FRASI_FISSE, 1):
            if giro != self.giro_cache:
                return       # le impostazioni sono cambiate: continua l'altro giro
            try:
                await loop.run_in_executor(None, self.voce.sintetizza, frase, *firma)
            except Exception:
                log.exception("cache: %s", frase)
            if giro != self.giro_cache:
                return       # finito dopo il giro nuovo: cache_pronta è sua, non si tocca
            self.cache_pronta = round(100 * i / len(FRASI_FISSE))
        log.info("cache delle frasi fisse pronta (%s) in %.1f s", firma, time.monotonic() - t0)

    # ---------- web ----------
    async def manda(self, ws, dati):
        try:
            await ws.send_str(json.dumps(dati, ensure_ascii=False))
        except (ConnectionError, RuntimeError):
            self.clienti.discard(ws)

    async def invia_radio(self, slot, dati):
        for ws in list(self.clienti):
            await self.manda(ws, dati)

    async def ws(self, req):
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(req)
        self.clienti.add(ws)
        await self.manda(ws, {"tipo": "stato", **self.stato_per()})
        try:
            async for msg in ws:
                if msg.type in (WSMsgType.CLOSE, WSMsgType.ERROR):
                    break
        finally:
            self.clienti.discard(ws)
        return ws

    async def indice(self, req):
        return web.FileResponse(os.path.join(WEB, "index.html"),
                                headers={"Cache-Control": "no-cache"})

    async def api_stato(self, req):
        return web.json_response(self.stato_per())

    async def api_imp(self, req):
        if req.method == "POST":
            nuovi = await _json(req)
            prima = (self.imp["voce"], self.imp["velocita"], self.imp["effetto_radio"])
            self.imp.aggiorna(nuovi)
            if prima != (self.imp["voce"], self.imp["velocita"], self.imp["effetto_radio"]):
                asyncio.create_task(self.prepara_cache())
        return web.json_response(self.imp.descrizione())

    async def api_prova(self, req):
        try:
            d = await _json(req)
        except web.HTTPBadRequest:
            d = {}
        testo = str(d.get("testo") or "").strip()[:200] or \
            "Radio check. Ti sento forte e chiaro. Box, box questo giro."
        grafia = str(d.get("grafia") or "").strip()[:200]   # «Prova» del dizionario: così com'è scritta
        v = self.imp
        loop = asyncio.get_running_loop()
        chiave, durata = await loop.run_in_executor(
            None, self.voce.sintetizza, grafia or testo, v["voce"], v["velocita"], v["effetto_radio"],
            bool(grafia))
        return web.json_response({"url": f"/audio/{chiave}.wav?v={v['volume']}",
                                  "testo": grafia or testo, "durata": round(durata, 2)})

    async def api_pronuncia(self, req):
        """GET: il dizionario. POST {"parola", "grafia"} aggiunge o cambia; {"parola", "togli": true}
        toglie (una voce cambiata torna quella di partenza); {"parola", "rimetti": true}."""
        if req.method == "POST":
            d = await _json(req)
            try:
                if d.get("togli"):
                    self.pronuncia.togli(d.get("parola", ""))
                elif d.get("rimetti"):
                    self.pronuncia.rimetti(d.get("parola", ""))
                else:
                    self.pronuncia.metti(d.get("parola", ""), d.get("grafia", ""))
            except ValueError as e:
                raise web.HTTPBadRequest(text=str(e))
            asyncio.create_task(self.prepara_cache())     # le frasi fisse con la parola cambiata
        return web.json_response({"voci": self.pronuncia.elenco()})

    async def audio(self, req):
        chiave = req.match_info["chiave"]
        if not chiave.isalnum():
            raise web.HTTPNotFound()
        p = self.voce.percorso(chiave)
        if not os.path.exists(p):
            raise web.HTTPNotFound()
        try:
            vol = int(req.query.get("v", "100"))
        except ValueError:
            vol = 100
        with open(p, "rb") as f:
            dati = scala_volume(f.read(), max(0, min(200, vol)))
        return web.Response(body=dati, content_type="audio/wav",
                            headers={"Cache-Control": "public, max-age=86400"})

    async def api_riassunti(self, req):
        return web.json_response(R.elenco(self.cartella_riassunti))

    async def api_riassunto(self, req):
        rid = req.match_info["id"]
        if not all(c.isalnum() or c == "-" for c in rid):
            raise web.HTTPNotFound()
        p = os.path.join(self.cartella_riassunti, rid + ".json")
        if not os.path.exists(p):
            raise web.HTTPNotFound()
        return web.FileResponse(p)

    async def api_crea_riassunto(self, req):
        self.chiudi_sessione("a mano")
        return web.json_response(R.elenco(self.cartella_riassunti)[:3])

    async def api_piste(self, req):
        return web.json_response(self.bib.piste())

    async def api_giri(self, req):
        return web.json_response(self.bib.giri(_pista(req)))

    async def api_confronto(self, req):
        """Traiettoria e curve: giro A confrontato con il giro B (il riferimento)."""
        pista = _pista(req)
        a = self.bib.leggi(pista, req.query.get("a", ""))
        b = self.bib.leggi(pista, req.query.get("b", ""))
        if a is None or b is None:
            raise web.HTTPNotFound(text="giro non trovato")
        loop = asyncio.get_running_loop()
        dati = await loop.run_in_executor(None, confronto, a, b, pista)
        return web.json_response(dati)

    async def api_registrazioni(self, req):
        return web.json_response(self.reg.elenco())

    async def avvio(self, app):
        loop = asyncio.get_running_loop()
        for slot in self.ing:
            self.radio[slot] = Radio(slot, self.voce, self.imp, self.invia_radio, self.stato.tempo,
                                     silenzio=lambda: self.analisi.giro_lanciato(self.stato))
            self.radio[slot].avvia()
        me = self

        class Proto(asyncio.DatagramProtocol):
            def datagram_received(self, data, addr):
                try:
                    me.datagramma(data, addr)
                except Exception:
                    log.exception("datagramma")

        await loop.create_datagram_endpoint(Proto, local_addr=("0.0.0.0", PORTA_UDP))
        log.info("in ascolto: UDP %s, web %s", PORTA_UDP, PORTA_WEB)
        app["compiti"] = [asyncio.create_task(c) for c in
                          (self.ciclo_ingegnere(), self.ciclo_stato(), self.prepara_cache())]

    async def spegni(self, app):
        self.reg.chiudi()       # chiude bene il gzip della registrazione in corso

    def crea(self):
        app = web.Application()
        app.router.add_get("/", self.indice)
        app.router.add_get("/ws", self.ws)
        app.router.add_get("/api/stato", self.api_stato)
        app.router.add_route("*", "/api/impostazioni", self.api_imp)
        app.router.add_post("/api/prova", self.api_prova)
        app.router.add_route("*", "/api/pronuncia", self.api_pronuncia)
        app.router.add_get("/api/riassunti", self.api_riassunti)
        app.router.add_post("/api/riassunti/crea", self.api_crea_riassunto)
        app.router.add_get("/api/riassunti/{id}", self.api_riassunto)
        app.router.add_get("/api/registrazioni", self.api_registrazioni)
        app.router.add_get("/api/piste", self.api_piste)
        app.router.add_get("/api/giri/{pista}", self.api_giri)
        app.router.add_get("/api/confronto/{pista}", self.api_confronto)
        app.router.add_get("/audio/{chiave}.wav", self.audio)
        app.router.add_static("/static/", WEB)
        app.on_startup.append(self.avvio)
        app.on_cleanup.append(self.spegni)
        return app


async def _json(req):
    """Il corpo JSON di una richiesta, che deve essere un oggetto (altrimenti 400)."""
    try:
        d = await req.json()
    except ValueError:
        raise web.HTTPBadRequest(text="JSON non valido")
    if not isinstance(d, dict):
        raise web.HTTPBadRequest(text="serve un oggetto JSON")
    return d


def _pista(req):
    try:
        return int(req.match_info["pista"])
    except ValueError:
        raise web.HTTPNotFound(text="pista non valida")


def _linea(c, passo=4.0):
    """Punti (x, z, v) ogni `passo` metri, per disegnare la traiettoria."""
    out, ultimo = [], -1e9
    for i, d in enumerate(c["d"]):
        if d is None or c["x"][i] is None or d - ultimo < passo:
            continue
        ultimo = d
        out.append([c["x"][i], c["z"][i], c["v"][i], round(d)])
    return out


def confronto(a, b, pista=None):
    curve = C.trova_curve(b["c"])
    lunghezza = max((d for d in b["c"]["d"] if d is not None), default=0)
    numerazione = N.assegna(curve, pista, lunghezza, b["c"])
    righe = C.confronta(a["c"], b["c"], curve)
    apici = []
    for cu in curve:
        d = b["c"]["d"]
        k = min(range(len(d)), key=lambda i: abs((d[i] or -1e9) - cu["apice"]))
        apici.append({"curva": cu["nome"], "n": cu["n"], "x": b["c"]["x"][k], "z": b["c"]["z"][k]})
    return {"a": {"meta": a["meta"], "linea": _linea(a["c"])},
            "b": {"meta": b["meta"], "linea": _linea(b["c"])},
            "curve": righe, "apici": apici, "numerazione": numerazione}


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s",
                        datefmt="%d/%m %H:%M:%S")
    web.run_app(App().crea(), port=PORTA_WEB, access_log=None, print=None)


if __name__ == "__main__":
    main()
