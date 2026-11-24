@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Rode INSTALAR_TESTE.bat primeiro.
 pause
 exit /b 1
)
echo Vai exportar um clipe SINTETICO de 20 s em cada modo de qualidade (e em cada placa de video compativel).
echo Feche outros programas pesados. Leva alguns minutos (o modo Entrega e o mais lento).
".venv\Scripts\python.exe" -m liveclips medir
echo.
echo Resultado em relatorio_desempenho.json (tempo, CPU, memoria e GPU; sem dados pessoais).
pause
