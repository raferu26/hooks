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
if "%LIVECLIPS_ROOT%"=="" set "LIVECLIPS_ROOT=C:\LiveClips"
echo.
echo  SAAS LOCAL DO HOOK'S - teste no seu computador, sem custo
echo  Servidor: %HOOKS_CLOUD_ROOT%
echo  Programa: %LIVECLIPS_ROOT%
echo.
if exist "%HOOKS_CLOUD_ROOT%\hooks_cloud.sqlite3" goto :tem_admin
echo Primeira execucao: vamos criar o administrador do servidor.
set /p ADM_EMAIL=E-mail do administrador: 
"%PYTHON_EXE%" -m hooks_cloud criar-admin --email "%ADM_EMAIL%" --nome Dono --papel dono
if errorlevel 1 goto :falha_admin
:tem_admin
echo Ligando o Hook's a este servidor...
"%PYTHON_EXE%" -m hooks_cloud vincular --programa "%LIVECLIPS_ROOT%"
echo.
echo Abrindo o servidor em outra janela. Deixe-a aberta.
start "Hook's servidor SaaS" "%PYTHON_EXE%" -m hooks_cloud iniciar
timeout /t 3 >nul
start "" http://127.0.0.1:8800/admin
echo.
echo  1. Entre no painel de administracao que abriu no navegador ^(super admin^).
echo  2. FECHE e abra de novo o Hook's ^(ABRIR_LIVECLIPS.bat^): a tela de login aparece.
echo  3. Para voltar ao modo sem login: DESLIGAR_SAAS_LOCAL.bat
echo.
pause
exit /b 0
:falha_admin
echo Nao foi possivel criar o administrador.
pause
exit /b 1
