@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PY=D:\Program Files\Python\python.exe"
if not exist "%PY%" (echo Python missing & pause & exit /b 1)
if not exist "WiiXLaunch\build_switch.bat" (
 where git >nul 2>&1
 if errorlevel 1 (
  echo ERROR: WiiXLaunch checkout missing. Install Git for Windows to fetch dependencies.
  pause
  exit /b 1
 )
 echo Downloading WiiXLaunch and its required submodules...
 git clone --recurse-submodules https://github.com/BladesawStudios/WiiXLaunch.git "WiiXLaunch"
 if errorlevel 1 (echo Git clone failed & pause & exit /b 1)
)
if not exist "botw\guard_switch_player_hook.py" (
 echo ERROR: missing v1.0.0 player-hook safety guard.
 pause
 exit /b 1
)
echo Installing source guard: unverified Switch player tick will NOT be hooked.
"%PY%" "botw\guard_switch_player_hook.py"
if errorlevel 1 (echo Hook guard failed; refusing to compile & pause & exit /b 1)
call "build_botw_windows.bat" --no-pause
if errorlevel 1 (echo Build failed: package not created & pause & exit /b 1)
"%PY%" "package_botw_windows.py"
if errorlevel 1 (echo Packaging failed & pause & exit /b 1)
echo.
echo ZIP: dist\BotwCraft-experimental.zip
echo WARNING: diagnostic only, Minecraft gameplay not implemented.
pause
