@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo.
echo BOTWCRAFT : MONITEUR NVN
echo Demarre ton BotwCraft habituel avec Zelda et Minecraft.
echo Ce programme affiche uniquement les sondes NVN.
echo.
set "PYTHON_EXE="
if exist "D:\Program Files\Python\python.exe" (
  "D:\Program Files\Python\python.exe" -c "import sys; assert sys.version_info.major == 3" >nul 2>nul
  if not errorlevel 1 set "PYTHON_EXE=D:\Program Files\Python\python.exe"
)
if not defined PYTHON_EXE (
  python -c "import sys; assert sys.version_info.major == 3" >nul 2>nul
  if not errorlevel 1 set "PYTHON_EXE=python"
)
if not defined PYTHON_EXE (
  py -c "import sys; assert sys.version_info.major == 3" >nul 2>nul
  if not errorlevel 1 set "PYTHON_EXE=py"
)
if not defined PYTHON_EXE (
  echo [ERREUR] Aucun interpreteur Python 3 fonctionnel trouve.
  pause
  exit /b 1
)
"%PYTHON_EXE%" monitor.py
if errorlevel 1 (
  echo [ERREUR] Surveillance NVN interrompue.
  pause
  exit /b 1
)
pause
