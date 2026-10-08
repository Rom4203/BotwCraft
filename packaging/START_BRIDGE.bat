@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PY=D:\Program Files\Python\python.exe"
if not exist "%PY%" (
  echo [ERROR] Missing Python: "%PY%"
  pause
  exit /b 1
)
if not exist "bridge\launcher.py" (
  echo [ERROR] Missing bridge/launcher.py; package incomplete.
  pause
  exit /b 1
)
echo Starting BotwCraft Windows input and telemetry bridge.
echo Ryujinx Player 1 needs the virtual X360 controller ^(vgamepad + ViGEmBus^).
echo IMPORTANT: native BOTW/Minecraft gameplay integration is unfinished.
"%PY%" "bridge\launcher.py"
pause
