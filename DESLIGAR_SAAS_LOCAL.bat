@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if "%LIVECLIPS_ROOT%"=="" set "LIVECLIPS_ROOT=C:\LiveClips"
if "%HOOKS_CLOUD_ROOT%"=="" set "HOOKS_CLOUD_ROOT=%USERPROFILE%\HooksCloud"
"%PYTHON_EXE%" -m hooks_cloud vincular --programa "%LIVECLIPS_ROOT%" --desligar
echo Feche e abra o Hook's de novo. Seus videos e cortes nao sao apagados.
pause
