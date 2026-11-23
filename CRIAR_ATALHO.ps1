# Cria os atalhos do Hook's (area de trabalho e menu Iniciar). Chamado por CRIAR_ATALHO.bat.
$dir = $PSScriptRoot.TrimEnd('\')
$pythonw = Join-Path $dir '.venv\Scripts\pythonw.exe'
if (-not (Test-Path $pythonw)) { Write-Host 'Python do Hook''s nao encontrado. Rode INSTALAR.bat primeiro.'; exit 1 }
$nome = 'Hook' + [char]0x2019 + 's.lnk'
$shell = New-Object -ComObject WScript.Shell
$pastas = @([Environment]::GetFolderPath('Desktop'), (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'))
foreach ($pasta in $pastas) {
    if (-not (Test-Path $pasta)) { continue }
    $atalho = $shell.CreateShortcut((Join-Path $pasta $nome))
    $atalho.TargetPath = $pythonw
    $atalho.Arguments = '-m liveclips.desktop'
    $atalho.WorkingDirectory = $dir
    $atalho.IconLocation = (Join-Path $dir 'assets\hooks.ico')
    $atalho.Description = 'Hook' + [char]0x2019 + 's - clipes de lives'
    $atalho.Save()
    Write-Host ('Atalho criado em: ' + $pasta)
}
