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
rem Keep WiiXLaunch and its BOTW submodule pinned even when called directly.
"%PY%" "%ROOT%botw\setup_wiixlaunch.py"
if errorlevel 1 goto :failed
rem Enforce source safety even if this helper is run without BUILD_AND_PACKAGE.bat.
if not exist "%ROOT%botw\guard_switch_player_hook.py" (
 echo [ERROR] Missing Switch hook safety guard.
 goto :failed
)
"%PY%" "%ROOT%botw\guard_switch_player_hook.py"
if errorlevel 1 goto :failed
rem Never probe unmounted SD paths: Ryujinx 1.3.3 aborts in nn::fs.
"%PY%" "%ROOT%botw\guard_switch_fs.py"
if errorlevel 1 goto :failed
"%PY%" "%ROOT%botw\guard_unknown_switch_build.py"
if errorlevel 1 goto :failed
rem BOTW Switch 1.5.0: sample PlayerInfo via documented native methods,
rem fingerprint-locked; NO unverified PlayerTick patch is installed.
"%PY%" "%ROOT%botw\patch_botw15_player_pose.py"
if errorlevel 1 goto :failed
rem WiiXLaunch uses bare "python" when generating its configuration.
rem Prepend the installed Python directory to PATH, bypassing Windows Store aliases.
set "PATH=D:\Program Files\Python;%PATH%"
echo [INFO] Python for host build:
where python
python --version
if errorlevel 1 goto :failed
rem Always compile the GitHub-tracked, safely capability-gated guest.
rem Legacy "mod\\botw\\guest_mod" may contain an experimental crashing hook.
if exist "%ROOT%botw\guest_mod\mod.json" (
 set "GUEST=%ROOT%botw\guest_mod"
) else (
 echo [ERROR] BOTW canonical guest botw\\guest_mod\\mod.json missing
 goto :failed
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
