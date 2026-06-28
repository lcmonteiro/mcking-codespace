# Mcking Context — Agent Notes

Context file for the agent (not for humans).
Store learnings about the project and workflow here, without polluting the workspace's MEMORY.md.

## Repo

- `lcmonteiro/mcking-codespace`
- SSH: `github.com-mcking` (~/.ssh/config)
- Deploy key: `~/.ssh/id_ed25519_mcking`
- Local: `C:\Users\monte\.openclaw\workspace\mcking-codespace\`

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

- `scripts/build.ps1` — auto-detects GCC/Clang/MSVC on Windows

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

## Projects in Repo

- `python/nocturne.py` — animated night landscape in terminal (stars, moon, shooting stars, fireflies)
- `python/mandelbrot.py` — interactive Mandelbrot set explorer (pan, zoom, 8 palettes, smooth coloring)
- `python/cellular_automata.py` — cellular automata playground with 6 rulesets (Conway, HighLife, Seeds, Brian's Brain, Day & Night, Wireworld)
