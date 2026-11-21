"""Prove della fase 6 · Blocco 1 & Blocco 2 (0.6.0), senza Docker e senza voce (solo libreria standard):

    cd app && python3 ../prove/prova_fase6.py

Verifica tutte le 12 funzioni del Blocco 1 e tutte le funzioni del Blocco 2:
- Blocco 1: tetto consigli, FTLP/soste altri, delta live, 4 ruote/ERS, ERS/lift&coast,
  brake bias, motore/PU/aria pulita, gomme/blistering+curva, target lap, settori avversari,
  bandiera blu/doppiaggi, track limits;
- Blocco 2: Piano A/B/C (pre-partenza, cambi in gara, domanda strategia, stato live),
  chiamate box esplicite («Box questo giro», «Box per undercut», «Resta fuori»),
  confronto con compagno di squadra / riferimento più veloce (in memoria, live, riassunto),
  analisi stacco partenza, mappa frenate per curva, setup aggregato, API `/api/pregara`,
  simulatore + prova_offline end-to-end.
Esce con 1 se qualcosa non va.
"""
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import types

APP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app")
sys.path.insert(0, APP)
os.environ["DATI"] = tempfile.mkdtemp()

from ingegnere import assetto as A  # noqa: E402
from ingegnere import curve as C  # noqa: E402
from ingegnere import domande as D  # noqa: E402
from ingegnere import gara as G  # noqa: E402
from ingegnere import livelli as L  # noqa: E402
from ingegnere import pacchetti as P  # noqa: E402
from ingegnere import pregara as PG  # noqa: E402
from ingegnere import riassunto as R  # noqa: E402
from ingegnere.analisi import Analisi  # noqa: E402
from ingegnere.impostazioni import Impostazioni  # noqa: E402
from ingegnere.ingegnere import Ingegnere  # noqa: E402
from ingegnere.pronuncia import Pronuncia  # noqa: E402
from ingegnere.stato import Stato  # noqa: E402
from ingegnere.strategia import Piste, calcola_piani  # noqa: E402
from ingegnere.traccia import Biblioteca, Giro  # noqa: E402

try:
    from ingegnere.server import App  # noqa: E402
except ModuleNotFoundError:
    _web = types.SimpleNamespace(
        json_response=lambda d, **kw: types.SimpleNamespace(text=json.dumps(d, ensure_ascii=False)),
        HTTPNotFound=RuntimeError,
        HTTPBadRequest=RuntimeError,
    )
    sys.modules.setdefault("aiohttp", types.SimpleNamespace(web=_web, WSMsgType=types.SimpleNamespace()))
    sys.modules.setdefault("numpy", types.SimpleNamespace())
    from ingegnere.server import App  # noqa: E402

problemi = []


def controlla(cond, cosa):
    print(("  ok  " if cond else "  NO  ") + cosa)
    if not cond:
        problemi.append(cosa)


def _stato_base(fmt=2026, n=4, idx=0, nomi=None):
    st = Stato()
    st.reset(0x6001)
    st.formato = fmt
    st.giocatore = idx
    st.n_auto = n
    st.ultimo_pacchetto = 1e9
    st.nomi = nomi or {0: "ROSSI", 1: "VERSTAPPEN", 2: "LECLERC", 3: "SAINZ"}
    S = P.STRUTTURE[fmt]

    ses = S[P.SESSION]()
    ses.header.packet_format, ses.header.packet_id, ses.header.session_uid = fmt, P.SESSION, 0x6001
    ses.session_type = 15
    ses.track_id = 6
    ses.track_length = 4361
    ses.total_laps = 20
    ses.pit_stop_window_ideal_lap = 8
    ses.pit_stop_window_latest_lap = 10
    st.p[P.SESSION] = P.Pacchetto(P.SESSION, fmt, ses.header, ses)

    lap = S[P.LAP]()
    lap.header.packet_format, lap.header.packet_id, lap.header.session_uid = fmt, P.LAP, 0x6001
    lap.header.player_car_index = idx
    for i in range(n):
        lap.cars[i].car_position = i + 1
        lap.cars[i].grid_position = i + 1
        lap.cars[i].current_lap_num = 3
        lap.cars[i].driver_status = 4
        lap.cars[i].result_status = 2
    st.p[P.LAP] = P.Pacchetto(P.LAP, fmt, lap.header, lap)

    tel = S[P.TELEMETRY]()
    tel.header.packet_format, tel.header.packet_id, tel.header.session_uid = fmt, P.TELEMETRY, 0x6001
    for i in range(n):
        tel.cars[i].speed = 220
        tel.cars[i].throttle = 1.0
        tel.cars[i].engine_temperature = 110
        tel.cars[i].brakes_temperature[:] = [550, 550, 550, 550]
        tel.cars[i].tyres_surface_temperature[:] = [95, 95, 95, 95]
        tel.cars[i].tyres_inner_temperature[:] = [95, 95, 95, 95]
    st.p[P.TELEMETRY] = P.Pacchetto(P.TELEMETRY, fmt, tel.header, tel)

    sta = S[P.STATUS]()
    sta.header.packet_format, sta.header.packet_id, sta.header.session_uid = fmt, P.STATUS, 0x6001
    for i in range(n):
        sta.cars[i].front_brake_bias = 58
        sta.cars[i].fuel_remaining_laps = 0.5
        sta.cars[i].fuel_in_tank = 25.0
        sta.cars[i].ers_store_energy = 2.8e6
        sta.cars[i].ers_deploy_mode = 1
        sta.cars[i].visual_tyre_compound = 17
        sta.cars[i].tyres_age_laps = 3
    st.p[P.STATUS] = P.Pacchetto(P.STATUS, fmt, sta.header, sta)

    dmg = S[P.DAMAGE]()
    dmg.header.packet_format, dmg.header.packet_id, dmg.header.session_uid = fmt, P.DAMAGE, 0x6001
    for i in range(n):
        dmg.cars[i].tyres_wear[:] = [15.0, 15.0, 16.0, 16.0]
    st.p[P.DAMAGE] = P.Pacchetto(P.DAMAGE, fmt, dmg.header, dmg)

    mex = S[P.MOTIONEX]()
    mex.header.packet_format, mex.header.packet_id, mex.header.session_uid = fmt, P.MOTIONEX, 0x6001
    st.p[P.MOTIONEX] = P.Pacchetto(P.MOTIONEX, fmt, mex.header, mex)

    if fmt == 2026:
        t2 = S[P.TELEMETRY2]()
        t2.header.packet_format, t2.header.packet_id, t2.header.session_uid = fmt, P.TELEMETRY2, 0x6001
        t2.cars[idx].regulations_2026 = 1
        st.p[P.TELEMETRY2] = P.Pacchetto(P.TELEMETRY2, fmt, t2.header, t2)

    return st, ses, lap, tel, sta, dmg, mex


def _traccia_finta():
    # pista 4000 m, una curva attorno a 900 m (frenata a 780 m, apice 900 m a 80 km/h, gas 1020 m)
    c = {k: [] for k in ("t", "d", "x", "z", "v", "th", "br", "st", "g", "sf", "sr", "sb", "yr", "wa", "ts", "ti", "bt", "am", "aa")}
    t = 0.0
    for d in range(0, 4001, 20):
        v = 280
        br = 0.0
        th = 1.0
        if 780 <= d < 900:
            v = int(280 - (d - 780) * (200 / 120))
            br = 0.9
            th = 0.0
        elif 900 <= d <= 1040:
            v = int(80 + (d - 900) * (200 / 140))
            th = 0.5 if d < 1000 else 1.0
        t += 20.0 / max(v / 3.6, 15.0)
        c["t"].append(round(t, 3))
        c["d"].append(float(d))
        c["x"].append(float(d))
        c["z"].append(0.0)
        c["v"].append(v)
        c["th"].append(th)
        c["br"].append(br)
        c["st"].append(0.0)
        c["g"].append(5)
        c["sf"].append(0.0)
        c["sr"].append(0.0)
        c["sb"].append(0.0)
        c["yr"].append(0.0)
        c["wa"].append(0.0)
        c["ts"].append([95, 95, 95, 95])
        c["ti"].append([95, 95, 95, 95])
        c["bt"].append([550, 550, 550, 550])
        c["am"].append(0)
        c["aa"].append(0)
    return c


def test_tetto_consigli():
    print("== 1. tetto consigli di guida per sessione")
    tmp = tempfile.mkdtemp()
    imp = Impostazioni(os.path.join(tmp, "imp.json"))
    controlla(imp["max_consigli_guida"] == 12, f"default max_consigli_guida = {imp['max_consigli_guida']}")
    imp.aggiorna({"max_consigli_guida": 2})
    controlla(imp["max_consigli_guida"] == 2, "aggiorna max_consigli_guida = 2")

    st, ses, lap, tel, sta, dmg, _ = _stato_base()
    an = Analisi(imp, Biblioteca(os.path.join(tmp, "giri")), Piste(os.path.join(tmp, "piste.json")))
    rif_c = _traccia_finta()
    an._imposta_rif({"pista": 6, "tempo_ms": 60000}, rif_c, 4000)

    lento = dict(rif_c)
    lento["t"] = [round(x * 1.12, 3) for x in rif_c["t"]]
    lento["br"] = [0.9 if 700 <= d < 900 else 0.0 for d in lento["d"]]  # frena 80 m prima

    emessi = 0
    for giro in (2, 3, 4):
        an.trac.giro = types.SimpleNamespace(c=lento, numero=giro, invalido=False, box=False, sc=False)
        an.valutate = set()
        an.dette_giro = 0
        an.ultimo.clear()
        lap.cars[0].current_lap_num = giro
        lap.cars[0].lap_distance = 1300.0
        out = []
        an._guida(out, giro * 100.0, st, ses, lap.cars[0])
        emessi += len(out)
    controlla(emessi == 2, f"con tetto=2 su 3 giri emessi {emessi} consigli (attesi 2)")

    imp.aggiorna({"max_consigli_guida": 0})
    an.consigli_sessione = 0
    emessi_illim = 0
    for giro in (5, 6, 7):
        an.valutate = set()
        an.dette_giro = 0
        an.ultimo.clear()
        lap.cars[0].current_lap_num = giro
        out = []
        an._guida(out, giro * 100.0, st, ses, lap.cars[0])
        emessi_illim += len(out)
    controlla(emessi_illim == 3, f"con tetto=0 (illimitato) emessi {emessi_illim} consigli")


def test_ftlp_e_soste_altri():
    print("== 2. giro veloce (FTLP) e soste avversari")
    st, ses, lap, tel, sta, dmg, _ = _stato_base(idx=0)
    ing = Ingegnere(1)
    E = P.STRUTTURE[2026][P.EVENT]
    ev = E()
    ev.header.packet_format, ev.header.packet_id, ev.header.session_time = 2026, P.EVENT, 210.0
    ev.code[:] = list(b"FTLP")
    ev.details.fastest_lap.vehicle_idx = 2
    ev.details.fastest_lap.lap_time = 74.25
    msgs = ing.evento(st, P.Pacchetto(P.EVENT, 2026, ev.header, ev))
    controlla(len(msgs) == 1 and "Leclerc giro più veloce, 1, 14 e 2" in msgs[0].testo,
              f"FTLP avversario: {msgs[0].testo if msgs else msgs}")
    p = Pronuncia(None)
    controlla("Leclèr" in p.applica(msgs[0].testo), "nome pilota passa dal dizionario di pronuncia")

    # soste ai box degli avversari
    tmp = tempfile.mkdtemp()
    imp = Impostazioni(os.path.join(tmp, "imp.json"))
    an = Analisi(imp, Biblioteca(os.path.join(tmp, "giri")), Piste(os.path.join(tmp, "piste.json")))
    lap.cars[0].car_position = 1
    lap.cars[1].car_position = 2
    lap.cars[2].car_position = 3
    lap.cars[3].car_position = 4
    lap.cars[1].delta_to_car_in_front_ms_part = 1500
    lap.cars[2].delta_to_car_in_front_ms_part = 5000
    lap.cars[3].delta_to_car_in_front_ms_part = 8000

    # giro 3: auto 1 (dietro < 4s → copri) e auto 3 (P4, non coperta) entrano ai box
    lap.header.session_time = 180.0
    an.strategia.osserva(st)
    lap.cars[1].pit_status = 1
    lap.cars[3].pit_status = 1
    nuove = an.strategia.osserva(st)
    an.ora = 180.0
    out = []
    an._strategia(out, 180.0, st, ses, lap.cars[0], 0, nuove)
    controlla(any(m.chiave == "sosta_altri" and "Verstappen" in m.testo for m in out),
              f"entrata coperta: {[m.testo for m in out]}")

    # escono dai box con dure (18): per auto 1 (coperta) non ripete, per auto 3 (Sainz) annuncia
    lap.cars[1].pit_status = 0
    lap.cars[1].num_pit_stops = 1
    sta.cars[1].visual_tyre_compound = 18
    lap.cars[3].pit_status = 0
    lap.cars[3].num_pit_stops = 1
    sta.cars[3].visual_tyre_compound = 18
    an.strategia.osserva(st)
    an.ora = 200.0
    out2 = []
    an._strategia(out2, 200.0, st, ses, lap.cars[0], 0, [])
    testi = [m.testo for m in out2 if m.chiave == "sosta_gomma"]
    controlla(len(testi) == 1 and "Sainz si è fermato, monta le dure." in testi[0],
              f"uscita box avversari: {testi}")


def test_delta_e_cruscotto():
    print("== 3 & 4. delta live + stato 4 ruote e ERS")
    tmp = tempfile.mkdtemp()
    imp = Impostazioni(os.path.join(tmp, "imp.json"))
    st, ses, lap, tel, sta, dmg, _ = _stato_base()
    an = Analisi(imp, Biblioteca(os.path.join(tmp, "giri")), Piste(os.path.join(tmp, "piste.json")))
    an._imposta_rif({"pista": 6, "tempo_ms": 20000}, {
        "d": [0.0, 500.0, 1000.0], "t": [0.0, 10.0, 20.0], "v": [200, 200, 200],
        "th": [1, 1, 1], "br": [0, 0, 0], "st": [0, 0, 0], "g": [5, 5, 5],
        "x": [0, 500, 1000], "z": [0, 0, 0], "sf": [0, 0, 0], "sr": [0, 0, 0], "sb": [0, 0, 0],
        "yr": [0, 0, 0], "wa": [0, 0, 0], "ts": [[95]*4]*3, "ti": [[95]*4]*3, "bt": [[500]*4]*3,
        "am": [0]*3, "aa": [0]*3,
    }, 1000)
    lap.cars[0].lap_distance = 500.0
    lap.cars[0].current_lap_time_in_ms = 9500
    controlla(an.delta_live(st) == -0.5, f"delta più veloce: {an.delta_live(st)}")
    lap.cars[0].current_lap_time_in_ms = 10420
    controlla(an.delta_live(st) == 0.42, f"delta più lento: {an.delta_live(st)}")
    lap.cars[0].pit_status = 1
    controlla(an.delta_live(st) is None, "in pit delta è None")

    # stato_per di App
    app = App()
    app.stato = st
    app.analisi = an
    app.radio[1] = types.SimpleNamespace(in_silenzio=False, zitto_fino=0.0, detti=[])
    lap.cars[0].pit_status = 0
    sta.cars[0].ers_deploy_mode = 3
    sta.cars[0].ers_store_energy = 2.0e6
    t2 = st.p[P.TELEMETRY2].dati
    t2.cars[0].overtake_available = 1
    t2.cars[0].overtake_active = 1
    dmg.cars[0].tyres_wear[:] = [21.0, 22.0, 28.0, 26.0]
    dmg.cars[0].tyre_blisters[:] = [0, 0, 18, 0]
    tel.cars[0].tyres_surface_temperature[:] = [96, 97, 108, 104]
    tel.cars[0].tyres_inner_temperature[:] = [94, 95, 105, 101]
    s = app.stato_per()["auto"]
    controlla(s.get("delta") == 0.42 and s.get("ers_modo") == "Overtake" and s.get("overtake_attivo") is True,
              f"stato_per ERS/delta: delta={s.get('delta')}, modo={s.get('ers_modo')}, ot={s.get('overtake_attivo')}")
    ruote = s.get("ruote") or []
    controlla(len(ruote) == 4 and ruote[0] == {"eti": "AS", "usura": 28, "blister": 18, "ts": 108, "ti": 105},
              f"stato_per 4 ruote: {ruote[0] if ruote else ruote}")


def test_ers_lift_coast():
    print("== 5. ERS attacco/difesa e Lift & Coast")
    st, ses, lap, tel, sta, dmg, _ = _stato_base(idx=1)
    lap.cars[0].car_position = 1
    lap.cars[1].car_position = 2
    lap.cars[2].car_position = 3
    lap.cars[1].delta_to_car_in_front_ms_part = 1050
    lap.cars[2].delta_to_car_in_front_ms_part = 2500
    t2 = st.p[P.TELEMETRY2].dati
    t2.cars[1].overtake_available = 1
    sta.cars[1].ers_store_energy = 3.0e6
    ing = Ingegnere(1)
    ing.ora = 100.0
    lap.header.session_time = 100.0
    out = ing.valuta(st)
    controlla(any(m.chiave == "ers_attacco" for m in out), f"ERS attacco: {[m.chiave for m in out]}")

    # difesa
    lap.cars[1].delta_to_car_in_front_ms_part = 3000
    lap.cars[2].delta_to_car_in_front_ms_part = 900
    t2.cars[1].overtake_available = 0
    ing.ora = 120.0
    lap.header.session_time = 120.0
    out = ing.valuta(st)
    controlla(any(m.chiave == "ers_difesa" for m in out), f"ERS difesa: {[m.chiave for m in out]}")

    # batteria bassa + carburante basso → lift & coast + cooldown
    sta.cars[1].ers_store_energy = 0.4e6
    sta.cars[1].fuel_remaining_laps = -0.3
    ing.ora = 140.0
    lap.header.session_time = 140.0
    out = ing.valuta(st)
    chiavi = {m.chiave for m in out}
    controlla("lift_coast_ers" in chiavi and "lift_coast_fuel" in chiavi, f"lift & coast ERS/fuel: {chiavi}")
    ing.ora = 150.0
    lap.header.session_time = 150.0
    out_cd = ing.valuta(st)
    controlla(not any(m.chiave.startswith("lift_coast") for m in out_cd), "cooldown lift & coast rispettato")


def test_brake_bias():
    print("== 6. Brake Bias live")
    tmp = tempfile.mkdtemp()
    imp = Impostazioni(os.path.join(tmp, "imp.json"))
    st, ses, lap, tel, sta, dmg, mex = _stato_base()
    an = Analisi(imp, Biblioteca(os.path.join(tmp, "giri")), Piste(os.path.join(tmp, "piste.json")))
    tel.cars[0].brake = 0.9
    tel.cars[0].speed = 180
    # primo bloccaggio davanti
    an.ora = 10.0
    mex.wheel_slip_ratio[:] = [0.0, 0.0, -0.32, -0.28]
    an._rileva_bloccaggi(st, 0)
    mex.wheel_slip_ratio[:] = [0.0, 0.0, 0.0, 0.0]
    an._rileva_bloccaggi(st, 0)
    # secondo bloccaggio davanti dopo 5 s
    an.ora = 15.0
    mex.wheel_slip_ratio[:] = [0.0, 0.0, -0.35, -0.1]
    an._rileva_bloccaggi(st, 0)
    out = []
    an._brake_bias(out, 15.0, st, lap.cars[0], 0)
    controlla(len(out) == 1 and "indietro" in out[0].testo and "56" in out[0].testo,
              f"bloccaggi davanti -> indietro: {out[0].testo if out else out}")

    # sbilanciamento calore posteriore dopo cooldown
    mex.wheel_slip_ratio[:] = [0.0, 0.0, 0.0, 0.0]
    tel.cars[0].brake = 0.0
    sta.cars[0].front_brake_bias = 54
    tel.cars[0].brakes_temperature[:] = [960, 960, 620, 620]
    an.ora = 400.0
    out2 = []
    an._brake_bias(out2, 400.0, st, lap.cars[0], 0)
    an.ora = 405.0
    an._brake_bias(out2, 405.0, st, lap.cars[0], 0)
    controlla(len(out2) == 1 and "avanti" in out2[0].testo and "56" in out2[0].testo,
              f"posteriore caldo -> avanti: {out2[0].testo if out2 else out2}")


def test_motore_pu_aria_pulita():
    print("== 7. motore, usura PU e aria pulita")
    st, ses, lap, tel, sta, dmg, _ = _stato_base(idx=1)
    lap.cars[0].car_position = 1
    lap.cars[1].car_position = 2
    lap.cars[1].delta_to_car_in_front_ms_part = 600
    tel.cars[1].engine_temperature = 122
    ing = Ingegnere(1)
    out = []
    for ts in (100.0, 101.0, 102.0, 103.0):
        lap.header.session_time = ts
        out += ing.valuta(st)
    controlla(any(m.chiave == "aria_pulita" for m in out), f"aria pulita in scia: {[m.testo for m in out]}")

    lap.cars[1].delta_to_car_in_front_ms_part = 3000
    tel.cars[1].engine_temperature = 127
    dmg.cars[1].engine_ice_wear = 78
    out2 = []
    for ts in (110.0, 111.0, 112.0, 113.0, 114.0):
        lap.header.session_time = ts
        out2 += ing.valuta(st)
    chiavi = {m.chiave for m in out2}
    controlla("motore_caldo" in chiavi and "usura_pu" in chiavi, f"motore caldo e usura PU: {chiavi}")

    dmg.cars[1].engine_ice_wear = 92
    lap.header.session_time = 180.0
    out3 = ing.valuta(st)
    controlla(any(m.chiave == "usura_pu_critica" for m in out3), f"usura critica PU (92%): {[m.testo for m in out3]}")


def test_gomme_e_blistering():
    print("== 8. temperature gomme superficie/carcassa e blistering con curva")
    tmp = tempfile.mkdtemp()
    imp = Impostazioni(os.path.join(tmp, "imp.json"))
    st, ses, lap, tel, sta, dmg, _ = _stato_base()
    an = Analisi(imp, Biblioteca(os.path.join(tmp, "giri")), Piste(os.path.join(tmp, "piste.json")))
    an.curve = [{"n": 1, "nome": "4", "apice": 900.0, "inizio": 700.0, "fine": 1100.0}]
    lap.cars[0].lap_distance = 900.0
    tel.cars[0].tyres_surface_temperature[:] = [96, 97, 118, 102]
    # 2 giri con surriscaldamento in curva 4
    an.ora = 100.0
    an._gomme_calde(out := [], 100.0, st, lap.cars[0], 0)
    an._gomme_giro = set()
    an.ora = 104.0
    an._gomme_calde(out, 104.0, st, lap.cars[0], 0)
    controlla(len(out) == 1 and "superficie" in out[0].testo and "curva 4" in out[0].testo,
              f"superficie calda + curva: {out[0].testo if out else out}")

    dmg.cars[0].tyre_blisters[:] = [0, 0, 26, 0]
    an.ora = 110.0
    out_b = []
    an._gomme_calde(out_b, 110.0, st, lap.cars[0], 0)
    controlla(len(out_b) == 1 and "Blistering" in out_b[0].testo and "curva 4" in out_b[0].testo,
              f"blistering + curva: {out_b[0].testo if out_b else out_b}")


def test_target_lap():
    print("== 9. Target Lap")
    tmp = tempfile.mkdtemp()
    imp = Impostazioni(os.path.join(tmp, "imp.json"))
    st, ses, lap, tel, sta, dmg, _ = _stato_base()
    an = Analisi(imp, Biblioteca(os.path.join(tmp, "giri")), Piste(os.path.join(tmp, "piste.json")))
    an.strategia.tempi[0] = [(2, 80000, False, False), (3, 79800, False, False)]
    an.usure = [(2, [18.0]*4, False), (3, [29.0]*4, False)]
    dmg.cars[0].tyres_wear[:] = [29.0]*4
    lap.cars[0].current_lap_num = 4
    lap.cars[0].last_lap_time_in_ms = 79500
    ses.pit_stop_window_ideal_lap = 8  # 29 + 11 * 4 = 73 > 72 -> spingendo troppo
    out = []
    an.ora = 300.0
    G.target_lap_avviso(an, out, 300.0, st, ses, lap.cars[0], 0, True)
    controlla(len(out) == 1 and out[0].chiave == "target_lap" and "gira sul" in out[0].testo,
              f"avviso target lap: {out[0].testo if out else out}")
    risp = D.rispondi("strategia", st, Ingegnere(1), an)
    controlla(risp is not None and "Passo obiettivo" in risp.testo,
              f"domanda strategia include target lap: {risp.testo if risp else risp}")
    r = an.riassunto(st)
    controlla("target_lap" in (r.get("strategia") or {}), f"riassunto include target_lap: {r.get('strategia')}")


def test_settori_avversari():
    print("== 10. confronto settori contro avversari")
    tmp = tempfile.mkdtemp()
    imp = Impostazioni(os.path.join(tmp, "imp.json"))
    st, ses, lap, tel, sta, dmg, _ = _stato_base(idx=1)
    an = Analisi(imp, Biblioteca(os.path.join(tmp, "giri")), Piste(os.path.join(tmp, "piste.json")))
    lap.cars[0].car_position = 1
    lap.cars[1].car_position = 2
    lap.cars[1].delta_to_car_in_front_ms_part = 1200
    lap.cars[0].current_lap_num = lap.cars[1].current_lap_num = 3
    # Verstappen (0) ha già finito S2 in 24.000 s, giocatore (1) finisce S2 in 24.350 s
    lap.cars[0].sector = 2
    lap.cars[0].sector1_time_ms_part = 22000
    lap.cars[0].sector2_time_ms_part = 24000
    lap.cars[1].sector = 1
    lap.cars[1].sector1_time_ms_part = 22050
    an.ora = 250.0
    G.aggiorna_settori_auto(an, st)
    out = []
    G.settori_avversari(an, out, 250.0, st, ses, lap.cars[1], 1, False)

    lap.cars[1].sector = 2
    lap.cars[1].sector2_time_ms_part = 24350
    an.ora = 275.0
    G.aggiorna_settori_auto(an, st)
    G.settori_avversari(an, out, 275.0, st, ses, lap.cars[1], 1, False)
    controlla(len(out) == 1 and "Rossi guadagna 4 decimi nel settore 2" in out[0].testo,
              f"settore contro avversario: {out[0].testo if out else out}")

    # differenza < 0.2 s non scatta
    an.ultimo.clear()
    lap.cars[1].sector = 0
    lap.cars[1].current_lap_num = lap.cars[0].current_lap_num = 4
    lap.cars[0].sector = 1
    lap.cars[0].sector1_time_ms_part = 22000
    lap.cars[1].sector1_time_ms_part = 22120
    G.aggiorna_settori_auto(an, st)
    out_piccolo = []
    G.settori_avversari(an, out_piccolo, 350.0, st, ses, lap.cars[1], 1, False)
    lap.cars[1].sector = 1
    G.aggiorna_settori_auto(an, st)
    G.settori_avversari(an, out_piccolo, 372.0, st, ses, lap.cars[1], 1, False)
    controlla(not out_piccolo, f"differenza 0.12 s ignorata: {out_piccolo}")


def test_doppiaggi_e_blu():
    print("== 11. doppiaggi e bandiera blu mirata")
    st, ses, lap, tel, sta, dmg, _ = _stato_base(idx=3)
    lap.cars[3].car_position = 4
    lap.cars[3].lap_distance = 1000.0
    lap.cars[3].total_distance = 5361.0
    lap.cars[1].car_position = 1   # Verstappen leader che doppia
    lap.cars[1].lap_distance = 850.0
    lap.cars[1].total_distance = 9572.0
    sta.cars[3].vehicle_fia_flags = 2
    ing = Ingegnere(1)
    lap.header.session_time = 400.0
    out = ing.valuta(st)
    controlla(any(m.chiave == "blu" and "Verstappen" in m.testo for m in out),
              f"bandiera blu con nome: {[m.testo for m in out]}")

    # giocatore davanti raggiunge Sainz (idx=2) doppiato
    st2, ses2, lap2, tel2, sta2, _, _ = _stato_base(idx=0)
    lap2.cars[0].car_position = 1
    lap2.cars[0].lap_distance = 1000.0
    lap2.cars[0].total_distance = 9722.0
    lap2.cars[3].car_position = 18
    lap2.cars[3].lap_distance = 1080.0   # 80 m avanti (~1.3 s a 220 km/h)
    lap2.cars[3].total_distance = 5441.0
    ing2 = Ingegnere(1)
    lap2.header.session_time = 420.0
    out2 = ing2.valuta(st2)
    controlla(any(m.chiave == "doppiaggio" and "Sainz" in m.testo for m in out2),
              f"doppiato davanti: {[m.testo for m in out2]}")


def test_track_limits():
    print("== 12. track limits prima della penalità")
    st, ses, lap, tel, sta, dmg, _ = _stato_base()
    ing = Ingegnere(1)
    lap.header.session_time = 100.0
    ing.valuta(st)
    lap.cars[0].corner_cutting_warnings = 1
    lap.header.session_time = 110.0
    out1 = ing.valuta(st)
    controlla(any(m.chiave == "avvertimento" and "Primo avvertimento" in m.testo for m in out1),
              f"1° avvertimento: {[m.testo for m in out1]}")
    lap.cars[0].corner_cutting_warnings = 2
    lap.header.session_time = 125.0
    out2 = ing.valuta(st)
    controlla(any(m.chiave == "avvertimento_ultimo" and "al prossimo è penalità" in m.testo for m in out2),
              f"2° avvertimento: {[m.testo for m in out2]}")
    # nessun doppione da evento PENA (tipo=5, infringement=7)
    E = P.STRUTTURE[2026][P.EVENT]
    ev = E()
    ev.header.packet_format, ev.header.packet_id, ev.header.session_time = 2026, P.EVENT, 125.0
    ev.code[:] = list(b"PENA")
    ev.details.penalty.penalty_type = 5
    ev.details.penalty.infringement_type = 7
    ev.details.penalty.vehicle_idx = 0
    out_p = ing.evento(st, P.Pacchetto(P.EVENT, 2026, ev.header, ev))
    controlla(not out_p, f"PENA (5,7) non duplica il messaggio track limits: {out_p}")


def test_piani_e_chiamate_box():
    print("== 13. Piano A/B/C e chiamate box esplicite / resta fuori")
    tmp = tempfile.mkdtemp()
    imp = Impostazioni(os.path.join(tmp, "imp.json"))
    st, ses, lap, tel, sta, dmg, _ = _stato_base(idx=0)
    ses.total_laps = 20
    ses.pit_stop_window_ideal_lap = 8
    ses.pit_stop_window_latest_lap = 10
    S = P.STRUTTURE[2026]
    ts = S[P.TYRESETS]()
    ts.header.packet_format, ts.header.packet_id, ts.header.session_uid = 2026, P.TYRESETS, 0x6001
    for k, (comp, vita, delta, disp, fit) in enumerate((
        (16, 10, -400, 1, 0),
        (17, 14, 0, 0, 1),
        (17, 14, 0, 1, 0),
        (18, 22, 350, 1, 0),
    )):
        ts.sets[k].visual_tyre_compound = comp
        ts.sets[k].usable_life = vita
        ts.sets[k].lap_delta_time = delta
        ts.sets[k].available = disp
        ts.sets[k].fitted = fit
    st.set_gomme[0] = ts

    an = Analisi(imp, Biblioteca(os.path.join(tmp, "giri")), Piste(os.path.join(tmp, "piste.json")))
    # Pre-partenza (in griglia/garage driver_status=0): calcola piani A/B/C senza emettere frasi
    lap.cars[0].driver_status = 0
    out_pre = an.valuta(st, [])
    controlla(not out_pre and an.piani_gara is not None and set(an.piani_gara["piani"]) == {"A", "B", "C"},
              f"piani pre-partenza calcolati: {list((an.piani_gara or {}).get('piani', {}))}")
    controlla(an.piani_gara["attivo"] == "A" and an.piani_gara["piani"]["B"]["soste"] == 2,
              f"Piano A attivo e Piano B 2 soste: {an.piani_gara['piani']['B']}")

    # In gara: degrado alto -> passa a Piano B
    lap.cars[0].driver_status = 4
    lap.cars[0].current_lap_num = 3
    an.usure = [(1, [15.0] * 4, False), (2, [31.0] * 4, False)]
    dmg.cars[0].tyres_wear[:] = [47.0] * 4  # 16%/giro -> 47 + 16*5 = 127% al giro 8 -> Piano B
    an.ora = 200.0
    out_b = []
    G.aggiorna_piani(an, out_b, 200.0, st, ses, lap.cars[0], 0, [])
    controlla(an.piano_attivo == "B" and any(m.chiave == "piano_strategia" and "Piano B" in m.testo for m in out_b),
              f"passaggio a Piano B: {[m.testo for m in out_b]}")

    # Domanda strategia e stato_per includono il piano attivo
    risp = D.rispondi("strategia", st, Ingegnere(1), an)
    controlla(risp is not None and "Piano attivo: Piano B" in risp.testo,
              f"domanda strategia cita Piano B: {risp.testo if risp else risp}")
    app = App()
    app.stato = st
    app.analisi = an
    app.radio[1] = types.SimpleNamespace(in_silenzio=False, zitto_fino=0.0, detti=[])
    s_live = app.stato_per()
    controlla((s_live.get("auto") or {}).get("piano", {}).get("attivo") == "B",
              f"stato_per espone piano attivo: {(s_live.get('auto') or {}).get('piano')}")

    # Chiamata esplicita «Box questo giro» sul giro target di Piano B (giro 6) nella seconda metà del giro
    target_b = an.piani_gara["piani"]["B"]["target_giro"]
    lap.cars[0].current_lap_num = target_b
    lap.cars[0].lap_distance = 3200.0
    an.ora = 400.0
    out_box = []
    G.aggiorna_piani(an, out_box, 400.0, st, ses, lap.cars[0], 0, [])
    controlla(any(m.chiave == "box_questo_giro" and "Box questo giro" in m.testo for m in out_box),
              f"chiamata Box questo giro: {[m.testo for m in out_box]}")

    # Undercut («Box per undercut») poi avversario davanti rientra proprio ora -> «Resta fuori»
    an2 = Analisi(imp, Biblioteca(os.path.join(tmp, "giri2")), Piste(os.path.join(tmp, "piste2.json")))
    an2.strategia.tempi[0] = [(g, 80000 + g * 350, False, False) for g in range(2, 7)]
    an2.usure = [(g, [6.0 * g] * 4, False) for g in range(2, 7)]
    lap.cars[0].car_position = 2
    lap.cars[1].car_position = 1
    lap.cars[0].delta_to_car_in_front_ms_part = 1400
    lap.cars[0].current_lap_num = 8
    sta.cars[1].tyres_age_laps = 8
    dmg.cars[1].tyres_wear[:] = [56.0] * 4
    an2.ora = 500.0
    out_uc = []
    an2._strategia(out_uc, 500.0, st, ses, lap.cars[0], 0, [])
    G.aggiorna_piani(an2, out_uc, 500.0, st, ses, lap.cars[0], 0, [])
    uc_msgs = [m for m in out_uc if m.chiave == "undercut"]
    controlla(len(uc_msgs) == 1 and "Box per undercut" in uc_msgs[0].testo
              and not any(m.chiave == "box_questo_giro" for m in out_uc),
              f"Box per undercut senza doppioni: {[m.testo for m in out_uc]}")

    # L'avversario davanti (1) entra in pit lane prima della nostra sosta -> Resta fuori
    lap.cars[1].pit_status = 1
    an2.ora = 505.0
    out_rf = []
    G.aggiorna_piani(an2, out_rf, 505.0, st, ses, lap.cars[0], 0, [1])
    controlla(any(m.chiave == "resta_fuori" and "Resta fuori" in m.testo and "Verstappen" in m.testo for m in out_rf),
              f"Resta fuori quando rientra chi precede: {[m.testo for m in out_rf]}")

    # Pioggia in arrivo -> Piano C + Resta fuori se era aperto box asciutto (dopo cooldown)
    lap.cars[1].pit_status = 0
    an2._box_chiamato = {"giro": 8, "motivo": "piano", "bersaglio": None, "ora": 535.0, "piano": "A"}
    ses.num_weather_forecast_samples = 2
    ses.weather_forecast_samples[0].session_type = 15
    ses.weather_forecast_samples[0].time_offset = 0
    ses.weather_forecast_samples[1].session_type = 15
    ses.weather_forecast_samples[1].time_offset = 5
    ses.weather_forecast_samples[1].weather = 3
    ses.weather_forecast_samples[1].rain_percentage = 80
    an2.ora = 540.0
    out_c = []
    G.aggiorna_piani(an2, out_c, 512.0, st, ses, lap.cars[0], 0, [])
    controlla(an2.piano_attivo == "C" and any(m.chiave == "resta_fuori" and "Piano C" in m.testo for m in out_c),
              f"Piano C + Resta fuori per pioggia in arrivo: {[m.testo for m in out_c]}")


def test_compagno_e_riferimento():
    print("== 14. confronto compagno di squadra / avversario più veloce")
    tmp = tempfile.mkdtemp()
    imp = Impostazioni(os.path.join(tmp, "imp.json"))
    bib_dir = os.path.join(tmp, "giri")
    st, ses, lap, tel, sta, dmg, _ = _stato_base(idx=0, n=4)
    S = P.STRUTTURE[2026]
    par = S[P.PARTICIPANTS]()
    par.header.packet_format, par.header.packet_id, par.header.session_uid = 2026, P.PARTICIPANTS, 0x6001
    par.num_active_cars = 4
    # 0=ROSSI (team 1, player), 1=VERSTAPPEN (team 1, compagno), 2=LECLERC (team 2, rivale veloce), 3=SAINZ (team 3, telemetria privata online)
    for i, (team, yt, ai) in enumerate(((1, 1, 0), (1, 1, 1), (2, 1, 1), (3, 0, 0))):
        par.cars[i].team_id = team
        par.cars[i].your_telemetry = yt
        par.cars[i].ai_controlled = ai
        par.cars[i].name = st.nomi[i].encode()
    st.p[P.PARTICIPANTS] = P.Pacchetto(P.PARTICIPANTS, 2026, par.header, par)

    an = Analisi(imp, Biblioteca(bib_dir), Piste(os.path.join(tmp, "piste.json")))
    rif_c = _traccia_finta()
    lento_c = dict(rif_c)
    lento_c["t"] = [round(x * 1.08, 3) for x in rif_c["t"]]
    lento_c["v"] = [max(40, v - 14) if 840 <= d <= 960 else v for d, v in zip(rif_c["d"], rif_c["v"])]
    an._imposta_rif({"pista": 6, "tempo_ms": 64800, "giro": 2}, lento_c, 4000)

    # Popoliamo in memoria un giro pulito del compagno (1), del rivale (2) e dell'auto privata (3)
    def carica_altro(car_idx, traccia, giro_n, last_ms):
        lap.cars[car_idx].current_lap_num = giro_n
        lap.cars[car_idx].driver_status = 4
        lap.cars[car_idx].result_status = 2
        for k in range(len(traccia["d"])):
            lap.cars[car_idx].lap_distance = traccia["d"][k]
            lap.cars[car_idx].current_lap_time_in_ms = int(traccia["t"][k] * 1000)
            tel.cars[car_idx].speed = traccia["v"][k]
            tel.cars[car_idx].throttle = traccia["th"][k]
            tel.cars[car_idx].brake = traccia["br"][k]
            tel.cars[car_idx].steer = traccia["st"][k]
            an.rif_ext.campione(st, 0)
        lap.cars[car_idx].current_lap_num = giro_n + 1
        lap.cars[car_idx].last_lap_time_in_ms = last_ms
        an.rif_ext.campione(st, 0)

    carica_altro(1, rif_c, 2, 60000)   # compagno veloce (60.0 s)
    carica_altro(3, rif_c, 2, 58000)   # auto 3 con telemetria privata online (deve essere ignorata!)
    controlla(1 in an.rif_ext.migliori and 3 not in an.rif_ext.migliori,
              f"compagno tracciato in memoria, auto privata esclusa: {list(an.rif_ext.migliori)}")
    controlla(not os.path.exists(bib_dir), "nessuna traccia altrui salvata in dati/giri/")

    # In curva il giocatore perde tempo rispetto al compagno -> consiglio mirato
    an.trac.giro = types.SimpleNamespace(c=lento_c, numero=3, invalido=False, box=False, sc=False)
    an.rif = ({"pista": 6, "tempo_ms": 64800, "giro": 2}, lento_c)
    an.rif_misure = {cu["n"]: C.misura(lento_c, cu) for cu in an.curve}
    an.valutate = set()
    an.dette_giro = 0
    lap.cars[0].current_lap_num = 3
    lap.cars[0].lap_distance = 1300.0
    out_g = []
    an._guida(out_g, 300.0, st, ses, lap.cars[0])
    controlla(len(out_g) == 1 and "il compagno" in out_g[0].testo and "perdi" in out_g[0].testo,
              f"consiglio live vs compagno: {out_g[0].testo if out_g else out_g}")

    # Riassunto espone il confronto con il compagno
    r = an.riassunto(st)
    cr = r.get("confronto_riferimento") or {}
    controlla(cr.get("tipo") == "compagno" and cr.get("pilota") == "VERSTAPPEN" and len(cr.get("curve") or []) >= 1,
              f"riassunto confronto compagno: tipo={cr.get('tipo')} pilota={cr.get('pilota')}")

    # Se il compagno si ritira o è più lento, fallback al rivale più veloce (2: Leclerc)
    fast_c = dict(rif_c)
    fast_c["t"] = [round(x * 0.96, 3) for x in rif_c["t"]]
    carica_altro(2, fast_c, 2, 57500)
    lap.cars[1].result_status = 7  # compagno ritirato
    sel = an.rif_ext.seleziona(st, 0, 64800)
    controlla(sel is not None and sel["tipo"] == "riferimento" and sel["idx"] == 2,
              f"compagno ritirato -> fallback rivale più veloce: {sel['nome'] if sel else sel}")


def test_pregara_e_stacco():
    print("== 15. stacco partenza, mappa frenate, setup aggregato e /api/pregara")
    tmp = tempfile.mkdtemp()
    imp = Impostazioni(os.path.join(tmp, "imp.json"))
    bib = Biblioteca(os.path.join(tmp, "giri"))
    piste = Piste(os.path.join(tmp, "piste.json"))
    piste.aggiungi_perdita(6, 20.5)
    cart_riass = os.path.join(tmp, "riassunti")
    os.makedirs(cart_riass, exist_ok=True)

    # Salva un giro pulito con marce nella biblioteca di prova per pista 6
    rif_c = _traccia_finta()
    rif_c["g"] = [2 if 850 <= d <= 960 else 7 for d in rif_c["d"]]
    g_obj = Giro(3)
    g_obj.c = rif_c
    bib.salva(g_obj, {"pista": 6, "tempo_ms": 60000, "valido": True, "sessione": "qualifica",
                      "session_uid": 0x6001, "pilota": "io", "formato": 2026})

    # Simula stacco partenza (STLG -> LGOT -> clutch release + gas 100% + pattinamento)
    st, ses, lap, tel, sta, dmg, mex = _stato_base(idx=0)
    an = Analisi(imp, bib, piste)
    E = P.STRUTTURE[2026][P.EVENT]
    for ev_code in (b"STLG", b"LGOT"):
        ev = E()
        ev.header.packet_format, ev.header.packet_id, ev.header.session_uid, ev.header.session_time = 2026, P.EVENT, 0x6001, 10.0
        ev.code[:] = list(ev_code)
        an.evento(st, P.Pacchetto(P.EVENT, 2026, ev.header, ev))

    ses.start_reaction_time = 0.52
    lap.cars[0].current_lap_num = 1
    lap.cars[0].grid_position = 8
    lap.cars[0].car_position = 7
    for step in range(45):
        dt = step * 0.1
        lap.header.session_time = 10.0 + dt
        tel.header.session_time = 10.0 + dt
        lap.cars[0].lap_distance = max(0.0, (dt - 0.5) * 28.0)
        tel.cars[0].speed = min(180, int(max(0.0, (dt - 0.5) * 35.0)))
        tel.cars[0].clutch = 100 if dt < 0.5 else 0
        tel.cars[0].throttle = 0.65 if dt < 0.5 else 1.0
        tel.cars[0].engine_rpm = 11500 if dt < 0.8 else 9000
        tel.cars[0].gear = 1 if tel.cars[0].speed < 90 else 2
        mex.wheel_slip_ratio[:] = [1.8, 1.8, 0.0, 0.0] if 0.5 <= dt <= 1.1 else [0.05, 0.05, 0.0, 0.0]
        an.stacco.campione(st, 0)

    sp = an.stacco.chiudi()
    controlla(sp is not None and sp["tempo_reazione_s"] == 0.52 and sp["pattinamento_max"] >= 1.5
              and "pattinamento" in sp["consiglio"].lower(),
              f"stacco partenza analizzato: rt={sp.get('tempo_reazione_s')} slip={sp.get('pattinamento_max')}")

    # Salva un riassunto completo di gara con assetto e stacco_partenza
    an.giri.append(({"giro": 3, "valido": True, "box": False, "safety_car": False}, rif_c))
    ing = Ingegnere(1)
    ing.giri.append({"giro": 1, "tempo_ms": 65000, "valido": True, "box": False, "safety_car": False})
    r_tot = R.costruisci(st, ing, an)
    r_tot["assetto"] = A.analizza([rif_c], {"ala_anteriore": 18, "ala_posteriore": 16,
                                            "differenziale_in_trazione": 70, "differenziale_in_rilascio": 50,
                                            "pressione_freni": 100, "ripartizione_freni": 57,
                                            "campanatura_anteriore": -3.5, "campanatura_posteriore": -2.0,
                                            "pressioni_gomme": [22.5, 22.5, 21.5, 21.5]},
                                      [2.0, 2.0, 4.0, 4.0], (310, 322), True)
    R.salva(cart_riass, r_tot)

    # API / dati_pregara
    pg = PG.dati_pregara(6, bib, piste, cart_riass, pilota="io")
    fren = pg.get("frenate") or {}
    c0 = (fren.get("curve") or [{}])[0]
    controlla(len(fren.get("curve") or []) >= 1 and c0.get("frenata_m") == 780
              and c0.get("vingresso") == 280 and c0.get("vmin") == 80 and c0.get("marcia_min") == 2
              and c0.get("gas_m") == 1000,
              f"mappa frenate per curva: {c0}")
    setup_cons = (pg.get("setup") or {}).get("consigli") or []
    controlla(len(setup_cons) >= 1 and not any("sospension" in c["consiglio"].lower() or "altezz" in c["consiglio"].lower() for c in setup_cons),
              f"setup aggregato senza sospensioni/altezze: {[c['area'] for c in setup_cons]}")
    controlla(set((pg.get("piani") or {}).get("piani") or {}) == {"A", "B", "C"}
              and len((pg.get("partenza") or {}).get("storico") or []) == 1,
              f"dati_pregara completi: piani={list((pg.get('piani') or {}).get('piani', {}))} stacchi={len((pg.get('partenza') or {}).get('storico', []))}")

    # Test handler App.api_pregara
    app = App()
    app.bib = bib
    app.analisi.strategia.piste = piste
    app.cartella_riassunti = cart_riass
    resp = asyncio.run(app.api_pregara(types.SimpleNamespace(match_info={"pista": "6"})))
    body = json.loads(resp.text)
    controlla(body.get("pista") == 6 and len((body.get("frenate") or {}).get("curve") or []) >= 1,
              "App.api_pregara risponde con JSON valido")


def test_simulatore_blocco2():
    print("== 16. simulatore end-to-end (stacco e confronto compagno nel riassunto)")
    tmp = tempfile.mkdtemp()
    f = os.path.join(tmp, "gara.f1rec.gz")
    out_r = os.path.join(tmp, "riass.json")
    subprocess.run([sys.executable, "-m", "ingegnere.simulatore", "--uscita", f],
                   cwd=APP, check=True, capture_output=True)
    prove = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prova_offline.py")
    res = subprocess.run([sys.executable, prove, f, "--quieto", "--json", out_r],
                         cwd=APP, capture_output=True, text=True)
    controlla(res.returncode == 0 and "ESITO: OK" in res.stdout, f"prova_offline su simulatore OK (rc={res.returncode})")
    with open(out_r, encoding="utf-8") as fp:
        rj = json.load(fp)
    controlla("stacco_partenza" in rj and "confronto_riferimento" in rj
              and (rj.get("strategia") or {}).get("piano_attivo") in {"A", "B", "C"},
              f"riassunto simulatore contiene stacco, confronto e piano: keys={sorted(rj.keys())}")


def main():
    test_tetto_consigli()
    test_ftlp_e_soste_altri()
    test_delta_e_cruscotto()
    test_ers_lift_coast()
    test_brake_bias()
    test_motore_pu_aria_pulita()
    test_gomme_e_blistering()
    test_target_lap()
    test_settori_avversari()
    test_doppiaggi_e_blu()
    test_track_limits()
    test_piani_e_chiamate_box()
    test_compagno_e_riferimento()
    test_pregara_e_stacco()
    test_simulatore_blocco2()
    m = L.mancanti()
    controlla(not m, f"livelli.mancanti() vuoto: {m}")
    print("\nESITO:", "OK" if not problemi else "NON VA")
    return 1 if problemi else 0


if __name__ == "__main__":
    sys.exit(main())
