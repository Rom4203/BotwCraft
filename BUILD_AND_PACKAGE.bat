@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PY=D:\Program Files\Python\python.exe"
if not exist "%PY%" (echo Python missing & pause & exit /b 1)
if not exist "build_botw_windows.bat" (echo Build script missing & pause & exit /b 1)
call "build_botw_windows.bat" --no-pause
if errorlevel 1 (echo Build failed: package not created & pause & exit /b 1)
"%PY%" "package_botw_windows.py"
if errorlevel 1 (echo Packaging failed & pause & exit /b 1)
echo.
echo ZIP: dist\BotwCraft-experimental.zip
pause
