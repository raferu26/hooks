# Correções da 0.18.2-beta.1

## 1. Vídeo do YouTube não gravava
**Causa [Verificado nos seus logs]:** o link de um vídeo comum do YouTube ia para o gravador de lives (streamlink). Para vídeo, o streamlink só oferece um fluxo de 360p que termina na hora com 0 bytes; a captura encerrava com "parou sozinha… 0 pedaços".

**Correção:** `liveclips/videodl.py`. Links do YouTube que **não** são live são baixados com o yt-dlp (até 1080p, mp4), com barra de progresso e botão cancelar na bandeja. Ao terminar, o arquivo vira uma sessão de vídeo e a análise começa sozinha. Lives continuam indo para o gravador. Links de outros sites não passam pelo yt-dlp.

**Validado aqui:** 7 testes (`tests/test_videodl.py`) contra um servidor HTTP local: download, progresso, cancelamento sem sobra, mensagens em português, fluxo completo até a sessão, live ainda pelo gravador.
**Não validado:** YouTube real (o ambiente de teste não acessa o YouTube). No seu PC o yt-dlp precisa estar atualizado e ter Deno ou Node para o YouTube atual: rode `ATUALIZAR.bat`/`INSTALAR.bat`. Se o YouTube mudar algo, o aviso aparece em português e a atualização do yt-dlp costuma resolver.
As sessões antigas que falharam ("Retomar gravação") podem ser ignoradas.

## 2. Onde está o SaaS
O servidor `hooks_cloud` (login, painel de super admin, planos, cobrança, portal do cliente) existe desde a 0.16, mas é um programa **separado** e o Hook's só mostra login quando um `cloud_config.json` o liga. Isso nunca foi feito sozinho, por isso nada apareceu.

**Agora:** execute `SAAS_LOCAL.bat`. Ele cria o administrador (primeira vez), liga o Hook's ao servidor, inicia o servidor e abre `http://127.0.0.1:8800/admin`. Depois feche e abra o Hook's: aparece "Entrar no Hook's" (login / criar conta) e a aba **Assinatura**. `DESLIGAR_SAAS_LOCAL.bat` volta ao modo livre sem apagar nada.
Comando equivalente: `python -m hooks_cloud vincular --programa C:\LiveClips [--desligar]`.

**Corrigido:** a aba Assinatura ficava vazia quando ainda não havia streamer.

**Validado aqui (Linux, Chrome headless):** criar administrador, painel `/admin` com dados de demonstração, tela de login do app, criar conta pelo app contra o servidor local, aba Assinatura com plano de teste e uso. Testes: `tests/test_saas_visivel.py`.
**Não validado:** Windows real, Asaas sandbox, envio de e-mail (SMTP), HTTPS/hospedagem e textos legais (rascunho). Hospedar de verdade gera custo: aprove antes.
