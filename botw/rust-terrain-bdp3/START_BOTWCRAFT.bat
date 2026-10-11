@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem The original BDP3 launcher stays untouched except for terrain environment.
if exist "%~dp0terrain\terrain.json" set "BOTWCRAFT_TERRAIN_DIR=%~dp0terrain"
set "PY_EXE="
if exist "D:\Program Files\Python\python.exe" set "PY_EXE=D:\Program Files\Python\python.exe"
if not defined PY_EXE for %%P in (python.exe) do set "PY_EXE=%%~$PATH:P"
if not defined PY_EXE (
  echo Python introuvable. Voir INSTALLER_COMPLET.bat.
  pause
  exit /b 1
)
"%PY_EXE%" install_clean.py --verify
if errorlevel 1 (
  echo.
  echo BOTWCRAFT n'est pas correctement installe.
  echo Lance INSTALLER_COMPLET.bat, puis reessaie.
  pause
  exit /b 1
)
echo.
echo ==== BOTWCRAFT - DEMARRAGE RUST NATIF ====
"%PY_EXE%" bridge\start_all_rust.py
pause