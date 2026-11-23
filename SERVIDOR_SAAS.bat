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
if "%HOOKS_CLOUD_ROOT%"=="" set "HOOKS_CLOUD_ROOT=%USERPROFILE%\HooksCloud"
if exist "%HOOKS_CLOUD_ROOT%\hooks_cloud.sqlite3" goto :tem_admin
echo Primeira execucao: vamos criar o administrador do servidor.
set /p ADM_EMAIL=E-mail do administrador: 
"%PYTHON_EXE%" -m hooks_cloud criar-admin --email "%ADM_EMAIL%" --nome Dono --papel dono
if errorlevel 1 goto :falha_admin
:tem_admin
echo.
echo Servidor de teste em http://127.0.0.1:8800/admin  ^(Ctrl+C para parar^)
echo Para producao use HTTPS e leia DEPLOY_SERVIDOR.md.
"%PYTHON_EXE%" -m hooks_cloud iniciar
pause
exit /b 0
:falha_admin
echo Nao foi possivel criar o administrador.
pause
exit /b 1
