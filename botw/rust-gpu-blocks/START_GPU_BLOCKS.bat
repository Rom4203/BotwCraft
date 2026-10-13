@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "BOTWCRAFT_BLOCKS=0"
set "RUST_GPU=%~dp0compositor\botwcraft-rust-gpu-blocks.exe"
if not exist "%RUST_GPU%" (
 echo.
 echo Le renderer Rust GPU est introuvable:
 echo   %RUST_GPU%
 echo Recupere l'artifact botwcraft-rust-gpu-blocks-windows-experimental
 echo dans GitHub Actions de la branche feature/rust-render-pipeline-20261012.
 echo Decompresse botwcraft-rust-gpu-blocks.exe dans compositor.
 pause
 exit /b 1
)
if not exist "%~dp0START_BOTWCRAFT.bat" (
 echo Ce BAT doit etre copie dans le dossier racine de BotwCraft.
 pause
 exit /b 1
)
echo.
echo === BotwCraft : vrai moteur 3D Rust/WGPU experimental ===
echo Collision/deplacement intacts; aucun fichier de Ryujinx modifie.
echo Lancement de la surcouche GPU puis du BotwCraft d'origine.
echo L'ancien bloc renderer Python est desactive.
echo.
start "BotwCraft GPU blocks" /b "%RUST_GPU%"
call "%~dp0START_BOTWCRAFT.bat"
rem One local BotwCraft session at a time; stop our experimental GPU layer.
taskkill /f /im botwcraft-rust-gpu-blocks.exe >nul 2>&1
endlocal
