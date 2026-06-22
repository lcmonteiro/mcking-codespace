# Mcking Context — Agent Notes

Ficheiro de contexto para o agente (não para humanos).
Guardar aqui o que aprender sobre o projeto e workflow, sem poluir o MEMORY.md do workspace principal.

## Repo

- `lcmonteiro/mcking-codespace`
- SSH: `github.com-mcking` (~/.ssh/config)
- Deploy key: `~/.ssh/id_ed25519_mcking`
- Local: `C:\Users\monte\.openclaw\workspace\mcking-codespace\`

## Estrutura

```
cpp/       — C++ projects
python/    — Python projects
web/       — HTML/JS/CSS
scripts/   — Build scripts, helpers
```

## Workflow — Branches

- Projetos longos/multidias → branch `inspiracao/<project-name>`
- Se falhar/correr mal: apagar branch, sem danos
- Se continuar: checkout do mesmo branch e seguir
- Sessões únicas de inspiração livre: branch `inspiracao/YYYY-MM-DD` opcional

## Build Helper

- `scripts/build.ps1` — auto-detecta GCC/Clang/MSVC no Windows

## Windows Python Gotchas

- **UTF-8 no stdout**: `sys.stdout.reconfigure(encoding='utf-8', errors='replace')` — obrigatório para Unicode em terminais Windows
- **Keyboard input**: `msvcrt.getwch()` para ler teclas; arrow keys vêm como `\xe0` + segunda tecla

## Terminal Visuals — Dicas

- **Smooth Mandelbrot**:
  ```python
  log_zn = log2(x2 + y2) / 2.0
  nu = log2(log_zn) if log_zn > 0 else 0.0
  smooth = iteration + 1 - nu
  t = smooth / max_iter
  ```
- **Color palettes**: função `(t: float) -> Tuple[int,int,int]` com t ∈ [0,1]; modular e permutável
- **Density ASCII chars**: `. :-=+*#%@` — índice baseado em smooth value para textura
- **Star twinkle**: `max(0, sin(t * speed + phase) ** 4)` para picos súbitos

## Projetos no Repo

- `python/nocturne.py` — paisagem nocturna animada no terminal (estrelas, lua, estrelas cadentes, pirilampos)
- `python/mandelbrot.py` — explorador interativo do Mandelbrot set (pan, zoom, 8 paletas, smooth coloring)
