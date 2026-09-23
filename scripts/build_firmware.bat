@echo off
REM Compile the C/C++ flight controller on Windows (needs MinGW g++ in PATH).
cd /d "%~dp0..\firmware"
if not exist build mkdir build

REM A server that is still running keeps drone_controller.exe locked,
REM which makes the linker fail with "Permission denied". Stop it first.
tasklist /FI "IMAGENAME eq drone_controller.exe" 2>nul | find /I "drone_controller.exe" >nul
if not errorlevel 1 (
  echo Stale drone_controller.exe processes found - stopping them...
  taskkill /F /IM drone_controller.exe >nul 2>&1
  timeout /t 1 /nobreak >nul
)

g++ -std=c++17 -O2 -Wall -Iinclude src\main.cpp src\pid.cpp src\navigation.cpp src\telemetry.c -o build\drone_controller.exe
if %errorlevel% neq 0 (
  echo Build FAILED. Is g++ installed and in PATH? ^(see README - Troubleshooting^)
  exit /b 1
)
echo OK ^> firmware\build\drone_controller.exe
