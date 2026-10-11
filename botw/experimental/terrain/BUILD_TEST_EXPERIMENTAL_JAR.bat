@echo off
setlocal
cd /d "%~dp0"
if not exist "BotwCollisionGate.class" (
 echo ERREUR : BotwCollisionGate.class absent. Utilise le ZIP experimente complet.
 exit /b 1
)
python patch_collision_jar.py "..\..\minecraft_mods\skycraft-0.1.2.jar" "BotwCollisionGate.class" "skycraft-botw-terrain-EXPERIMENTAL.jar"
if errorlevel 1 exit /b 1
echo Jar experimental cree. Le Jar stable est conserve intact.
endlocal