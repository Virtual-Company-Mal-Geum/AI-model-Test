@echo off
setlocal

set "PYTHON=%~dp0.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo Virtual environment was not found.
    echo Run this first:
    echo python -m venv .venv
    echo .\.venv\Scripts\python -m pip install -r requirements.txt
    exit /b 1
)

pushd "%~dp0" >nul
"%PYTHON%" "%~dp0src\chatgpt_macro.py" %*
set "EXIT_CODE=%ERRORLEVEL%"
popd >nul
exit /b %EXIT_CODE%
