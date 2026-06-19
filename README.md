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
./run.sh scripts/build.ps1     # ⚡ PowerShell
```

Deteta a extensão e escolhe o interpretador certo. Sem stress.

**Suporta:** `cpp cc cxx c` `py` `js ts` `sh ps1` `go rs` `html`

## ⚙️ Compilar C++ (manual)

Se precisares de flags específicas:

```powershell
.\scripts\build.ps1 cpp\gpt.cpp          # 🔧 build só
.\scripts\build.ps1 cpp\gpt.cpp -run     # 🔧🚀 build + run
.\scripts\build.ps1 cpp\gpt.cpp -msvc    # 🏗️ MSVC
```

## 📐 Diagramas

- `web/*.drawio` — editável em [diagrams.net](https://app.diagrams.net/)
- `web/diagramas.html` — visualizador com tabs
- GitHub renderiza `.drawio` nativo no browser

---

_Repo gerido automaticamente pelo Mcking — sync diário via cron._
