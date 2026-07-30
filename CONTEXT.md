# Mcking Context — Agent Notes

Context file for the agent (not for humans).
Store learnings about the project and workflow here, without polluting the workspace's MEMORY.md.

## Repo

- `lcmonteiro/mcking-codespace`
- SSH: `github.com-mcking` (~/.ssh/config)
- Deploy key: `~/.ssh/id_ed25519_mcking`
- Local: `/home/monteiro/.openclaw/workspace/mcking-codespace/`

## Structure

```
cpp/       — C++ projects
python/    — Python projects
web/       — HTML/JS/CSS
scripts/   — Build scripts, helpers
```

## Workflow — Branches

- Long/multi-day projects → branch `inspiracao/<project-name>`
- If it fails: delete the branch, no harm done
- If it continues: checkout same branch and keep going
- Single inspiration sessions: optional branch `inspiracao/YYYY-MM-DD`
- **Scrum-like merge**: when a project has something new/functional, merge to `master` (main branch)
  - Merge inspiration branch → master
  - Inspiration branch stays for work in progress

## Build Helper

- `scripts/build.sh` — build helper that auto-detects GCC/Clang/MSVC on Linux/WSL2

## Root Scripts Convention

Cada projeto deve ter dois scripts na sua raiz:

- **`run.sh`** — corre o projeto (compila, executa, abre browser, etc.)
- **`setup.sh`** — prepara o ambiente pela primeira vez:
  - Instala dependências (pip, npm, etc.)
  - Cria virtualenv / `.venv` se necessário
  - Corre `uv sync`, `npm install`, ou equivalente
  - Deve ser idempotente (pode correr多次 sem partir nada)

O `run.sh` da raiz (`./run.sh`) já delega para `run.sh` dentro de pastas projeto.

Todos os projetos têm `setup.sh` e `run.sh`:

| Project | setup.sh | run.sh |
|---|---|---|
| `cpp/` | Compila C++ | Compila + corre o binário |
| `python/clai/` | `uv venv` + `uv sync` | Corre `clai` CLI |
| `python/llm-proxy/` | `uv venv` + `uv pip install` | Corre uvicorn (`main:app`) |
| `web/` | Overview de sub-projetos | Lista sub-projetos |
| `web/cellular-automata/` | Noop (static) | Abre index.html no browser |
| `web/chat-codec/` | `npm install` + submodule | `npm run dev` |
| `web/diagrams/` | Noop (static) | Lista SVGs |
| `web/fluid-sim/` | Noop (static) | Abre index.html no browser |
| `web/particle-life/` | Noop (static) | Abre index.html no browser |
| `web/thunderstorm/` | Noop (static) | Abre index.html no browser |

### Exemplo de setup.sh para Python

```bash
#!/usr/bin/env bash
set -euo pipefail

if [ ! -d .venv ]; then
    uv venv
fi
uv sync
```

### Exemplo para Node

```bash
#!/usr/bin/env bash
set -euo pipefail

if [ ! -d node_modules ]; then
    npm install
fi
```

### Exemplo para Python single-script (sem pyproject.toml)

```bash
#!/usr/bin/env bash
set -euo pipefail

if [ ! -d .venv ]; then
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
fi
```

### Projects with setup.sh

Todos os projetos do repo já têm `setup.sh`:

| Project | Type | setup.sh faz |
|---|---|---|
| `cpp/` | C++ | Verifica g++/clang++, compila .cpp |
| `python/clai/` | Python (uv) | `uv venv` + `uv sync` |
| `python/llm-proxy/` | Python (pip) | `venv` + `pip install -r requirements.txt` |
| `web/` | Root | Overview de sub-projetos |
| `web/chat-codec/` | Node + WASM | `npm install` + git submodule + check Emscripten |
| `web/cellular-automata/` | Static HTML | Noop (basta abrir index.html) |
| `web/diagrams/` | Static SVG | Noop |
| `web/fluid-sim/` | Static HTML | Noop (basta abrir index.html) |
| `web/particle-life/` | Static HTML | Noop (basta abrir index.html) |
| `web/thunderstorm/` | Static HTML | Noop (basta abrir index.html) |
## Windows Python Gotchas

- **UTF-8 stdout**: `sys.stdout.reconfigure(encoding='utf-8', errors='replace')` — required for Unicode in Windows terminals
- **Keyboard input**: `msvcrt.getwch()` to read keys; arrow keys come as `\xe0` + second key

## Terminal Visuals — Tips

- **Smooth Mandelbrot**:
  ```python
  log_zn = log2(x2 + y2) / 2.0
  nu = log2(log_zn) if log_zn > 0 else 0.0
  smooth = iteration + 1 - nu
  t = smooth / max_iter
  ```
- **Color palettes**: function `(t: float) -> Tuple[int,int,int]` with t ∈ [0,1]; modular and swappable
- **Density ASCII chars**: `. :-=+*#%@` — index based on smooth value for texture
- **Star twinkle**: `max(0, sin(t * speed + phase) ** 4)` for sudden peaks
- **3D Lorenz rendering**: Project via focal length `fov = focal * scale`, Z-buffer for occlusion, depth-indexed ASCII chars `.:-=+*#%@█`

## Projects in Repo

- `python/nocturne.py` — animated night landscape in terminal (stars, moon, shooting stars, fireflies)
- `python/plasma.py` — classic demoscene plasma effect with 5 palettes (Lava, Ocean, Neon, Forest, Ice), interactive controls, auto-cycle
- `python/mandelbrot.py` — interactive Mandelbrot set explorer (pan, zoom, 8 palettes, smooth coloring)
- `python/cellular_automata.py` — cellular automata playground with 6 rulesets (Conway, HighLife, Seeds, Brian's Brain, Day & Night, Wireworld)
- `python/hyperspace.py` — hyperspace starfield with warp drive, 8 palettes, FPS counter, interactive controls
- `web/thunderstorm/` — thunderstorm simulator (rain, lightning, thunder via Web Audio, fog, wind)
- `web/fluid-sim/` — WebGL fluid simulation
- `web/particle-life/` — emergent artificial life simulation
- `python/snake.py` — terminal Snake game (curses, arrow/WASD, pause, score, speed scaling)
- `python/lorenz.py` — Lorenz Attractor 3D chaotic system (RK4 integration, rotating ASCII, ANSI colour, interactive controls)
- `python/wave_interference.py` — multi-source wave superposition, 7 presets, ANSI truecolor
- `python/ocean.py` — ocean surface simulator with animated waves, sky, celestial bodies, clouds, seabirds, 5 palettes (Sunset, Moonlit, Dawn, Storm, Tropical), wind/sea-state controls
- `python/fireworks.py` — ASCII fireworks display with particle physics, 5 types (Burst, Fountain, Comet, Crossette, Willow), 5 palettes, auto-show mode, trails, sparkle effects
- `python/solar_system.py` — terminal solar system simulator with Keplerian orbits, planet trails, asteroid belt, 3 palettes (Realistic, Neon, Retro), zoom/pan, speed control, info panel
- `python/raycaster.py` — terminal raycasting engine (Wolfenstein 3D-style): DDA raycasting, coloured/textured walls, minimap, WASD + arrow controls, smooth turning, auto-rotate
