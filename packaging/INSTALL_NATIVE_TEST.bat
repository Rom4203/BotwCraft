@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PY=D:\Program Files\Python\python.exe"
if not exist "%PY%" (
  where py >nul 2>&1
  if not errorlevel 1 (
    set "PY=py -3"
  ) else (
    set "PY=python"
  )
)
echo.
echo BOTWCRAFT - INSTALLATION DU MOD NATIF SWITCH 1.5.0
echo --------------------------------------------------
echo Sauvegarde tes parties Zelda avant tout essai.
echo Aucun module de version 1.0.0 ne doit rester actif.
echo Les fichiers sont copies dans ExeFS ET la SD virtuelle de Ryujinx.
echo.
%PY% "install_native.py"
if errorlevel 1 (
  echo [ECHEC] Installation interrompue; regarde l'erreur ci-dessus.
  pause
  exit /b 1
)
echo.
echo Modules copies. Cette compilation est un essai technique,
echo PAS un Minecraft jouable confirme.
echo.
echo Lance ensuite START_BRIDGE.bat dans ce dossier,
echo puis BOTW Switch 1.5.0 dans Ryujinx.
pause
