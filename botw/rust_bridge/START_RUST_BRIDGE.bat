@echo off
setlocal
cd /d "%~dp0"
if exist "target\release\botwcraft-rust-bridge.exe" goto run
where cargo >nul 2>nul
if errorlevel 1 (
  echo [RUST_BRIDGE] Cargo not found. Install the Rust toolchain.
  exit /b 1
)
echo [RUST_BRIDGE] First-time compilation (offline).
cargo build --release --offline
if errorlevel 1 (
  echo [RUST_BRIDGE] Missing cached crates; retrying online.
  cargo build --release
)
if errorlevel 1 (
  echo [RUST_BRIDGE] Build failed; see Cargo diagnostics above.
  exit /b 1
)
:run
echo [RUST_BRIDGE] Starting localhost server + shared-memory producer.
"target\release\botwcraft-rust-bridge.exe"
exit /b %ERRORLEVEL%
