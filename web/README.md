# 🌐 Web — HTML/JS/CSS

```bash
./run.sh web/diagramas.html   # abre no browser
# ou
python -m http.server 8080    # serve localmente
```

## 📐 Diagramas (draw.io)

| Formato | Uso |
|---------|-----|
| `*.drawio` | Editável em [diagrams.net](https://app.diagrams.net/) |
| `*.drawio.svg` | Renderizado (abre em qualquer browser) |
| `diagramas.html` | Visualizador com tabs no browser |

**Ver online:** GitHub renderiza `.drawio` nativo — clica no ficheiro no repo.

**Editar:** https://app.diagrams.net/ → File → Open → GitHub

**Converter para SVG:**
```bash
drawio --export --format svg --output out.svg input.drawio
```

---

## 🧬 Particle Life

Emergent artificial life simulation — colored particles attract/repel each other
via configurable force matrices, creating organic flowing patterns.

```bash
./run.sh web/particle-life/index.html
```

**Features:** 4 species, 6 presets, interactive controls, glow toggle, mouse drag.

---

## ⛈️ Thunderstorm Simulator

Full-screen weather simulation with layered rain, lightning bolts, thunder sounds (Web Audio API), wind, fog, and splash effects. 3 presets, night/day mode, interactive splashes.

```bash
./run.sh web/thunderstorm/index.html
```

**Features:** 2000 rain drops, procedural branching lightning, distance-based thunder audio, fog drift, click-to-splash, keyboard controls.

---

💡 Nota: `viewer.diagrams.net` com `raw.githubusercontent.com` não funciona em repos privados.
