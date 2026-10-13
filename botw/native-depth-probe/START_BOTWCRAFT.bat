@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo.
echo Demarre ton BotwCraft habituel (Ryujinx + Minecraft).
echo Ce programme ne remplace pas le jeu ; il affiche les sondes NVN.
echo.
where py >nul 2>nul
if not errorlevel 1 (
  py -3 monitor.py
) else (
  python monitor.py
)
pause
