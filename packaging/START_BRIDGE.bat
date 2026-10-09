@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PY=D:\Program Files\Python\python.exe"
if not exist "%PY%" (
  where py >nul 2>&1
  if not errorlevel 1 (
    set "PY=py -3"
  ) else (
    set "PY=python"
  )
)
if not exist "bridge\launcher.py" (
  echo [ERROR] bridge\launcher.py missing.
  pause
  exit /b 1
)
if exist "ryujinx-data.txt" (
  set /p BOTWCRAFT_RYUJINX_DATA=<"ryujinx-data.txt"
  if defined BOTWCRAFT_RYUJINX_DATA (
    set "BOTWCRAFT_SDROOT=%BOTWCRAFT_RYUJINX_DATA%\sdcard"
  )
)
echo [BotwCraft] Native BOTW 1.5.0 bridge: Minecraft host, Link log, NVN meshes.
echo [BotwCraft] Ctrl+C stops the bridge. Ryujinx runs separately.
echo [BotwCraft] This is NOT a verified playable game build.
%PY% "bridge\launcher.py"
pause
