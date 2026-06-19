#!/usr/bin/env pwsh
# build.ps1 — Compila C++ com MSYS2 (GCC/Clang) ou MSVC.
#
#   .\scripts\build.ps1 cpp\gpt.cpp        # 🔧 build
#   .\scripts\build.ps1 cpp\gpt.cpp -run   # 🔧🚀 build + run
#   .\scripts\build.ps1 cpp\gpt.cpp -msvc  # 🏗️ MSVC

param(
  [Parameter(Position=0)] [string]$File,
  [switch]$Msvc,
  [switch]$Run
)

$die   = { param($m) Write-Host "❌ $m" -ForegroundColor Red; exit 1 }
$ok    = { param($m) Write-Host "✅ $m" -ForegroundColor Green }

if (-not $File) { &$die "Usage: .\scripts\build.ps1 <file.cpp> [-msvc] [-run]" }
if (-not (Test-Path $File)) { &$die "File not found: $File" }

$outName = [IO.Path]::GetFileNameWithoutExtension($File)
$outPath = Join-Path (Get-Location) "$outName.exe"

Write-Host "🔧 Compiling $([IO.Path]::GetFileName($File))..." -ForegroundColor Cyan

if ($Msvc) {
  & "cl" "/std:c++latest" "/O2" "/EHsc" "/Fe:$outPath" $File 2>&1
  if ($LASTEXITCODE -ne 0) { &$die "MSVC build failed" }
} elseif (Test-Path "C:\msys64\ucrt64\bin\g++.exe") {
  C:\msys64\usr\bin\bash.exe -l -c "export PATH=/ucrt64/bin:/usr/bin && cd '$(Get-Location | Resolve-Path)' && g++ -std=c++23 -O2 -o '${outName}.exe' '$File' 2>&1"
  if ($LASTEXITCODE -ne 0) { &$die "GCC build failed" }
} elseif (Test-Path "C:\msys64\ucrt64\bin\clang++.exe") {
  C:\msys64\usr\bin\bash.exe -l -c "export PATH=/ucrt64/bin:/usr/bin && cd '$(Get-Location | Resolve-Path)' && clang++ -std=c++23 -O2 -o '${outName}.exe' '$File' 2>&1"
  if ($LASTEXITCODE -ne 0) { &$die "Clang build failed" }
} else {
  &$die "No C++ compiler found (MSYS2 or MSVC)"
}

&$ok "Built: $outPath"

if ($Run) {
  Write-Host "🚀 Running..." -ForegroundColor Cyan
  & $outPath
}
