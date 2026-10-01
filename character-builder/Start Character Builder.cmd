@echo off
title Tekken 3 Recompiled Character Builder
cd /d "%~dp0"
rem Tekken 3 Expanded's Python first (it has Pillow for the Custom page),
rem then the one that comes with the Tekken3Recompiled Easy Setup.
set "PY=%~dp0..\.setup\venv\Scripts\python.exe"
if exist "%PY%" goto :run
set "PY=%~dp0..\.runtime\python\python.exe"
if exist "%PY%" goto :run
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto :nopython
:run
echo Starting Character Builder...
echo Keep this window open while you use the builder.
echo.
if "%PY%"=="py -3" goto :runpy
"%PY%" "app\server.py"
goto :after
:runpy
py -3 "app\server.py"
:after
if errorlevel 1 pause
exit /b
:nopython
echo Python was not found.
echo Put the character-builder folder in the main folder of your Tekken 3
echo Recompiled Easy Setup, next to "Play Tekken 3.exe". The builder then uses
echo the Python that comes with the Easy Setup.
pause
