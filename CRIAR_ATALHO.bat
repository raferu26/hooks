@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
echo HOOK'S - Criar atalho (area de trabalho e menu Iniciar)
rem Usa o script CRIAR_ATALHO.ps1; o atalho abre ".venv\Scripts\pythonw.exe -m liveclips.desktop" com o icone assets\hooks.ico
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0CRIAR_ATALHO.ps1"
if errorlevel 1 (
 echo Nao foi possivel criar o atalho. Voce ainda pode abrir pelo ABRIR_LIVECLIPS.bat.
) else (
 echo Pronto. Abra o Hook's pelo atalho.
)
if /i not "%~1"=="silencioso" pause
exit /b 0
