@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Rode INSTALAR_TESTE.bat primeiro.
 pause
 exit /b 1
)
echo Diagnostico do Hook s - so le informacoes deste computador; nao envia nada.
".venv\Scripts\python.exe" -m liveclips diagnostico
echo.
echo O relatorio ficou em diagnostico_windows.txt. Abra, revise e so entao envie se quiser.
pause
