@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 installer.py
) else (
  python installer.py
)
echo.
echo Diagnostic seulement : ta version normale de BotwCraft reste installee.
echo Relance ce fichier et choisis la desactivation pour retirer le module.
pause
