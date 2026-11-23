# Hook’s 0.19.0-beta.1 — Estúdio simplificado, prévia que não some e qualidade real de exportação (sobre a 0.18.2)

> **0.19 (leia `NOVIDADES_0_19.md`):** o Estúdio troca as 8 abas por um inspetor contextual, a linha do tempo começa com 3 pistas, cada alteração é salva sozinha sem apagar a prévia anterior, “Agente” virou “Sugestões”, Ctrl+Enter pede confirmação e os 4 modos de qualidade (Rápido, Equilibrado, Qualidade, Entrega) agora mudam de verdade o arquivo final — escolha por corte ao lado de Exportar. Tabela do que depende de IA e alternativas sem IA no mesmo arquivo. Roteiro de teste com pessoas: `ROTEIRO_TESTE_USUARIOS_0_19.md`. **Nada foi testado no Windows nem com placa de vídeo.**

> **0.18.2 (leia `CORRECOES_0_18_2.md`):** (1) vídeos do YouTube agora são **baixados com o yt-dlp** (antes iam para o gravador de lives, que grava 0 bytes de um vídeo comum e parava sozinho); o progresso aparece na bandeja e dá para cancelar. (2) O **SaaS** (login, aba Assinatura, painel de super admin) já existia desde a 0.16, mas ficava desligado: agora `SAAS_LOCAL.bat` liga servidor + login com um clique e `DESLIGAR_SAAS_LOCAL.bat` volta ao modo livre. Corrige a aba Assinatura vazia quando ainda não há streamer.

> **0.18.1:** rodada de validação complementar (qualidade dos cortes em mídia sintética, atualização a partir de dados da 0.17.1, proteção de dados e recuperação). Correções e o que ficou sem validação: `VALIDACAO_COMPLEMENTAR.md`.

> **Novo na 0.18 (leia `NOVIDADES_0_18.md` e `PROGRESSO_P00_P27.md`):** modo de análise **sem IA** (nada de Whisper, MediaPipe ou RNNoise; cortes por marcadores seus, picos técnicos marcados como heurística e legendas importadas), pausas pelo silêncio medido, replay do momento marcado, voz/cor/LUT, capas, formatos 1:1/4:5/16:9 conferidos, rastreio clássico de região, áudio externo sincronizado, receitas de imagem, gráficos 2D por modelo, controle de qualidade com recuo para versão simples e pacote OTIO/projeto portátil. Tudo validado só com mídia sintética: **nada foi testado no Windows nem em live real**.

> **Novo na 0.17.1 (leia `REFINAMENTO_0_17_1.md` e `PENDENCIAS_0_17_1.md`):** modo demonstração e tela de boas-vindas, revisão por teclado e em lote, pasta de entrega (para o Google Drive pelo aplicativo do computador), backup verificado, pré-voo com estimativas, taxa de aprovação por semana e acessibilidade. Nada foi validado no Windows nem com live real.

> **Novo na 0.17 (leia `REFINAMENTO_0_17.md`):** painel bem mais rápido, motivo de rejeição em um clique e taxa de aceitação, legenda precisa por padrão com correções por streamer, controle de qualidade sobre o vídeo exportado (selo “revisar”, 3 imagens de amostra) e áreas a borrar para privacidade. Nada foi validado no Windows nem com live real.

> **Novo na 0.16 (leia `SAAS_0_16.md` e `DEPLOY_SERVIDOR.md`):** servidor `hooks_cloud` (contas, planos com limites, licença assinada, medição de uso, cobrança por Pix manual ou Asaas, painel do dono, portal do cliente, LGPD) e aba **Assinatura** no app. Sem `cloud_config.json` ativado o app funciona como na 0.15, sem login e sem limites. **Tudo foi testado só localmente e de forma simulada; textos legais são rascunho; o Asaas não foi testado em sandbox.**

> **0.16.0-beta.2 — auditoria (leia `PENDENCIAS_0_16.md`):** lista completa do que falta e do que foi testado. Corrige erro 500 do painel admin com campos inválidos, adiciona backup diário automático do servidor e o ícone do site.

> **Atalho/aplicativo (leia `APLICATIVO_0_16.md`):** depois do `INSTALAR.bat` aparece o atalho **Hook’s** com ícone; ele abre numa janela própria, sem console, e tem o botão **Encerrar Hook’s**. Não foi testado em Windows real.

> **Pistas da 0.15 (`PISTAS_0_15.md`):** várias lives ao mesmo tempo, cada uma com sua pista de trabalho.

> **Novo na 0.14 (leia `INTELIGENCIA_0_14.md`):** cada corte ganha uma leitura de contexto (promessas sem desfecho, fontes independentes, conflitos, qualidade do rosto), reações sem fala viram candidatos exploratórios, a aba **Por quê** do estúdio explica o que foi entendido e o que ficou sem conclusão, e você pode marcar **momentos perdidos**. Tudo é heurístico e foi testado só com dados sintéticos: confira os cortes antes de usar.


> **Novo nome: Hook’s.** O programa passou de LiveClips para Hook’s (nome na tela, logo e mensagens). Por dentro, a pasta de dados `C:\LiveClips`, o pacote Python `liveclips` e os nomes dos `.bat` continuam iguais de propósito, para não quebrar seus dados nem a atualização. Logos em `assets/`.

> **0.13 — leia `ESTUDIO_0_13.md` primeiro.** A 0.13 acrescenta o plano de edição versionado (`plano.json`), replay e rampa de velocidade, a memória editorial do streamer, a revisão ciente do plano (`revisao.json`), o pacote de entrega com hashes e linha do tempo OTIO, a edição por pedido em português e a aba "Por quê" no Estúdio. O arquivo diz, item por item, o que foi implementado, integrado e validado — e que **nada foi validado com conteúdo real**. A 0.12 continua descrita abaixo.


A 0.12 melhora os agentes que escolhem e preparam os cortes, adiciona identidade visual por streamer, controle de qualidade na exportação, suporte (log e diagnóstico) e uma interface redesenhada. **Leia ESTUDIO_0_12.md**: ele diz o que foi testado aqui e o que só dá para validar com o seu conteúdo real. A base de edição manual da 0.11 está em ESTUDIO_0_11.md.

Novidades da 0.12: medição dos agentes com gabarito próprio (benchmark), prévia com legenda e título ao vivo, kit de marca por streamer (logo, abertura/encerramento, fonte, cor e posição do título), reenquadramento seguindo quem fala, áudio com redução de ruído neural opcional, importação de CSV de desempenho, teste A/B de gancho e série Parte 1/2, barra de progresso com tempo restante, log rotativo e pacote de diagnóstico, controle de qualidade automático na exportação.

---

# Base da 0.11 — Estúdio de edição

- **Estúdio**: tela única com fala, prévia, ferramentas e linha do tempo. Tudo é editável por corte (estilo, legendas, títulos, música, cortes, zoom, velocidade, congelar imagem, efeitos sonoros, imagens/memes, layout) com desfazer/refazer.
- **Layouts**: lives (câmera em cima, tela dividida, jogo com câmera no canto, só câmera) e vídeos (ajustar ou preencher a tela).
- **Música por link**: cole o link do YouTube/SoundCloud; baixa só o áudio, mostra batidas e reduz o volume sob a voz. Também aceita arquivo. Exige confirmar que você pode usar a música.
- **Gancho e abertura**: título na tela, reordenação de abertura (teaser) e nota de gancho nos primeiros segundos.
- **Outros formatos**: 1:1, 4:5 e 16:9 junto com o vertical.
- **Pacote de publicação** (legenda, hashtags, créditos) e **registro de desempenho**: com 4 ou mais clipes com 100+ visualizações, o ranking passa a preferir o que rendeu mais.
- **Desempenho**: transcrição small/medium/turbo com placa NVIDIA automática; exportação por placa de vídeo (NVENC/QuickSync/AMF) opcional, com volta automática ao processador.
- **Avaliador local opcional (Ollama)**: desligado por padrão; nada sai do computador.
- Não publica nem agenda no TikTok: o sistema entrega o clipe e o texto prontos.

Após atualizar, rode INSTALAR.bat de novo (instala o yt-dlp e o Deno, necessários para músicas do YouTube).

# LiveClips V8 — 0.10.0-beta.1

## Editor profissional da V8

Esta versão melhora somente a edição. Detalhes, medições e limites em **EDITOR_PRO_V8.md**.

- Cada estilo tem look próprio: curva de zoom, cor leve e legenda automática. O zoom de cada punch tem alvo e curva próprios.
- Legendas sem piscar, com estilos novos (caixa alta animada, entrada animada, faixa escura) e ênfase na palavra do pico.
- O corte é codificado uma única vez, direto dos originais; se falhar, o método da V7 assume sozinho.
- Loudness medido antes quando o pico permite ganho linear.
- Inspirado no editor open source ReaCut (MIT); veja THIRD_PARTY_NOTICES.md.


## História completa da V7.1

- O agente marca preparação, clímax e frase final a partir da fala temporizada e de sinais observáveis de áudio, vídeo e chat.
- Distingue a categoria do momento antes de escolher a pista principal.
- Avisa quando a reação ou o desfecho continua além do corte sugerido.
- Oferece versões alternativas próximas de 30, 45 e 60 segundos quando o contexto disponível comporta frases inteiras. O botão ajusta os limites para revisão e prévia.
- Evita criar versão longa quando há pouco contexto. Os limites são heurísticos e exigem conferência humana.

## Editor profissional da V7

- Treze estilos nomeados e explicados: Limpo, Gameplay, Reação, Podcast, Entrevista, Hype, Criativo, Storytelling, Educacional, Comentário, Meme, Cinemático e o preset de humor legado.
- Cada estilo possui uma demonstração vertical curta e leve no perfil, com descrição de ritmo, intensidade e conteúdo indicado. Não é preciso escolher “edição 1” sem saber o resultado esperado.
- O plano de cada corte lista zoom, pausa, repetição, imagem, efeito e música como decisões individuais. O revisor pode desligar cada uma antes de exportar.
- Pausas só são encurtadas entre palavras temporizadas, preservando margens de respiração. Repetições automáticas começam desligadas e exigem revisão humana.
- Recursos externos só entram quando o usuário fornece o arquivo. Música exige confirmação explícita de autorização e recebe redução automática sob a voz.
- A saída usa normalização de voz, legenda selecionável, reenquadramento seguro e comparação entre o original e o editado depois da exportação.
- O manifesto registra preset, decisões, substituições e cortes aplicados sem expor caminhos dos arquivos de recursos.

O editor reforça a história existente; ele não deve fabricar reação, inverter sentido nem esconder contexto. Captura, análise, backups e originais da V6.9 permanecem preservados.

## Interface profissional da V6.9

- Identidade visual azul-escuro com azul luminoso para a ação principal, ciano para confirmação, violeta para diferenciação e laranja reservado a alertas.
- Fluxo visível em quatro etapas: adicionar conteúdo, analisar, revisar cortes e exportar.
- As ações frequentes ficam na tela; backup, reclassificação e gerenciamento de sessão ficam agrupados em menus secundários.
- Capturas simultâneas podem ser recolhidas para liberar espaço sem interromper nenhuma live.
- Conteúdo, cortes encontrados e editor formam uma hierarquia clara, com melhor contraste, estados selecionados e textos em linguagem comum.
- Layout adaptado para monitores menores e dispositivos estreitos sem remover funções.

Toda a inteligência, captura, YouTube, Twitch, vídeo/podcast, recuperação e exportação da V6.8 foi preservada.

## Inteligência profissional da V6.8

- O agente combina fala, áudio, mudança visual, chat e sinais faciais observáveis. Nenhuma pista isolada declara um grande momento.
- A classificação cobre humor, surpresa, jogada/vitória, tensão, opinião, história, explicação, momento emocional e reação, em vez de limitar o perfil a reações e jogadas.
- Cada sugestão recebe notas separadas de gancho, preparação, clímax, encerramento e completude narrativa.
- A análise facial local usa pontos do rosto quando o MediaPipe está disponível. Ela mede sorriso geométrico, abertura da boca, sobrancelhas, olhos, pressão dos lábios, assimetria, olhar e movimento de cabeça em relação ao padrão daquela pessoa. A dependência está fixada na série anterior à telemetria observada nas distribuições mais recentes.
- Esses sinais não diagnosticam emoção, intenção ou personalidade. Servem apenas como evidência auxiliar confirmada por fala, som, imagem ou chat.
- Cada perfil pode escolher sensibilidade comportamental e manter vocabulário de nomes, jogos, marcas e expressões para orientar a transcrição local.
- Quando nenhum momento passa o padrão profissional, o agente pode mostrar no máximo cinco oportunidades exploratórias, claramente marcadas como baixa confiança e obrigatoriamente sujeitas à revisão humana.
- No estilo criativo, uma reação confirmada por sinais multimodais pode receber aproximação sutil. O plano fica na assinatura da renderização para impedir o reaproveitamento incorreto de um clipe antigo.

## Compatibilidade preservada

A V6.8 foi construída sobre a V6.7. Captura e importação por link, YouTube, Twitch, modo live, modo vídeo/podcast, cortes manuais, análise progressiva, enquadramento dinâmico, auditoria editorial, backups e recuperação permanecem na base. A versão experimental de outro computador foi tratada somente como fonte de ideias: foram reaproveitados o fallback exploratório, tentativas extras de Streamlink e o plano de aproximação criativa; ela não substituiu arquivos ou recursos mais novos.

## Confiabilidade da V6.7

- A montagem entre segmentos usa recorte preciso depois da abertura do arquivo. Isso evita perder os primeiros quadros quando o ponto escolhido não coincide com um keyframe H.264.
- Alterar prioridade, estilo ou duração editorial reclassifica as sugestões automáticas; transcrições prontas não são refeitas sem necessidade. Revisados, aprovados e exportados são preservados.
- O botão **Reclassificar** permite aplicar novamente o perfil e o aprendizado atual aos cortes automáticos pendentes.
- Sessões com erro mostram **Tentar novamente**. Uma origem movida pode ser religada por **Localizar original** somente depois da conferência SHA-256 dos bytes já registrados.
- Sessões concluídas podem ser arquivadas e reativadas sem apagar originais, análises ou cortes.
- A abertura cria um backup automático rotativo do banco e dos perfis. O botão **Backup** cria uma cópia manual; `RESTAURAR_BACKUP.bat` valida o ZIP, preserva o estado atual e restaura com o aplicativo fechado.
- O instalador verifica Python, dependências, Streamlink, FFmpeg e ffprobe. Quando necessário e disponível, usa o Windows Package Manager para instalar gratuitamente o pacote Gyan.FFmpeg.
- A proteção HTTP consome pedidos locais rejeitados antes de encerrar a conexão, evitando resets intermitentes no Windows.

## Inteligência de corte da V6.2

- Combina transcrição, crescimento do áudio, movimento geral, movimentos faciais breves e reação coletiva do chat.
- Chat, volume e rosto são pistas auxiliares: nenhum deles declara um bom corte sozinho.
- Prioriza uma mini-história compreensível fora da live: preparação curta, acontecimento, reação e desfecho.
- Depois de quatro aprovações/rejeições manuais por streamer, ajusta pesos de forma conservadora ao estilo real do revisor.
- O botão **Testar link e qualidades** informa plataforma, canal, resoluções disponíveis e a resolução escolhida antes de gravar.
- O perfil editorial diferencia Shorts de cortes narrativos e oferece presets de edição limpa, engraçada e criativa.
- A revisão mostra história, fidelidade, legendas, falantes, créditos, política e valor editorial antes de exportar.
- Perfis marcados como bloqueados não exportam. Alertas editoriais exigem confirmação humana.
- Cada entrega aprovada inclui `creditos.txt` e os dados editoriais no manifesto.

## Dois modos de trabalho

- **Modo Live:** mantém a captura por link, webcam nos 640 px superiores e jogo nos 1280 px inferiores.
- **Modo Vídeo/Podcast:** vincula diretamente MP4, MKV, MOV, WEBM, TS ou M4V sem copiar o original, não exige webcam e preserva o quadro completo sobre um fundo vertical desfocado.
- O modo vídeo aumenta o peso de opiniões, explicações e histórias, além das reações e do humor já analisados.
- Cada gravação guarda seu próprio modo; importar um vídeo não altera o comportamento das lives existentes.
- O modo vídeo também aceita um link público: Streamlink recebe o fluxo, o FFmpeg cria segmentos de trabalho e a análise começa sem o usuário baixar o arquivo inteiro manualmente.
- Mesmo por link, os bytes precisam passar pelo computador e os segmentos ficam no disco até o usuário decidir removê-los; não existe análise de vídeo sem transferir os dados.

## Enquadramento de vídeos

- **Conservador:** mantém sempre o quadro integral sobre o fundo vertical desfocado.
- **Dinâmico:** analisa mudanças de cena e rostos localmente. Aproxima e acompanha suavemente quando existe um rosto claro; preserva o quadro integral quando há um grupo aberto, tela, apresentação, cena sem rosto ou baixa confiança.
- O modo é escolhido para cada vídeo antes da análise e fica congelado junto ao corte aprovado.
- O plano utilizado na exportação fica salvo em `plano_enquadramento.json` e no manifesto para auditoria.

## Sugestões progressivas em vídeos por link

- O LiveClips alterna cadastro, transcrição e análise dos segmentos recebidos.
- Os primeiros cortes podem aparecer enquanto o restante do vídeo continua sendo recebido e analisado.
- Pausar uma sessão ou a análise geral preserva segmentos, transcrições, sugestões, prévias e exportações já concluídas.
- O botão **Corte manual** permite escolher um intervalo já analisado, de 1 a 90 segundos, mesmo quando o agente ainda não gerou sugestões automáticas.
- O limite liberado aparece na tela; intervalos não analisados continuam bloqueados para não produzir legendas incompletas.

### Limites honestos da análise facial

A V6.2 não afirma reconhecer emoções nem microexpressões clínicas. Ela mede mudanças breves nas regiões de olhos/sobrancelhas e boca, assimetria e movimento geral. Uma webcam pequena dentro de uma live a 30/60 fps não contém o mesmo detalhe das bases científicas gravadas a 100–200 fps. Por isso, o sinal facial só ganha importância quando outra pista confirma o momento.

### Chat da Twitch, gratuito

A captura oficial do chat usa Twitch IRC e grava somente as mensagens recebidas durante a captura em `chat.jsonl`. Configure as variáveis `LIVECLIPS_TWITCH_USER` e `LIVECLIPS_TWITCH_TOKEN` com um token OAuth gratuito que tenha `chat:read`. Sem token, o vídeo continua normalmente e o painel mostra **Chat: não conectado**. A V6.2 não raspa o site nem pede API paga.

### Regras profissionais incorporadas

O agente procura abertura forte, sentido independente da live, contexto mínimo, clímax confirmado por mais de uma modalidade, frase completa e encerramento logo após o payoff. Ele penaliza silêncio excessivo, repetições e conversa neutra. A mesa de revisão continua obrigatória: não existe garantia matemática de viralização.

Painel local para organizar streamers, capturar até cinco lives ao mesmo tempo, sugerir momentos com contexto entre arquivos e revisar a exportação para TikTok. Esta é uma versão de teste separada da V5/etapa 7.

## Começar no computador que já roda a V5

1. Extraia este pacote inteiro em uma pasta nova, por exemplo **AGENTE CLIPADOR V6**. Não cole os arquivos dentro da pasta V5.
2. Abra **ABRIR_LIVECLIPS.bat**, na raiz da nova pasta. O navegador abrirá o painel local. Mantenha a janela do programa aberta.
3. Clique em **Adicionar streamer** e escreva, por exemplo, **CORINGA**. A pasta e o perfil serão criados em `C:\LiveClips\CORINGA`.
4. Para testar sem outra live: clique em **Vincular gravação**, escolha uma sessão das versões anteriores e confirme se a captura já terminou. Os vídeos antigos ficam no lugar original; o programa cria um vínculo, sem copiá-los.
5. Abra **Perfil do streamer**, confira o enquadramento e salve. Um perfil antigo da sessão é reaproveitado quando disponível. Para marcar a webcam, clique em **Preparar imagem da sessão** e arraste sobre ela.
6. Clique em **Iniciar análise**. As sugestões aparecem na mesa de revisão. Escolha uma, gere a prévia, ajuste início/fim em segundos e clique em **Aprovar e exportar** ou **Rejeitar**.

A prévia mostra a gravação original para conferir os limites. O arquivo aprovado é exportado em 1080×1920, com a webcam nos 640 pixels superiores, o jogo nos 1280 pixels inferiores e legendas por palavra. O painel passa a mostrar o vídeo final quando a exportação termina.

## Qualidade da fonte e da webcam na V6.1

- Novos perfis preferem 1440p e recuam para 1080p/720p quando a plataforma não oferece 1440p. Perfis já existentes mantêm a escolha anterior para não mudar capturas sem aviso; altere a qualidade no perfil quando desejar.
- A captura grava o fluxo recebido sem recodificar. Se a live disponibilizar somente 1080p, o LiveClips não inventa uma fonte 1440p.
- A montagem entre segmentos preserva até 2560×1440, mantém 60 fps quando a fonte real tem 50/60 fps e a exportação vertical usa escala Lanczos, H.264 High, CRF 18 e preset medium.
- O painel mostra a resolução real da fonte e o tamanho em pixels do recorte da webcam. Quando esse recorte precisa ser ampliado, o aviso deixa claro que detalhes ausentes na transmissão não podem ser recuperados.
- Uma webcam pequena dentro de uma live 1440p ainda pode ter poucos pixels. Iluminação, foco, resolução configurada no OBS e tamanho da webcam na cena continuam limitando a qualidade final.

O iniciador usa somente o ambiente `.venv` da própria pasta, evitando abrir acidentalmente uma versão antiga. Se ele não existir, execute **INSTALAR.bat**. O instalador precisa de Python 3.11 e acesso à internet; instala as dependências Python, verifica Streamlink/FFmpeg/ffprobe e tenta instalar gratuitamente o pacote Gyan.FFmpeg pelo `winget` quando necessário. O painel oferece **Verificar novamente** quando uma ferramenta ainda não é encontrada.

## Várias lives ao mesmo tempo

1. Cadastre os perfis desejados. Você pode guardar mais perfis que o limite de capturas.
2. No primeiro streamer, clique em **Nova captura**, cole o link e confirme. A opção **Iniciar análise junto com a captura** vem marcada.
3. Selecione outro streamer na lateral e repita. A captura anterior continua.
4. A área **Lives em captura** mostra os perfis ativos. **Abrir perfil e cortes** leva à gravação daquele streamer; **Encerrar esta live** finaliza somente aquela captura. **Encerrar todas** finaliza todas.

São permitidas até **cinco capturas simultâneas, com uma live por perfil**. O limite pode ser reduzido no painel. Reduzir o limite abaixo das capturas ativas é recusado, sem interrompê-las. Uma falha ao abrir ou encerrar uma live não encerra as outras.

As capturas gravam em paralelo. A transcrição, as prévias e as exportações usam **uma tarefa pesada por vez**, alternando entre sessões/perfis. Isso controla memória e CPU; não garante que cinco lives sejam analisadas em tempo real em qualquer computador. Se os segmentos se acumularem, reduza o número de lives ou use o modelo Tiny. O padrão é Base e captura preferencial de 480p; 720p oferece uma fonte melhor para o enquadramento vertical e usa mais rede/espaço.

Quando a qualidade preferida não existe, a captura tenta alternativas disponíveis. Essa seleção usa o [mecanismo de alternativas do Streamlink](https://streamlink.github.io/cli.html#positional-arguments); a resolução obtida pode ser diferente da preferência.

As sugestões continuam passando pela revisão. Iniciar várias capturas não aprova nem publica clipes automaticamente. O programa não procura sozinho quais streamers estão online.

## Organização dos arquivos

```text
C:\LiveClips\
  liveclips_v8.sqlite3         histórico, revisões e fila de todos os perfis
  liveclips_v8.lock            impede abrir duas instâncias para a mesma pasta
  backups\                     banco e perfis, sem copiar os vídeos pesados
    LiveClips-automatico-....zip
    LiveClips-manual-....zip
  CORINGA\
    perfil_v8.json            webcam, idioma, modelo, legendas e desempenho
    sessoes\
      DATA_DA_CAPTURA\
        segmentos\            vídeos originais das novas capturas
        analise\              transcrição e sinais calculados
        previas\              vídeos para revisão
        cortes\
          ID_DO_CORTE_ASSINATURA\
            clipe.mp4         vídeo final aprovado
            legendas.srt
            legendas.ass
            manifesto.json    origem, limites e conferência do arquivo
        captura.log           diagnóstico daquela captura
        vinculo_origem.json   aparece nas sessões vinculadas
  OUTRO_STREAMER\
    ...
```

Você também pode cadastrar uma pasta de streamer vazia criada manualmente dentro de `C:\LiveClips`. Uma pasta já preenchida e sem cadastro V8 é recusada para preservar seu conteúdo. Nomes inválidos do Windows são recusados.

**Abrir pasta** mostra a sessão selecionada. Os clipes aprovados ficam na subpasta **cortes**, cada um em sua própria pasta. Vídeos antigos vinculados continuam dependendo dos originais em `C:\LiveClips\segmentos\...`; não mova nem apague esses originais enquanto estiver trabalhando com a sessão.

## Contexto entre segmentos

- Usa as durações medidas nos arquivos, sem presumir que todos têm exatamente 60 segundos.
- Combina transcrição, palavras, áudio e movimento da webcam do segmento anterior, atual e seguinte.
- Nas sessões abertas, aguarda o próximo segmento completo e analisado antes de concluir a seleção do último contexto. A espera faz parte da preservação do desfecho.
- Um arquivo parado durante um travamento da live não é considerado completo só porque deixou de crescer. O último arquivo de uma captura aberta aguarda o próximo ou o encerramento.
- Ao encerrar a captura, libera a análise do trecho final disponível.
- Inclui preparação/desfecho e tenta ajustar limites de frases. Sugestões automáticas têm até 60 segundos; na revisão você pode ajustar entre 1 e 90 segundos.
- Cortes podem atravessar arquivos consecutivos do mesmo formato. Lacunas na numeração ou mudanças de formato quebram o grupo de continuidade e impedem a junção automática sobre essa quebra.

Essa seleção combina fala, humor, pistas de jogada, preparação/desfecho, crescimento da energia do áudio e movimento da webcam. Ela ainda não compreende semanticamente cada jogo nem garante que toda jogada → reação → comentário será preservada. Os motivos da sugestão e os avisos de limites ajudam a revisar isso. A prévia continua sendo parte necessária do controle de qualidade.

## Evitar cortes repetidos

- Guarda as decisões no banco local, inclusive depois de reabrir o programa.
- Compara a sobreposição temporal na mesma sessão e os intervalos dos mesmos arquivos por SHA-256, inclusive quando uma cópia idêntica aparece em outra sessão do mesmo streamer.
- Sobreposição de pelo menos 55% do menor intervalo é tratada como repetição. Sugestões próximas podem ser consolidadas na de maior pontuação enquanto ninguém as revisou.
- Uma sugestão já editada, aprovada, exportada ou rejeitada fica protegida contra substituição automática.
- Confere novamente os aprovados antes de exportar. Aprovações concorrentes do mesmo momento não reservam duas exportações.
- A V6.1 acrescenta uma impressão visual perceptual do quadro central. Ela só bloqueia uma possível recodificação quando imagem, transcrição e duração são parecidas; uma frase repetida sozinha não descarta um momento.

Isso não é uma identificação universal de vídeos visualmente iguais: arquivos recodificados, cortes de outra origem e intervalos com pouca sobreposição podem escapar. Dois momentos diferentes com a mesma frase não são descartados apenas pela frase.

## Pausar, encerrar e retomar

- **Pausar análise** aguarda a operação atual terminar. As capturas continuam; prévias solicitadas e exportações já aprovadas continuam na fila.
- **Pausar esta sessão** retira aquela gravação da análise automática. Não encerra a captura.
- **Arquivar** retira uma sessão concluída da fila sem apagar nenhum arquivo; **Reativar** a devolve à fila.
- **Localizar original** religa uma fonte movida somente quando os arquivos conhecidos continuam idênticos aos SHA-256 registrados.
- **Encerrar esta live** encerra o produtor e permite ao FFmpeg finalizar o último segmento. Os arquivos completos continuam disponíveis para análise.
- **Encerrar todas** encerra todas as capturas e mantém o restante da fila.
- Para fechar o aplicativo, use **Ctrl+C na janela do programa**. Fechar apenas a aba do navegador deixa o programa e as capturas em execução.
- Depois de reiniciar, perfis, sugestões, rejeições e aprovações permanecem salvos. A análise reabre pausada; as capturas precisam ser iniciadas novamente. Exportações aprovadas ou interrompidas são retomadas pela fila.

Uma exportação finalizada guarda uma assinatura e a conferência do vídeo. Se o processo parar antes de registrar a conclusão no banco, a retomada reutiliza o arquivo válido. Os originais são conferidos antes de gerar um corte; se mudaram, o programa bloqueia aquela exportação. Uma tarefa com erro fica visível para conferir e tentar novamente.

Mudar idioma, modelo ou enquadramento refaz a análise dos segmentos e retira sugestões automáticas desatualizadas. Mudar prioridade, estilo ou formato reclassifica sem transcrever novamente. O painel explica quando sugestões anteriores foram preservadas como substituídas e pede para retomar a análise se ela estiver pausada. Revisões manuais e cortes aprovados são preservados. O perfil e as legendas de uma aprovação ficam congelados para a exportação daquela revisão.

Os backups automáticos/manuais protegem banco, perfis e decisões, mas não duplicam gravações e exportações pesadas. Para proteção completa da mídia, copie também as pastas dos streamers para outro disco. A restauração deve ser feita com o LiveClips fechado por **RESTAURAR_BACKUP.bat**.

A reserva de espaço é configurada por perfil. Capturas monitoram o disco e encerram quando atingem a reserva. Tarefas pesadas também conferem espaço antes de começar. Nenhum vídeo é apagado automaticamente. Uma reserva mais alta em um perfil não bloqueia tarefas de outro perfil que ainda tenha espaço suficiente.

## Validado nesta entrega

Foram executados **150 testes automáticos** (31 deles da V8: curvas de zoom, legendas, render em uma passada, sincronismo e loudness com FFmpeg real). Os testes anteriores cobrem durações variáveis, seek preciso, cortes em dois arquivos, espera pelo segmento seguinte, persistência e bloqueio de repetição, aprovações simultâneas, reclassificação por prioridade, backups/restauração, religação segura de originais, mudanças de perfil durante a análise, recuperação de exportação, proteção contra arquivo original alterado, cinco capturas simuladas, falha isolada, encerramento individual, limite de lives, distribuição da fila, espaço baixo e acesso ao painel/mídia.

O painel foi exercitado no Chrome com dados e vídeo sintéticos: cadastro, perfil, duas capturas simuladas, encerramento de uma mantendo a outra, prévia na fila, aprovação, rejeição e preservação de ajustes durante a atualização da tela.

O defeito real que perdia aproximadamente 4,4 segundos foi repetido com os segmentos 12 e 13 de uma gravação existente. A V6.7 montou 50,21 segundos começando no quadro 0,000s e concluiu a exportação vertical em 1080×1920 com 50,17 segundos. A proteção HTTP rejeitou 30/30 tentativas de origem falsa sem abortar a conexão.

**Pendente para validar a beta:** captura real simultânea prolongada e operação diária com o pacote instalado. Os testes não medem o desempenho de cinco lives reais nem comprovam que todo momento sugerido será editorialmente bom. Use o roteiro em **TESTE_GUIADO.md**, começando com duas lives.

## Dependências, dados e versões

O processamento é local. O primeiro uso do Whisper pode baixar o modelo público; a captura acessa o serviço da live. Não há API paga de seleção de momentos nem publicação automática em redes sociais. O painel aceita acesso apenas pelo próprio computador, em `127.0.0.1`.

Os testes foram executados com Python 3.11.9, faster-whisper 1.2.1, NumPy 2.4.6 e PyAV 18.1.0. `requirements.txt` fixa faster-whisper e Streamlink; FFmpeg é uma ferramenta externa. Para executar os testes em um ambiente instalado:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

O código desta entrega é a versão **0.19.0-beta.1**. O pacote não contém ambiente virtual, vídeos, banco de dados ou segredos. O instalador baixa e valida o modelo facial gratuito quando necessário. O LiveClips cria backups locais do banco e dos perfis; as gravações continuam exigindo uma cópia própria para outro disco quando você quiser proteção completa da mídia.

Para escolher outra pasta de dados, defina `LIVECLIPS_ROOT` antes de abrir. `LIVECLIPS_LEGACY_ROOT` permite indicar onde estão as gravações antigas. Não use duas instâncias sobre o mesmo banco. Não altere o banco manualmente durante o processamento.
