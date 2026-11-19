# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

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
