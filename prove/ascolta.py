"""Prova dal vivo: si collega alla web app come un cellulare e stampa quello che dice la radio.

    docker run --rm --network host -v $PWD/prove:/prove ingegnere-f1:locale \
        python /prove/ascolta.py [--secondi 120] [--url http://127.0.0.1:8777]

Controlla anche che le frasi non si sovrappongano (la frase dopo arriva quando la prima è
finita, salvo le urgenti che interrompono) e che ogni audio si scarichi davvero.
Esce con 1 se ci sono sovrapposizioni o audio mancanti.
"""

import argparse
import asyncio
import json
import sys
import time

import aiohttp


async def main():
    a = argparse.ArgumentParser()
    a.add_argument("--secondi", type=float, default=120)
    a.add_argument("--url", default="http://127.0.0.1:8777")
    o = a.parse_args()
    frasi, problemi = [], []
    fine_prec = 0.0
    inizio = time.monotonic()
    async with aiohttp.ClientSession() as s:
        async with s.ws_connect(f"{o.url}/ws") as ws:
            while time.monotonic() - inizio < o.secondi:
                try:
                    msg = await ws.receive(timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                if msg.type != aiohttp.WSMsgType.TEXT:
                    break
                d = json.loads(msg.data)
                if d.get("tipo") != "radio":
                    continue
                adesso = time.monotonic()
                async with s.get(o.url + d["url"]) as r:
                    corpo = await r.read()
                    if r.status != 200 or corpo[:4] != b"RIFF":
                        problemi.append(f"audio mancante: {d['url']}")
                sopra = adesso < fine_prec - 0.05 and not d.get("interrompi")
                if sopra:
                    problemi.append(f"sovrapposta: {d['testo']}")
                fine_prec = adesso + d["durata"]
                frasi.append(d)
                print(f"{adesso - inizio:7.1f}s P{d['priorita']} {d['categoria']:<11} "
                      f"{'[INTERROMPE] ' if d.get('interrompi') else ''}{d['testo']} "
                      f"({d['durata']} s, {len(corpo) // 1024} KB){'  <-- SOPRA' if sopra else ''}",
                      flush=True)
    print(f"\n{len(frasi)} frasi, {len(problemi)} problemi")
    for p in problemi:
        print("  -", p)
    return 1 if problemi else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
