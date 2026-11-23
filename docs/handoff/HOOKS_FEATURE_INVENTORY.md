# HOOKS — Inventário de funcionalidades (estado real na 0.19.0-beta.1)

Parte do pacote `HOOKS_MASTER_HANDOFF`. Descreve capacidades **existentes no código**, com localização, dependências, limites e testes. O que é só desejo está em `HOOKS_ROADMAP.md`.

Como ler a coluna **Estado**:
- **OK-S** = implementado e validado só com mídia sintética/Linux ([TESTADO] automático).
- **PARCIAL** = existe, mas incompleto ou com limite que o próprio código/documento declara.
- **NÃO-VAL** = existe mas nunca foi exercitado no ambiente real (Windows, GPU, live real, YouTube real).
- **LAB** = laboratório, desligado ou rotulado exploratório.
- **AUSENTE** = não existe (listado só para evitar suposição).

"IA?" indica se usa **modelo de aprendizado de máquina** (Sim) ou algoritmo clássico/regras (Não). Nenhum item foi validado com conteúdo real de live/vídeo de terceiros; isso vale para todo o documento. Fonte principal: leitura dos módulos de `liveclips/` e dos documentos de estado (`PROGRESSO_P00_P27.md`, `INTELIGENCIA_0_14.md`, `NOVIDADES_0_19.md`). Os testes citados ficam em `tests/` (nomes reais).

Registro formal de capacidades: `capabilities.py` (`RECIPES` R01–R36, 36 receitas; estados definidos na 0.13, ampliados na 0.18 — o texto do estado por receita fica no próprio arquivo, [NÃO VERIFICADO] se todos foram atualizados após P00–P27).

---

## 6.1 Importação

| Funcionalidade | Como funciona | Onde | IA? | Dependências | Estado | Limites | Testes |
|---|---|---|---|---|---|---|---|
| Arquivo local de vídeo/podcast | Vincula o original sem copiar (MP4, MKV, MOV, WEBM, TS, M4V); metadados via ffprobe; artefatos dentro da pasta do Hook's | `app.py` (`/api/video/import`, `/api/upload`), `inventory.py`, `media.py` | Não | FFmpeg/ffprobe | OK-S | Religar por SHA-256 se o arquivo mudar de lugar | `test_inventory`, `test_http`, `test_acceptance` |
| Vídeo do YouTube (não live) | `videodl.py` baixa com yt-dlp (até 1080p, mp4), vira sessão e analisa sozinho | `videodl.py`, `/api/video/url` | Não | yt-dlp, Deno ou Node para YouTube atual | **NÃO-VAL** (YouTube real nunca acessado) | Se o YouTube mudar, atualizar yt-dlp | `test_videodl` (servidor HTTP local simulado) |
| Live ao vivo (Twitch/YouTube/outros) | Streamlink grava em segmentos `.ts`; até 5 capturas no gerenciador; fallback de qualidade; encerramento registrado; "Retomar gravação" | `capture.py`, `/api/capture/*` | Não | streamlink 8.6.3 | NÃO-VAL (só `.ts` simulados) | Captura real de 2+ lives nunca validada; reconexão com "épocas" ausente (N02) | `test_multi_live`, `test_qualidade`, `test_crash` |
| Vídeo por link público (não YouTube) | Pipe do Streamlink; análise progressiva | `capture.py` | Não | streamlink | NÃO-VAL | O vídeo precisa chegar à máquina | `test_acceptance` |
| Importar marcadores | `.json/.csv/.txt` ou atalho "Marcar este momento agora" | `markers.py`, `/api/session/marker(s)` | Não | — | OK-S | Só o que você marcou | `test_markers`, `test_markers_api` |
| Importar legendas prontas | SRT/VTT/ASS/SSA → segmentos temporizados, sem reconhecimento | `subtitles.py` | Não | — | OK-S | Destaque por palavra só com ASS `\k` | `test_subtitles` |
| Áudio externo / sincronismo | Correlação cruzada para achar deslocamento entre gravações | `syncaudio.py`, `/api/session/external-audio` | Não | — | OK-S | Não aprende alinhamento sozinho | `test_syncaudio` |
| Pré-checagem | Webcam marcada, GPU/CPU, disco, ferramentas, limite de lives; estimativa por medições reais | `preflight.py` | Não | — | OK-S | Sem medições, sem estimativa | `test_preflight*` |
| Arquivos temporários | Pastas `render_*` incompletas são apagadas ao abrir; renders em pasta atômica | `media.py`, `atomic.py`, `store.recover` | Não | — | OK-S (interrupção simulada) | Política de retenção só simula (`retention.py` nunca apaga) | `test_crash`, `test_recovery` |

## 6.2 Clipagem

| Funcionalidade | Como funciona | Onde | IA? | Estado | Limites | Testes |
|---|---|---|---|---|---|---|
| Ranking de momentos | Pontuação por fala, áudio, movimento, chat, comportamento; tipos de momento (9); notas `heuristico_nao_calibrado` | `ranking.py`, `intelligence.py`, `signals.py` | Usa transcrição (Whisper) como entrada no modo padrão; regra pura | PARCIAL | Listas fixas de expressões PT/EN; ordem não calibrada com dados reais | `test_ranking` |
| Juiz de seleção | Refina começo/fim, diversidade, "se sustenta sozinho" | `judge.py` | Não | OK-S | — | `test_judge` |
| Candidatos por marcador / sinais técnicos | Silêncio, tela preta, imagem parada, picos de energia (sempre rotulados) | `markers.py`, `technical.py`, `engine._suggest_free` | Não | OK-S | Nunca publica sozinho | `test_technical`, `test_markers` |
| Candidatos silenciosos | Até 2 por contexto, exploratórios | `silent_path.py` | Não | LAB | Bocejo/movimento global são descartados | `test_fusion_silent` |
| Episódios e contexto | Promessa→desfecho, retomadas, referência distante (até 15 min), memória de contexto com proveniência | `episodes.py`, `context_search.py`, `context_store.py`, `camada_contexto.py` | Não (regras de texto em PT) | PARCIAL | Participantes/tópicos não extraídos sozinhos; N11 percepção do gameplay ausente | `test_context`, `test_camada_contexto` |
| Dimensões do candidato | observação/interpretação/prontidão/valor/novidade/afinidade | `dimensions.py` | Não | PARCIAL | Mostradas, mas a ordem ainda usa o escore antigo | — |
| Duração e alternativas | 30/45/60 s só com frases completas; preparação/clímax/encerramento | `narrative.py`, `timeline.py`, `agents.py` | Não | OK-S | Corte manual de 1–90 s | `test_narrative`, `test_timeline` |
| Deduplicação | `fingerprint` + filtro SQL + comparação fina; imagem/transcrição/duração | `store.propose` | Não | OK-S | Conservadora | `test_engine` |
| Corte manual | Início/fim entre 1 e 90 s sobre o trecho já analisado | `app.py`, `store.py` | Não | OK-S | — | `test_acceptance` |
| Motivo de rejeição | 1 clique (9 motivos); taxa de aceitação por live | `store.REJECT_REASONS`, `/api/review` | Não | OK-S | **Não realimenta** o ranking ainda | `test_reject_reason` |
| Calibração e benchmark | Só afirma "calibrado" com ≥30 casos reservados; gabarito ≥20 momentos | `calibration.py`, `bench.py`, `evalkit.py` | Não | OK-S (estrutura) | Sem dados reais não há número | `test_bench`, `test_evalkit` |

## 6.3 Análise de conteúdo

| Funcionalidade | Onde | IA? | No modo Sem IA | Estado |
|---|---|---|---|---|
| Transcrição com palavras temporizadas | `engine.py` + faster-whisper 1.2.1 (modelos tiny→turbo; CUDA com fallback para CPU) | **Sim** | Desligada | OK-S (modelo falso); Whisper real/CUDA: NÃO-VAL |
| 2ª passagem de legenda (modelo `small`, padrão desde 0.17) | `engine.queue_refine/do_refine` | **Sim** | Desligada | OK-S |
| Energia de áudio, movimento | `signals.py` | Não | Funciona | OK-S |
| Sinais visuais do jogo (clarões, rajadas, cortes de cena) | `visual.py` | Não | Funciona | OK-S (heurística) |
| Movimento facial breve (blendshapes) | `behavior.py` (MediaPipe 0.10.21 Face Landmarker) | **Sim** | Desligado | NÃO-VAL; não classifica emoção |
| Localizar webcam sozinho | `camera_detect.py` (MediaPipe; recua para Haar do OpenCV) | **Sim**/clássico | Desligado | OK-S com rostos sintéticos |
| Chat como sinal auxiliar | `chat.py`, `clockmap.py` | Não | n/d | PARCIAL (Twitch; nunca decide sozinho) |
| Percepção de cena (fatos/hipóteses) | `perception.py`, `face_quality.py` | Não | Funciona | PARCIAL |
| Avaliador de ganchos Ollama | `ollama.py` | **Sim (LLM local)** | Desligado | Desligado por padrão; sem Ollama instalado nunca testado |
| Sugestões (gancho, títulos, limites, abertura) e "Por quê" | `agents.py`, `editorial.py` | Não | Funcionam | OK-S |

## 6.4 Edição

| Funcionalidade | Onde | IA? | Estado / limites |
|---|---|---|---|
| Estúdio (fala + prévia + inspetor + timeline) | `ui10/studio.js` → `static/index.html` | Não | OK-S (e2e 28 verificações). Nenhuma verificação com pessoas |
| Projeto de edição por cima do plano automático | `project.py`, `/api/project/get|save` | Não | OK-S; versão otimista (`version`) |
| Cortes (trim/split/remover) | `editing.cuts_for`, `studio.js` | Não | OK-S. Ripple como ação de primeira classe: PARCIAL (ver roadmap) |
| Zoom (curvas smooth/snap/pop/beat; avanço lento) | `motion.py`, `editing.punches_for` | Não | OK-S |
| Enquadramento (webcam em cima + jogo embaixo 640/1280 px; dividido; câmera no canto; só câmera; vídeo: ajustar/preencher) | `media.resolve_layout/live_filters`, `layout_policy.py` | Não | OK-S. Layout troca por clipe, não por trecho |
| Reenquadramento (por rosto/quem fala/rastreio) | `speaker.py`, `track.py`, `media.dynamic_reframe_plan` | Haar = clássico; rastreio Lucas-Kanade = clássico | PARCIAL; só vídeo (live é fixo) |
| Títulos (grande/faixa/topo), títulos por dados, abertura teaser | `captions.title_blocks`, `titledata.py`, `project.teaser` | Não | OK-S; desde 0.18.1 não cobre a webcam |
| Imagens/memes (PNG/JPG/WEBP), receitas de imagem, chave de cor | `assets.py`, `imagerecipe.py`, `keying.py` | Não | OK-S; receitas em lote só pela API |
| Velocidade 0,5×–4× (degraus), rampa, congelar, replay | `project.py`, `editing.Remap`, `plan.py` | Não | OK-S. Câmera lenta por duplicação de quadros; interpolada opcional. Replay automático só usa o que você marcou |
| Transições | `media.py` (fade de áudio nas emendas) | Não | **PARCIAL**: sem xfade de vídeo nem J/L cut |
| Presets/estilos (13) | `editing.EDITOR_PRESETS`, `LOOKS` | Não | OK-S. Estética não julgada por pessoas |
| Cor (histograma auto, LUT .cube, estilo) | `grade.py`, `editing.grade_filters` | Não | OK-S; só correção global |
| Estabilização | `media.py` (`deshake`, uma passada) | Não | PARCIAL (sem vidstab) |
| Capa/thumbnail | `cover.py` | Não | OK-S (quadro por medidas, modelos fixos) |
| Gráficos 2D animados | `graphics2d.py` | Não | PARCIAL (sem editor por item no Estúdio) |
| Marca por streamer (logo, abertura/encerramento, fonte, cores) | `brand.py` | Não | OK-S; fontes na pasta `fontes` |
| Edição por conversa | `converse.py` | Não (regex/regras) | OK-S; frase não entendida volta como pergunta |
| Formatos extras 1:1, 4:5, 16:9 | `multiformat.py`, `media._render_variants` | Não | OK-S |
| Variações A/B e série Parte 1/2 | `variants.py` | Não | OK-S |
| Desfazer/refazer (80 níveis, JSON completo por ação) | `studio.js` `mutate/snap` | Não | OK-S; custo em clipes longos [NÃO MEDIDO] |

## 6.5 Legendas

| Aspecto | Estado |
|---|---|
| Origem | Whisper (modo padrão) ou arquivo SRT/VTT/ASS (Sem IA) — `captions.py`, `subtitles.py` |
| Sincronização/confiança | Cada palavra tem literal/exibição/confiança/origem/nível de alinhamento; WER e erro de tempo contra amostra revisada — `caption_track.py` |
| Correção de texto | Edição no Estúdio; correções fixas por streamer `errado => certo` (valem para cortes existentes; não alteram o tempo) |
| Estilos | dynamic, clean, impact, pop, box, minimal; "Automática" segue o estilo; destaque contínuo sem piscar; ênfase na palavra do pico |
| Renderização | ASS via libass dentro do filtergraph; prévia ao vivo em HTML é **aproximada** (fonte/quebra podem diferir; comparação lado a lado nunca feita) |
| Margem inferior padrão | 340 px (era 260; 260 ficava na faixa que o TikTok cobre) |
| Medido | Legenda × voz: −20 ms (limite 150) em mídia sintética |

## 6.6 Áudio

Cadeia em `media.audio_chain`: passa-alta, redução de ruído (`afftdn` clássico por padrão; RNNoise `arnndn` se baixado), normalização `loudnorm` em 2 passos ou ganho linear quando o pico permite, `alimiter`, música com sidechain (redução sob a voz), SFX sintetizados pelo FFmpeg (`sfx.py`) e catálogo por função (`sfx_catalog.py`), batidas (`music.beat_times`). Música por link usa yt-dlp (NÃO-VAL) e exige confirmação de autorização. Alvo −16 LUFS / −1,5 dBTP são **propostas internas**, não regras de plataforma. Sem EQ/compressor/de-esser (P12 parcial). Medido em sintético: −16,0 LUFS, pico −4,9 dBTP.

## 6.7 Exportação

| Item | Estado |
|---|---|
| Saída padrão 1080×1920, H.264, AAC; 60 fps preservado se a fonte tiver ≥50 fps; Lanczos | OK-S |
| 4 modos de qualidade (Rápido/Equilibrado/Qualidade/Entrega) | OK-S; tabela em `NOVIDADES_0_19.md`; medidas: SSIM 0,854/0,964/0,975/0,981 |
| Encoders GPU (NVENC/QSV/AMF) com teste real e volta à CPU | **NÃO-VAL** (nenhuma GPU) |
| Progresso real, tempo restante (só após 5 s e 3%), cancelamento seguro | OK-S (`progress.py`) |
| Recuperação: render atômico, plano B `_render_legacy` sem módulos opcionais, registro no manifesto | OK-S |
| Pacote: `plano.json`, `revisao.json`, `pacote.json` (hashes), `linha_do_tempo.otio` (lida pela biblioteca OTIO; **não** testado em Premiere/Resolve/CapCut) | OK-S |
| Estados: em revisão → pronto p/ revisão → aprovado (por hash) → pronto p/ publicar | OK-S |
| QC pós-exportação (volume, pico, quadro preto, rosto cortado, quadro congelado, começo mudo, dessincronia, legenda fora da zona) com selo "revisar · N" | OK-S; limites (ex.: 2 s de congelamento) são **valores iniciais** |
| Pasta de entrega (cópia conferida por hash, nunca sobrescreve) | OK-S; "copiado" ≠ "enviado" |
| Publicação / agendamento em plataformas | **AUSENTE** (só pacote de texto) |

## 6.8 Interface

Telas: Cortes (biblioteca), Adicionar, Música, Ajustes (11 seções), Assinatura (quando o SaaS está ligado). Estúdio: ver 0.19 em `NOVIDADES_0_19.md`. Barra lateral com **Encerrar Hook's**. Atalhos: biblioteca (setas/J/K, X, A, R, Enter), Estúdio (←/→ 1 s, Shift 5 s, +/−, P, ?, Ctrl+S, `[`/`]`, R, Espaço, Delete, C, Esc, Ctrl+Z/Y com guarda de campo de texto, Ctrl+Enter duplo). Busca por comando (Ctrl+K): **não existe**. Onboarding guiado, acessibilidade por leitor de tela: **não verificados**. Fonte: `ui10/*.js`, `body.html`, `style.css` → `build.sh` → `liveclips/static/index.html`.

## 6.9 Persistência e operação

| Item | Onde |
|---|---|
| Dados em `C:\LiveClips` (Windows) ou `~/LiveClips` (Linux); instância única por pasta (lock) | `__main__.py` |
| SQLite: `streamers, sessions, segments, centers, candidates, events, settings` + memória editorial `memoria_editorial.sqlite3` | `store.py`, `memory.py` |
| Perfis por streamer (`perfil_v8.json` na pasta do streamer) com migração de chave | `store.py` |
| Backups automáticos/manuais verificados (reabre o ZIP e compara contagens); restauração valida e guarda cópia anterior; **sem gravações pesadas** | `recovery.py` |
| Cache por conteúdo (SHA-256) | `cache.py` |
| Telemetria local p50/p95; diagnóstico em ZIP sem vídeos/banco/perfis, tokens ocultados | `telemetry.py`, `support.py` |
| Atualização e rollback | `ATUALIZAR.bat` (`liveclips_anterior`) |

## SaaS (servidor `hooks_cloud`) e licença no app

Contas (scrypt, recuperação), planos editáveis, ciclo de vida, licença Ed25519 (72 h), uso (`analise_s`, `clipe`, `live`), cobrança Pix manual e Asaas (desligado), admin com TOTP e papéis, portal `/conta`, LGPD mecânica, e-mails em fila (só saem com SMTP). `SAAS_LOCAL.bat` liga tudo localmente. Testes: `test_cloud`, `test_cloud_migrations`, `test_licensing`, `test_saas_visivel`. **NÃO-VAL:** hospedagem, HTTPS, Asaas sandbox, SMTP, Windows real, textos legais (rascunho `DPA_RASCUNHO.md`).

## Recursos conhecidamente ausentes ou fracos (não prometer)

Reconhecer fala sem modelo; emoção/sarcasmo; remover fundo por significado; separar vozes; transições de vídeo (xfade), J/L cut; reenquadramento em live; desfoque rastreado de informação sensível; setas/anotações; estabilização de duas passadas; EQ/compressor de voz; publicação automática; busca de comandos; miniaturas na pista Vídeo; prévia por trecho.
