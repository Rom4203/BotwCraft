@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "PY_EXE="
if exist "D:\Program Files\Python\python.exe" set "PY_EXE=D:\Program Files\Python\python.exe"
if not defined PY_EXE for %%P in (python.exe) do set "PY_EXE=%%~$PATH:P"
if not defined PY_EXE for %%P in (py.exe) do set "PY_EXE=%%~$PATH:P"
if not defined PY_EXE (
 echo ERREUR: Python 3 introuvable pour le lanceur.
 pause
 exit /b 1
)
"%PY_EXE%" install_clean.py --verify
if errorlevel 1 (
 echo.
 echo Installation incomplete. Lance INSTALLER_COMPLET.bat.
 pause
 exit /b 1
)
"%PY_EXE%" bridge\start_all_rust.py
if errorlevel 1 (
 echo.
 echo BotwCraft s'est arrete avec une erreur. Regarde logs\botwcraft.log.
)
pause