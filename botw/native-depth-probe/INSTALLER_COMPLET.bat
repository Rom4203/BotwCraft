@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo.
echo BOTWCRAFT : TEST NVN SEPARE (ne remplace pas ton BotwCraft jouable)
choice /C IR /M "Installer le module (I) ou le retirer (R)"
set "MODE="
if errorlevel 2 set "MODE=--disable"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 installer.py %MODE%
) else (
  python installer.py %MODE%
)
echo.
echo La version de jeu BotwCraft installee n'est pas modifiee.
pause
