@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Rode INSTALAR_TESTE.bat primeiro.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" -m liveclips selfcheck
echo.
echo O resultado detalhado ficou em relatorio_autoteste.json (nao tem videos nem dados pessoais).
pause
