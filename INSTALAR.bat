@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
echo HOOK'S - Preparar ambiente local
set "PYTHON_BASE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if exist "%PYTHON_BASE%" goto python_ok
py -3.11 -c "import sys; print(sys.version)" >nul 2>nul
if not errorlevel 1 (
 set "USE_PY_LAUNCHER=1"
 goto python_ok
)
echo Python 3.11 nao encontrado. Instale o Python 3.11 e reabra esta janela.
pause
exit /b 1
:python_ok
if exist .venv\Scripts\python.exe goto ambiente_pronto
if defined USE_PY_LAUNCHER (
 py -3.11 -m venv .venv
) else (
 "%PYTHON_BASE%" -m venv .venv
)
if errorlevel 1 goto erro
:ambiente_pronto
".venv\Scripts\python.exe" -m pip install --log instalacao.log -r requirements.txt
if errorlevel 1 goto erro
echo Atualizando o yt-dlp (usado para baixar musicas por link)...
".venv\Scripts\python.exe" -m pip install -U "yt-dlp[default]"
where deno >nul 2>nul
if not errorlevel 1 goto js_ok
where node >nul 2>nul
if not errorlevel 1 goto js_ok
where winget >nul 2>nul
if errorlevel 1 goto js_aviso
echo Instalando o Deno (necessario para o yt-dlp baixar do YouTube)...
winget install --id DenoLand.Deno --exact --accept-package-agreements --accept-source-agreements
echo Se o yt-dlp nao achar o Deno, feche e abra esta janela de novo.
goto js_ok
:js_aviso
echo AVISO: instale o Deno ou o Node.js para baixar musicas do YouTube por link. Enviar o arquivo de audio funciona sem isso.
:js_ok
echo Preparando o modelo gratuito de movimentos faciais...
".venv\Scripts\python.exe" -m liveclips.behavior
if errorlevel 1 (
 echo AVISO: o modelo facial nao foi baixado, talvez sem internet. O Hook's funciona sem ele: o modo sem IA e a analise de voz e movimento seguem normais.
 echo Para ativar a leitura facial depois, execute este instalador de novo com internet.
)
".venv\Scripts\python.exe" -m liveclips.diagnostics
if not errorlevel 1 goto pronto
echo.
echo FFmpeg ou ffprobe ainda nao foram localizados.
where winget >nul 2>nul
if errorlevel 1 goto ferramentas
echo Instalando o pacote gratuito FFmpeg pelo Windows Package Manager...
winget install --id Gyan.FFmpeg --exact --accept-package-agreements --accept-source-agreements
".venv\Scripts\python.exe" -m liveclips.diagnostics
if errorlevel 1 goto ferramentas
:pronto
echo Ambiente e ferramentas verificados.
call "%~dp0CRIAR_ATALHO.bat" silencioso
echo Abra o atalho Hook's na area de trabalho. Se ele nao aparecer, use ABRIR_LIVECLIPS.bat.
pause
exit /b 0
:ferramentas
echo Nao foi possivel instalar FFmpeg/ffprobe automaticamente.
echo Instale o pacote Gyan.FFmpeg pelo winget e execute este instalador novamente.
pause
exit /b 1
:erro
echo Nao foi possivel concluir a instalacao. Confira o erro acima.
echo O registro completo ficou em instalacao.log nesta pasta: envie esse arquivo se precisar de ajuda.
pause
exit /b 1
