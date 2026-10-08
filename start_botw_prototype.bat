@echo off
setlocal EnableExtensions
rem BotwCraft experimental telemetry transport; does NOT modify Ryujinx.
cd /d "%~dp0"
set "PY=D:\Program Files\Python\python.exe"
if not exist "%PY%" (
 echo ERROR: Python not found at "%PY%"
 pause
 exit /b 1
)
if not exist "botw\host_bridge.py" (
 echo ERROR: botw\host_bridge.py missing
 pause
 exit /b 1
)
if not exist "botw\ryujinx_log_relay.py" (
 echo ERROR: botw\ryujinx_log_relay.py missing
 pause
 exit /b 1
)
echo Running validation tests...
"%PY%" -m unittest botw.test_ryujinx_log_relay
if errorlevel 1 (
 echo ERROR: Relay validation failed. Ryujinx unchanged.
 pause
 exit /b 1
)
echo Launching host bridge in another window...
start "BotwCraft host bridge" "%PY%" "botw\host_bridge.py"
echo Relay follows actual Ryujinx logs and sends them to the bridge.
echo Minecraft input/control, collision and rendering are not implemented.
"%PY%" "botw\ryujinx_log_relay.py"
echo Relay stopped. Close the host bridge window when finished.
pause
