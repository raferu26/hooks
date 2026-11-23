# Hook's 0.19.0-beta.1 — Estúdio simplificado, salvar sem perder a prévia e qualidade real de exportação

Base: 0.18.2-beta.1 (preservada sem alterações). Etapas do roteiro aprovado: E0 (linha de base), E1 (salvar × prévia),
E2 (modos de qualidade) e E3 (inspetor contextual, 3 pistas, "Sugestões"). Nenhuma dependência de IA foi adicionada.

## 1. O que mudou para quem usa

### Estúdio
- **Sem as 8 abas.** O painel da direita virou um **inspetor**:
  - clicar num zoom, título, corte, velocidade, imagem, efeito sonoro ou abertura mostra só os controles daquele item, no topo;
  - selecionar um trecho (na fala ou na régua) mostra as ações do trecho: Cortar, Zoom, Título, Velocidade e Abertura;
  - o resto do corte fica em seções recolhíveis, cada uma com um resumo em uma linha: Estilo, cor e som · Legendas · Títulos · Música · Cortes e efeitos · Layout e imagens · Sugestões · Por quê · Publicar.
  - Todas as funções da 0.18.2 continuam lá; nenhuma foi removida.
- **"Agente" virou "Sugestões"**, no Estúdio e nos Ajustes ("Sugestões e aprendizado"). As funções continuam as mesmas e determinísticas.
- **Linha do tempo com 3 pistas** (Vídeo, Legendas, Áudio). Zoom, Ritmo, Imagens e Títulos aparecem sozinhos quando têm conteúdo. "Todas as pistas" mostra as 7.
- **Vídeo maior:** de cerca de 7% para 17,2% da tela em 1440×900 (354×629 px).
- **Barra superior em uma linha** (antes quebrava). Ela mostra dois estados separados:
  - salvamento: Salvo / Salvando… / Alterações não salvas / Não salvou · tentar de novo;
  - prévia: Prévia atualizada / Gerando prévia… / Prévia anterior / A prévia falhou.
- **Um só controle de reprodução** (antes havia o do navegador e o do Hook's). Clicar no vídeo reproduz ou pausa. Há botão de som.
- **Atalhos novos:**
  - ← → navegam 1 s (Shift: 5 s); + e − dão zoom na linha do tempo; P atualiza a prévia; ? abre a lista de atalhos.
  - Ctrl+S agora só salva.
  - **Ctrl+Enter precisa ser pressionado duas vezes** para exportar (antes exportava sem confirmação).

### Salvar e prévia
- **Salvamento automático.** Cada alteração é salva cerca de 1,6 s depois, sem apagar o histórico de desfazer. Sair, trocar de corte e exportar salvam antes.
- **Salvar não apaga mais a prévia.** A prévia anterior continua tocando, marcada como "Prévia anterior", até a nova ficar pronta. O vídeo não some mais a cada mudança.
- **Prévia automática** (pode desligar embaixo do vídeo): a prévia nova é pedida sozinha depois que você para de editar. Legendas e títulos continuam aparecendo ao vivo por cima do vídeo.
- **O salvamento automático não ensina a memória do streamer.** O aprendizado acontece uma vez, com a diferença inteira, quando você salva de propósito, sai, troca de corte ou exporta.

### Qualidade da exportação
- **Os 4 modos agora mudam o arquivo final de verdade.** Na 0.18.2 eles só valiam no plano B: o caminho normal sempre usava o mesmo ajuste.
- **O modo pode ser escolhido em cada corte,** ao lado do botão Exportar. O padrão continua em Ajustes.

| Modo | CPU (x264) | NVIDIA | Intel | AMD | Áudio |
|---|---|---|---|---|---|
| Rápido | veryfast, CRF 21 | p3, CQ 23 | global_quality 24, faster | speed, QP 23/25 | 128 kbit/s |
| Equilibrado (padrão) | medium, CRF 18 (igual à 0.18) | p5, CQ 20 (igual à 0.18) | 20, slow (igual) | quality, QP 19/21 (igual) | 160 kbit/s |
| Qualidade | slow, CRF 16, aq-mode 3 | p7 + hq, CQ 18, 3 quadros B | 18, veryslow | quality, QP 17/19 | 192 kbit/s |
| Entrega | slower, CRF 15, aq-mode 3 — **sempre na CPU** | (usa a CPU) | (usa a CPU) | (usa a CPU) | 192 kbit/s |

- As escalas de qualidade das placas de vídeo **não são equivalentes** ao CRF do x264. Por isso Entrega ignora a placa de vídeo.
- Se a placa recusar um ajuste, o render refaz na CPU (comportamento que já existia).
- O manifesto de cada exportação registra o modo e os argumentos usados (`quality_mode`, `video_args`).

## 2. Bugs corrigidos

| # | Problema na 0.18.2 | Correção |
|---|---|---|
| P04 | Salvar zerava a prévia (`preview_path=''`), e o vídeo sumia até renderizar de novo | A prévia anterior fica disponível e marcada como desatualizada, com o mapa de tempo dela (`preview_timing`) para o cursor cair no lugar certo |
| P10 | Os 4 modos de qualidade eram iguais no caminho principal | Modos aplicados em `hardware.choose`/`media._video_codec`, também nas variações 1:1, 4:5 e 16:9 e no plano B |
| N1 | Barra superior quebrava em duas linhas | Barra em linha única, nome encurta com reticências; testado a 1440, 1280 e 1024 px |
| N2 | Dois controles de reprodução (navegador + Hook's) | Um só |
| N3 | "Agente" para algo que não é IA | "Sugestões" |
| N4 | Salvar várias vezes ensinava a memória a cada salvamento | Salvamento automático não ensina; o aprendizado acontece uma vez, com a diferença inteira |
| N6 | Ctrl+Enter exportava sem confirmação | Pede um segundo Ctrl+Enter em até 2,5 s |
| — | Trocar de corte com alterações era bloqueado ("Salve antes") | Salva e troca |
| — | Salvar de novo o mesmo projeto deixava a prévia atual como desatualizada | A prévia continua atual quando o projeto não mudou |

N5 (redesenho completo a cada mudança) foi reduzido: as seções fechadas não são desenhadas e a linha do tempo só desenha as pistas visíveis. Não fiz uma otimização mais profunda; ver pendências.

## 3. Arquivos alterados
- **Backend:**
  - `liveclips/store.py`: `save_project` (prévia preservada, `learn`, projeto idêntico) e `review` (prévia preservada);
  - `liveclips/app.py`: `preview_info`, `quality_catalog`, prévia anterior servida, `quality_mode` na exportação, `learn` no salvar;
  - `liveclips/engine.py`: guarda `preview_timing`;
  - `liveclips/editing.py`: `timing_for`, a fonte única do mapa de tempo;
  - `liveclips/hardware.py`: `mode_arguments`, `GPU_MODES`, `choose(mode=)`;
  - `liveclips/telemetry.py`: modos reais, `cpu_args`, `audio_bitrate`;
  - `liveclips/media.py`: o modo é aplicado no caminho principal, nas variações e no plano B.
- **Interface:** `liveclips/static/index.html` (Estúdio, linha do tempo, inspetor, atalhos, textos de Sugestões e do modo de qualidade nos Ajustes).
- **Validação:** `validacao/medir_modos.py` (SSIM/PSNR por modo) e `validacao/e2e_estudio_0_19.py` (teste de ponta a ponta do Estúdio, precisa de Playwright e de um Hook's rodando).
- **Testes novos:** `tests/test_salvar_previa.py` (9) e `tests/test_modos_qualidade.py` (9). **Testes ajustados:** `tests/test_telemetry.py` (o modo Rápido passou de CRF 23 para 21) e `tests/test_studio_extras.py` (assinatura de `choose`).
- **Versão:** `liveclips/__init__.py` e `hooks_cloud/__init__.py` → 0.19.0-beta.1.

## 4. Testes executados (Linux, Python 3.13, FFmpeg do sistema, Chrome headless; mídia sintética)
**Suíte automatizada completa:** 1212 testes (eram 1194 na 0.18.2; 18 novos), em ~39 min.
- Resultado: 1211 OK e 1 falha. A falha era o teste antigo que exigia a palavra "Agente" na interface.
- Esse teste foi atualizado para o nome aprovado, "Sugestões", e agora também confere os controles novos. Depois disso, a interface, o HTTP, o salvar/prévia, os modos de qualidade, os instaladores e o modo sem IA rodaram de novo: OK.

**Medida objetiva dos modos** (fonte sintética difícil de 4 s em 1080×1920, com ruído temporal, comparada ao original sem perdas; script `validacao/medir_modos.py`):

| Modo | SSIM | PSNR (dB) | Tempo para 4 s |
|---|---|---|---|
| Rápido | 0,854 | 33,8 | 7,4 s |
| Equilibrado | 0,964 | 39,4 | 9,2 s |
| Qualidade | 0,975 | 40,8 | 90,9 s |
| Entrega | 0,981 | 42,0 | 168,0 s |

- A qualidade cresce de modo a modo. Nessa fonte extrema (ruído em todo quadro) Qualidade e Entrega são **muito mais lentos**.
- Em vídeo real a diferença de tempo e de tamanho deve ser menor [Hipótese: não medido com clipe real].

**Teste de ponta a ponta do Estúdio** (`validacao/e2e_estudio_0_19.py`, 1440×900): 28 verificações, todas OK.
- Abrir o Estúdio leva ~140 ms. O zoom aparece ~60–70 ms após o clique.
- O salvamento automático preserva o desfazer. A prévia anterior continua disponível; a nova fica pronta sozinha em ~9–10 s.
- Desfazer e refazer, Delete, seções, atalhos e Ctrl+Enter duplo funcionam.
- O seletor de qualidade tem 4 modos e "Todas as pistas" mostra 7 pistas.
- A barra fica em uma linha a 1280 e 1024 px. Nenhum erro no console.

**Compatibilidade:** dados e projeto criados com o código 0.18.2, com zoom, título e prévia pronta, abertos na 0.19.
- O projeto foi lido intacto e a prévia antiga continuou disponível depois do salvamento automático.
- A exportação no modo Qualidade terminou em 1080×1920, e o manifesto registra `-preset slow -crf 16 -x264-params aq-mode=3`.

## 5. Sem IA: o que depende de modelo e o que é algoritmo clássico
O modo **Sem IA** (Ajustes → Análise) já existia. Um teste (`tests/test_noai_mode.py`) bloqueia a importação de faster_whisper, mediapipe, torch, onnxruntime e tensorflow durante a análise, e ela termina.

| Recurso | Usa modelo? | No modo Sem IA | Alternativa clássica e limite |
|---|---|---|---|
| Transcrição e legenda automática (faster-whisper) | Sim, rede neural | Desligada | Importar SRT/VTT/ASS ou digitar no Estúdio. **Não existe alternativa clássica equivalente para reconhecer fala**: sem arquivo de legenda, o corte sai sem legenda. Destaque por palavra só com ASS `\k` |
| 2ª passagem da legenda (Whisper maior) | Sim | Desligada | Correções fixas por streamer (errado => certo) e edição manual |
| Reações e expressões da webcam (MediaPipe Face Landmarker) | Sim, rede neural | Desligado | Picos de energia do áudio e de movimento (marcados como heurística); marcadores seus. Não detecta expressão facial |
| Localizar a webcam sozinho (MediaPipe; recua para Haar) | Sim | Desligado | Marcar o retângulo à mão em Ajustes → Webcam |
| Reenquadramento por rosto e "por quem fala" (classificador Haar do OpenCV) | Classificador treinado clássico (Viola-Jones), não rede neural | Desligado | "Por rastreio": fluxo óptico Lucas-Kanade da região que você marca. Acompanha textura, não pessoa |
| Limpeza de voz neural (RNNoise / `arnndn`) | Sim, rede neural pequena | Usa a clássica | `afftdn` + passa-alta (filtro espectral do FFmpeg): reduz chiado constante, não separa voz de música ou fala ao fundo |
| Avaliador de ganchos (Ollama) | Sim, LLM local opcional | Desligado | Ranking determinístico normal (o Ollama já vinha desligado por padrão) |
| Sugestões (gancho, títulos, limites, abertura), conversa em português, "Por quê" | Não: regras e medidas | Funcionam | — |
| Silêncio, tela preta, imagem parada, energia, cor por histograma, loudness, cortes, zoom, velocidade | Não | Funcionam | — |

**Decisão pendente:**
- Hoje o padrão de perfil novo é "padrão (com IA)", e `requirements.txt` ainda instala faster-whisper e mediapipe.
- Tornar Sem IA o padrão e retirar esses pacotes da instalação **tira a legenda automática de quem não tem arquivo de legenda**.
- É uma mudança de escopo com perda de recurso. Por isso não fiz sem a sua decisão.

## 6. O que continua pendente
- **Teste com pessoas reais:** roteiro pronto em `ROTEIRO_TESTE_USUARIOS_0_19.md`.
- **Windows real:** nada desta versão foi aberto no Windows (o ambiente é Linux).
- **Placas de vídeo:** NVENC, QSV e AMF não foram testadas (não há GPU aqui). Os ajustes p7/hq, veryslow e QP 17/19 podem ser recusados por drivers antigos; nesse caso o render refaz na CPU.
- **Clipes reais:** tempo e tamanho por modo não foram medidos com clipes de verdade. Mande 2 ou 3 clipes e a placa de vídeo para eu medir.
- **Prévia em camadas mais rápida:**
  - hoje a prévia nova renderiza o clipe inteiro em 540×960 (~9–10 s para 14 s de vídeo aqui);
  - não implementei a prévia por trecho alterado nem a reprodução direta da fonte com cortes aplicados no navegador.
- **Ajustes:** as 11 seções dos Ajustes não foram reorganizadas; só o Estúdio foi.
- **Desempenho do redesenho (N5):** a lista de fala e o inspetor aberto ainda são redesenhados a cada alteração. Não medi em clipes de 90 s com muitas palavras.
- **Miniaturas na pista Vídeo:** a pista mostra só a barra do clipe e os cortes.
- **Sem IA como padrão:** decisão acima.

## 7. Como executar no Windows
**Atualizando uma instalação existente (recomendado):**
1. Feche o Hook's.
2. Na pasta do Hook's atual, execute `ATUALIZAR.bat` e cole o caminho do `Hooks-0.19.0-beta.1.zip`. Seus dados em `C:\LiveClips` não são tocados, e o programa anterior fica em `liveclips_anterior`.
3. Abra pelo atalho **Hook's** ou por `ABRIR_LIVECLIPS.bat`.
4. **Para voltar à 0.18.2:** feche o Hook's, apague a pasta `liveclips` e renomeie `liveclips_anterior` para `liveclips`.

**Instalação nova:**
1. Instale o Python 3.11.
2. Extraia o ZIP numa pasta nova.
3. Execute `INSTALAR.bat` e depois `CRIAR_ATALHO.bat`, se quiser o atalho.
4. Abra com o atalho ou `ABRIR_LIVECLIPS.bat`.

**Projetos antigos:** abrem normalmente. O primeiro salvamento grava o projeto no formato da 0.19, que é compatível: os campos novos são opcionais. Se voltar para a 0.18.2, a prévia antiga de um corte editado na 0.19 aparece como "Sem prévia" até gerar de novo.
