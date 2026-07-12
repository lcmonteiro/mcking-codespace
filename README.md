# 🚀 Mcking Codespace

Repositório pessoal gerido pelo **Mcking** (🤖 AI assistant do Luis).

Código, scripts, diagramas — tudo centralizado aqui. Autosync com GitHub.

## 📁 Estrutura

```
├── cpp/        → C++23 std-only
├── python/     → Python scripts
├── web/        → HTML/JS/CSS + diagramas
└── scripts/    → Build helpers & ferramentas
```

## 🏃‍♂️ Run unificado

```bash
./run.sh cpp/gpt.cpp           # 🔧 compila C++ e executa
./run.sh python/script.py      # 🐍 Python
./run.sh web/index.html        # 🌐 abre no browser
./run.sh scripts/sync-github.js # 📦 Node.js
./run.sh scripts/build.sh       # ⚡ Build script (bash)
```

Deteta a extensão e escolhe o interpretador certo. Sem stress.

**Suporta:** `cpp cc cxx c` `py` `js ts` `sh` `go rs` `html`

## ⚙️ Compilar C++ (manual)

Se precisares de flags específicas:

```bash
./scripts/build.sh cpp/gpt.cpp          # 🔧 build só
./scripts/build.sh cpp/gpt.cpp -run     # 🔧🚀 build + run
./scripts/build.sh cpp/gpt.cpp -clang   # 🏗️ Clang
```

## 🌐 GitHub Pages

Este repo está deployado em [**lcmonteiro.github.io/mcking-codespace**](https://lcmonteiro.github.io/mcking-codespace/) via GitHub Actions.

| Página | URL | Descrição |
|---|---|---|
| 💬 **CodecShare Chat** | [`/chat-codec/public/`](https://lcmonteiro.github.io/mcking-codespace/chat-codec/public/) | Chat P2P cifrado com fountain codes + WebRTC mesh |
| 🔮 **Plasma** | _(terminal-only)_ | Classic demoscene plasma effect — 5 palettes, sine-wave layers, interactive controls |
| 🧬 **Cellular Automata** | [`/cellular-automata/`](https://lcmonteiro.github.io/mcking-codespace/cellular-automata/) | Simulador interativo de autómatos celulares (Conway, HighLife, Seeds, Brian's Brain, Day & Night, Wireworld) |
| 📊 **Diagrams** | [`/diagrams/`](https://lcmonteiro.github.io/mcking-codespace/diagrams/) | Diagramas e whiteboards (SVG) |
| λ **λ-tree** | _(terminal-only)_ | Lambda calculus visualiser — β-reduction, ASCII trees, Church numerals |
| 🏠 **Landing** | [`/`](https://lcmonteiro.github.io/mcking-codespace/) | Página inicial com links para todos os projetos |

O deploy corre automaticamente em cada push para `master` (`.github/workflows/pages.yml`).

## 📐 Diagramas

- `web/*.drawio` — editável em [diagrams.net](https://app.diagrams.net/)
- `web/diagramas.html` — visualizador com tabs
- GitHub renderiza `.drawio` nativo no browser

---

_Repo gerido automaticamente pelo Mcking — sync diário via cron._
