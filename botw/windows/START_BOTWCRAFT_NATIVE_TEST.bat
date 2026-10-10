@echo off
setlocal
cd /d "%~dp0"
echo BOTWCRAFT - Nintendo BOTW 1.5.0 native Rust test
echo =====================================================
echo [1] Installing the experimental WiiXLaunch module...
set "PYTHON_EXE=python"
if exist "D:\Program Files\Python\python.exe" set "PYTHON_EXE=D:\Program Files\Python\python.exe"
"%PYTHON_EXE%" install_native_experimental.py
if errorlevel 1 (
  echo [BOTWCRAFT] Native installation failed. Ryujinx was not started.
  pause
  exit /b 1
)
echo [2] Starting Rust bridge, Ryujinx log relay and Rust game window...
"%PYTHON_EXE%" bridge\start_all_rust.py
pause
