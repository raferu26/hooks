@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist MANIFESTO.sha256 (
 echo MANIFESTO.sha256 nao encontrado.
 pause
 exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$bad=0; Get-Content -Encoding UTF8 MANIFESTO.sha256 | ForEach-Object { if($_.Trim()){ $p=$_ -split '  ',2; $h=$p[0]; $f=$p[1]; if(Test-Path -LiteralPath $f){ if((Get-FileHash -LiteralPath $f -Algorithm SHA256).Hash.ToLower() -ne $h){ Write-Host 'DIFERENTE:' $f; $bad++ } } else { Write-Host 'FALTA:' $f; $bad++ } } }; if($bad -eq 0){ Write-Host 'Pacote integro: todos os arquivos conferem.' } else { Write-Host $bad 'arquivo(s) com problema.'; exit 1 }"
pause
