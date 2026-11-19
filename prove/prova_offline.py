"""Prova offline dell'ingegnere, senza Docker, senza rete e senza voce (solo libreria standard):

    cd app && python3 ../prove/prova_offline.py FILE.f1rec.gz [--verbosita 3]

Rilegge una registrazione, la passa a Stato + Ingegnere come fa il server (eventi subito,
regole ogni 0,2 s), filtra come la Radio (categoria accesa e verbosità) e stampa i messaggi.
Alla fine: conteggio per categoria, categorie mai scattate, pacchetti scartati, riassunto.
Esce con 1 se una categoria non scatta mai o se manca il riassunto.
"""
import argparse
import json
import os
import sys
import tempfile
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
from ingegnere import pacchetti as P  # noqa: E402
from ingegnere import riassunto as R  # noqa: E402
from ingegnere.analisi import Analisi  # noqa: E402
from ingegnere.strategia import Piste  # noqa: E402
from ingegnere.traccia import Biblioteca  # noqa: E402
from ingegnere.impostazioni import CATEGORIE, Impostazioni  # noqa: E402
from ingegnere.ingegnere import Ingegnere  # noqa: E402
from ingegnere.registratore import leggi  # noqa: E402
from ingegnere.stato import Stato  # noqa: E402

DA_DECODIFICARE = {P.SESSION, P.LAP, P.EVENT, P.PARTICIPANTS, P.TELEMETRY, P.STATUS, P.FINAL,
                   P.DAMAGE, P.HISTORY, P.TELEMETRY2, P.MOTION, P.MOTIONEX, P.SETUPS}


def main():
    a = argparse.ArgumentParser()
    a.add_argument("file")
    a.add_argument("--verbosita", type=int, default=3)
    a.add_argument("--quieto", action="store_true", help="non stampare i messaggi uno per uno")
    a.add_argument("--dati", help="cartella per la biblioteca dei giri e piste.json (di partenza: temporanea)")
    a.add_argument("--pilota", default="io")
    a.add_argument("--json", help="salva qui il riassunto completo")
    o = a.parse_args()
    tmp = tempfile.mkdtemp()
    imp = Impostazioni(os.path.join(tmp, "imp.json"))
    imp.aggiorna({"verbosita": o.verbosita, "pilota": o.pilota})
    dati = o.dati or tmp
    an = Analisi(imp, Biblioteca(os.path.join(dati, "giri")), Piste(os.path.join(dati, "piste.json")))
    soste = []
    st = Stato()
    ing = {1: Ingegnere(1)}   # un giocatore solo (player_car_index)
    detti, conta, chiavi = [], Counter(), Counter()
    riassunti = {}
    prossimo = 0.0

    def ammesso(m):
        return imp.acceso(m.categoria) and imp["verbosita"] >= m.livello

    def dici(slot, msgs, t):
        for m in msgs:
            if not ammesso(m):
                continue
            detti.append((t, slot, m))
            conta[m.categoria] += 1
            chiavi[(slot, m.chiave)] += 1
            if not o.quieto:
                print(f"{t:7.1f}  G{slot} P{m.priorita} {m.categoria:<10} {m.chiave:<16} {m.testo}")

    def chiudi():
        for slot, i in ing.items():
            if st.indice(slot) is None:
                continue
            r = R.costruisci(st, i, an)
            if r:
                riassunti[slot] = r

    for t, buf in leggi(o.file):
        h = P.intestazione(buf)
        if h is None or h.packet_format not in P.STRUTTURE:
            st.scartati["formato"] += 1
            continue
        if st.session_uid and h.session_uid != st.session_uid:
            chiudi()
        pk = P.decodifica(buf, DA_DECODIFICARE)
        if pk is None:
            st.scartati["taglia"] += 1
            st.taglie_scartate[(h.packet_format, h.packet_id, len(buf))] += 1
            continue
        if st.aggiorna(pk, "prova"):
            for i in ing.values():
                i.nuova_sessione()
            an.nuova_sessione()
        if pk.id == P.TELEMETRY and pk.dati is not None:
            an.campione(st)
        elif pk.id == P.LAP and pk.dati is not None:
            soste += an.strategia.osserva(st)
        if pk.id == P.EVENT and pk.dati is not None:
            for slot, i in ing.items():
                dici(slot, i.evento(st, pk), pk.header.session_time)
            if P.codice_evento(pk) == "SEND":
                chiudi()
        elif pk.id == P.FINAL and pk.dati is not None:
            chiudi()
        if t >= prossimo:
            prossimo = t + 0.2
            for slot, i in ing.items():
                msgs = i.valuta(st)
                r = i.riepilogo_giro(imp, st.tempo())
                if r:
                    msgs.append(r)
                nuove, soste = soste, []
                msgs += an.valuta(st, nuove)
                dici(slot, msgs, st.tempo())

    print("\n== messaggi per categoria ==")
    for c in CATEGORIE:
        print(f"  {c:<11} {conta[c]}")
    mai = [c for c in CATEGORIE if not conta[c] and not (c == "ali" and st.formato == 2025)]  # nel 2025 non ci sono
    print("categorie mai scattate:", ", ".join(mai) or "nessuna")
    raffica = [(k, n) for k, n in chiavi.items() if n > 6]
    print("chiavi ripetute più di 6 volte:", raffica or "nessuna")
    print("pacchetti scartati:", dict(st.scartati) or 0, dict(st.taglie_scartate) or "")
    print("formato:", st.formato, "· pacchetti ricevuti:", sum(st.ricevuti.values()))
    for slot, r in riassunti.items():
        print(f"\n== riassunto giocatore {slot} ==")
        print(json.dumps({k: v for k, v in r.items() if k not in ("giri", "guida", "assetto", "ali")},
                         ensure_ascii=False, indent=1))
        g = r.get("guida")
        if g:
            print("guida, dove perdi di più:", [(c["curva"], c["perdita_media_s"], c["causa_frequente"]) for c in g["dove_perdi"]])
            for c in g["curve"]:
                print("   curva", c["curva"], "apice", c["apice_m"], "vmin", c["vmin_rif"], "frenata", c["frenata_rif_m"],
                      "gas", c["gas_rif_m"], "perdita media", c["perdita_media_s"], c["causa_frequente"])
        a_ = r.get("assetto")
        if a_:
            print("assetto, dati:", json.dumps(a_.get("dati"), ensure_ascii=False))
            for c in a_.get("consigli", []):
                print("   consiglio:", c["consiglio"], "|", c["dato"])
        if r.get("ali"):
            print("ali:", json.dumps(r["ali"], ensure_ascii=False))
        if o.json:
            with open(o.json, "w", encoding="utf-8") as f:
                json.dump(r, f, ensure_ascii=False, indent=1)
        for g in r["giri"]:
            print("   ", g["giro"], g["tempo"], g["s1"], g["s2"], g["s3"], "valido" if g["valido"] else "NON VALIDO",
                  "box" if g["box"] else "", "SC" if g["safety_car"] else "", g["posizione"], g["gomma"], g["usura_max"])
    ok = not mai and 1 in riassunti
    print("\nESITO:", "OK" if ok else "NON VA")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
