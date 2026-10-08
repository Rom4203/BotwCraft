@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PY=D:\Program Files\Python\python.exe"
if not exist "%PY%" (
  echo Python was not found in D:\Program Files\Python.
  pause
  exit /b 1
)
if not exist "bridge\host_bridge.py" (
  echo The package is incomplete.
  pause
  exit /b 1
)
start "BotwCraft host bridge" "%PY%" "bridge\host_bridge.py"
echo The bridge is running in another window. Close it after playing.
echo This is telemetry-only. It does not control BOTW or render Minecraft blocks.
"%PY%" "bridge\ryujinx_log_relay.py"
pause
