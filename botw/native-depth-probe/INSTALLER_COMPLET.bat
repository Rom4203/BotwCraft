@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo.
echo BOTWCRAFT : TEST NVN SEPARE (ne remplace pas ton BotwCraft jouable)
choice /C IR /M "Installer le module (I) ou le retirer (R)"
if errorlevel 2 (set "MODE=--disable") else (set "MODE=")

rem Le lanceur 'py' de certains PC ne reconnait PAS l'option -3.
rem Tester directement quel interpreteur Python 3 fonctionne vraiment.
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
"%PYTHON_EXE%" installer.py %MODE%
if errorlevel 1 (
  echo [ERREUR] Installation ou retrait non termine. Lis le message ci-dessus.
  pause
  exit /b 1
)
echo.
echo La version jouable de BotwCraft n'a pas ete remplacee.
pause
