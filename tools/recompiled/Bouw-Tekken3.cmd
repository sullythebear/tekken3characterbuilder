@echo off
setlocal EnableExtensions
title Tekken 3 Recompiled - testbuild
cd /d "%~dp0"
set "ROOT=%CD%"
set "PY=%ROOT%\.runtime\python\python.exe"
set "LOG=%ROOT%\build-log.txt"

echo.
echo  TEKKEN 3 RECOMPILED - TESTBUILD
echo  Map: %ROOT%
echo.

if not exist "%ROOT%\game.toml" goto :no_root
if not exist "%PY%" goto :no_python

rem Zoek de compiler die de Easy Setup zelf heeft gedownload.
set "TC="
for /d %%D in ("%ROOT%\.setup\tools\toolchain-*") do set "TC=%%~fD"
if not defined TC goto :no_tools
if not exist "%TC%\bin\cmake.exe" goto :no_tools

rem Zelfde omgeving als launcher\setup_backend.py; alleen voor dit venster.
set "PATH=%TC%\bin;%PATH%"
set "PSXRECOMP_TOOLCHAIN_DIR=%TC%"
set "RETCOMM_TOOLCHAIN_DIR=%TC%"
set "PYTHONUTF8=1"
set "PYTHONNOUSERSITE=1"
set /a JOBS=%NUMBER_OF_PROCESSORS%
if %JOBS% LSS 2 set JOBS=2
if %JOBS% GTR 8 set JOBS=8
set "CMAKE_BUILD_PARALLEL_LEVEL=%JOBS%"

set "ROOTF=%ROOT:\=/%"
set "TCF=%TC:\=/%"
set "PYF=%PY:\=/%"

rem Een gekopieerde map heeft nog een CMake-cache die naar de originele map wijst.
if not exist "%ROOT%\build-release\CMakeCache.txt" goto :configure
findstr /I /C:"CMAKE_HOME_DIRECTORY:INTERNAL=%ROOTF%" "%ROOT%\build-release\CMakeCache.txt" >nul
if not errorlevel 1 goto :configure
echo  Deze map is een kopie: de oude CMake-cache wordt opgeruimd.
echo  De eerste build duurt daardoor ongeveer net zo lang als de setup.
echo.
del /q "%ROOT%\build-release\CMakeCache.txt"
if exist "%ROOT%\build-release\CMakeFiles" rmdir /s /q "%ROOT%\build-release\CMakeFiles"

:configure
echo  [1/2] Configureren...
"%TC%\bin\cmake.exe" -S "%ROOTF%" -B "%ROOTF%/build-release" -G Ninja ^
 -DCMAKE_BUILD_TYPE=Release -DCMAKE_SUPPRESS_REGENERATION=ON ^
 "-DCMAKE_C_COMPILER=%TCF%/bin/clang.exe" "-DCMAKE_CXX_COMPILER=%TCF%/bin/clang++.exe" ^
 "-DCMAKE_MAKE_PROGRAM=%TCF%/bin/ninja.exe" "-DPython3_EXECUTABLE=%PYF%" ^
 -DPSX_STATIC_RUNTIME=ON -DPSX_DEBUG_TOOLS=OFF -DPSX_DEBUG_SERVER_LITE=OFF -DPSX_NETPLAY=OFF ^
 -DPSXRECOMP_BIOS_STEMS=OpenBIOS -DPSXRECOMP_FORCE_SETUP_HOST=OFF -DPSXRECOMP_REQUIRE_GAME_C=ON ^
 -DTEKKEN3_BUILD_PC_PORT=OFF -DTEKKEN3_JUN_EXPERIMENTAL=ON > "%LOG%" 2>&1
if errorlevel 1 goto :failed

echo  [2/2] Bouwen met %JOBS% processen, even geduld...
"%TC%\bin\cmake.exe" --build "%ROOTF%/build-release" --target psx-runtime --parallel %JOBS% >> "%LOG%" 2>&1
if errorlevel 1 goto :failed

echo.
echo  KLAAR! Start deze testversie met:
echo  build-release\Tekken_3_Recompiled.exe
goto :end

:failed
echo.
echo  De build is mislukt. Laatste regels uit build-log.txt:
echo  ------------------------------------------------------
powershell -NoProfile -Command "Get-Content -LiteralPath $env:LOG -Tail 40"
goto :end

:no_root
echo  Zet dit script in de hoofdmap van je Easy Setup-kopie,
echo  naast "Play Tekken 3.exe" en game.toml.
goto :end

:no_python
echo  Ingebouwde Python niet gevonden (.runtime\python\python.exe).
echo  Is dit wel een Easy Setup-map?
goto :end

:no_tools
echo  Compiler niet gevonden in .setup\tools\toolchain-*.
echo  Heeft de Easy Setup in deze map al een keer succesvol gebouwd?
goto :end

:end
echo.
pause
