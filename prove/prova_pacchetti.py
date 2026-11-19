"""Prova del decodificatore (solo libreria standard):
    cd app && python3 ../prove/prova_pacchetti.py
- le taglie del formato 2025 devono essere quelle della specifica ufficiale EA;
- un pacchetto costruito e decodificato torna uguale (2026 e 2025);
- un pacchetto troppo corto o di un formato sconosciuto si scarta; uno più lungo si accetta.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
from ingegnere import pacchetti as P  # noqa: E402

UFFICIALI_2025 = {0: 1349, 1: 753, 2: 1285, 3: 45, 4: 1284, 5: 1133, 6: 1352, 7: 1239, 8: 1042,
                  9: 954, 10: 1041, 11: 1460, 12: 231, 13: 273, 14: 101, 15: 1131}
errori = []
for k, v in UFFICIALI_2025.items():
    if P.TAGLIE[2025][k] != v:
        errori.append(f"2025 id {k}: {P.TAGLIE[2025][k]} invece di {v}")
if P.HEADER_SIZE != 29:
    errori.append(f"header {P.HEADER_SIZE} invece di 29")

for formato in (2026, 2025):
    S = P.STRUTTURE[formato]
    # stato delle auto
    st = S[P.STATUS]()
    st.header.packet_format, st.header.packet_id, st.header.session_uid = formato, P.STATUS, 42
    st.header.player_car_index = 3
    st.cars[3].fuel_remaining_laps = -0.75
    st.cars[3].ers_store_energy = 1.5e6
    st.cars[3].visual_tyre_compound = 17
    b = bytes(st)
    pk = P.decodifica(b)
    c = pk.dati.cars[3]
    if not (pk.id == P.STATUS and pk.formato == formato and abs(c.fuel_remaining_laps + 0.75) < 1e-6
            and c.ers_store_energy == 1.5e6 and c.visual_tyre_compound == 17):
        errori.append(f"{formato}: andata e ritorno di status sbagliata")
    # evento
    ev = S[P.EVENT]()
    ev.header.packet_format, ev.header.packet_id = formato, P.EVENT
    ev.code[:] = list(b"PENA")
    ev.details.penalty.penalty_type, ev.details.penalty.time, ev.details.penalty.vehicle_idx = 4, 5, 3
    pk = P.decodifica(bytes(ev))
    if P.codice_evento(pk) != "PENA" or pk.dati.details.penalty.time != 5:
        errori.append(f"{formato}: evento PENA sbagliato")
    # nomi dei partecipanti (driver id a 16 bit nel 2026)
    pa = S[P.PARTICIPANTS]()
    pa.header.packet_format, pa.header.packet_id = formato, P.PARTICIPANTS
    pa.num_active_cars = 20
    pa.cars[19].name = b"ROSSI"
    pa.cars[19].team_id = 300 if formato == 2026 else 200
    pk = P.decodifica(bytes(pa))
    if pk.dati.cars[19].name != b"ROSSI" or pk.dati.cars[19].team_id != (300 if formato == 2026 else 200):
        errori.append(f"{formato}: partecipanti sbagliati")
    # troppo corto → scartato; più lungo → accettato
    if P.decodifica(b[:-1]) is not None:
        errori.append(f"{formato}: un pacchetto troppo corto non è stato scartato")
    if P.decodifica(b + b"\0" * 8) is None:
        errori.append(f"{formato}: un pacchetto più lungo è stato scartato")

sconosciuto = bytearray(bytes(P.STRUTTURE[2026][P.STATUS]()))
sconosciuto[0:2] = (2024).to_bytes(2, "little")
if P.decodifica(bytes(sconosciuto)) is not None:
    errori.append("formato 2024 non scartato")
if P.TAGLIE[2026][P.TELEMETRY2] != 29 + 24 * 10:
    errori.append("telemetry2 2026 di taglia inattesa")

print("taglie 2026:", P.TAGLIE[2026])
print("OK" if not errori else "ERRORI:\n  " + "\n  ".join(errori))
sys.exit(1 if errori else 0)
