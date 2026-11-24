@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Rode INSTALAR_TESTE.bat primeiro.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" -m liveclips relatorio
echo.
echo Envie o ZIP da pasta RELATORIOS para quem esta ajudando voce. Nada e enviado automaticamente.
pause
