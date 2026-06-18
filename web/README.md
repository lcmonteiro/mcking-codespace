# Web (HTML/JS/CSS)

Abrir `index.html` no browser ou servir com `python -m http.server`.

## Diagramas (draw.io)

- `*.drawio` — ficheiros editáveis no [diagrams.net](https://app.diagrams.net/)
- `*.drawio.svg` — versão SVG gerada a partir do drawio (abre em qualquer browser)

### 📎 Ver diagrama no browser (sem instalar nada)

Basta um link para o **diagrams.net viewer**:

```markdown
[📐 Ver diagrama](https://viewer.diagrams.net/?url=https://raw.githubusercontent.com/lcmonteiro/mcking-codespace/main/web/mcking-codespace.drawio)
```

Fica assim:

[📐 Ver diagrama](https://viewer.diagrams.net/?url=https://raw.githubusercontent.com/lcmonteiro/mcking-codespace/main/web/mcking-codespace.drawio)

Funciona com qualquer `.drawio` no repo — só mudar o URL. O viewer carrega **todos os tabs** do ficheiro.

### Tabs no HTML (alternativa)

Ver `diagramas.html` — carrega SVGs com tabs nativos, sem servidor.

### Converter drawio → SVG

```powershell
# Opção 1: drawio CLI (se instalado)
drawio --export --format svg --output out.svg input.drawio

# Opção 2: Abrir em https://app.diagrams.net/ e File → Export → SVG
```
