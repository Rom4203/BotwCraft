@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem INSTALLER UNIQUE : bridge Rust inclus, JAR Minecraft et module Zelda Havok.
set "PY_EXE="
if exist "D:\Program Files\Python\python.exe" set "PY_EXE=D:\Program Files\Python\python.exe"
if not defined PY_EXE for %%P in (python.exe) do set "PY_EXE=%%~$PATH:P"
if not defined PY_EXE for %%P in (py.exe) do set "PY_EXE=%%~$PATH:P"
if not defined PY_EXE (
  echo ERREUR : Python est requis uniquement pour installer et lancer BDP3.
  echo Le moteur des COLLISIONS fonctionne dans Rust + Zelda + Fabric.
  pause
  exit /b 1
)
if not exist "bridge\botwcraft-rust-bridge.exe" (echo ERREUR : bridge Rust absent. & pause & exit /b 1)
if not exist "native\bwc_pose.wxlm" (echo ERREUR : module Havok absent. & pause & exit /b 1)
if not exist "minecraft_mods\skycraft-0.1.2.jar" (echo ERREUR : mod Minecraft absent. & pause & exit /b 1)
echo.
echo ====================================================
echo BOTWCRAFT - INSTALLATION DES COLLISIONS SKYCRAFT/HAVOK
echo ====================================================
echo Ferme Ryujinx et Minecraft avant l'installation.
echo.
set "PRISM=D:\Jeux\Minecraft\prism\instances\BotwCraftNative\minecraft\mods"
if not exist "%PRISM%" set "PRISM=%APPDATA%\PrismLauncher\instances\BotwCraftNative\minecraft\mods"
if exist "%PRISM%" (
  echo Instance Prism trouvee : %PRISM%
  "%PY_EXE%" install_clean.py --minecraft-mods "%PRISM%"
) else (
  echo Instance Prism auto introuvable : selectionner son dossier mods lorsque demande.
  "%PY_EXE%" install_clean.py
)
if errorlevel 1 (echo. & echo Installation echouee. Verifie le message ci-dessus. & pause & exit /b 1)
echo.
echo [OK] Zelda Havok + Rust + mod Minecraft installes.
echo Pour jouer : double-clique sur START_BOTWCRAFT.bat.
pause