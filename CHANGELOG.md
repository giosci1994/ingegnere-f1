# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

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
