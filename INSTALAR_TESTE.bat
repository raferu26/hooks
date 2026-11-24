@echo off
setlocal enableextensions
chcp 65001 >nul
cd /d "%~dp0"
set "LOG=%~dp0instalacao_teste.log"
echo HOOK'S - instalacao de TESTE (variante experimental sem IA)
echo HOOK'S - instalacao de TESTE > "%LOG%"
echo %date% %time% >> "%LOG%"
echo.
echo Este instalador usa os arquivos da pasta "wheels" (sem baixar pacotes Python). So o winget pode baixar Python 3.11 e FFmpeg, se faltarem.
echo O registro fica em instalacao_teste.log nesta pasta.
echo.
if not exist "%~dp0wheels\" (
 echo ERRO: a pasta "wheels" nao esta aqui. Extraia o ZIP inteiro e rode de novo.
 goto erro
)
set "PYEXE="
set "USE_PY_LAUNCHER="
py -3.11 -c "import sys" >nul 2>nul
if not errorlevel 1 set "USE_PY_LAUNCHER=1"
if not defined USE_PY_LAUNCHER if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not defined USE_PY_LAUNCHER if not defined PYEXE if exist "%ProgramFiles%\Python311\python.exe" set "PYEXE=%ProgramFiles%\Python311\python.exe"
if defined USE_PY_LAUNCHER goto python_ok
if defined PYEXE goto python_ok
echo Python 3.11 nao encontrado. Tentando instalar pelo winget...
echo Python 3.11 nao encontrado; winget >> "%LOG%"
where winget >nul 2>nul
if errorlevel 1 (
 echo O winget nao existe neste Windows. Instale o Python 3.11 de 64 bits em python.org, marque "Add to PATH" e rode de novo.
 goto erro
)
winget install --id Python.Python.3.11 --exact --scope user --accept-package-agreements --accept-source-agreements >> "%LOG%" 2>&1
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not defined PYEXE (
 echo O Python 3.11 foi instalado, mas esta janela ainda nao o enxerga. Feche esta janela e rode INSTALAR_TESTE.bat de novo.
 goto erro
)
:python_ok
if exist .venv\Scripts\python.exe goto venv_ok
echo Criando o ambiente (.venv)...
if defined USE_PY_LAUNCHER (
 py -3.11 -m venv .venv >> "%LOG%" 2>&1
) else (
 "%PYEXE%" -m venv .venv >> "%LOG%" 2>&1
)
if errorlevel 1 goto erro
:venv_ok
echo Instalando as bibliotecas (offline, da pasta wheels)...
".venv\Scripts\python.exe" -m pip install --no-index --find-links "%~dp0wheels" -r "%~dp0requirements-sem-ia.txt" >> "%LOG%" 2>&1
if errorlevel 1 goto erro
".venv\Scripts\python.exe" -m pip check >> "%LOG%" 2>&1
if errorlevel 1 (
 echo AVISO: o pip reportou conflitos de bibliotecas; veja instalacao_teste.log.
)
".venv\Scripts\python.exe" -m liveclips.diagnostics >> "%LOG%" 2>&1
if not errorlevel 1 goto ferramentas_ok
echo FFmpeg nao encontrado. Tentando instalar pelo winget (Gyan.FFmpeg)...
where winget >nul 2>nul
if errorlevel 1 goto sem_ffmpeg
winget install --id Gyan.FFmpeg --exact --accept-package-agreements --accept-source-agreements >> "%LOG%" 2>&1
".venv\Scripts\python.exe" -m liveclips.diagnostics >> "%LOG%" 2>&1
if errorlevel 1 goto sem_ffmpeg
:ferramentas_ok
echo Ferramentas verificadas.
call "%~dp0CRIAR_ATALHO.bat" silencioso
echo Rodando o autoteste (leva alguns segundos)...
".venv\Scripts\python.exe" -m liveclips selfcheck
echo.
echo PRONTO. Abra o atalho Hook's na area de trabalho (ou ABRIR_LIVECLIPS.bat) e siga o arquivo LEIA-ME_TESTE_WINDOWS.txt.
pause
exit /b 0
:sem_ffmpeg
echo Nao foi possivel instalar o FFmpeg automaticamente. Instale o pacote Gyan.FFmpeg (winget) ou ffmpeg.org e rode de novo.
goto erro
:erro
echo.
echo A instalacao nao terminou. Envie o arquivo instalacao_teste.log (use COLETAR_RELATORIO.bat).
pause
exit /b 1
