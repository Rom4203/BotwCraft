@echo off
setlocal EnableExtensions
rem BotwCraft Switch v1.0.0 build helper. Builds only: never installs into Ryujinx.
rem IMPORTANT: game-specific host hooks are experimental and must be validated.
set "ROOT=%~dp0"
set "WIIXL=%ROOT%WiiXLaunch"
set "DEVKITPRO_WIN=D:\Bordel\Code\gameboy\devkit\devkitPro"
set "DEVKITPRO=%DEVKITPRO_WIN%"
set "DEVKITA64=%DEVKITPRO%\devkitA64"
set "PY=D:\Program Files\Python\python.exe"
if not exist "%WIIXL%\build_switch.bat" (
 echo [ERROR] WiiXLaunch not found at "%WIIXL%"
 goto :failed
)
if not exist "%DEVKITA64%\bin" (
 echo [ERROR] devkitA64 not found at "%DEVKITA64%"
 goto :failed
)
if not exist "%PY%" (
 echo [ERROR] Python not found at "%PY%"
 goto :failed
)
rem WiiXLaunch uses bare "python" when generating its configuration.
rem Prepend the installed Python directory to PATH, bypassing Windows Store aliases.
set "PATH=D:\Program Files\Python;%PATH%"
echo [INFO] Python for host build:
where python
python --version
if errorlevel 1 goto :failed
if exist "%ROOT%mod\botw\guest_mod\mod.json" (
 set "GUEST=%ROOT%mod\botw\guest_mod"
) else (
 if exist "%ROOT%botw\guest_mod\mod.json" (
  set "GUEST=%ROOT%botw\guest_mod"
 ) else (
  echo [ERROR] BOTW guest mod.json missing
  goto :failed
 )
)
echo [1/2] Compiling BOTW host...
pushd "%WIIXL%"
call build_switch.bat botw
set "RC=%ERRORLEVEL%"
popd
if not "%RC%"=="0" (
 echo [ERROR] Host compilation failed with code %RC%.
 goto :failed
)
echo [2/2] Compiling BotwCraft guest...
"%PY%" "%WIIXL%\sdk\scripts\build_mod.py" --source "%GUEST%" --target switch
if errorlevel 1 (
 echo [ERROR] Guest compilation failed.
 goto :failed
)
echo.
echo [OK] Builds completed. Ryujinx was NOT modified.
echo Host: "%WIIXL%\build\switch\subsdk9"
echo Guest: "%GUEST%\build\switch-mods\botwcraft.wxlm"
echo [NOTE] This does not demonstrate a working player hook or Minecraft linkage.
goto :end
:failed
set "BUILD_FAILED=1"
echo.
echo Build stopped; Ryujinx remains unchanged.
:end
if /i not "%~1"=="--no-pause" pause
if defined BUILD_FAILED (exit /b 1) else (exit /b 0)
