@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
 echo Execute INSTALAR.bat nesta pasta primeiro.
 pause
 exit /b 1
)
"%PYTHON_EXE%" -m liveclips diag
echo.
echo O ZIP fica na pasta "diagnosticos" dentro da pasta de dados (C:\LiveClips por padrao).
echo Ele nao leva videos, banco de dados nem perfis. Tokens e o nome de usuario do Windows sao ocultados.
pause
