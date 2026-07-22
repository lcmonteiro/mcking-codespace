# ⛈️ Thunderstorm Simulator

Canvas-based weather simulation with rain, lightning, thunder, fog, and wind.

## Features

- **Layered rain** — 2000 drops across front/back depth layers with blur
- **Lightning bolts** — procedural branching bolts with core + glow rendering
- **Thunder sound** — Web Audio API: sawtooth rumble + filtered noise crack, distance-based
- **Wind** — smooth interpolated wind affecting rain angle and fog drift
- **Fog** — radial gradient fog clouds drifting with wind
- **Splashes** — ground splash rings + particle droplets on impact
- **Mouse/touch interaction** — click anywhere to create a splash
- **3 presets** — Gentle, Storm, Hurricane
- **Night/Day mode** — sky gradient toggle

## Controls

- Sliders: Rain, Wind, Thunder, Fog, Speed, Drop size
- ⚡ button: trigger lightning manually
- 🔊 button: toggle sound
- 🌙 button: toggle night/day
- Keyboard: H (HUD), T (thunder), S (sound)

## Tech

- Pure HTML/JS/CSS, single file, no dependencies
- Canvas 2D rendering at 60fps
- Web Audio API for procedural thunder sound
