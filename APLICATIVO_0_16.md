# Hook’s como aplicativo (atalho com ícone) — 0.16.0-beta.1

## O que mudou para você
- Depois do `INSTALAR.bat` aparece o atalho **Hook’s** (área de trabalho e menu Iniciar) com o ícone do Hook’s. Se precisar recriar: `CRIAR_ATALHO.bat`.
- Um clique abre uma **janela própria** do Hook’s, sem tela preta de console. O servidor roda escondido em segundo plano.
- A janela usa o **Microsoft Edge** (já vem no Windows 10/11) ou, se não houver, o **Google Chrome**, em modo aplicativo e com perfil separado (pasta `janela` dentro de `C:\LiveClips`; não mexe no seu navegador). Se nenhum dos dois for achado, abre no navegador padrão e avisa.
- Botão **Encerrar Hook’s** no canto da barra lateral: pede confirmação, avisa se há gravação/análise/exportação em andamento, finaliza as gravações e fecha tudo.

## O que acontece ao fechar a janela (X)
- **Nada em andamento** (sem live gravando, sem análise, sem exportação): o Hook’s encerra sozinho.
- **Algo em andamento:** o Hook’s **continua em segundo plano** e uma caixa de mensagem avisa o que está rodando. Clicar no atalho de novo traz a janela de volta. Para encerrar de vez, use **Encerrar Hook’s**.
- Se a janela fechar em menos de 8 s, o Hook’s **não encerra**: alguns navegadores repassam a janela a outro processo e saem, e eu prefiro deixar aberto a derrubar uma gravação por engano.
- Clicar no atalho duas vezes não abre dois Hook’s: o segundo clique só traz uma janela para o mesmo programa.

## Arquivos novos
`liveclips/desktop.py` (lançador), `CRIAR_ATALHO.bat` + `CRIAR_ATALHO.ps1` (atalhos), `tests/test_desktop.py`. O `ABRIR_LIVECLIPS.bat` continua existindo e mostra o console: use-o para investigar problemas. O programa grava `servidor.json` (porta e token temporários, apagado ao encerrar) e o log do servidor em `C:\LiveClips\logs\hooks_servidor.log`.

## O que foi testado e o que não foi
- Testado aqui (Linux): lógica do lançador com servidor de verdade e processos de mentira; início real do servidor pelo lançador e encerramento por ele; botão Encerrar em navegador automatizado.
- **Não testado:** Windows real, Edge/Chrome reais em modo aplicativo, criação do atalho pelo PowerShell, ícone no atalho e na barra de tarefas, caixa de mensagem. Pontos que dependem do comportamento do Windows/Edge e que eu não consegui confirmar:
  - se a janela do Edge em modo aplicativo mostra o ícone do Hook’s na barra de tarefas (esperado: usa o ícone da página; pode aparecer o do Edge);
  - se o Edge sai mesmo quando a última janela fecha (se ficar vivo, o Hook’s não encerra sozinho: use **Encerrar**);
  - se o servidor sem console abre janelas pretas ao chamar ffmpeg/streamlink (usei `python.exe` com console escondido justamente para evitar).
  Se algum acontecer, mande o `C:\LiveClips\logs\hooks_servidor.log` e uma descrição.

## O que ainda não é "um programa instalável de verdade"
Isto é um atalho sobre a instalação atual (Python + `.venv` na pasta). Continua exigindo Python 3.11 e rodar o `INSTALAR.bat` uma vez. Um **instalador .exe** (Next, Next, Concluir; sem Python separado, desinstalador, atualização automática, assinatura digital) é um projeto à parte: precisa ser montado e testado em Windows, o pacote fica na casa de gigabytes por causa de Whisper, MediaPipe e OpenCV, e o certificado de assinatura de código tem custo. Não está nesta versão.
