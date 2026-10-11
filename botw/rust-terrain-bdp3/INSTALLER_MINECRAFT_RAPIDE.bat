@echo off
setlocal
cd /d "%~dp0"
set "PROFILE=D:\Jeux\Minecraft\prism\instances\BotwCraftNative\minecraft\mods"
if not exist "%PROFILE%" set "PROFILE=%APPDATA%\PrismLauncher\instances\BotwCraftNative\minecraft\mods"
if not exist "%PROFILE%" (
  echo Le dossier Minecraft BotwCraftNative est introuvable.
  echo Installe le JAR manuellement dans Minecraft/Prism : minecraft\mods.
  pause
  exit /b 1
)
if not exist "minecraft_mods\skycraft-0.1.2.jar" (
  echo JAR introuvable.
  pause
  exit /b 1
)
if exist "%PROFILE%\skycraft-0.1.2.jar" copy /Y "%PROFILE%\skycraft-0.1.2.jar" "%PROFILE%\skycraft-0.1.2.jar.bak-before-havok" >nul
copy /Y "minecraft_mods\skycraft-0.1.2.jar" "%PROFILE%\skycraft-0.1.2.jar" >nul
if errorlevel 1 (echo Echec copie JAR. Ferme Minecraft et reessaie. & pause & exit /b 1)
echo [OK] JAR SkyCraft installe dans %PROFILE%
echo ATTENTION : il faut AUSSI INSTALLER_COMPLET.bat pour le module native Havok Zelda.
pause