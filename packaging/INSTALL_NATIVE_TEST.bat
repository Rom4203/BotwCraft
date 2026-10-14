@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo.
echo BOTWCRAFT - INSTALLATION DU MOD NATIF EXPERIMENTAL SWITCH 1.5.0
echo ====================================================================
echo Sauvegarde les parties Zelda avant le test.
echo Cette installation n'active PAS les hooks natifs sur BOTW 1.6.0.
echo.
if exist "D:\Program Files\Python\python.exe" (
 "D:\Program Files\Python\python.exe" "install_native.py"
) else (
 where py >nul 2>&1
 if not errorlevel 1 (
  py -3 "install_native.py"
 ) else (
  python "install_native.py"
 )
)
if errorlevel 1 (
 echo [BotwCraft] ECHEC installation. Voir le message ci-dessus.
 pause
 exit /b 1
)
echo.
echo Installation terminee. Lance START_BRIDGE.bat puis Zelda.
pause
