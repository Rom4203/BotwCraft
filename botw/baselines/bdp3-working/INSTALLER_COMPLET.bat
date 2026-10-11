@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "PY_EXE="
if exist "D:\Program Files\Python\python.exe" set "PY_EXE=D:\Program Files\Python\python.exe"
if not defined PY_EXE for %%P in (python.exe) do set "PY_EXE=%%~$PATH:P"
if not defined PY_EXE (
  echo ERREUR: Python 3 introuvable.
  echo Installer Python 3 ou changer PY_EXE dans ce .bat.
  pause
  exit /b 1
)
echo.
echo ==== BOTWCRAFT - INSTALLATION COMPLETE ET PROPRE ====
echo Fermer Ryujinx avant de continuer.
echo Sauvegarde des anciens modules, puis remplacement et verification.
echo Le programme detectera votre profil Ryujinx et proposera de le confirmer.
echo Il faut choisir le dossier contenant Config.json, pas le dossier mods.
echo.
"%PY_EXE%" install_clean.py
if errorlevel 1 (
  echo.
  echo INSTALLATION ECHEC - voir le message au-dessus.
  pause
  exit /b 1
)
echo.
echo Tout est installe et verifie. Lance START_BOTWCRAFT.bat.
pause
