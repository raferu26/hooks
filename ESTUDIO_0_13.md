# LiveClips 0.13 — plano versionado, memória editorial e revisão

Esta versão aplica o dossiê "Editor Profissional" ao que já existia. **Leia este arquivo antes de confiar em qualquer recurso novo**: ele separa o que foi desenhado, implementado, integrado e validado, e diz o que nunca foi visto com conteúdo real.

## Como ler os estados

- **Implementado**: existe código e teste automatizado.
- **Integrado**: o fluxo normal do programa (importar, analisar, renderizar, exportar, interface) usa o recurso.
- **Validado (sintético)**: testado com mídia gerada pelo FFmpeg (render real, medição real), nunca com lives ou vídeos seus.
- **Validado (conteúdo real)**: **nenhum item desta versão** chegou a esse estado. Só você consegue fazer isso, com os seus cortes e o `TESTE_GUIADO.md`.

Metas de áudio (−16 LUFS, −1,5 dBTP), tempos de legenda (100/200 ms), limite de 2 correções automáticas e alarme de 20 caracteres por segundo são **propostas internas do dossiê**, não regras de plataforma.

## O que mudou

1. **Plano de edição versionado** (`plan.py`): cada render grava `plano.json` com tempo em ticks inteiros (90 000/s), intervalos semiabertos, uma entrada por ocorrência (replay repete a mesma origem), velocidades exatas e hash. O plano descreve os trechos que o renderizador usa de fato, e a duração do arquivo é conferida contra ele em quadros.
2. **Replay, rampa de velocidade e congelamento** no projeto e no render, com remapeamento de legendas após cortes, replay e velocidade.
3. **Registro de capacidades** (`capabilities.py`): 10 disponíveis, 14 parciais, 10 ausentes, 2 em laboratório. O plano só aceita efeitos conhecidos, com parâmetros dentro dos limites. "Nenhum efeito" é uma escolha válida.
4. **Memória editorial** (`memory.py`, `knowledge.py`, `curriculum.py`): banco próprio (`memoria_editorial.sqlite3`), 11 áreas, escopos global/projeto/streamer/job, origem de cada registro, validade (tendência sempre expira), histórico, desfazer e conflitos. Correção humana fica **local** ao corte; só vira preferência do streamer se você pedir ("sempre", "para este streamer"). Texto vindo da mídia ou do chat nunca vira regra. 16 fundamentos de edição vêm de fábrica.
5. **Habilidade narrativa** (`narrative_skill.py`): mapa de funções (contexto, ação decisiva, reação, resolução), pausas narrativas protegidas e escolha de montagem. A cronológica é a padrão; abertura antecipada só com promessa verdadeira, clímax tardio e resolução preservada.
6. **Revisão ciente do plano** (`review.py`): separa o que foi planejado (congelamento) do que é falha (quadro preto sem motivo, duração fora do plano, palavra cortada na borda de um trecho, pausa protegida cortada, efeito alto sobre a fala, legenda rápida demais). Grava `revisao.json`. **Falha crítica impede o estado "pronto".** Um relatório limpo nunca diz "aprovado": diz "revisão humana", porque o programa não ouve nem assiste o vídeo.
7. **Entrega** (`export_pack.py`): estados em revisão → pronto para revisão → aprovado → pronto para publicar; aprovação vale só para o hash do arquivo aprovado; pacote com hashes (`pacote.json`) e linha do tempo OpenTimelineIO (`linha_do_tempo.otio`, lida com sucesso pela biblioteca oficial nos testes). **Nada publica sozinho.**
8. **Edição por conversa** (`converse.py`): frases como "corta de 8 a 11", "replay de 12 a 15 em câmera lenta", "sem zoom" viram mudanças tipadas, validadas pelas mesmas regras do editor, com desfazer, refazer e confirmação para corte grande. O que não entende volta como pergunta. A proposta aparece no Estúdio; você decide se atualiza a prévia.
9. **Legendas** (`caption_track.py`): cada palavra tem literal, exibição, confiança, origem e nível de alinhamento (palavra, estimado, bloco). Mede erro de texto (WER) e de tempo contra uma amostra revisada. Exporta `legendas_revisao.json`.
10. **Observações de cena** (`perception.py`): fatos com intervalo, fonte, confiança e cobertura; pontos de atenção como **hipóteses**, incluindo contraexemplos. Não rotula emoção.
11. **Catálogo de efeitos sonoros por função** (`sfx_catalog.py`), **inventário de mídia** (`inventory.py`), **telemetria com p50/p95 e modos de qualidade** (`telemetry.py`), **referências com validade** (`references.py`), **kit de avaliação cega** (`evalkit.py`), **política de layout** (`layout_policy.py`).
12. **Aprendizado por salvamento** (`feedback.py`): o que você muda ao salvar um corte (cortes, zooms, replays, efeitos) vira caso local na memória.
13. **Interface**: aba "Por quê" no Estúdio (decisões, revisão, estado de entrega, aprovar, montar pacote), caixa de pedido em português na aba Agente, painel de memória do streamer (vocabulário, esquecer) e modo de qualidade nos ajustes.

## Matriz F01–F28 (dossiê)

Legenda: Impl = implementado e testado · Integ = usado pelo fluxo normal · Sint = validado com mídia sintética · Real = validado com conteúdo real.

| Id | Item | Impl | Integ | Sint | Real | Observação |
|---|---|---|---|---|---|---|
| F01 | Inventário de mídia | sim | só na importação de vídeo (aviso + `inventario.json`) | sim (ffprobe) | não | Não altera `media.probe`; capturas ao vivo não passam por ele. |
| F02 | Modelo temporal único | sim | sim | sim (render real, ±3 quadros) | não | Ticks no plano; o render por baixo continua em segundos (float). |
| F03 | Plano versionado | sim | sim | sim | não | `plano.json` por render. |
| F04 | Renderizador controlado | sim | sim | sim | não | Modelo/conversa só geram operações tipadas; nenhum comando de shell. |
| F05 | Prévia e revisão local | parcial | sim | — | não | Prévia e ajuste por intervalo já existiam; comparar antes/depois só pelas variações A/B. |
| F06 | Verificação final | sim | sim | sim | não | `qc.py` + `review.py`; não ouve nem assiste o resultado. |
| F07 | Planejador narrativo | sim | sim | parcial | não | Heurístico, sem modelo; não avaliado em conteúdo real. |
| F08 | Corte semântico e pausas | sim | sim | sim | não | Pausas protegidas e checagem de palavra cortada. |
| F09 | Composição adaptativa | sim | **não** | sim (unidade) | não | O render ainda aplica **um** layout por clipe. A decisão por trecho está pronta e testada, falta o render. |
| F10 | Perfil da webcam | parcial | parcial | sim (unidade) | não | Seleção manual por streamer já existia; o registro normalizado novo não está ligado ao armazenamento. |
| F11 | Legenda editorial | sim | parcial | sim | não | Contrato e métricas integrados só ao `legendas_revisao.json`; o ASS ainda sai do `captions.py`. Nenhuma medição de erro em amostra revisada. |
| F12 | Mixagem por função | parcial | parcial | — | não | Ducking de música existia; catálogo/mix novos **não** estão ligados à escolha automática. Sem separação de faixas. |
| F13 | Memória por streamer | sim | sim | sim | não | Vocabulário, referências, hábitos; painel na interface. |
| F14 | Zoom e movimento | existente | sim | — | não | Sem mudança nesta versão. |
| F15 | Registro de receitas | sim | sim | sim | não | Validação do plano usa o registro no render. |
| F16 | Replay e congelamento | sim | sim | sim | não | Replay mudo ou com som, limites de 4 replays e 8 s. |
| F17 | Montagem musical e velocidade | parcial | sim | sim | não | Rampa em degraus constantes; corte na batida continua ausente. |
| F18 | Grafismos e B-roll | parcial | sim | — | não | Imagem de apoio existia; busca por significado: ausente. |
| F19 | Máscaras e composição | ausente | não | — | não | Fora do alcance desta versão. |
| F20 | Tratamento de cor | parcial | sim | — | não | Cor global; por região ausente. |
| F21 | Revisor multimodal | parcial | sim | sim | não | **Só regras.** Dimensões de áudio e movimento ficam "não verificado". |
| F22 | Aprendizado por feedback | sim | sim | sim | não | Via salvamento do corte; sem motivo declarado vira hipótese fraca. |
| F23 | Avaliação comparativa | sim | **não** | sim (unidade) | não | `evalkit.py` não tem tela nem rotina; é preciso montar os 60–100 casos autorizados. |
| F24 | Exportação editável | sim | sim | sim (OTIO lido pela biblioteca) | não | Não testado em editor de vídeo real. |
| F25 | Orçamento de processamento | sim | sim | sim | não | Modos trocam preset/CRF; revisões automáticas ainda não rodam sozinhas. |
| F26 | Observabilidade e retomada | parcial | parcial | sim | não | Telemetria local por etapa (previa/exportação/qualidade); análise e transcrição ainda sem medição. |
| F27 | Explicação das decisões | sim | sim | sim (interface no navegador) | não | Aba "Por quê". |
| F28 | Gestão de ativos | parcial | parcial | sim | não | Permissões por destino na memória; catálogo de efeitos novo não está ligado à escolha automática. |

## Matriz R01–R36 (registro de capacidades)

Estado vem direto de `capabilities.py`; a coluna de evidência aponta onde está o código.

| Id | Receita | Estado | Evidência | Alternativa |
|---|---|---|---|---|
| R01 | Corte limpo e ajuste de entrada/saída | parcial | agents.tighten_bounds, timeline.expand_context, editor manual | Ajuste manual no Estúdio |
| R02 | Pausas e repetições | parcial | editing._safe_silences/_safe_repetitions, safety.py, narrative_skill.protected_pauses | Não cortar |
| R03 | Jump cut motivado | parcial | editing.cuts_for | Manter o trecho |
| R04 | J cut e L cut | ausente |  | Corte seco |
| R05 | Abertura por antecipação curta | disponivel | project.teaser, agents.suggest_teaser, media.plan_pieces | Cronologia integral |
| R06 | Preparação e payoff | parcial | narrative.story_plan, narrative_skill.function_map | Corte cronológico |
| R07 | Pausa e silêncio intencionais | parcial | narrative_skill.protected_pauses | Manter pausa original |
| R08 | Corte por correspondência visual | ausente |  | Corte seco |
| R09 | Layout vertical webcam + gameplay | disponivel | media.live_filters, media.resolve_layout | Layout "Ajustar" |
| R10 | Punch in sobre reação | disponivel | motion.py, editing.plan_edits, project.zooms | Sem zoom |
| R11 | Reenquadramento rastreado | parcial | speaker.py, media.dynamic_reframe_plan | Enquadramento fixo do perfil |
| R12 | Troca motivada entre layouts | parcial | layout_policy.py (política e plano); render troca layout por clipe, não por trecho | Layout fixo do perfil |
| R13 | Congelamento e anotação | parcial | media.build_source (hold), project.freezes | Sem congelar |
| R14 | Replay explicativo | disponivel | editing.Remap (replays), project.replays | Sem replay |
| R15 | Legenda limpa por blocos | disponivel | captions.py | Legenda por bloco de frase |
| R16 | Destaque sincronizado de palavras | disponivel | captions.keyword_indexes, make_ass | Legenda sem destaque |
| R17 | Tipografia cinética | parcial | captions.CAPTION_STYLES (estilos animados) | Legenda estática |
| R18 | Título de contexto | disponivel | captions.title_blocks, project.titles | Sem título |
| R19 | B-roll e imagem de apoio | parcial | assets.py, project.overlays | Sem imagem |
| R20 | Setas e anotações rastreadas | ausente |  | Sem anotação |
| R21 | Corte sincronizado à música | parcial | music.beat_times, agents.snap_to_beats | Cortes sem grade musical |
| R22 | Rampa de velocidade (velocity) | parcial | project.ramp_steps, editing.Remap | Velocidade constante |
| R23 | Câmera lenta seletiva | parcial | project.speeds | Velocidade normal |
| R24 | Ducking de música sob voz | disponivel | media.audio_chain (sidechaincompress) | Música em volume baixo fixo |
| R25 | Efeito sonoro por função | disponivel | sfx.py (catálogo sintetizado, com função e intensidade) | Sem efeito |
| R26 | Acabamento de voz | disponivel | media.audio_chain, denoise.py, loudnorm em dois passes | Áudio original normalizado |
| R27 | Transição por movimento | ausente |  | Corte seco |
| R28 | Shake localizado | ausente |  | Sem shake |
| R29 | Máscara de pessoa | ausente |  | Layout comum |
| R30 | Texto atrás do sujeito | ausente |  | Texto na frente |
| R31 | Desfoque rastreado de informação | ausente |  | Cobertura fixa manual |
| R32 | Colagem e paralaxe 2.5D | laboratorio |  | Sem efeito |
| R33 | Composição e câmera 3D | laboratorio |  | Sem efeito |
| R34 | Correção de cor | parcial | editing.grade_filters, LOOKS | Sem correção |
| R35 | Estabilização e ruído visual | ausente |  | Sem tratamento |
| R36 | Loop editorial e final | ausente |  | Final simples |

## Limites que importam

- **Nada foi validado com conteúdo real.** Todos os testes de mídia usam sinais sintéticos do FFmpeg.
- **O programa não ouve nem assiste o vídeo.** A revisão automática cobre regras verificáveis; as dimensões de áudio, movimento e conteúdo ficam "não verificado".
- **O laço de correção automática existe (`review.correct`, máximo 2) mas não roda sozinho.** As correções sugeridas aparecem em `revisao.json`; você decide.
- **Layout por trecho não chega ao render** (F09/R12).
- **Máscaras, rastreamento de anotações, cortes J/L, transições de movimento, tremor de câmera e estabilização continuam ausentes.**
- **Pesquisa de tendências é rotina manual:** o catálogo guarda e consulta; não pesquisa sozinho nem agenda nada.
- **Pesos da rubrica de avaliação, tamanhos mínimos (60 casos, 2 avaliadores) e limites de legenda são propostas** do dossiê, ajustáveis.
- **Arquivos `.bat` do Windows não foram testados** aqui, e não há `.exe`.
- **Mudar o modo de qualidade altera o arquivo gerado**, então invalida o cache de renders daquele corte.

## Próximo gargalo provável

Ligar a política de layout ao render (trechos com layouts diferentes no mesmo clipe) e rodar a avaliação cega com casos seus. Sem isso, não dá para saber se as decisões novas melhoram o resultado ou só o descrevem melhor.
