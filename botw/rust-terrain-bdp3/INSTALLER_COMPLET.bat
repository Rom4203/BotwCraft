@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "PY_EXE="
if exist "D:\Program Files\Python\python.exe" set "PY_EXE=D:\Program Files\Python\python.exe"
if not defined PY_EXE for %%P in (python.exe) do set "PY_EXE=%%~$PATH:P"
if not defined PY_EXE for %%P in (py.exe) do set "PY_EXE=%%~$PATH:P"
if not defined PY_EXE (
 echo ERREUR: Python 3 introuvable pour l'installation.
 pause
 exit /b 1
)
echo.
echo ==== BOTWCRAFT : INSTALLER TOUT ====
echo Ferme Minecraft et Ryujinx avant l'installation.
echo.
set "PRISM=D:\Jeux\Minecraft\prism\instances\BotwCraftNative\minecraft\mods"
if not exist "%PRISM%" set "PRISM=%APPDATA%\PrismLauncher\instances\BotwCraftNative\minecraft\mods"
if exist "%PRISM%" (
 "%PY_EXE%" install_clean.py --minecraft-mods "%PRISM%"
) else (
 echo Ton instance BotwCraftNative n'a pas ete trouvee automatiquement.
 "%PY_EXE%" install_clean.py
)
if errorlevel 1 (
 echo.
 echo ERREUR: installation non terminee. Lis le message ci-dessus.
 pause
 exit /b 1
)
echo.
echo [OK] Mod Minecraft, module Zelda et bridge Rust prepares.
echo Lance START_BOTWCRAFT.bat pour jouer.
pause