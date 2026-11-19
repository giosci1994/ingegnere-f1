# Ingegnere F1

A home-made **race engineer for EA SPORTS F1 25 (2026 Season Pack)**. It listens to the game's UDP telemetry, decides what is worth saying, and says it **in Italian with a team-radio effect** on a small web app for the phone (Android and iPhone). The console audio is left alone.

Everything runs locally in one Docker container: no cloud services, no cloned voices, no broadcast audio. The voice is [Piper](https://github.com/rhasspy/piper) (local TTS); the radio effect (beeps, band-pass, saturation, hiss, squelch) is generated in code.

## Features
- **Telemetry**: UDP packet format **2026** (24 cars, Car Telemetry 2 with active aero and Overtake Mode) and **2025** as a fallback.
- **Live calls**, each group can be switched on/off from the page: flags and wrong way, safety car and VSC, box window and pit limiter, penalties and track limits, tyres (wear, temperatures, blistering), fuel, battery and Overtake, damage, weather, gaps ahead/behind, positions, laps to go, lap times and records, **strategy** (undercut/overcut, where you rejoin after a stop, pit loss measured per track), **braking and corner exits** compared with your best lap (one short call on the next straight), **2026 active aero** reminders.
- Priorities (safety > box/penalties > tyres/fuel/damage/weather > gaps/positions > the rest), no overlapping phrases, cooldowns, three verbosity levels.
- **After the session**: laps, pace, best sectors and ideal lap, stops and stints, errors; per-corner losses and causes; **setup reading with indicative suggestions**, each backed by the data point behind it; active aero usage.
- **Racing line**: every lap of the player is stored as a compact trace; the *Traiettoria* (racing line) tab overlays any two laps of a track (also from different sessions or drivers) with per-corner braking point, minimum speed and throttle point.
- **Recorder and player**: real sessions are saved and can be replayed over UDP; a **simulator** generates a full fake race that triggers every rule, for testing without the game.

## Run
```bash
# 1. voices (not in the repository): put these four files in ./voci
#    https://huggingface.co/rhasspy/piper-voices/tree/main/it/it_IT/riccardo/x_low
#      it_IT-riccardo-x_low.onnx, it_IT-riccardo-x_low.onnx.json
#    https://huggingface.co/rhasspy/piper-voices/tree/main/it/it_IT/paola/medium
#      it_IT-paola-medium.onnx, it_IT-paola-medium.onnx.json
# 2. optional: echo "TZ=Europe/Rome" > .env
docker compose up -d --build
```
- UDP **20777**: game telemetry. TCP **8777**: the web app (`http://<server-ip>:8777`). There is no login: keep it on the home network.
- In the game (Settings → Telemetry): UDP on, broadcast off, IP of the server, port 20777, 20 Hz, **UDP format 2026**.
- On the phone: open the page, tap **«Collega la radio»** once (iOS only plays audio after a tap), keep the page in the foreground. Without HTTPS the Screen Wake Lock API is not available, so a muted looping video keeps the screen on.

## Test without the game
```bash
docker exec ingegnere-f1 python -m ingegnere.simulatore --uscita /dati/registrazioni/fake.f1rec.gz
docker run --rm --network host -v $PWD/prove:/prove ingegnere-f1:locale python /prove/ascolta.py --secondi 300 &
docker exec ingegnere-f1 python -m ingegnere.riproduci /dati/registrazioni/fake.f1rec.gz --velocita 2
```
Offline (standard library only): `cd app && python3 ../prove/prova_pacchetti.py` and `python3 ../prove/prova_offline.py <recording>`. Page check in a real Firefox: `python3 prove/pagina.py` (needs geckodriver).

Fake laps go into the same per-track library as real ones (the simulator uses track id 11): clear `dati/giri/11` and `dati/piste.json` after testing on a real install.

## Notes
- Packet structures follow EA's official *F1 25 2026 Season Pack UDP specification*, as shipped in `data/spec.h` of the open-source [`f1-packets`](https://pypi.org/project/f1-packets/) 2026.1.1 package; the 2025 sizes match the official F1 25 specification.
- `onnxruntime` (used by Piper) sends usage telemetry unless disabled: the image sets `ORT_DISABLE_TELEMETRY=1` and the code calls `disable_telemetry_events()`.
- Setup suggestions are rules of thumb, not truth: the telemetry has no inner/outer tyre edge temperatures and no kerb data, so there are no suspension or ride-height suggestions.
- The user interface and the radio are in Italian.
