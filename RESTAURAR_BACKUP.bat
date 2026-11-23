@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
 echo Execute INSTALAR.bat antes de restaurar um backup.
 pause
 exit /b 1
)
echo Feche o Hook's antes de continuar.
set /p "BACKUP_ZIP=Cole o caminho completo do backup ZIP: "
if not exist "%BACKUP_ZIP%" (
 echo Backup nao encontrado.
 pause
 exit /b 1
)
"%PYTHON_EXE%" -m liveclips --restore "%BACKUP_ZIP%"
if errorlevel 1 (
 echo A restauracao nao foi concluida. O estado atual foi preservado.
) else (
 echo Restauracao concluida. Abra o Hook's normalmente.
)
pause
