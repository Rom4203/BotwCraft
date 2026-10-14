@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PY=D:\Program Files\Python\python.exe"
if not exist "%PY%" (
 echo [ERROR] Python introuvable: %PY%
 pause
 exit /b 1
)
if not exist "bridge\launcher.py" (
 echo [ERROR] Le ZIP manque le lanceur BotwCraft.
 pause
 exit /b 1
)
echo.
echo BOTWCRAFT - MODE CONSTRUCTION EXPERIMENTAL
echo =========================================
echo Minecraft cree un ilot constructible et envoie ses images
echo par-dessus la fenetre Ryujinx.
echo.
echo Ce mode N'INTEGRE PAS les collisions ni la position de Link.
echo AUCUN mod BOTW n'est installe dans Ryujinx.
echo.
"%PY%" "bridge\launcher.py" --preview-blocks
if errorlevel 1 echo [ERROR] Un composant s'est arrete. Consulte la fenetre ci-dessus.
pause
