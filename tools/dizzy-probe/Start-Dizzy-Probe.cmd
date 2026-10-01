@echo off
cd /d "%~dp0"
if not exist "build-release\Tekken_3_Recompiled.exe" (
  echo Testversie niet gevonden. Bouw eerst met Bouw-Tekken3.cmd.
  pause & exit /b 1
)
set "TEKKEN3_DIZZY_PROBE=1"
echo Dizzy probe actief. Logboek: dizzy-log.txt
cd build-release
"Tekken_3_Recompiled.exe" 2> "..\dizzy-log.txt"
cd ..
echo.
echo Spel afgesloten. Regels over Dizzy en Jun uit het logboek:
findstr /I "Dizzy Jun" dizzy-log.txt
echo.
pause
