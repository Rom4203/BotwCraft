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
echo.
echo ==== COLLISIONS DIRECTES DE ZELDA (SANS RAYCAST) ====
set "ROMFS=D:\Jeux\Emu\Jeux\botw_dump\romfs"
if not exist "%ROMFS%\Physics\TeraMeshRigidBody\MainField" (
  echo Dossier BOTW RomFS non trouve au chemin habituel.
  set /p "ROMFS=Chemin complet du dossier romfs extrait (Entree = ignorer) : "
)
if exist "%ROMFS%\Physics\TeraMeshRigidBody\MainField" (
 echo Conversion de tes collisions locales, uniquement la premiere fois ou si elles changent...
 "%PY_EXE%" botw_collision_converter.py "%ROMFS%\Physics\TeraMeshRigidBody\MainField" --output "%~dp0terrain_cache"
 if errorlevel 1 (
   echo [AVERTISSEMENT] Conversion incomplete. Tu peux relancer INSTALLER_COMPLET plus tard.
   echo Le mode raycast de secours reste disponible.
 ) else (
   echo [OK] Terrain de Zelda extrait et en cache local. Aucun fichier de jeu dans le ZIP.
 )
) else (
 echo [AVERTISSEMENT] Terrain RomFS introuvable : seul le raycast de secours fonctionnera.
)
echo.
echo ==== COLLISIONS DE DECORS ZELDA (arbres, batiments, rochers) ====
if exist "%ROMFS%\Physics\StaticCompound\MainField" (
 echo Conversion des formes statiques, leurs rotations et positions ; cache reutilisable...
 "%PY_EXE%" botw_decor_converter.py "%ROMFS%\Physics\StaticCompound\MainField" --output "%~dp0terrain_cache"
 if errorlevel 1 echo [AVERTISSEMENT] Cache des decors incomplet, relief deja conserve.
) else (
 echo [AVERTISSEMENT] StaticCompound/MainField introuvable. Relief seul disponible.
)
echo.
echo [OK] Mod Minecraft, module Zelda et bridge Rust prepares.
echo Lance START_BOTWCRAFT.bat pour jouer.
pause