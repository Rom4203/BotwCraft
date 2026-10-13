@echo off
setlocal
cd /d "%~dp0"
set "SDK=%~dp0..\..\vendor\WiiXLaunch\sdk"
if not exist "%SDK%\scripts\build_mod.py" (
  echo [BOTWCRAFT] WiiXLaunch SDK missing: %SDK%
  echo [BOTWCRAFT] Clone https://github.com/BladesawStudios/WiiXLaunch into vendor\WiiXLaunch
  exit /b 2
)
py -3 "%SDK%\scripts\build_mod.py" --source "%~dp0" --target switch --wiixlaunch "%SDK%"
if errorlevel 1 (
  echo [BOTWCRAFT] Native build failed. Requires devkitPro devkitA64.
  exit /b 1
)
echo [BOTWCRAFT] Module created. DO NOT REPLACE the existing active mod.
