#!/usr/bin/env pwsh
# build.ps1 - Build helper for C++ files using MSYS2 or MSVC
param(
  [Parameter(Position=0)] [string]$File,
  [switch]$Msvc,
  [switch]$Run
)

if (-not $File) {
  Write-Host "Usage: .\scripts\build.ps1 <file.cpp> [-msvc] [-run]" -ForegroundColor Yellow
  exit 1
}

if (-not (Test-Path $File)) {
  Write-Host "❌ File not found: $File" -ForegroundColor Red
  exit 1
}

$outName = [System.IO.Path]::GetFileNameWithoutExtension($File)
$outPath = Join-Path (Get-Location) "$outName.exe"

if ($Msvc) {
  # MSVC (Visual Studio)
  & "cl" "/std:c++latest" "/O2" "/EHsc" "/Fe:$outPath" $File 2>&1
  if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ MSVC build failed" -ForegroundColor Red
    exit 1
  }
} elseif (Test-Path "C:\msys64\ucrt64\bin\g++.exe") {
  # MSYS2 GCC
  C:\msys64\usr\bin\bash.exe -l -c "export PATH=/ucrt64/bin:/usr/bin && cd '$(Get-Location | Resolve-Path)' && g++ -std=c++23 -O2 -o '${outName}.exe' '$File' 2>&1"
  if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ GCC build failed" -ForegroundColor Red
    exit 1
  }
} elseif (Test-Path "C:\msys64\ucrt64\bin\clang++.exe") {
  # MSYS2 Clang
  C:\msys64\usr\bin\bash.exe -l -c "export PATH=/ucrt64/bin:/usr/bin && cd '$(Get-Location | Resolve-Path)' && clang++ -std=c++23 -O2 -o '${outName}.exe' '$File' 2>&1"
  if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Clang build failed" -ForegroundColor Red
    exit 1
  }
} else {
  Write-Host "❌ No C++ compiler found (MSYS2 or MSVC)." -ForegroundColor Red
  exit 1
}

Write-Host "✅ Built: $outPath" -ForegroundColor Green

if ($Run) {
  Write-Host "🚀 Running..." -ForegroundColor Cyan
  & $outPath
}
