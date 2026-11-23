# Progresso P00–P27 (Hook’s 0.18) — registro vivo

Ambiente de desenvolvimento Linux, sem Windows e sem live real. “Validado” aqui = teste automático ou render curto com mídia sintética. Estados: pendente · em andamento · implementado · validado · bloqueado.
Cada módulo cita arquivo/função e se participa do fluxo automático (entrada → análise → decisão → receita → render → QC).

## P00 — Mapa do código (feito em 22/11/2026 23:5x)
Fluxo real de um corte: `capture/scan_one` (segmentos) → `engine.analyze_one` (Whisper + `signals.extrair`) → `engine.suggest_one` (`ranking.rank` → `judge.curate` → `plan_edits` → `store.propose`) → revisão (`store.review`) → `engine.do_render` → `media.render` (`_render_single`, FFmpeg em um passe; plano de B `_render_legacy`) → `engine.run_qc` (`qc.py`, `qc_visual.py`) → `delivery`.
Dependências de IA/rede no fluxo padrão: faster-whisper (transcrição e 2ª passagem), MediaPipe (`behavior.py`, `camera_detect.py`), RNNoise (`denoise.py`, opcional), Ollama (opcional), yt-dlp/streamlink (rede, captura).
Registro de receitas já existente: `capabilities.RECIPES` (R01–R36).

| Módulo | Estado antes (23/11, início) | Evidência (arquivo · função) | Participa do fluxo automático? |

_O estado atual de cada módulo está na seção “Estado final por módulo”, no fim deste arquivo._

|---|---|---|---|
| P01 plano/receita | implementado | `plan.py` build/validate/dump/load; `media._attach_plan` | sim (render grava o plano) |
| P02 relógio/remap | implementado | `plan.TimeMap`, `editing.Remap`, `retime_transcript`, `retime_points` | sim |
| P03 análise técnica | parcial | `signals.extrair` (energia, movimento, MediaPipe), `qc_visual` (freeze/preto/silêncio só no arquivo pronto) | parcial; sem detector de silêncio/preto/congelamento na fonte |
| P04 montagem por marcadores | ausente | só `Criar corte manual` e candidatos por transcrição | não |
| P05 pausas conservadoras | parcial | `editing._safe_silences` (depende de transcrição) | só com transcrição |
| P06 sincronismo multi-fonte | ausente | — | não |
| P07 layouts | implementado | `layout_policy`, `media.resolve_layout/live_filters` | sim |
| P08 tracking clássico | parcial | `media.dynamic_reframe_plan`, `speaker.py` (usam detector de rosto) | sim, mas com detector de rosto |
| P09 zooms/curvas | implementado | `motion.py`, `editing.punches_for`, `project.zooms` | sim |
| P10 replay/freeze | implementado | `plan.KINDS`, `editing.Remap`, `project.replays/freezes` | sim (manual/projeto; política automática parcial) |
| P11 velocidade | parcial | `project.ramp_steps/speeds` (degraus, sem interpolação) | sim |
| P12 voz/mixagem | parcial | `media.audio_chain` (passa-alta, afftdn/RNNoise, loudnorm 2 passos, alimiter) | sim; sem EQ/compressor/de-esser |
| P13 música/ducking/batidas/SFX | implementado/parcial | `media.audio_chain` (sidechain), `music.beat_times`, `sfx_catalog` | sim; batida só em transições manuais |
| P14 legendas prontas | ausente | legendas só vêm do Whisper (`captions.py`) | não importa SRT/VTT/ASS |
| P15 gráficos por dados | parcial | `captions.title_blocks`, `project.titles` (texto livre) | sem campos/dados |
| P16 máscara/chroma | ausente | só blur (`media.blur_graph`) | não |
| P17 cor/identidade | parcial | `editing.grade_filters`, `LOOKS` | sem LUT nem correção por histograma |
| P18 estabilização | ausente | R35 ausente | não |
| P19 transições | ausente | R27/R04 ausentes | não |
| P20 capas/thumbnails | ausente | — | não |
| P21 macros de imagem | parcial | `brand.py`, `assets.py` | sem receitas/variantes |
| P22 diretor de estilos | parcial | `editing.apply_budget`, `preset_for` | sem registro de recusas |
| P23 multiformato | parcial | `media._render_variants`, `captions.make_ass(canvas=…)` | conferir |
| P24 proxy/cache/fila | parcial | `store.recover`, `recovery.py`, render atômico | sem proxy/cache de análise |
| P25 QC e recuo | parcial | `qc.py`, `qc_visual.py`, `engine.run_qc`, `media` plano B | QC sim; recuo por módulo não |
| P26 intercâmbio | parcial | `export_pack.otio/manifest` | sim; não testado em NLE real |
| P27 motion graphics | ausente | R32/R33 laboratório | não |

## Modo sem IA (requisito transversal) — implementado e validado em mídia sintética (22/11/2026)
Perfil `ai_mode='sem_ia'` (Ajustes → Avançado → Modo de análise). No fluxo: `engine.analyze_one` → `_analyze_free` (sinais clássicos de energia/movimento + `technical.analyze`: silêncio, preto, imagem parada; sem Whisper) → `_suggest_free` (marcadores de `marcadores.json|csv|txt`, atalho “Marcar este momento agora”, e picos técnicos marcados `heuristic`; legendas importadas só viram texto) → `plan_edits(protected_spans)` → revisão → `media.render` → QC (`qc.check_export(ai=False)` sem busca de rosto).
Travas: `get_model`/`queue_refine`/`do_refine` (sem 2ª passagem), `_camera_step` e `/api/camera/detect` (sem detecção de webcam), `media.reframe_points` (sem rosto: enquadramento fixo do perfil), `media.voice_mode` (neural → limpeza clássica com aviso), Ollama só no caminho padrão.
Arquivos: `subtitles.py`, `technical.py`, `markers.py`, `editing.py` (`SILENCE_POLICIES`), `signals.py` (`ai=False`), `timeline.py`, `engine.py`, `store.py`, `app.py` (`/api/session/marker*`, `/api/session/subtitles/*`), UI (`body.html`, `core.js`).
Testes: `test_subtitles`, `test_technical`, `test_markers`, `test_silence_policy`, `test_markers_api`, `test_noai_mode` (sessão sintética real: análise → sugestão por marcador → aprovação → render → QC, com bloqueio de import de `faster_whisper`/`mediapipe`/`torch`/`onnxruntime`/`tensorflow`; 0 tentativas). UI: Playwright (marcar/importar/salvar, axe 0 violações no painel Avançado).
Limites: relógio do PC define o “marcar agora” (estimativa rotulada); nada validado no Windows nem em live real.

## Estado por módulo (atualizado)
- P03 análise técnica: **validado** (sintético) — `technical.py`, usado em `_analyze_free` e `shifted_signals`.
- P04 marcadores: **validado** (sintético) — `markers.py`, API, UI, `_suggest_free`.
- P05 pausas conservadoras: **validado** (sintético) — `editing.SILENCE_POLICIES`, `_audio_silences`; funciona sem transcrição.
- P14 legendas prontas: **validado** (sintético) — `subtitles.py` (SRT/VTT/ASS), importação por API/UI, origem registrada (`transcript_segments_origin`).
- Demais: pendentes (ver tabela P00).

## Atualização 23/11/2026 (módulos adicionados nesta rodada)
Todos os itens abaixo participam do fluxo real `do_render` → `media.render` → QC → entrega e foram exercitados em mídia sintética (nada no Windows nem em live real). Opcionais ficam **desligados por padrão** (exceto capa), para preservar o comportamento anterior; ligam em Ajustes por streamer.
- **P20 capas** — implementado/validado (sintético). `cover.py` (nitidez/exposição/contraste, 12 amostras, 3 melhores, modelos limpo/faixa/destaque, 9:16, 1:1, 4:5, margens seguras), `engine.make_cover` (após render, antes do QC), `delivery` copia `_capa.jpg`, QC avisa capa fraca. Perfil: `cover`, `cover_template`. Testes: `test_cover`, integração em `test_noai_mode`.
- **P12 voz** — implementado/validado. `media.VOICE_PRESETS` (EQ, de-esser, compressor; `has_filter` pula filtro ausente e registra em `voice_skipped`), perfil `voice_preset` off/natural/forte; sem modelo, vale no modo sem IA. Testes: `test_voice_chain` (todos os textos de filtro rodam no FFmpeg).
- **P17 cor** — implementado/validado. `grade.py` (histograma conservador com limites e motivos; LUT `.cube` 3D validada, intensidade por mistura com identidade), `media._with_color`, upload `/api/upload?kind=lut`, perfil `auto_color`, `lut`, `lut_strength`; `color_report` no manifesto. Testes: `test_grade`.
- **P25 QC e recuo** — implementado/validado. `media._single_ladder` (falha com módulos opcionais ligados → refaz sem eles e grava `recuo`), `qc.manifest_checks` (recuo, plano B antigo, filtro de voz ausente, estabilização ausente, efeito de imagem não aplicado, capa fraca). Testes: `test_retreat`. A integração real pegou um erro de verdade (deshake exige múltiplos de 16) — corrigido.
- **P19 transições (parcial)** — só fade curto de áudio nas emendas (`cut_fade` off/suave/media; `build_source(fade=)`); **não** há xfade de vídeo nem J/L-cut. Testes: `test_cut_fade`.
- **P11 velocidade** — `slow_interp` off/mistura/movimento (`minterpolate`, só câmera lenta ≤ 6 s); degraus continuam como antes. Testes: `test_cut_fade`.
- **P18 estabilização** — `stabilize` off/leve/forte (`deshake`, uma passada, desligada por padrão; sem o filtro, avisa no QC). Sem vidstab de duas passadas.
- **P15 títulos por dados** — `titledata.py` (campos {rotulo}, {streamer}, {data}, {numero}, {sessao}; campo vazio some com o separador; limite 60), `engine.apply_auto_title` → `media._titles`, perfil `title_template`. Só vale quando o corte não tem título feito à mão. Testes: `test_titledata`, integração em `test_noai_mode` (rótulo do marcador vira título no ASS).
- **P16 chave/máscara/mistura** — `keying.py` (chroma com despill, luma, máscara circle/rounded com suavização, camada screen/multiply), validado em `project.clean`, aplicado em `media.prepare_overlays`/`final_video`; aviso no QC se falhar. Sem UI no Estúdio (só pelo projeto/API). Testes: `test_keying` (inclui render real).
- Teste combinado de módulos no render real: `test_modules_combined` (voz + cor + fade + interpolação + estabilização + capa, sem recuo).

## Atualização 23/11/2026 (2) — P06, P22, P24, P08
- **P06 áudio externo** — implementado/validado (sintético). `syncaudio.py` (sincronia por envelope + correlação cruzada; recusa quando ambíguo), `link/load/unlink`, arquivo `audio_externo.json`, `build_source(external=)`, UI (Avançado: vincular/remover). Só para sessão de vídeo de um arquivo; o manifesto registra `external_audio`. Teste: `test_syncaudio`.
- **P22 diretor de estilos** — implementado/validado. `editing.director_report` + `plan['director']` com causas orçamento/proteção/configuração/regra; zoom desligado informa o motivo. Teste: `test_director`.
- **P24 cache (parcial)** — `cache.py` (cache por SHA do conteúdo em `<root>/cache`, `technical.VERSION`). Não há arquivos proxy; fila durável e render atômico já existiam. Teste: `test_cache`.
- **P08 rastreio clássico** — implementado/validado (sintético). `track.py` (fluxo óptico Lucas-Kanade com checagem direta-inversa, leitura sequencial, zona morta, recusa em região sem textura / corte de cena / perda de pontos → `face=False` e quadro volta ao padrão). Perfil `track_roi` (fração da imagem) validado em `store.py`; `reframe_mode='rastreio'` (importação exige região marcada); `media.reframe_points` roteia ANTES da trava de IA, então funciona no modo sem IA (testado: nenhum import de módulo de IA); render real grava `plano_enquadramento.json`. Atualização de `track_roi` vale na hora da exportação (`engine.do_render`). UI: botões "Marcar região a acompanhar/Limpar região" e opção "Por rastreio" nos dois diálogos de vídeo (axe 0 violações). Limites: acompanha textura (não identifica pessoa); a região vale para o primeiro quadro de cada corte; só movimento horizontal (corte 9:16 de fonte larga); nada validado em vídeo real. Teste: `test_track` (11 casos, 1 com render real).
- **P21 receitas de imagem** — implementado/validado (sintético). `imagerecipe.py`: contain/cover sem distorcer (Lanczos, alfa pré-multiplicado, sem halo escuro), margem, contorno, sombra, recorte por região, máscara fornecida, fundo uniforme com tolerância (recusa foto comum), conversão PNG/JPG/WEBP (JPG achata a transparência e avisa), perfil ICC → sRGB; lote com erros isolados, nomes Unicode, sem sobrescrever fontes; variantes por destino (logo, marca d’água, moldura, cartão, logo da capa) com catálogo `imagens/variantes/catalogo.json` (fonte, SHA, medidas, alfa, versão) e invalidação por conteúdo. Integração: `brand.py` (`logo.style` sombra/contorno, `logo.cover`, `frame`, `card_fit`) → `brand.assets` usa variante (falha cai na imagem original com aviso) → `media.prepare_overlays`/`final_video`; `cover._brand_logo` põe o logo na capa; API `/api/image/batch`, `/api/image/variants`; UI na marca. Comportamento anterior preservado quando nenhuma opção é ligada. Testes: `test_imagerecipe` (16, incl. render real: moldura visível no vídeo, logo na capa).
- **P23 multiformato** — implementado/validado (sintético). `multiformat.py`; perfil `export_formats` (1:1, 4:5, 16:9) e `export_srt`; `media._render_variants` junta formatos do perfil e do Estúdio, valida cada arquivo (medidas, codec h264, yuv420p, áudio, duração) e apaga/registra variante inutilizável (`variants` no manifesto); legenda `.ass` própria de cada proporção guardada e `.srt` opcional; capas por formato (16:9 incluído); entrega com nomes estáveis (`_1x1.mp4`, `_capa_16x9.jpg`, `_1x1.srt`) sem sobrescrever outros arquivos. O teste de codificador por placa de vídeo já existia (`hardware.works`). Sequencial (sem concorrência de variantes). Teste: `test_multiformat` (render real, layout/margens recalculados por proporção).
- **P26 intercâmbio/projeto portátil** — implementado/validado com a biblioteca OpenTimelineIO 0.18.1 (não em editor real). Bugs reais achados pela biblioteca e corrigidos: `FreezeFrame` sem `time_scalar` (arquivo ilegível) e durações de clipe com velocidade ≠ 1 (a soma não batia com o vídeo). Agora: marcadores OTIO para zoom/título/SFX/música/imagem/congelar/replay/velocidade, `linha_do_tempo_limites.txt` + `nao_transportado` no `pacote.json` (o que NÃO vai), conferência com a biblioteca quando instalada; `portable_project` (`projeto_hooks/projeto.json`: plano, perfil sem pasta de entrega, referências com SHA e tamanho; fontes opcionais, com tamanho informado antes) e `reopen` (confere o plano, localiza mídia por cópia/caminho/pastas e acusa ausente/alterada); API `/api/package/project`, `/api/package/reopen`; botões no Estúdio. Não testado no Premiere/Resolve/Final Cut/CapCut — nada promete abertura perfeita.
- **P27 gráficos 2D por template** — implementado/validado (sintético). `graphics2d.py` (não é o `motion.py` de zoom, que continua intacto): templates barra de nome, título animado, contador (formato BR), pulso por áudio (envelope + 9 bandas de FFT; não "entende" música); entradas validadas (texto ≤60, cores #RRGGBB, número, duração, instante — campos desconhecidos/“scripts” descartados); vídeo com transparência (.mov codec png) só da caixa do template; cache `cache/motion` por parâmetros + versão + formato do quadro (+ trecho de áudio no pulso); níveis do perfil `motion_level` off/leve (PNG estático)/completo; orçamento: corte ≥ 8 s, ≤ 2 gráficos, ≤ 25% da duração, 1 s de intervalo, decisões registradas com motivo; automático = barra com nome do canal aos 1,2 s (não entra se há título seu no começo). Integração: `media.motion_assets` → `extra_inputs`/`final_video` (overlay com `-itsoffset`), recuo do P25 inclui o módulo, QC avisa quando um gráfico não pôde ser aplicado, `manifesto.motion`, OTIO leva como marcador. Projeto: `project.motion` (até 4). Sem UI de edição por gráfico (só nível no perfil + projeto/API). Testes: `test_graphics2d` (22: variantes com dados diferentes, duração e cores fora da caixa preservadas, cache, pulso por áudio, nível leve). Incidente: sobrescrevi `motion.py` por engano e restaurei do pacote 0.17.1 (diff idêntico).

## Atualização 23/11/2026 (3) — exemplo completo do documento, replay automático, pausas com legenda importada, recuo de recursos
Cenário do documento (“Exemplo completo”) montado em `tests/test_exemplo_completo.py`, no caminho real (`analyze_one` → `suggest_one` → `review` → `do_render` → QC → entrega), modo `sem_ia`, com bloqueio de import de `faster_whisper`/`mediapipe`/`torch`/`onnxruntime`/`tensorflow` (0 tentativas). Fonte sintética de 100 s, dois marcadores, legenda `.srt` importada, música local autorizada, webcam no perfil.
Lacunas que o teste expôs e que foram corrigidas **no caminho de geração**:
- **P05/P14 — pausa com legenda importada.** `plan_edits` só olhava pausas entre palavras quando havia texto; legenda importada (sem tempo por palavra) fazia a pausa medida no áudio ser ignorada. Agora, sem tempo por palavra, vale o silêncio MEDIDO, descontando os trechos em que a legenda indica fala (`editing._without_speech`, folga de 0,2 s) e os trechos protegidos dos marcadores.
- **P10 — replay automático (não existia).** `editing._auto_replay` (perfil `auto_replay`: `off` padrão, `lento` 0,5× e mudo, `normal` com áudio original). Só em corte com momento marcado pela pessoa (nada deduzido de movimento), no máximo 1 por corte, de 1,5 s antes a 2,5 s depois do marcador, no máximo 8 s acrescentados e 25% do corte, e o corte final (já sem as pausas cortadas) não passa do limite do formato. Recusa, com motivo no plano e no “diretor”, quando falta marcador, não cabe, atravessa uma pausa cortada ou o projeto da pessoa já tem replay (o dela vale). Entra no render por `editing.auto_replays` → `remap_for(..., extra_replays)`; o Estúdio (`app.project_get`) usa o mesmo mapa. UI: Ajustes → Edição automática → “Replay do momento marcado”.
- **P02/P10 — legenda no replay.** Frase sem tempo por palavra que o replay interrompe ficava na tela durante todo o replay (texto de outro instante, contra o critério do P10). Agora é dividida no ponto do replay (`retime_transcript`); durante o replay só aparece o que existe naquele trecho.
- **P25 — recuo de recursos automáticos.** `media._single_ladder` ganhou o 2º degrau: depois de tirar os módulos opcionais, se ainda falhar (ou se um arquivo de recurso do perfil sumiu), refaz sem a música, efeito sonoro e imagem escolhidos pelo plano automático e grava `recuo` no manifesto (QC mostra o item). Recurso que a pessoa escolheu no Estúdio não some em silêncio: o erro continua. Outros `ValueError` não são engolidos.
Verificado no teste: duração do arquivo = corte − pausa + replay (54,9 s) com tolerância de 0,5 s; mapa de tempo no `plano.json` (peça `replay`, 1/2, mudo); 3ª fala da legenda no instante esperado; capa 9:16; título do marcador; variante 1:1 + `.srt`; QC sem erro; manifesto sem `recuo` no caminho feliz; com filtro de cor quebrado → `recuo` “cor automática” e vídeo 1080×1920 com áudio e replay mantido; com a trilha apagada → `recuo` “música automática” e entrega com áudio.
Limites: zoom do exemplo vem do estilo (“gameplay”); no estilo “limpo” o zoom nasce desligado de propósito. O replay automático não aparece como item editável no Estúdio (a pessoa liga/desliga a decisão pelas decisões do plano; se definir replays no projeto, o automático sai). Música com falha de decodificação no meio do render cai no 2º degrau, mas só foi testado o arquivo ausente.

## Estado final por módulo (23/11/2026)
Legenda: **validado** = teste automático/render real com mídia sintética; **parcial** = faz parte, com limite declarado. Nada foi testado no Windows nem em live real.
| Módulo | Estado | Onde age no caminho automático | Limite principal |
|---|---|---|---|
| P00 mapa | feito | este arquivo | — |
| P01 plano/receita | validado | `media._attach_plan` grava `plano.json` em todo render | — |
| P02 relógio/remap | validado | `Remap`, `retime_transcript` (agora divide frase em replay), `retime_points` | — |
| P03 análise técnica | validado | `technical.py` em `_analyze_free` | silêncio de áudio não prova ausência de conteúdo |
| P04 marcadores | validado | `markers.py`, `_suggest_free` | “marcar agora” usa o relógio do PC |
| P05 pausas | validado | `_audio_silences` (agora também com legenda importada) | medida desligada se o contraste for baixo |
| P06 áudio externo | validado | `syncaudio.py`, `build_source(external=)` | só vídeo de um arquivo |
| P07 layouts | validado | `layout_policy`, `media.resolve_layout` | — |
| P08 rastreio | validado | `track.py`, `reframe_mode='rastreio'` | região marcada no perfil; só horizontal |
| P09 zoom/curvas | validado | `motion.py`, `punches_for` | no estilo “limpo” nasce desligado |
| P10 replay/freeze | validado | `_auto_replay` (marcador), `project.replays/freezes` (manual) | freeze automático não existe |
| P11 velocidade | validado | `project.speeds`, `slow_interp` | interpolação só ≤ 6 s |
| P12 voz | validado | `VOICE_PRESETS`, `audio_chain` | filtros ausentes são pulados e avisados |
| P13 música/ducking | validado | `audio_chain` (sidechain), `music.beat_times` | batida só em transições manuais |
| P14 legendas prontas | validado | `subtitles.py` | origem registrada; só horário |
| P15 títulos por dados | validado | `titledata.py`, `apply_auto_title` | só em corte sem título manual |
| P16 chave/máscara | validado | `keying.py` | sem UI no Estúdio |
| P17 cor/LUT | validado | `grade.py`, `_with_color` | correção leve por histograma |
| P18 estabilização | parcial | `stabilize` (deshake) | uma passada |
| P19 transições | parcial | `cut_fade` (áudio) | sem xfade de vídeo nem J/L |
| P20 capas | validado | `cover.py`, `make_cover` | nota técnica, não de “qualidade” |
| P21 receitas de imagem | validado | `imagerecipe.py`, `brand.assets` | lote só por API |
| P22 diretor | validado | `director_report`, recusas com causa | — |
| P23 multiformato | validado | `multiformat.py`, `_render_variants` | variantes em sequência |
| P24 proxy/cache | parcial | `cache.py` | sem proxy |
| P25 QC e recuo | validado | `qc.py`, `_single_ladder` (2 degraus) | limiares do QC não calibrados com vídeos reais |
| P26 intercâmbio | validado (OTIO) | `export_pack.py`, projeto portátil | não aberto em NLE real |
| P27 gráficos 2D | validado | `graphics2d.py`, `motion_assets` | fonte do sistema; sem UI por item |
Exemplo completo do documento: `tests/test_exemplo_completo.py` (18 testes). Suíte completa em 23/11/2026: 1111 testes, 0 falhas (uma primeira rodada teve 1 erro num teste com assinatura antiga em `test_pro_audio`; corrigido e a suíte inteira rodada de novo, EXIT=0).

## Atualização 23/11/2026 (3) — validação complementar (0.18.1-beta.1)
Detalhes, matriz e lacunas em `VALIDACAO_COMPLEMENTAR.md`. Resumo: título automático deixou de cobrir a webcam; margem padrão da legenda 260→340; escrita atômica dos arquivos de estado; `reopen` valida caminhos; original não é relido inteiro a cada prévia/exportação; reserva de disco atual vale para cortes antigos; mensagens de arquivo ilegível em português; diagnóstico oculta mais credenciais; `.bat` em CRLF e sem abortar por falta do modelo facial. Lacuna conhecida: `layout_policy` (layout adaptativo por trecho) continua sem ligação ao render.
