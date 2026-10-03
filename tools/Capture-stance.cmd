@echo off
rem Starts Tekken 3 with the renderer's probe on: it records how every body part is drawn.
rem Pick NINA (P1) against anyone, stand still for 10 seconds in the fight, then close the game.
cd /d "%~dp0..\build-release"
set TEKKEN3_NATIVE_PROBE=%~dp0logs\stance.probe
del "%~dp0logs\stance.probe*" 2>nul
Tekken_3_Recompiled.exe 2> "%~dp0logs\stance-log.txt"
echo Done. You can close this window.
pause
