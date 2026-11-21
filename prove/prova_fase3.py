"""Prove della fase 3, senza Docker e senza voce (solo libreria standard):

    cd app && python3 ../prove/prova_fase3.py [--registrazioni ../dati/registrazioni] [--giri ../dati/giri]

- dizionario di pronuncia: parole intere, maiuscole, voci di più parole, modifiche salvate;
- tasti: solo il fronte di salita delle UDP Action 1–12;
- registratore: i pacchetti dei menu con session_uid 0 non spezzano la sessione in tanti file;
- numeri ufficiali delle curve: su un giro vero di Montréal (se c'è la biblioteca), se no su
  curve finte messe dove sono quelle ufficiali;
- consigli di guida: dicono che cosa fare, con il dato;
- contatti: la stessa macchina una volta al minuto, anche dopo i flashback;
- livelli di verbosità: ogni frase del codice ha un nome (`livelli.py`).
Con `--registrazioni`: freni caldi detti una volta sola nella qualifica vera con i flashback.
Esce con 1 se qualcosa non va.
"""
import argparse
import glob
import gzip
import json
import os
import sys
import tempfile
import time
import types

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
from ingegnere import curve as C  # noqa: E402
from ingegnere import domande as D  # noqa: E402
from ingegnere import numeri_curve as N  # noqa: E402
from ingegnere import pacchetti as P  # noqa: E402
from ingegnere.impostazioni import Impostazioni  # noqa: E402
from ingegnere.ingegnere import Messaggio  # noqa: E402
from ingegnere.pronuncia import Pronuncia  # noqa: E402
from ingegnere.radio import Radio  # noqa: E402
from ingegnere.registratore import Registratore, leggi  # noqa: E402

try:
    from ingegnere import server as SRV  # noqa: E402
except ModuleNotFoundError:
    _web = types.SimpleNamespace(
        json_response=lambda d, **kw: types.SimpleNamespace(text=json.dumps(d, ensure_ascii=False)),
        HTTPNotFound=RuntimeError,
        HTTPBadRequest=RuntimeError,
    )
    sys.modules.setdefault("aiohttp", types.SimpleNamespace(web=_web, WSMsgType=types.SimpleNamespace()))
    sys.modules.setdefault("numpy", types.SimpleNamespace())
    from ingegnere import server as SRV  # noqa: E402
App = SRV.App

problemi = []


def controlla(cond, cosa):
    print(("  ok  " if cond else "  NO  ") + cosa)
    if not cond:
        problemi.append(cosa)


def pronuncia():
    print("== dizionario di pronuncia")
    tmp = tempfile.mkdtemp()
    p = Pronuncia(os.path.join(tmp, "pronuncia.json"))
    t = p.applica("Virtual safety car. Sei dietro a LECLERC, usa l'overtake. Spazio in pit lane.")
    controlla("vìrciual séifti car" in t, f"voci di più parole e maiuscole: {t}")
    controlla("Leclèr" in t and "l'overtéik" in t, "nomi e parole dopo l'apostrofo")
    controlla("Spazio" in t, "solo parole intere («Spazio» non diventa «Spàzio»)")
    p.metti("Antonelli", "Antonèlli")
    p.togli("Haas")
    q = Pronuncia(os.path.join(tmp, "pronuncia.json"))
    controlla(q.applica("Antonelli e Haas") == "Antonèlli e Haas", "le modifiche restano nel file")
    controlla(any(v["origine"] == "tolta" for v in q.elenco()), "la voce tolta si vede nell'elenco")


def tasti():
    print("== tasti (UDP Action)")
    imp = Impostazioni(os.path.join(tempfile.mkdtemp(), "imp.json"))
    t = D.Tasti()
    r2, a1, a12 = 0x1000, 0x00100000, 0x80000000
    sequenza = [r2 | a1, r2 | a1, r2, r2 | a1 | a12, 0]
    uscite, domande = [], []
    for x in sequenza:
        uscite.append(t.premuti(x, imp))
        domande.append(t.ultima_azione["domanda"] if t.ultima_azione else None)
    controlla(uscite == [[1], [], [], [1, 12], []], f"fronte di salita: {uscite}")
    controlla(domande[0] == "strategia" and domande[3] is None,
              f"UDP Action 1 → strategia, la 12 senza domanda (di partenza): {domande}")

    with tempfile.TemporaryDirectory() as tmp_dati:
        vecchio_dati = SRV.DATI
        SRV.DATI = tmp_dati
        try:
            app = App()
        finally:
            SRV.DATI = vecchio_dati
    radio = Radio(1, app.voce, app.imp, lambda s, d: None, app.stato.tempo)
    app.radio = {1: radio}
    app.stato.reset(0x1234)
    app.stato.formato = 2026
    app.stato.giocatore = 0
    app.stato.ultimo_pacchetto = time.monotonic()
    S = P.STRUTTURE[2026]
    ses = S[P.SESSION]()
    ses.header.packet_format, ses.header.packet_id, ses.header.session_uid = 2026, P.SESSION, 0x1234
    ses.session_type = 15
    ses.track_id = 6
    ses.total_laps = 20
    ses.session_time_left = 600
    ses.game_paused = 0
    app.stato.p[P.SESSION] = P.Pacchetto(P.SESSION, 2026, ses.header, ses)
    lap = S[P.LAP]()
    lap.header.packet_format, lap.header.packet_id, lap.header.session_uid = 2026, P.LAP, 0x1234
    lap.cars[0].current_lap_num = 3
    lap.cars[0].driver_status = 4
    app.stato.p[P.LAP] = P.Pacchetto(P.LAP, 2026, lap.header, lap)

    a9 = 0x00100000 << 8   # silenzio di partenza
    controlla(app._fuori_pista(0) is True, "_fuori_pista True con session_uid == 0")
    app.domande(a1 | a9, 0)
    controlla(app.tasti.prima == (a1 | a9) and not radio.coda and not radio.zitta(),
              "domande() con session_uid == 0 aggiorna tasti ma ignora risposta e silenzio")
    app.domande(0, 0x1234)

    ses.game_paused = 1
    controlla(app._fuori_pista(0x1234) is True, "_fuori_pista True con game_paused == 1")
    app.domande(a1 | a9, 0x1234)
    controlla(not radio.coda and not radio.zitta(),
              "domande() con game_paused == 1 ignora risposta e silenzio")
    app.domande(0, 0x1234)

    ses.game_paused = 0
    lap.cars[0].driver_status = 0
    controlla(app._fuori_pista(0x1234) is True, "_fuori_pista True con driver_status == 0 (garage)")
    app.domande(a1 | a9, 0x1234)
    controlla(not radio.coda and not radio.zitta(),
              "domande() in garage (driver_status == 0) ignora risposta e silenzio")
    app.domande(0, 0x1234)

    lap.cars[0].driver_status = 4
    controlla(app._fuori_pista(0x1234) is False, "_fuori_pista False in pista (driver_status == 4)")
    app.domande(a1, 0x1234)
    controlla(len(radio.coda) == 1 and radio.coda[0].categoria == "domande",
              f"domande() in pista accoda la risposta: {[m.categoria for m in radio.coda]}")

    radio.coda = [
        Messaggio("domande", "d1", "domanda 1", priorita=2, livello=1, ttl=10, creato=1),
        Messaggio("gomme", "g1", "gomme ok", priorita=3, livello=1, ttl=10, creato=1),
        Messaggio("domande", "d2", "domanda 2", priorita=2, livello=1, ttl=10, creato=1),
    ]
    radio.tenuti = [
        Messaggio("domande", "d3", "domanda 3", priorita=2, livello=1, ttl=10, creato=1),
        Messaggio("box", "b1", "box box", priorita=2, livello=1, ttl=10, creato=1),
    ]
    radio.svuota_categoria("domande")
    controlla([m.chiave for m in radio.coda] == ["g1"] and [m.chiave for m in radio.tenuti] == ["b1"],
              f"svuota_categoria('domande') rimuove solo 'domande': coda={[m.chiave for m in radio.coda]} tenuti={[m.chiave for m in radio.tenuti]}")


def registratore():
    print("== registratore (session_uid 0 nei menu)")
    tmp = tempfile.mkdtemp()
    imp = {"registra": True, "registra_motion": False, "max_registrazioni_mb": 100}
    r = Registratore(tmp, imp)
    h = P.Header()

    def pacchetto(uid, pid):
        h.packet_format, h.packet_id, h.session_uid = 2026, pid, uid
        return bytes(h)

    for i in range(20):                     # la sessione, poi i menu: BUTN con uid 0 e classifica
        r.scrivi(pacchetto(0xABC, P.LAP), 0xABC, P.LAP, "gara")
    for i in range(10):
        r.scrivi(pacchetto(0, P.EVENT), 0, P.EVENT, "gara")
        r.scrivi(pacchetto(0xABC, P.FINAL), 0xABC, P.FINAL, "gara")
    r.chiudi()
    r.scrivi(pacchetto(0xABC, P.HISTORY), 0xABC, P.HISTORY, "gara")   # dopo la chiusura: si riapre
    r.chiudi()
    file = glob.glob(os.path.join(tmp, "*.f1rec.gz"))
    controlla(len(file) == 1, f"un file solo per la sessione: {len(file)}")
    tempi = [t for t, _ in leggi(file[0])] if file else []
    controlla(len(tempi) == 31, f"dentro ci sono i 31 pacchetti della sessione, senza quelli con uid 0: {len(tempi)}")
    controlla(all(a <= b for a, b in zip(tempi, tempi[1:])), "i tempi crescono anche dopo la riapertura")


def curve(giri):
    print("== numeri ufficiali delle curve e consigli")
    montreal = sorted(glob.glob(os.path.join(giri, "6", "*.json.gz"))) if giri else []
    validi = []
    for f in montreal:
        try:
            g = json.load(gzip.open(f))
        except (OSError, ValueError):
            continue
        if g["meta"].get("valido") and not g["meta"].get("box"):
            validi.append(g)
    if validi:
        g = min(validi, key=lambda x: x["meta"]["tempo_ms"])
        cu = C.trova_curve(g["c"])
        esito = N.assegna(cu, 6, 4361, g["c"])
        nomi = [x["nome"] for x in cu]
        controlla(esito == "ufficiale" and "10" in nomi and "13 e 14" in nomi,
                  f"Montréal, giro vero: tornante = 10, chicane finale = 13 e 14: {nomi}")
    else:
        frazioni = dict((str(n), f) for n, f in N.UFFICIALI[6][2])
        cu = [{"n": i + 1, "apice": frazioni[k] * 4361 + 40, "vmin": 80}
              for i, k in enumerate(("2", "4", "6", "8", "10", "14"))]
        esito = N.assegna(cu, 6, 4361)
        controlla(esito == "ufficiale" and cu[4]["nome"] == "10", f"Montréal, curve finte: {[x['nome'] for x in cu]}")
    controlla(N.etichetta({"n": 1, "nome": "13 e 14"}, False, "a") == "alle curve 13 e 14", "articoli al plurale")
    controlla(N.assegna([{"n": 1, "apice": 500, "vmin": 80}], 42, 5000) == "nostra", "Madrid: la nostra numerazione")
    r = {"frenata": 100, "vmin": 90, "gas": 200, "rilascio": 150}
    for m, atteso in (({"frenata": 80, "vmin": 90, "gas": 200}, "frena 20 metri più tardi"),
                      ({"frenata": 100, "vmin": 80, "gas": 200, "rilascio": 170}, "rilascia il freno 20 metri prima"),
                      ({"frenata": 100, "vmin": 90, "gas": 230}, "dai gas pieno 30 metri prima"),
                      ({"frenata": 100, "vmin": 90, "gas": 200, "bloccaggio": True}, "evita il bloccaggio")):
        k, frase = C.consiglio(m, r)
        controlla(frase and frase.startswith(atteso), f"consiglio: «{frase}»")


def contatti():
    print("== contatti dopo i flashback")
    from ingegnere.ingegnere import Ingegnere
    from ingegnere.stato import Stato
    st = Stato()
    st.giocatore, st.formato, st.nomi = 0, 2026, {3: "RUSSELL", 5: "SAINZ"}
    E = P.STRUTTURE[2026][P.EVENT]
    ing = Ingegnere(1)

    def coll(altro, t):
        e = E()
        e.code[:] = list(b"COLL")
        e.header.session_time = t
        e.details.collision.vehicle1_idx, e.details.collision.vehicle2_idx = 0, altro
        return [m.testo for m in ing.evento(st, P.Pacchetto(P.EVENT, 2026, e.header, e))]

    detti = []
    for ora, t, altro in ((10, 100, 3), (12, 90, 3), (14, 100, 3), (40, 120, 5), (45, 125, 3), (80, 160, 3)):
        ing.ora = ora                 # l'orologio che non torna indietro; t torna indietro (flashback)
        detti += coll(altro, t)
    controlla(detti == ["Contatto con Russell. Controllo i danni.", "Contatto con Sainz. Controllo i danni.",
                        "Contatto con Russell. Controllo i danni."], f"contatti detti: {detti}")
    controlla(ing.contatti == 3, f"contatti contati: {ing.contatti}")


def livelli():
    print("== livelli di verbosità letti dal codice")
    from ingegnere import livelli as L
    m = L.mancanti()
    controlla(not m, f"ogni frase del codice ha un nome e un livello: {m[:3]}")
    d = L.descrizione()
    controlla(all(d[k] for k in (1, 2, 3)), f"ogni livello aggiunge qualcosa: {[len(d[k]) for k in (1, 2, 3)]}")
    controlla("bandiere gialla, blu e rossa" in d[1] and "consigli di guida dopo le curve" in d[2]
              and "distacchi davanti e dietro a ogni giro" in d[3], "le bandiere a 1, la guida a 2, i distacchi a ogni giro a 3")


def freni(cartella):
    f = os.path.join(cartella, "20261120-010511-sessione.f1rec.gz") if cartella else None
    if not f or not os.path.exists(f):
        print("== freni caldi: registrazione vera della qualifica non trovata, salto")
        return
    print("== freni caldi nella qualifica vera (6 flashback)")
    import subprocess
    out = subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "prova_offline.py"), f],
                         capture_output=True, text=True).stdout
    n = sum(1 for riga in out.splitlines() if " freni " in riga and "tenuta" not in riga and "Freni" in riga)
    controlla(n <= 2, f"«Freni caldi» detto {n} volte (prima: 5 volte in un minuto)")


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--registrazioni")
    a.add_argument("--giri")
    o = a.parse_args()
    pronuncia()
    tasti()
    registratore()
    contatti()
    livelli()
    curve(o.giri)
    freni(o.registrazioni)
    print("\nESITO:", "OK" if not problemi else "NON VA")
    return 1 if problemi else 0


if __name__ == "__main__":
    sys.exit(main())
