"""Prova della pagina in un Firefox vero, senza schermo, via geckodriver (WebDriver, solo libreria standard).

    python3 prove/pagina.py [--url http://127.0.0.1:8777] [--cartella prove/schermate]

Apre la pagina a larghezza di telefono, controlla che non ci siano errori JavaScript, apre le
schede Avvisi (con il dizionario di pronuncia e i tasti), Riassunti (con il primo riassunto) e Traiettoria (con la curva 4), e salva le foto.
Esce con 1 se qualcosa non va.
"""
import argparse
import base64
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request


def porta_libera():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def chiama(base, metodo, percorso, dati=None):
    req = urllib.request.Request(base + percorso, method=metodo,
                                 data=json.dumps(dati).encode() if dati is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())["value"]


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--url", default="http://127.0.0.1:8777")
    a.add_argument("--cartella", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "schermate"))
    o = a.parse_args()
    os.makedirs(o.cartella, exist_ok=True)
    porta = porta_libera()
    gd = subprocess.Popen([os.environ.get("GECKODRIVER", "geckodriver"), "--port", str(porta)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{porta}"
    problemi = []
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(base + "/status", timeout=1)
                break
            except OSError:
                time.sleep(0.2)
        sess = chiama(base, "POST", "/session", {"capabilities": {"alwaysMatch": {
            "moz:firefoxOptions": {"args": ["-headless", "--width=390", "--height=1400"]}}}})["sessionId"]
        s = f"/session/{sess}"
        chiama(base, "POST", s + "/window/rect", {"width": 390, "height": 1400})
        chiama(base, "POST", s + "/url", {"url": o.url + "/"})
        chiama(base, "POST", s + "/execute/sync", {"script": """
            window.__errori = [];
            window.addEventListener('error', e => window.__errori.push(String(e.message)));
            window.addEventListener('unhandledrejection', e => window.__errori.push(String(e.reason)));
            return 1;""", "args": []})

        def js(codice):
            return chiama(base, "POST", s + "/execute/sync", {"script": codice, "args": []})

        def foto(nome):
            png = chiama(base, "GET", s + "/screenshot")
            with open(os.path.join(o.cartella, nome), "wb") as f:
                f.write(base64.b64decode(png))

        def clicca(selettore):
            js(f"document.querySelector({json.dumps(selettore)}).click(); return 1;")

        time.sleep(2)
        foto("p-radio.png")
        clicca('nav button[data-vista="avvisi"]')
        time.sleep(1)
        n_cat = js("return document.querySelectorAll('#categorie input').length;")
        scelta = js("return document.body.innerText.includes('Giocatore 2');")
        n_voci = js("return document.querySelectorAll('#pronuncia li').length;")
        n_tasti = js("return document.querySelectorAll('#tasti select').length;")
        nuovi = js("return ['silenzio_qualifica', 'una_curva_alla_volta'].filter(i => document.getElementById(i)).length;")
        foto("p-avvisi.png")
        if n_cat < 17:
            problemi.append(f"interruttori degli avvisi: {n_cat} invece di 17")
        if n_voci < 30:
            problemi.append(f"dizionario di pronuncia: {n_voci} voci")
        if n_tasti != 12:
            problemi.append(f"tasti UDP Action: {n_tasti} invece di 12")
        if nuovi != 2:
            problemi.append("mancano gli interruttori del silenzio radio o della curva alla volta")
        if scelta:
            problemi.append("c'è ancora la scelta del giocatore")
        clicca('nav button[data-vista="gare"]')
        time.sleep(1.5)
        clicca('#elenco-gare li button')
        time.sleep(1.5)
        schede = js("return Array.from(document.querySelectorAll('#dettaglio-gara .scheda h3')).map(h => h.textContent);")
        foto("p-riassunto.png")
        for atteso in ("Staccate e uscite", "Assetto (consigli indicativi)"):
            if not any(atteso in x for x in schede):
                problemi.append(f"nel riassunto manca «{atteso}» (ci sono: {schede})")
        clicca('nav button[data-vista="traiettoria"]')
        time.sleep(2.5)
        linee = js("return document.querySelectorAll('#t-mappa polyline').length;")
        bottoni = js("return document.querySelectorAll('#t-curve button').length;")
        foto("p-traiettoria.png")
        if linee != 2:
            problemi.append(f"traiettoria: {linee} linee invece di 2")
        if bottoni >= 5:
            js("document.querySelectorAll('#t-curve button')[4].click(); return 1;")
            time.sleep(0.8)
            foto("p-traiettoria-curva4.png")
        else:
            problemi.append(f"traiettoria: {bottoni} bottoni delle curve")
        errori = js("return window.__errori;")
        if errori:
            problemi.append(f"errori JavaScript: {errori}")
        print(f"interruttori {n_cat}, voci di pronuncia {n_voci}, tasti {n_tasti}, schede del riassunto {schede}, linee {linee}, bottoni curve {bottoni}")
        chiama(base, "DELETE", s)
    finally:
        gd.terminate()
        gd.wait(timeout=10)
    print("OK" if not problemi else "PROBLEMI:\n  " + "\n  ".join(problemi))
    return 1 if problemi else 0


if __name__ == "__main__":
    sys.exit(main())
