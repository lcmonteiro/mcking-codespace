# Web (HTML/JS/CSS)

Abrir `index.html` no browser ou servir com `python -m http.server`.

## Diagramas (draw.io)

- `*.drawio` — ficheiros editáveis no [diagrams.net](https://app.diagrams.net/)
- `*.drawio.svg` — versão SVG gerada a partir do drawio (abre em qualquer browser)

### 📎 Ver diagramas

**Opção 1 — GitHub (recomendado):** O GitHub renderiza `.drawio` nativamente.
Basta clicar no ficheiro no repo:

https://github.com/lcmonteiro/mcking-codespace/blob/main/web/mcking-codespace.drawio

**Opção 2 — Local:** abre `web/diagramas.html` no browser.

**Opção 3 — Editar:** https://app.diagrams.net/ → File → Open → GitHub

**Nota:** `viewer.diagrams.net` com `raw.githubusercontent.com` não funciona em repos privados.

### Converter drawio → SVG

```powershell
# Opção 1: drawio CLI (se instalado)
drawio --export --format svg --output out.svg input.drawio

# Opção 2: Abrir em https://app.diagrams.net/ e File → Export → SVG
```
