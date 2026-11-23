@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
echo HOOK'S - Atualizar para uma versao nova
echo Seus dados (C:\LiveClips) NAO sao tocados. O programa antigo fica guardado em liveclips_anterior.
echo Feche o Hook's antes de continuar.
set /p "NOVO_ZIP=Cole o caminho completo do ZIP da versao nova: "
:: Arrastar o arquivo para a janela coloca aspas; aspas soltas quebrariam a checagem.
set "NOVO_ZIP=%NOVO_ZIP:"=%"
if not exist "%NOVO_ZIP%" (
 echo ZIP nao encontrado.
 pause
 exit /b 1
)
set "TEMP_NOVO=%TEMP%\liveclips_novo"
if exist "%TEMP_NOVO%" rmdir /s /q "%TEMP_NOVO%"
powershell -NoProfile -Command "Expand-Archive -LiteralPath '%NOVO_ZIP:'=''%' -DestinationPath '%TEMP_NOVO:'=''%' -Force"
if errorlevel 1 goto erro
if not exist "%TEMP_NOVO%\LiveClips\liveclips\__init__.py" (
 echo Este ZIP nao parece ser uma versao do Hook's.
 goto erro
)
if exist liveclips_anterior rmdir /s /q liveclips_anterior
move liveclips liveclips_anterior >nul
if errorlevel 1 goto erro
robocopy "%TEMP_NOVO%\LiveClips" "%~dp0." /E /XD .venv /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto volta
".venv\Scripts\python.exe" -m pip install --log instalacao.log -r requirements.txt
if errorlevel 1 goto volta
echo Atualizacao concluida. Abra o ABRIR_LIVECLIPS.bat. O Hook's faz um backup automatico dos dados ao abrir.
pause
exit /b 0
:volta
echo A copia falhou. Voltando para a versao anterior...
if exist liveclips rmdir /s /q liveclips
move liveclips_anterior liveclips >nul
:erro
echo A atualizacao nao foi concluida. Nada foi apagado dos seus dados.
pause
exit /b 1
