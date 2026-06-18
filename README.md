# 🚀 Mcking Codespace

Repositório pessoal gerido pelo **Mcking** (🤖 AI assistant do Luis).

## 📁 Estrutura

```
├── cpp/        → C++ (C++23, std-only, compilável com GCC/Clang/MSVC)
├── python/     → Python scripts
├── web/        → HTML/JavaScript/CSS
└── scripts/    → Build helpers e ferramentas
```

## ⚙️ Compilar C++

**Windows (MSYS2 MinGW GCC/Clang):**
```powershell
.\scripts\build.ps1 cpp\meu_programa.cpp
```

**Windows (Visual Studio):**
```powershell
.\scripts\build.ps1 -msvc cpp\meu_programa.cpp
```

**Linux/Mac:**
```bash
./scripts/build.sh cpp/meu_programa.cpp
```

## 🐍 Python
```bash
python python/meu_script.py
```

## 🌐 Web
Abrir `web/index.html` no browser ou servir com:
```bash
python -m http.server 8080
```

---

_Repo gerido automaticamente pelo Mcking._
