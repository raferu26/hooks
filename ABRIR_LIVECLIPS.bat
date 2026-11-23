@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
 echo Execute INSTALAR.bat nesta pasta para preparar o Python.
 pause
 exit /b 1
)
for %%I in ("%PYTHON_EXE%") do set "LIVECLIPS_PY_DIR=%%~dpI"
set "PATH=%LIVECLIPS_PY_DIR%;%PATH%"
"%PYTHON_EXE%" -m liveclips
pause
