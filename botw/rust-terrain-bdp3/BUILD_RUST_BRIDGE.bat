@echo off
setlocal
cd /d "%~dp0sources\botw\rust_bridge"
where cargo >nul 2>nul
if errorlevel 1 (
 echo Rust n'est pas installe. Installer https://rustup.rs/ avec MSVC.
 pause
 exit /b 1
)
cargo test
if errorlevel 1 (
 echo ECHEC tests Rust. Le bridge actuel reste intact.
 pause
 exit /b 1
)
cargo build --release
if errorlevel 1 (
 echo ECHEC build Rust. Le bridge actuel reste intact.
 pause
 exit /b 1
)
copy /y "target\release\botwcraft-rust-bridge.exe" "%~dp0bridge\botwcraft-rust-bridge.exe" >nul
if errorlevel 1 (
 echo ECHEC de copie de l'executable.
 pause
 exit /b 1
)
echo OK : bridge Rust avec collisions installe.
pause