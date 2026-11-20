"""Prova della pagina in un Firefox vero, senza schermo, via geckodriver (WebDriver, solo libreria standard).

    python3 prove/pagina.py [--url http://127.0.0.1:8777] [--cartella prove/schermate]
                            [--larghezze 375,768,1024,1440] [--orizzontale 844x390]

Per ogni larghezza (telefono, tablet, pc) e per il telefono in orizzontale: apre la pagina,
controlla che non ci siano errori JavaScript né scorrimento orizzontale della pagina in nessuna
scheda e che i pulsanti siano alti almeno 40 px, apre le schede Avvisi (con il dizionario di
pronuncia e i tasti), Riassunti (con il primo riassunto) e Traiettoria (con la curva 4), e salva
le foto (`<misura>-<scheda>.png`). Esce con 1 se qualcosa non va.
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


def prova(base, url, cartella, larghezza, altezza, problemi, nome):
    """Una sessione di Firefox a una misura. Restituisce una riga di riassunto."""
    sess = chiama(base, "POST", "/session", {"capabilities": {"alwaysMatch": {
        "moz:firefoxOptions": {"args": ["-headless", f"--width={larghezza}", f"--height={altezza}"]}}}})["sessionId"]
    s = f"/session/{sess}"

    def js(codice):
        return chiama(base, "POST", s + "/execute/sync", {"script": codice, "args": []})

    def foto(scheda):
        png = chiama(base, "GET", s + "/screenshot")
        with open(os.path.join(cartella, f"{nome}-{scheda}.png"), "wb") as f:
            f.write(base64.b64decode(png))

    def clicca(selettore):
        js(f"document.querySelector({json.dumps(selettore)}).click(); return 1;")

    def apri(scheda, attesa=1.0):
        clicca(f'nav button[data-vista="{scheda}"]')
        time.sleep(attesa)
        larga = js("return [document.documentElement.scrollWidth, window.innerWidth];")
        if larga[0] > larga[1] + 1:
            problemi.append(f"{nome}, scheda {scheda}: la pagina scorre in orizzontale ({larga[0]} px su {larga[1]})")
        piccoli = js("""return Array.from(document.querySelectorAll('.vista.attiva button, nav button'))
            .filter(b => b.offsetParent && b.getBoundingClientRect().height < 40)
            .map(b => b.textContent.trim().slice(0, 20));""")
        if piccoli:
            problemi.append(f"{nome}, scheda {scheda}: pulsanti alti meno di 40 px: {piccoli[:5]}")

    try:
        chiama(base, "POST", s + "/window/rect", {"width": larghezza, "height": altezza})
        chiama(base, "POST", s + "/url", {"url": url + "/"})
        js("""window.__errori = [];
            window.addEventListener('error', e => window.__errori.push(String(e.message)));
            window.addEventListener('unhandledrejection', e => window.__errori.push(String(e.reason)));
            return 1;""")
        time.sleep(2)
        apri("radio", 0.5)
        foto("radio")
        apri("avvisi")
        n_cat = js("return document.querySelectorAll('#categorie input').length;")
        n_voci = js("return document.querySelectorAll('#pronuncia li').length;")
        n_tasti = js("return document.querySelectorAll('#tasti select').length;")
        nuovi = js("return ['silenzio_qualifica', 'una_curva_alla_volta'].filter(i => document.getElementById(i)).length;")
        scelta = js("return document.body.innerText.includes('Giocatore 2');")
        foto("avvisi")
        if n_cat < 17:
            problemi.append(f"{nome}: interruttori degli avvisi {n_cat} invece di 17")
        if n_voci < 30:
            problemi.append(f"{nome}: dizionario di pronuncia con {n_voci} voci")
        if n_tasti != 12:
            problemi.append(f"{nome}: tasti UDP Action {n_tasti} invece di 12")
        if nuovi != 2:
            problemi.append(f"{nome}: mancano gli interruttori del silenzio radio o della curva alla volta")
        if scelta:
            problemi.append(f"{nome}: c'è ancora la scelta del giocatore")
        apri("gare", 1.5)
        clicca('#elenco-gare li button')
        time.sleep(1.5)
        schede = js("return Array.from(document.querySelectorAll('#dettaglio-gara .scheda h3')).map(h => h.textContent);")
        js("window.scrollTo(0, 0); return 1;")
        foto("riassunto")
        for atteso in ("Staccate e uscite", "Assetto (consigli indicativi)"):
            if not any(atteso in x for x in schede):
                problemi.append(f"{nome}: nel riassunto manca «{atteso}» (ci sono: {schede})")
        apri("traiettoria", 2.5)
        linee = js("return document.querySelectorAll('#t-mappa polyline').length;")
        bottoni = js("return document.querySelectorAll('#t-curve button').length;")
        foto("traiettoria")
        if linee != 2:
            problemi.append(f"{nome}: traiettoria con {linee} linee invece di 2")
        if bottoni >= 5:
            js("document.querySelectorAll('#t-curve button')[4].click(); return 1;")
            time.sleep(0.8)
            foto("traiettoria-curva4")
        else:
            problemi.append(f"{nome}: traiettoria con {bottoni} bottoni delle curve")
        apri("info")
        foto("info")
        errori = js("return window.__errori;")
        if errori:
            problemi.append(f"{nome}: errori JavaScript: {errori}")
        return (f"{nome}: interruttori {n_cat}, voci di pronuncia {n_voci}, tasti {n_tasti}, "
                f"schede del riassunto {len(schede)}, linee {linee}, bottoni curve {bottoni}, errori JS {len(errori)}")
    finally:
        chiama(base, "DELETE", s)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--url", default="http://127.0.0.1:8777")
    a.add_argument("--cartella", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "schermate"))
    a.add_argument("--larghezze", default="375,768,1024,1440")
    a.add_argument("--orizzontale", default="844x390", help="telefono in orizzontale (vuoto: niente)")
    o = a.parse_args()
    os.makedirs(o.cartella, exist_ok=True)
    misure = [(int(x), 1400 if int(x) < 1000 else 1000, x.strip()) for x in o.larghezze.split(",") if x.strip()]
    if o.orizzontale:
        w, h = o.orizzontale.lower().split("x")
        misure.append((int(w), int(h), f"{w}x{h}"))
    porta = porta_libera()
    gd = subprocess.Popen([os.environ.get("GECKODRIVER", "geckodriver"), "--port", str(porta)],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{porta}"
    problemi = []
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(base + "/status", timeout=1)
                break
            except OSError:
                time.sleep(0.2)
        for larghezza, altezza, nome in misure:
            print(prova(base, o.url, o.cartella, larghezza, altezza, problemi, nome), flush=True)
    finally:
        gd.terminate()
        gd.wait(timeout=10)
    print("OK" if not problemi else "PROBLEMI:\n  " + "\n  ".join(problemi))
    return 1 if problemi else 0


if __name__ == "__main__":
    sys.exit(main())
