@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo [BotwCraft BWC2] Native Hyrule WORLD SPACE mesh transport.
echo [BotwCraft BWC2] This is NOT the legacy 2D triangle projection.
echo [BotwCraft BWC2] The native Zelda camera must provide a real view matrix.
echo [BotwCraft BWC2] Ryujinx GDB stub must listen on 127.0.0.1:22225.
echo [BotwCraft BWC2] Do NOT start another bridge simultaneously.
set "BOTWCRAFT_WORLD_GDB_PORT=22225"
call "%~dp0START_BRIDGE.bat"
