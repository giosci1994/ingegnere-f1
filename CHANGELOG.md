# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [0.6.3] - 2026-11-22

### Fixed
- **Position calls always up to date**: the position call no longer waits 4 s before a new one
  (`_posizioni`, `attesa=0`). Every change replaces the queued call with the right one; when the
  position goes back to the one already said, the queued call is withdrawn and nothing is said
  (`Messaggio.valore` / `Messaggio.da`, handled in `Radio.metti`). Before, being passed and
  passing back within 4 s left the old, wrong call in the queue.
- **The phone drops stale phrases**: every radio phrase now carries `chiave`, `creato`, `ttl` and,
  for the categories of the moment (`DEL_MOMENTO`: positions, gaps, spotter, active aero, pace,
  sectors) and priority > 1, `scade_tra` (seconds left). The phone (`web/fila.js`, used by
  `web/app.js`) does not play a phrase more than 1 s past its expiry and, when a phrase with the
  same key arrives, removes the old one from its queue. Urgent phrases (priority 1) are unchanged.
- **Held phrases dropped in the pits**: phrases held during the qualifying flying-lap silence (or
  the mute button) are thrown away when the silence ends in the pit lane, in the garage or in
  pause (`Radio(ai_box=...)`, `App._ai_box`). Before, they were said in the garage 10–100 s late.
- **No driving tip after an incident**: no corner tip when the loss in that corner is above 2 s
  (`analisi.PERDITA_MAX`): that is a spin, an off or a contact, not a driving mistake.

### Changed (less chatter, measured on the recorded sessions)
- ERS attack/defence calls (`ers_attacco`, `ers_difesa`) moved to verbosity 3: at «normale» they
  repeated the gap calls «Attacca!» / «Difendi.», which already name the car and the gap.
- Overheating tyres (`gomme_calde`): at most once every 4 minutes (was 150 s).
- Rivals' fastest lap (`giro_veloce_altri`) and rivals' sector gains (`settore_altro`) moved to
  verbosity 3.
- Position calls: 1.5 s of stable position before the call (was 2 s), ttl 6 s (was 8),
  priority 3 (was 4) so they no longer wait behind tyre and fuel calls.

### Tests
- `prova_fase6.py`: position passed and passed back within 3 s (withdrawn), two places lost in a
  row (only the last one queued), already-spoken call not withdrawn, `scade_tra` and the fields
  sent to the phone; `prove/prova_fila.js` (run with node when available) for the phone queue;
  held phrases dropped in the pits, no tip above 2 s, verbosity levels read from the code, tyre
  overheating every 4 minutes, position debounce/ttl/priority. `prova_offline.py` drops held
  phrases in the pits like the radio.

## [0.6.2] - 2026-11-21

### Fixed
- **UDP Action questions in menus/pause/garage**: `App.domande` now ignores UDP Action presses
  when off track (`session_uid == 0`, `game_paused == 1`, or `driver_status == 0`), while still
  updating button state for web diagnostics.
- **Queued questions cleared off track**: `Radio.svuota_categoria("domande")` clears pending
  question replies from both the active queue and held messages when entering pause or garage.

### Tests
- `prova_fase3.py`: added tests for off-track UDP Action filtering (`session_uid == 0`,
  `game_paused`, `driver_status == 0` vs on-track `driver_status == 4`) and
  `Radio.svuota_categoria("domande")`.

## [0.6.1] - 2026-11-21

### Fixed
- **Rain already on track with slicks**: switching to the rain Plan C while a pit call was open
  said "Stay out", contradicting Plan C (pit now for intermediates). It now calls
  "Box this lap, intermediates." (or full wets when the weather is heavy rain), once per stint,
  and marks the open pit call as a rain call so undercut, cover/overcut and SC/VSC pit calls do
  not repeat it in the same lap. "Stay out" for rain only forecast is unchanged.

### Tests
- `prova_fase6.py`: rain already on track, slicks, pit call open -> intermediates call, no
  "Stay out", not repeated.

## [0.6.0] - 2026-11-21

Phase 6 (Block 1 + Block 2): richer live dashboard, proactive race/telemetry calls, dynamic
Plan A/B/C strategy, teammate/rival corner comparison, and Pre-race tab.

### Added
- **Live dashboard**: real-time lap delta bar against the reference lap, 4-wheel card (wear %,
  surface and inner temperatures, blistering), ERS battery/deploy mode/Overtake status, and
  active race strategy plan badge.
- **Coaching cap & track limits**: configurable per-session coaching limit (`max_consigli_guida`,
  default 12, 0 = unlimited) and pre-penalty track-limit warnings (`corner_cutting_warnings`).
- **ERS, Lift & Coast, Brake Bias & PU**: ERS attack/defence calls, Lift & Coast calls for low
  battery or fuel, live brake-bias adjustments from 20 Hz lockup detection and front/rear
  heat/wear imbalance, engine/PU wear warnings, and clean-air slipstream calls.
- **Tyre overheating & blistering with corner**: persistent surface/inner temperature and
  blistering calls naming the worst corners.
- **Target Lap & rival telemetry**: target lap time before the pit window, fastest-lap (`FTLP`)
  and pit-exit tyre calls for rivals, sector-by-sector comparison against cars ahead/behind,
  named blue flags, and lapped-car warnings ahead.
- **Plan A / B / C & explicit pit calls**: pre-start and live race calculation of Plan A
  (standard), Plan B (aggressive / undercut / 2-stop), and Plan C (conservative / rain),
  automatic in-race switches, active plan in `strategia` button response and UI, and explicit
  pit calls (*«Box questo giro»*, *«Box per undercut»*, and *«Resta fuori»* when the target
  pits first or SC/VSC/rain invalidates the call).
- **Teammate / fastest rival corner comparison**: in-memory clean-lap tracing of eligible
  cars (`your_telemetry` / AI, never saved into `dati/giri/`), automatic selection of teammate
  or fastest available rival, live corner-by-corner coaching calls, and session summary table.
- **Pre-race tab & API (`/api/pregara`, `/api/pregara/<pista>`)**: responsive Pre-race view
  with Plan A/B/C, aggregated setup suggestions (via `assetto.py`, no suspension/height guesses),
  per-corner braking map (`numeri_curve.py`, braking metre, entry speed, min speed, min gear,
  full throttle), and race-start launch analysis (`LGOT`, `start_reaction_time`, `clutch`,
  `throttle`, `wheel_slip`, 0–100 km/h, history & advice).

### Tests
- `prove/prova_fase6.py` (added to CI) and extended `prove/pagina.py` (5 viewports, Pre-race tab).

## [0.5.0] - 2026-11-20

Ten calls and buttons found in similar projects (Crew Chief, iRacing's crew chief, Pits n'
Giggles, T1, Simulator Controller), chosen one by one. Each one has its switch or category and
its verbosity level, and every cooldown runs on a clock that does not go back with flashbacks.

### Added
- **Radio mute button**: a UDP Action silences the radio for 30 s (priority 1 still passes, the
  rest is said afterwards if still valid); pressed again, the radio comes back.
- **Rivals' tyre wear** in the undercut: when the game sends it (offline it does, for every car)
  the rival's tyres are aged from their real wear and your wear per lap, and the call says it
  («Ha le gomme al 55 per cento»); otherwise the estimate from the tyre age, as before.
- **Tyre and fuel forecast** (race, every 5 laps): when the tyres reach 80 per cent or with how
  much wear you finish; with how much fuel you finish and the maximum per lap; if it is not enough,
  how many grams per lap to save.
- **Which tyre set to fit** (from the game's tyre-sets packet): once per stint when the stop gets
  close, and in the strategy answer: a compound you have not used yet in a dry race, one that lasts
  to the end if any, the fastest of those, and for how many laps.
- **Pit under safety car or VSC**: the estimated cost of stopping now (pit loss × 0.65 / 0.70),
  said as an estimate, when a stop is still needed.
- **Pace against the cars ahead and behind** (race, last 3 clean laps, 0.15–2 s a lap): «lo
  prendi in N giri», «ti recupera N decimi a giro».
- **Sector times** against your best (practice and qualifying; silent on a qualifying flying lap).
- **«Dove perdo?»** button: the two worst corners of the last lap with the advice.
- **Spotter**: a car alongside on the left or right (from every car's position, at 20 Hz),
  «Libero» when it is over; it can cut a priority-2 phrase, which the phone then says again.
  **Off by default**: server-side delay measured at about 1 ms (up to 0.3–1.4 s if another urgent
  phrase is playing), plus about 0.35 s of radio beep before the voice and the phone's own audio
  delay, not measured: to be tried on the PS5.
- **Fuel target per lap** (see the forecast above).

### Tests
- `prove/prova_fase5.py` (also in CI): mute, «dove perdo», undercut with and without rivals' wear,
  tyre-set choice, and simulator races (normal 2026/2025, clean, practice) for every new call.
- The simulator sends the player's tyre sets, sector times, and a car running alongside.

## [0.4.1] - 2026-11-20

### Added
- Under the verbosity selector (Essenziale/Normale/Tutto) the page says what each level adds,
  and that the switches choose the topics while the level chooses how much is said about them.
  The lists are read from the code (`livelli.py` parses the `livello` of every call with `ast`),
  so they cannot drift; `prova_fase3.py` fails if a call has no name.

## [0.4.0] - 2026-11-20

### Changed
- **The page works on phone, tablet and PC**: two columns where they help (Radio: dashboard and
  calls side by side; Summaries: list and detail; Racing line: map and table on a wide screen;
  Info), the settings as cards on two or three columns, a compact header for a phone in
  landscape, touch targets of at least 40 px, no horizontal page scroll, a «Salvato» message that
  stays visible, corner labels on the map sized to their text («13-14»), text columns that wrap in
  the corner tables, identical penalties grouped in the summary («avvertimento ×8»).
- «Freni ancora caldi» at most every 10 minutes of game time (was 5) unless they get hotter.

### Fixed
- «Contatto con…» repeated after every flashback: the same car is called once a minute on a
  clock that does not go back with flashbacks, and two different contacts within 15 s are called
  once; the summary counts them the same way.
- The same pit stop listed twice in the summary after a flashback in the pit lane.
- Cooldowns of the coaching and strategy calls are measured on the same flashback-proof clock.
- API: a JSON body that is not an object, or a non-numeric track id, now gives 400/404 instead
  of a server error; on/off settings sent as the text «false» are no longer read as true.
- Code review: unused imports, attributes, a helper function, four fixed phrases that were never
  said (they were synthesised at every start), unused CSS and JavaScript removed; the lap index
  is rewritten atomically when old laps are pruned.

### Tests
- `prove/pagina.py` checks five sizes (375, 768, 1024, 1440 and a phone in landscape 844×390):
  no JavaScript errors, no horizontal scroll on any tab, buttons at least 40 px high.
- `prove/prova_fase3.py` also checks the contacts after flashbacks.

## [0.3.0] - 2026-11-20

Phase 3, after the first real sessions on the PS5 (practice, a race and a short qualifying in
Montréal).

### Added
- **Coaching that says how to improve**: the call after a corner now says what to do, with the
  number — brake N metres later or earlier, release the brake more gently and carry N km/h more,
  full throttle N metres earlier, less steering on exit, avoid the lock-up, smoother throttle —
  then how much time is lost there. Same thresholds and caps as before; a braking-point
  difference above 80 m is not called (traffic or a mistake, not a braking point to fix). In practice, optional
  **one corner at a time**: the worst corner until it improves, then the next one.
- **Official corner numbers**: «Curva 8», «Curve 13 e 14» as on the circuit map, for the tracks
  of the 2026 calendar (table of corner positions as a fraction of the lap, from the MultiViewer
  circuit API, F1 live-timing data); the finish-line offset is found automatically. Elsewhere
  (Madrid, reverse layouts) the own numbering stays.
- **Pronunciation dictionary** before Piper: whole words, case-insensitive (2026 drivers, teams,
  tracks, English radio terms). The default table is in the code, your changes are stored in
  `dati/pronuncia.json`; a page section lets you add or change entries and **«Prova»** plays the
  word at once. The WAV cache key uses the substituted text, so a changed entry gives new audio.
- **Questions with the PS5 buttons**: the UDP Action 1–12 bits of the `BUTN` event (rising edge
  only) ask the engineer for strategy, tyres, gaps, fuel, damage, pace, or to repeat the last
  phrase; answers have high priority. Assign each UDP Action from the page, which also shows the
  last button received.
- **Radio silence on a qualifying flying lap** (switch, on by default): only priority 1–2 calls
  and the lap time; the rest is kept and said after the line if still valid.

### Fixed
- «Freni caldi» repeated every ~9 s: each flashback cleared the cooldown. Hot brakes are now said
  once, then only if they get 50 °C hotter or after 5 minutes of game time (a clock that does not
  go back with flashbacks), with the cause when there is one (front/rear, the corner).
- Sessions split into many tiny recordings at the end of a session: in the menus the game sends
  `BUTN` events with `session_uid` 0, alternating with the final classification of the session.
  Packets with uid 0 are no longer recorded, a file closed a moment ago is reopened for the same
  session, the file name gets the session type as soon as it is known, and the summary takes
  the final classification once instead of every 5 seconds.

## [0.2.1] - 2026-11-19

### Fixed
- The *Info* page could stay at «Frasi pronte 31%» although the phrase cache was ready: when the
  voice settings changed twice, the older cache run finished after the new one and overwrote the
  progress. Each run now has a generation number and only the latest one updates the progress.

### Added
- AGPL-3.0 `LICENSE`, this changelog, English README with credits and trademark notice, landing page
  (`docs/`, English/Italian), social preview, GitHub Actions build (Docker image + offline tests).

## [0.2.0] - 2026-11-19

Phase 2: the engineer looks at how you drive, not only at what the car says.

### Added
- **Lap traces**: every lap of the player is stored as a compact trace (20 Hz: distance, position,
  speed, throttle, brake, steering, gear, slip, yaw, temperatures, active aero), with a per-track
  library and a driver name.
- **Corners and live coaching**: corners found on the reference lap; one short call on the next
  straight when you lose time in a corner, with the cause (braking point, minimum speed, throttle).
- **Strategy**: pit loss measured per track from every car's stops, tyre degradation from your
  clean laps, undercut/overcut calls, where you rejoin after a stop.
- **Setup reading** with indicative suggestions, each backed by the data point behind it.
- **2026 active aero**: reminders and per-lap usage in the summary.
- **Racing line** tab (*Traiettoria*): overlay of any two laps of a track, also across sessions
  and drivers, with per-corner braking point, minimum speed and throttle point.
- Simulator with track geometry, a clean-race mode and a "slower driver" mode for comparisons.

## [0.1.0] - 2026-11-19

Phase 1: the first working race engineer.

### Added
- UDP decoding for the **2026** packet format (24 cars, Car Telemetry 2) and **2025** as a fallback.
- Live calls in Italian for flags, safety car, pit window, penalties, tyres, fuel, battery,
  damage, weather, gaps, positions, laps and lap times, with priorities and cooldowns.
- Local voice (Piper) with a team-radio effect generated in code, and a WAV cache.
- Mobile web app (PWA) with per-category switches, verbosity, volume, voice and speed.
- Session recorder, UDP replayer and a simulator that triggers every rule.
- After-session summary: laps, sectors, pace, ideal lap, stops, stints, errors.
