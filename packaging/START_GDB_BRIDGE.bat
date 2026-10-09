@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo [BotwCraft GDB] EXPERIMENTAL GDB MEMORY TRANSPORT.
echo [BotwCraft GDB] Back up Zelda saves before testing.
echo [BotwCraft GDB] In Ryujinx Options - Debug, enable GDB Stub, port 22225.
echo [BotwCraft GDB] DO NOT run START_BRIDGE.bat alongside this script.
echo [BotwCraft GDB] Zelda may pause briefly for each transfer.
set "BOTWCRAFT_GDB_PORT=22225"
call "%~dp0START_BRIDGE.bat"
