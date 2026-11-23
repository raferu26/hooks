# Arquitetura do Hook's 0.19.0-beta.1

Legenda: **[V]** verificado no código nesta migração · **[H]** herdado dos documentos recebidos (`docs/handoff/`), não reverificado.

## Visão geral
```
Janela Edge/Chrome (modo app) ── HTTP 127.0.0.1 + token ──► app.py (ThreadingHTTPServer)
                                                              ├─ store.py   SQLite + perfis JSON
                                                              ├─ engine.py  pistas de trabalho (threads)
                                                              │    ├─ capture.py (streamlink → .ts)
                                                              │    ├─ análise: signals/technical/visual (+Whisper/MediaPipe se ai_mode=padrao)
                                                              │    └─ ranking → judge → agents → plan_edits → store.propose
                                                              └─ media.py   FFmpeg (filtergraph único) → qc/qc_visual → export_pack → delivery
App ··· licença assinada/uso ··· hooks_cloud (conta, plano, cobrança)  [só servidor SaaS; nunca vídeo]
```
- **[V]** Servidor `ThreadingHTTPServer` ligado a `127.0.0.1`; exige cabeçalho `X-LiveClips-Token` ou cookie `lc_session` (HttpOnly, SameSite=Strict); valida `Host` e `Origin` (barra DNS rebinding) — `app.py` ~960–1071.
- **[V]** `Engine.LANES=('analise','edicao','exportacao','exportacao2','refino')`; cada pista é uma thread daemon `LiveClips-<nome>` (`engine.py` 73, 163–170), além da principal. `lanes=unico` usa só a principal [H].
- **[V]** ~97 rotas: 84 em `app.py`, 13 em `studio_api.py`.
- **[H]** Estado do painel com `X-State-Tag`; UI consulta a cada 2,5 s quando visível.

## Componentes
| Camada | Arquivos | Papel |
|---|---|---|
| Entrada | `__main__.py` (lock por pasta `liveclips_v8.lock`), `desktop.py` | Sobe servidor, janela de app, instância única |
| API | `app.py`, `studio_api.py` | Rotas JSON, segurança local |
| Persistência | `store.py`, `memory.py`, `atomic.py`, `recovery.py`, `cache.py` | SQLite (`streamers, sessions, segments, centers, candidates, events, settings`), perfis `perfil_v8.json`, memória editorial, escrita atômica, backup verificado, cache SHA-256 |
| Análise | `signals.py`, `technical.py`, `visual.py`, `markers.py`, `subtitles.py`, `syncaudio.py`; opcionais `engine.py`(Whisper), `behavior.py`, `camera_detect.py` | Sinais e candidatos |
| Seleção | `ranking.py`, `judge.py`, `agents.py`, `narrative.py`, `episodes.py`, `fusion.py` | Pontuação heurística explicável |
| Edição | `project.py` (projeto do usuário), `plan.py` (plano versionado), `editing.py` (`timing_for`, `cuts_for`, `punches_for`), `motion.py`, `captions.py` | Modelo de edição |
| Render | `media.py` (1485 linhas), `hardware.py`, `telemetry.py` (modos), `sfx*.py`, `music.py`, `grade.py`, `cover.py` | FFmpeg |
| Qualidade/entrega | `qc.py`, `qc_visual.py`, `export_pack.py`, `delivery.py`, `publish.py` | QC, pacote com hashes e OTIO, pasta de entrega |
| UI | `ui/*` → `liveclips/static/index.html` | Interface única |
| SaaS | `hooks_cloud/`, `licensing.py` | Licença Ed25519 (72 h) |

## Fluxo de ponta a ponta [H, trechos [V] abaixo]
1. Abrir → `App`+`server` → `GET /` devolve `index.html` com `__BOOT_TOKEN__` → `refresh()` chama `/api/state`.
2. Importar (`/api/video/import|url`, `/api/upload`, `/api/capture/start`) → `store.new_session`, segmentos.
3. Analisar → `engine.analyze_one` ou `_analyze_free` (sem IA) → `suggest_one` → `ranking.rank` → `judge.curate` → `plan_edits` → `store.propose`.
4. Editar no Estúdio: `ST.proj` alterado por `mutate()` (desfazer 80 níveis, JSON completo por ação).
5. Salvar: `/api/project/save` → `store.save_project(learn=…)`. **[V]** Ctrl+S chama `saveNow()` (não renderiza); autosave com `learn=False`.
6. Prévia: pista `edicao` → `media.render(preview=True)` 540×960 libx264 ultrafast; grava `preview_timing`. Disparo: botão/tecla **P** (`refreshPreview`) ou "auto-prévia" **[V]** `studio.js` 388–391.
7. Aprovar/exportar: `/api/review` (aceita `quality_mode`) → pista `exportacao` → `media.render` → `_render_single` → `_render_variants` → QC → pacote → pasta de entrega.

## Estados de salvar e prévia [V parcial]
`candidates.version` (versão do projeto) × `preview_version` × `preview_status`. Salvar sobe `version`, mantém a prévia antiga como "stale" tocável com `preview_timing`; nova prévia vai à fila. `preview_info`: `ready` / `stale` / `available`.

## Pipeline de vídeo
`media.render` → `plan_pieces` → `build_source` (concat) → `audio_chain` → legenda ASS (libass) → `_video_codec(profile,draft,meta)` → **um** comando FFmpeg; falha → `_render_legacy` (método V7) e motivo no manifesto. Layout vertical: webcam 640 px + jogo 1280 px, Lanczos, 60 fps se fonte ≥50 fps. Encoders: `hardware.choose` testa NVENC/QSV/AMF com encode real e recua ao x264; `telemetry.MODES` define CPU, `hardware.GPU_MODES` define GPU [V]. Render atômico em pasta `render_*`, limpeza ao abrir.

## Erros e cancelamento [H]
Retentativas de análise 30 s/2 min/5 min; `LowSpace` pausa a pista; falha de análise não derruba o cadastro de pedaços; cancelamento seguro com progresso (`progress.py`). Rede de segurança 400 para entradas inválidas.

## Limites conhecidos
Ver `docs/KNOWN_ISSUES.md`. Nada foi validado em Windows, GPU, live real, YouTube real ou com pessoas.
