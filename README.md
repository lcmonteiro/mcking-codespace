# 🚀 Mcking Codespace

Repositório pessoal gerido pelo **Mcking** (🤖 AI assistant do Luis).

## 📁 Estrutura

```
├── cpp/        → C++ (C++23, std-only, compilável com GCC/Clang/MSVC)
├── python/     → Python scripts
├── web/        → HTML/JavaScript/CSS
└── scripts/    → Build helpers e ferramentas
```

## 🏃‍♂️ Run (unificado)

```bash
./run.sh cpp/gpt.cpp      # compila C++ e executa
./run.sh python/script.py # executa Python
./run.sh web/index.html   # abre no browser
./run.sh scripts/sync-github.js  # executa Node.js
./run.sh scripts/build.ps1       # executa PowerShell
```

Deteta automaticamente a extensão e usa o interpretador/compilador certo.

**Suporta:** `cpp` `cc` `cxx` `c` `py` `js` `ts` `sh` `ps1` `go` `rs` `html`

## ⚙️ Compilar C++ (avançado)

Se precisares de flags específicas (MSVC, debug, -run flag):

**Windows (MSYS2 MinGW GCC/Clang):**
```powershell
.\scripts\build.ps1 cpp\meu_programa.cpp
```

**Windows (Visual Studio):**
```powershell
.\scripts\build.ps1 -msvc cpp\meu_programa.cpp -run
```

## 🐍 Python
```bash
./run.sh python/meu_script.py
```

## 🌐 Web
```bash
./run.sh web/index.html   # abre no browser
# ou servir com:
python -m http.server 8080
```

## 📐 Diagramas

**GitHub já renderiza .drawio** — vê o ficheiro diretamente no repo:

https://github.com/lcmonteiro/mcking-codespace/blob/main/web/mcking-codespace.drawio

**Localmente:** abre `web/diagramas.html` no browser (tabs com SVGs).

**Para editar:** abre o `.drawio` em https://app.diagrams.net/ (File → Open → GitHub) ou localmente com drawio desktop.

---

_Repo gerido automaticamente pelo Mcking._
