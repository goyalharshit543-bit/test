@echo off
REM ── SkyCart: stop any running server + drone firmware processes ──
echo Stopping SkyCart server and drone processes...

taskkill /F /IM drone_controller.exe >nul 2>&1

REM Kill only python processes that run backend.main (not all of Python).
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*backend.main*' } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop } catch {} }"

timeout /t 1 /nobreak >nul
echo Done. Port 8000 should now be free - start the server again with:
echo     python -m backend.main
