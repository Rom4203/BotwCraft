@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo ============================================================
echo BotwCraft - Steve controls Link (experimental XInput)
echo ============================================================
echo Required: START_BRIDGE.bat running, BOTW 1.5.0 in Ryujinx,
echo Minecraft world with /botwcraft connect and /botwcraft inputs on.
echo Ryujinx Settings > Input > Player 1 must use the VIRTUAL Xbox pad.
echo This sends movement+camera stick input. First-person camera is
echo NOT yet overridden inside Zelda. No saves, TP, or game files altered.
echo ============================================================
set "PYTHON_EXE="
if exist "D:\Program Files\Python\python.exe" set "PYTHON_EXE=D:\Program Files\Python\python.exe"
if not defined PYTHON_EXE (
  where py >nul 2>&1
  if not errorlevel 1 set "PYTHON_EXE=py -3"
)
if not defined PYTHON_EXE set "PYTHON_EXE=python"
%PYTHON_EXE% -c "import vgamepad" >nul 2>&1
if errorlevel 1 (
 echo [BotwCraft Link] Missing vgamepad Python package or ViGEmBus driver.
 echo [BotwCraft Link] Install vgamepad with:
 echo     py -3 -m pip install vgamepad
 echo and ensure ViGEmBus is installed, then relaunch.
 pause
 exit /b 2
)
if not exist "bridge\steve_controller.py" (
 echo [BotwCraft Link] ERROR: bridge\steve_controller.py missing.
 pause
 exit /b 3
)
%PYTHON_EXE% -u "bridge\steve_controller.py" %*
echo [BotwCraft Link] Stopped; virtual sticks released.
pause
