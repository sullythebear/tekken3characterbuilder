@echo off
cd /d "%~dp0"
echo.
echo  DIZZY PROBE - CONTROLE
echo  Map: %CD%
echo.
echo  [1] Is de broncode aangepast?
findstr /C:"TEKKEN3_DIZZY_PROBE" "src\tekken3_jun_roster.c" >nul && (echo      JA) || (echo      NEE - het patchscript is in deze map niet toegepast)
if exist "src\tekken3_jun_roster.c.dizzy-backup" (echo      Backup gevonden) else (echo      Geen backup gevonden)
echo.
echo  [2] Zit de aanpassing in het gebouwde spel?
powershell -NoProfile -Command "if (Select-String -LiteralPath 'build-release\Tekken_3_Recompiled.exe' -Pattern 'Dizzy probe' -SimpleMatch -Quiet) { '     JA' } else { '     NEE - het spel is niet opnieuw gebouwd met de aangepaste code' }"
echo.
echo  [3] Tijdstippen:
powershell -NoProfile -Command "'     Broncode aangepast: ' + (Get-Item 'src\tekken3_jun_roster.c').LastWriteTime; '     Spel gebouwd:       ' + (Get-Item 'build-release\Tekken_3_Recompiled.exe').LastWriteTime"
echo.
echo  [4] Laatste regels van de vorige build:
powershell -NoProfile -Command "if (Test-Path 'build-log.txt') { Get-Content 'build-log.txt' -Tail 5 } else { '     Geen build-log.txt gevonden' }"
echo.
pause
