"""Prove della fase 5 (0.5.0), senza Docker e senza voce (solo libreria standard):

    cd app && python3 ../prove/prova_fase5.py

- tasto del silenzio: per 30 s passano solo le priorità 1, poi tornano le frasi ancora valide;
  premuto di nuovo riaccende;
- «dove perdo?»: le due curve peggiori dell'ultimo giro con il consiglio;
- undercut con l'usura vera di chi è davanti (e senza: il calcolo di prima);
- set per la sosta: una mescola diversa in gara asciutta, che arrivi in fondo, la più veloce;
- sulle gare del simulatore (normale 2026 e 2025, pulita, prove): box sotto safety car, set per la
  sosta, previsioni di usura e carburante, spotter, passo, settori.
Esce con 1 se qualcosa non va.
"""
import asyncio
import os
import subprocess
import sys
import tempfile
import types

APP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app")
sys.path.insert(0, APP)
from ingegnere import domande as D  # noqa: E402
from ingegnere import gara as G  # noqa: E402
from ingegnere.analisi import Analisi  # noqa: E402
from ingegnere.ingegnere import Messaggio  # noqa: E402
from ingegnere.radio import Radio  # noqa: E402

problemi = []


def controlla(cond, cosa):
    print(("  ok  " if cond else "  NO  ") + cosa)
    if not cond:
        problemi.append(cosa)


class Imp(dict):
    def acceso(self, c):
        return True


def silenzio():
    print("== tasto del silenzio")
    imp = Imp(verbosita=3, voce="r", velocita=1.0, effetto_radio=2, volume=100)

    class Voce:
        def sintetizza(self, testo, *a):
            return "k", 0.2

    async def prova():
        ora = [100.0]
        detti = []

        async def invia(slot, d):
            detti.append(d["testo"])

        r = Radio(1, Voce(), imp, invia, lambda: ora[0])
        r.avvia()
        secondi = r.zitto(0.8)
        r.metti([Messaggio("guida", "g", "consiglio", livello=1, ttl=6, creato=100),
                 Messaggio("distacchi", "d", "attacca", livello=1, ttl=6, creato=100),
                 Messaggio("box", "b", "box box", priorita=2, livello=1, ttl=6, creato=100),
                 Messaggio("bandiere", "y", "gialla", priorita=1, livello=1, ttl=6, creato=100)])
        await asyncio.sleep(0.5)
        durante = list(detti)
        for _ in range(12):
            await asyncio.sleep(0.25)
            ora[0] += 0.25
        dopo = list(detti)
        r.zitto(30)
        di_nuovo = r.zitto(30)
        return secondi, durante, dopo, di_nuovo

    secondi, durante, dopo, di_nuovo = asyncio.run(prova())
    controlla(secondi > 0.5, "il tasto zittisce la radio")
    controlla(durante == ["gialla"], f"durante il silenzio solo la priorità 1: {durante}")
    controlla(set(dopo) == {"gialla", "consiglio", "box box"}, f"dopo tornano quelle ancora valide (non «attacca»): {dopo}")
    controlla(di_nuovo == 0, "premuto di nuovo riaccende")


def dove_perdo():
    print("== «dove perdo?»")
    an = types.SimpleNamespace(
        curve=[{"n": 1, "nome": "1 e 2"}, {"n": 2, "nome": "6"}, {"n": 3, "nome": "10"}],
        ultime_perdite={"1 e 2": (0.32, "frena 20 metri più tardi", 300), "6": (0.05, None, 1200),
                        "10": (0.6, "dai gas pieno 30 metri prima", 2700)})
    testo = D._dove_perdo(None, None, an, 0, None, None)
    controlla(testo == "Curva 10: dai gas pieno 30 metri prima, perdi mezzo secondo. "
                       "Curve 1 e 2: frena 20 metri più tardi, perdi 3 decimi.", f"risposta: {testo}")
    an.ultime_perdite = {"6": (0.05, None, 1200)}
    controlla("niente di grosso" in D._dove_perdo(None, None, an, 0, None, None), "senza perdite vere lo dice")


def undercut():
    print("== undercut con l'usura vera degli altri")
    imp = Imp(pilota="io", salva_giri=False, assetto=False, una_curva_alla_volta=True, silenzio_qualifica=True)
    an = Analisi(imp, None, types.SimpleNamespace(perdita_box=lambda p: (20.0, True)))
    an.usure = [(g, [2.0 * g] * 4, False) for g in range(1, 8)]      # tu: 2 per cento a giro
    sta = types.SimpleNamespace(cars=[types.SimpleNamespace(tyres_age_laps=6)] * 3)
    st = types.SimpleNamespace(get=lambda pid: sta)
    vecchio = G.usura_altro
    try:
        G.usura_altro = lambda st_, j: 30.0
        eta, usura = an.eta_gomme(st, 1)
        controlla(usura == 30.0 and abs(eta - 15) < 0.01, f"con l'usura vera (30 per cento): {eta:.1f} giri equivalenti")
        G.usura_altro = lambda st_, j: None
        eta, usura = an.eta_gomme(st, 1)
        controlla(usura is None and eta == 6, "senza l'usura: l'età vera del set, come prima")
    finally:
        G.usura_altro = vecchio


def set_sosta():
    print("== set per la sosta")

    def s(mescola, vita, delta, usura=0, disp=1, montato=0):
        return types.SimpleNamespace(visual_tyre_compound=mescola, usable_life=vita, lap_delta_time=delta,
                                     wear=usura, available=disp, fitted=montato)

    ts = types.SimpleNamespace(sets=[s(16, 10, -500), s(17, 13, 0, montato=1), s(17, 13, 0), s(18, 17, 400),
                                     s(7, 27, 4000)])
    storia = types.SimpleNamespace(num_tyre_stints=1, stints=[types.SimpleNamespace(tyre_visual_compound=17)])
    ses = types.SimpleNamespace(weather=0)
    st = types.SimpleNamespace(set_gomme={0: ts}, storia={0: storia}, sessione=lambda: ses)
    controlla(G.set_per_sosta(st, 0, 9)[:2] == ("soft", True), f"9 giri: le soft (le medie le hai già): {G.set_per_sosta(st, 0, 9)}")
    controlla(G.set_per_sosta(st, 0, 15)[0] == "dure", f"15 giri: le dure, le soft non arrivano: {G.set_per_sosta(st, 0, 15)}")
    ses.weather = 4
    controlla(G.set_per_sosta(st, 0, 15)[0] == "intermedie", "con la pioggia: intermedie")
    controlla(G.frase_set(("medie", False, 6, 12)) == "Per la sosta: medie usate al 6 per cento, durano circa 12 giri.",
              "la frase del set")


def simulatore():
    print("== gare del simulatore")
    tmp = tempfile.mkdtemp()
    prove = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prova_offline.py")

    def gira(nome, *argomenti):
        f = os.path.join(tmp, nome + ".f1rec.gz")
        subprocess.run([sys.executable, "-m", "ingegnere.simulatore", "--uscita", f, *argomenti],
                       cwd=APP, check=True, capture_output=True)
        return subprocess.run([sys.executable, prove, f], cwd=APP, capture_output=True, text=True).stdout

    for formato in ("2026", "2025"):
        out = gira("gara" + formato, "--formato", formato)
        for chiave in ("box_sc", "mescola", "prev_usura", "prev_benzina", "spotter"):
            controlla(f" {chiave} " in out, f"gara {formato}: «{chiave}» c'è")
        controlla("ESITO: OK" in out, f"gara {formato}: prova offline OK")
    out = gira("pulita", "--pulita", "--giri", "10")
    controlla(" passo " in out and "a giro" in out, "gara pulita: confronto di passo")
    out = gira("prove", "--sessione", "prove", "--giri", "5")
    controlla(" settori " in out and "Settore 1" in out, "prove: tempi di settore")


def main():
    silenzio()
    dove_perdo()
    undercut()
    set_sosta()
    simulatore()
    print("\nESITO:", "OK" if not problemi else "NON VA")
    return 1 if problemi else 0


if __name__ == "__main__":
    sys.exit(main())
