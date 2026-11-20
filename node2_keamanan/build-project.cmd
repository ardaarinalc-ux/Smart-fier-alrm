@echo off
setlocal
cd /d "%~dp0"
set "PYTHONNOUSERSITE=1"
set "PLATFORMIO_CORE_DIR=%~dp0.hermes-tools\platformio"
set "PLATFORMIO_SETTING_ENABLE_TELEMETRY=No"
set "TEMP=%~dp0.hermes-tools\temp"
set "TMP=%TEMP%"
"%~dp0.hermes-tools\python\python.exe" -m platformio run -e esp32-c3-devkitm-1 -j 1
if errorlevel 1 exit /b %errorlevel%
"%~dp0.hermes-tools\python\python.exe" -m platformio run -e esp32-c3-devkitm-1 -t compiledb
if errorlevel 1 exit /b %errorlevel%
"%~dp0.hermes-tools\python\python.exe" "%~dp0.hermes-tools\normalize_compiledb.py"
exit /b %errorlevel%
