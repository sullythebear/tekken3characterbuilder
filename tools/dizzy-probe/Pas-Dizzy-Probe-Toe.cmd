@echo off
cd /d "%~dp0"
if not exist ".runtime\python\python.exe" (
  echo Zet dit bestand in de hoofdmap van je testkopie, naast game.toml.
  pause & exit /b 1
)
".runtime\python\python.exe" dizzy_probe_patch.py %*
echo.
pause
