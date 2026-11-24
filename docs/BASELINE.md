# BASELINE — Hook's 0.19.0-beta.1 (medido na migração, 23/11/2026)

**Ambiente:** Linux (kernel 6.18), 4 vCPU, 16 GB RAM, **sem GPU**, Python 3.13, FFmpeg 6.1.1, Chrome headless. Mídia **sintética**. Nada aqui vale para Windows, i7-3770, GPU real, live real, YouTube real ou pessoas. Marco git: `baseline-0.19.0-beta.1` (código idêntico ao ZIP recebido, sha256 `e5ed57bc…`).

## 1. Suíte de testes
| Rodada | Resultado | Duração |
|---|---|---|
| 1ª (ambiente sem `cv2`, `yt_dlp`, `opentimelineio`) | 1148 executados: **12 falhas, 24 erros, 8 ignorados** (4 módulos nem carregaram: `test_corpus_cortes`, `test_entradas_extremas`, `test_ligacao_modulos`, `test_protecao_dados`) | 28,6 min |
| 2ª: os 13 módulos afetados, com `opencv-contrib 4.10.0.84`, `yt-dlp`, `streamlink 8.6.3` | **182 testes, 0 falhas** | 26,5 min |
| 3ª: `test_export_pack`, `test_videodl`, `test_pro_audio`, `test_speaker` com `opentimelineio` | 38 testes OK, **4 ignorados** | 44 s |
| Anteriores | 24 testes-chave (salvar/prévia, modos, sem IA) OK em 56 s; pyflakes sem nome indefinido | — |

**Classificação (nada foi mudado no código para obter o verde):**
- **Falha de ambiente (36):** 17× `No module named 'cv2'`, 7× `yt_dlp`; as 12 falhas de asserção foram **classificadas** (reexecução sem `cv2`): `test_grade` (gamma não aplicado), 5 de capa (`test_imagerecipe`, `test_modules_combined`, `test_multiformat`×2, `test_exemplo_completo`) e 6× `test_track` — todas por **`cv2` ausente**: `cover.py`, `grade.py` e `track.py` importam `cv2`; sem ele o app **degrada em silêncio** (sem capa, sem correção de gamma, sem rastreio) em vez de avisar → ver KI-10. → `requirements-dev.txt` criado.
- **Falha real de código:** nenhuma encontrada.
- **Não puderam ser executados (4):** 2× RNNoise e 2× detector de rosto exigem baixar arquivo de modelo (`modelo não baixado`, `detector de rosto não baixado`). São justamente componentes de ML da decisão A01.
- **Não computo um total único** (1212 do dossiê): a soma das rodadas não foi deduplicada módulo a módulo; cada módulo passou ao menos uma vez com as dependências corretas.
- **Ressalva:** a rodada com dependências usou o `numpy 2.5.5` instalado junto do OpenCV; o `requirements.txt` não fixa numpy.

## 2. E2E do Estúdio (`ui/e2e10.py`, 1440×900)
Todas as verificações passaram, sem erro de console. Medidas: abrir Estúdio **110–130 ms**; resposta ao zoom **67 ms**; prévia nova pronta em **11 s** (clipe de 14,5 s); barra superior 47,8 px (1 linha em 1440/1280/1024); 3 pistas por padrão; sem abas; "Sugestões" no lugar de "Agente".
**Nota:** o e2e mediu 15,6% (337 px de largura, com a faixa de prévia anterior visível); em repouso medi 354×629 = 17,2% (confere com o documento). A 1280×720 o vídeo é 233×414 (10,5%); a 1920×1080, 455×809 (17,8%).

## 3. Benchmark da timeline/undo (`validacao/bench_ui.py`; N cortes sintéticos, 30 `mutate()`, 10 desfazer)
| Cortes | mutate p50 / p95 / máx (ms) | undo p50 / p95 (ms) | snapshot | DOM |
|---|---|---|---|---|
| 50 | 4,3 / 5,2 / 5,4 | 4,3 / 5,0 | 5,9 KB | 1405 |
| 200 | 7,7 / 11,3 / 14,0 | 6,6 / 8,1 | 15,6 KB | 1854 |
| 500 | 14,1 / 24,0 / 25,1 | 15,1 / 27,1 | 35 KB | 2754 |
(Clipe de 14,5 s; heap JS 4–12 MB.) Meta do roadmap (<16 ms/quadro com 200 blocos): **atendida em p95 (11,3)**, **não** com 500 (p95 24). Custo cresce ~linearmente com o número de itens (redesenho completo a cada ação).
**V09 (clipe de 90 s) — medido em 24/11** (corte manual de 90 s, 46 linhas de fala ~270 palavras, `HOOKS_SEED_LONG=1`; ver §3b).

## 4. Modos de exportação (`validacao/medir_modos.py`, 4 s 1080×1920 sintético com ruído, CPU)
| Modo | Tempo | kbps | SSIM | PSNR (dB) |
|---|---|---|---|---|
| Rápido | 5,7 s | 86 406 | 0,853 | 33,8 |
| Equilibrado | 21,8 s | 163 980 | 0,951 | 38,2 |
| Qualidade | 62,9 s | 210 365 | 0,975 | 40,8 |
| Entrega | 100,4 s | 228 943 | 0,981 | 42,0 |
Confirma que os 4 modos **mudam o comando** (preset/CRF/aq-mode distintos). Diferenças vs. documento recebido (Equilibrado 0,964 / 9,2 s): máquina diferente; fonte sintética extrema, **não representa vídeo real**. Bitrates absurdos são do ruído sintético.

## 5. Pendências de validação física (lista permanente)
Windows 10/11 (atalho, janela, `.bat`, encerramento) · NVENC/QSV/AMF · i7-3770 com 2–4 lives · vídeo real (tempos/qualidade) · YouTube real · OTIO em Premiere/Resolve/CapCut · legenda HTML × libass lado a lado · pessoas (iniciante/casual/experiente/máquina fraca) · clipe de 90 s (V09) · consumo de RAM/CPU em sessão longa · estabilidade prolongada.


## 3b. Clipe de 90 s com muitas palavras (V09, após as otimizações de 24/11; ms, p50 / p95)
| Cortes | mutate (editar cortes) | desfazer | edição sem tocar a fala (zoom): sem memo → com memo | snapshot | DOM | arrasto p95 |
|---|---|---|---|---|---|---|
| 100 | 8.45 / 13 | 8.55 / 11.2 | 10.4 / 18.5 → **4.1 / 6.8** | 18.9 KB | 1939 | 0.2 |
| 200 | 15.4 / 19 | 12.5 / 24.5 | 12.7 / 17.9 → **4.8 / 8.9** | 25.1 KB | 2247 | 0.6 |
| 500 | 14.6 / 21.8 | 15.95 / 30.4 | 16.1 / 24.7 → **11 / 17.4** | 44.0 KB | 3147 | 0.7 |
Antes da memorização, o perfil de `mutate` com 100 cortes mostrou `drawLeft` (lista de fala) = **6,2 ms de 11 ms**; o snapshot JSON de desfazer **não** é gargalo (0,08 ms). Meta de 16 ms por ação: atendida no p95 para edições que não alteram a fala (até ~200 cortes); editar cortes (que riscam palavras) ainda redesenha a fala.
