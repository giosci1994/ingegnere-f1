# Ingegnere F1 · notes for coding agents

Read `README.md` first. If a local, untracked `SCHELETRO.md` exists next to this file, read it too: it holds the notes for this specific installation (it is git-ignored on purpose and must never be committed).

## Map
| Part | File | What it does |
|---|---|---|
| Decoding | `app/ingegnere/pacchetti.py` | ctypes structures for UDP formats 2026 and 2025; only the packets the engineer needs are decoded |
| State | `app/ingegnere/stato.py` | last packet per type, names, lap history, events, diagnostics |
| Rules | `app/ingegnere/ingegnere.py` | the live calls (one engineer, for `player_car_index` only; split screen is not followed) |
| Radio | `app/ingegnere/radio.py` | the queue: one phrase at a time, priority, expiry, de-duplication, urgent calls interrupt priority ≥ 3, radio silence on a qualifying flying lap |
| Voice | `app/ingegnere/voce.py` | Piper + radio effect (numpy), WAV cache keyed by voice/speed/effect/text after the pronunciation dictionary |
| Phase 2 | `traccia.py`, `curve.py`, `analisi.py`, `strategia.py`, `assetto.py` | lap traces and library, corners, live braking/exit calls, undercut/overcut and pit loss per track, setup suggestions, active aero |
| Phase 5 | `gara.py`, `spotter.py` | sector times, pace against neighbours, tyre/fuel forecast, pit under SC/VSC, tyre set for the stop, rivals' tyre wear; spotter from the motion packet (called on every motion packet, not in the 5 Hz loop) |
| Phase 3 | `numeri_curve.py`, `pronuncia.py`, `domande.py`, `livelli.py` (what each verbosity level adds, read from the code with `ast`: give every new call a name in `ETICHETTE`) | official corner numbers per track, pronunciation dictionary applied before Piper (defaults in code, user entries in `dati/pronuncia.json`), questions from the UDP Action buttons (`BUTN`, rising edge) |
| Summary | `app/ingegnere/riassunto.py` | after-session JSON |
| Server | `app/ingegnere/server.py` | asyncio + aiohttp: UDP, 5 Hz engineer loop, REST, WebSocket `/ws` |
| Tools | `registratore.py`, `riproduci.py`, `simulatore.py` | record, replay, generate a fake session |
| Page | `web/` | single-page app, Italian UI |
| Showcase | `docs/` | landing page (EN/IT, `data-en`/`data-it` + `js/main.js`) and `social-preview.html` → `social-preview.png` (1280×640, Firefox headless screenshot) |
| CI | `.github/workflows/build.yml` | builds the image and runs the offline tests inside it on simulator races; keep it green. Update `CHANGELOG.md` with every change |
| Tests | `prove/` | `prova_pacchetti.py`, `prova_offline.py`, `prova_fase3.py`, `ascolta.py` (fake phone), `pagina.py` (real Firefox at 375, 768, 1024, 1440 px and 844×390: no JS errors, no horizontal scroll, touch targets ≥ 40 px) |

## Rules
- Code, comments and UI are in Italian; keep it that way.
- Before calling a change done: run the offline tests and a UDP replay with `ascolta.py` (no overlapping phrases, no missing audio); for page changes, `prove/pagina.py`.
- Never put personal data in tracked files or commit messages: no names, IP addresses, host names, home paths, tokens. `dati/`, `voci/*.onnx*`, `.env` and `SCHELETRO.md` stay out of git.
- Do not invent data the game does not send (for example other cars' tyre wear); when a value is estimated, say so in the phrase or in the summary.
- amd64 only; keep the container light (it runs next to other home services).
