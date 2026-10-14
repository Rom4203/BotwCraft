@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo [BotwCraft] Start Ryujinx and capture its live console when available.
echo [BotwCraft] This does NOT enable native hooks for Zelda 1.6.0.
if exist "D:\Program Files\Python\python.exe" (
 "D:\Program Files\Python\python.exe" -u "bridge\start_ryujinx_logged.py"
) else (
 where py >nul 2>&1
 if not errorlevel 1 (
  py -3 -u "bridge\start_ryujinx_logged.py"
 ) else (
  python -u "bridge\start_ryujinx_logged.py"
 )
)
if errorlevel 1 echo [BotwCraft] Capture failure - see above.
pause
