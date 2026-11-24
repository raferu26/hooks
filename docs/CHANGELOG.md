# CHANGELOG (a partir da migração para o Claude Code)
Histórico anterior à migração é **herdado e não reverificado**: ver `docs/handoff/HOOKS_HISTORY_AND_DECISIONS.md`. Aqui só entra o que foi feito e verificado neste repositório.

## [Linha de base] — 23/11/2026
- **Ponto de recuperação:** commit `dc8e371` / tag `baseline-0.19.0-beta.1` = ZIP recebido sem alterações. ZIPs originais com SHA-256 em `../_recovery/`.
- **Adicionado:** `ui/` (fontes da UI, build reproduzível byte a byte, scripts sem caminhos absolutos); `CLAUDE.md`; `docs/*`; `validacao/bench_ui.py`; `requirements-dev.txt`; variante `HOOKS_SEED_LONG` no `ui/seed.py`.
- **Alterado:** `ui/build.sh`, `run.py`, `seed.py`, `fresh.sh` para caminhos relativos.
- **Medido:** suíte, e2e, timeline, modos (ver `docs/BASELINE.md`). **Nenhum código do produto foi alterado.**
- **Decisão A01 (Rafael, 23/11):** Hook's definitivamente sem IA; transição planejada, sem remoção antes de documentar perdas, testes e aprovação (`docs/SEM_IA_MIGRACAO.md`).

## [Foco no vídeo] — 23/11/2026 (P02/KI-01)
- **ANTES:** vídeo limitado pela *altura* (não pela largura): 354×629 px (17,2%) a 1440×900 e 233×414 (10,5%) a 1280×720; alargar colunas não ampliaria a prévia. Linha do tempo fixa ocupa 167 px.
- **PROBLEMA:** sem como dar mais espaço à prévia em telas pequenas.
- **ALTERAÇÃO:** botão "Ampliar prévia" / tecla **F** recolhe a linha do tempo; preferência lembrada (`hk-foldtl`); ignorada ao digitar. Arquivos: `ui/body.html`, `ui/style.css`, `ui/studio.js`, `ui/e2e10.py`; `index.html` regenerado.
- **TESTE:** e2e `foco_*` (6 verificações) + `test_interface`, `test_http` (22 OK); e2e completo sem falhas.
- **RESULTADO (1440×900, Linux, sintético):** área da prévia **+46%** com a linha do tempo recolhida. Sem recolher, nada muda.
- **Não validado:** pessoas; telas reais; o estado recolhido não permite editar na timeline (só reproduzir/inspetor).

## [Snap magnético na timeline] — 23/11/2026 (A03/E3)
- **ANTES:** arrastar itens só quantizava a 0,05 s; alinhar a outro item exigia acertar no olho (itens "quase colados" deixavam vazios/sobreposições).
- **ALTERAÇÃO:** ao mover/redimensionar zoom, título, corte, velocidade, imagem, SFX e congelar, o valor alinha ao alvo mais próximo (cursor, bordas de outros itens, início/fim) dentro de **8 px**; **Alt** desliga. `snapTargets`/`snapTo` em `ui/studio.js`; atalho listado no diálogo `?`.
- **TESTE:** e2e `snap_alinha_na_borda` (3 px da borda → exatamente 4,00 s) e `alt_desliga_snap` (→ 4,05 s); e2e completo sem falhas nem erros de console.
- **Não validado:** sensação de uso com pessoas; sem guia visual da linha de alinhamento (pendente); trim/split por snap em palavras não implementado.

## [Decisão sem IA — plano e guarda] — 23/11/2026
- **Documento:** `docs/SEM_IA_MIGRACAO.md` (D1–D7: função, arquivos, recursos, alternativa, limites, impacto, custo, complexidade, testes; classes A/B/C; comparação de experiência; 5 fases). Achado: Haar (OpenCV) também é classificador pré-treinado (`media.py` ~392, `speaker.py` ~112, `camera_detect.py`), então entra na lista de saída pela regra "sem modelos pré-treinados".
- **Teste:** `tests/test_sem_ia_guard.py` (2 OK) trava o conjunto atual de arquivos com ML; `test_noai_mode` continua OK.
- **Nenhuma funcionalidade removida.**

## [Layout adaptativo da prévia] — 23/11/2026 (P02/KI-01)
- **ANTES (0.19, fresh, 3 pistas):** vídeo 233×414 (10,5%) a 1280×720; 280×497 (13,3%) a 1366×768; 354×629 (17,2%) a 1440×900; 455×809 (17,8%) a 1920×1080. Causa: vídeo limitado pela altura; controles abaixo do vídeo; largura sobrando.
- **ALTERAÇÃO:** (1) com largura ≥520 px no palco (*container query*), controles de reprodução e chaves vão para o **lado** do vídeo, que usa a altura toda; (2) **divisor arrastável** entre o palco e a linha do tempo (mouse, setas ↑↓, duplo clique restaura; altura lembrada em `hk-tlh`); (3) pista Áudio 44→36 px. Proporção 9:16 preservada por `aspect-ratio` + `object-fit:contain`. Arquivos: `ui/body.html`, `ui/style.css`, `ui/studio.js`.
- **TESTE:** `validacao/medir_layout.py` (antes/depois em `validacao/layout_*.json`); e2e `divisor_*` (6) + e2e completo sem falhas; `test_interface`, `test_http` OK.
- **RESULTADO (Linux, sintético, com a timeline visível):** 1280×720 **233×414 → 280×497 (+44% de área)**; 1366×768 → 307×545 (+20%); 1440×900 → 381×677 (+16%); 1920×1080 → 482×857 (+12%). Razão 0,5625 em todos; sem rolagem horizontal. Arrastando o divisor 40 px, o vídeo cresce mais (medido no e2e).
- **Limite honesto:** em telas altas o ganho é pequeno porque o vídeo vertical já usa ~83% da altura útil; mais espaço exige reduzir timeline/barra (o divisor permite).
- **Não validado:** telas reais, escalas de DPI do Windows, pessoas.

## [Prévia mais rápida: rascunho com filtros baratos] — 23/11/2026 (P03)
- **ANTES:** prévia de 28 s de vídeo = **15,8 s** de `_do_render` (perfil: 15,55 s só no FFmpeg). e2e: **11 s** até a prévia nova (clipe 14,5 s). O grafo de filtros rodava a 1080×1920 (blur gaussiano σ=28 e Lanczos em tela cheia, `filter_complex_threads 1`) e só no fim reduzia para 540×960.
- **DIAGNÓSTICO (medido com `ffmpeg` isolando filtros):** blur do fundo em tela cheia + Lanczos eram o gargalo (variantes: atual 15,7 s · blur barato 11,9 s · bilinear 14,6 s · ambos **6,4 s**).
- **ALTERAÇÃO** (`liveclips/media.py`, só no rascunho; **exportação inalterada**): fundo desfocado calculado a 1/4 do tamanho (σ=7) e ampliado; `lanczos`→`bilinear` nas escalas do rascunho. Mesmo canvas 1080×1920, sem mexer em coordenadas de títulos/legendas/overlays.
- **TESTE:** 126 testes relacionados OK (`test_corpus_cortes`, `test_engine`, `test_modos_qualidade`, `test_studio_api`, `test_studio_extras`, `test_ligacao_modulos`, `test_blur`); e2e completo sem falhas (3 execuções).
- **RESULTADO:** `_do_render` 28 s de vídeo **15,8 → 6,6 s (−58%)**; e2e "prévia nova pronta" **11 s → 5–6 s** (resolução de 1 s). Fidelidade: novo rascunho × antigo SSIM **0,991**, PSNR **43,5 dB** (fonte sintética).
- **Não validado:** layouts ao vivo (webcam+jogo) só ganham o `bilinear` (blur não se aplica); vídeo real; CPU com 2+ pistas disputando núcleos (i7-3770).
- **Próximo:** prévia imediata sobreposta (L1) e render parcial só se a medição mostrar necessidade; latência restante = debounce do autosave (1,6 s) + fila + render.

## [Aviso de dependência ausente] — 24/11/2026 (KI-10)
- **ANTES:** sem `cv2`/`yt_dlp` o app seguia sem capa, sem gamma e sem rastreio **sem avisar** (36 testes revelaram).
- **ALTERAÇÃO:** `liveclips/deps.py` (cv2, numpy, yt_dlp obrigatórios; opentimelineio opcional) → `App.state()['dependencies']`, banner vermelho "Recurso indisponível" com o que para de funcionar e como corrigir, e item `dependencias` na pré-checagem (aviso se obrigatório, ok/informativo se opcional).
- **TESTE:** `tests/test_deps.py` (6) + `test_interface`, `test_http`, `test_sem_ia_guard` (30 OK); verificado no navegador sem OpenCV: banners de opencv e yt-dlp aparecem.
- **Não coberto:** mensagem dentro do corte quando a capa é pulada (hoje só o evento já existente + banner).

## [Design system base: escala tipográfica e alvos de clique] — 24/11/2026 (P06)
- **ANTES (`validacao/medir_design.py`, Estúdio 1440×900):** 6 tamanhos de fonte (11,5 / 12 / 12,5 / 13,5 / 14 / 15 px); **17** textos < 12 px (tempos da fala em 11,5 px, rótulos); **18** alvos de clique < 28 px (desfazer/refazer 32×27, zoom 35×27, "?" 28×27, estado 93×22…); contraste AA: 0 falhas.
- **ALTERAÇÃO** (`ui/style.css`): tokens `--fs-xs/sm/md/lg` (12/13/14/16 px) + `--tap:28px`; 54 tamanhos soltos trocados pelos tokens (títulos 18–28 px mantidos); `button.small` com mínimo 28×28; `#stState` 28 px.
- **TESTE:** `tests/test_design_tokens.py` (4) + `test_interface`; e2e completo sem falhas; layout inalterado (±1 px).
- **RESULTADO:** tamanhos de fonte **6 → 4**; textos < 12 px **17 → 0**; alvos < 28 px **18 → 0**; contraste AA segue 0 falhas (medição exclui blocos da timeline e o vídeo).
- **Não feito/validado:** contraste dos blocos da timeline; espaçamento em grade de 4 px; áreas de 40 px para toque; revisão visual por pessoas.

## [Etapas do corte: Importar → Editar → Conferir → Exportar] — 24/11/2026 (P07)
- **ANTES:** a barra do Estúdio só mostrava "1 de N"; nenhuma indicação de em que ponto do fluxo o usuário estava nem do que fazer em seguida.
- **ALTERAÇÃO** (`ui/studio.js`, `body.html`, `style.css`): indicador de 4 etapas **derivado do estado real**: *Exportar/Exportando…/Exportado* quando o corte foi aprovado; *Editar* com alterações não salvas, salvando ou prévia desatualizada; *Conferir* com tudo salvo e prévia atual. Dicas ao passar o mouse; `aria-current="step"`; oculto abaixo de 1180 px (como "1 de N").
- **TESTE:** e2e `etapa_editar_ao_alterar` e `etapa_conferir_com_previa_pronta`; e2e completo sem falhas; barra continua em 1 linha (47,8 px) a 1440/1280/1024; `test_interface`, `test_design_tokens`, `test_http` OK.
- **Não feito:** as etapas são informativas (não clicáveis); o fluxo "Importar" fora do Estúdio (tela Adicionar) não foi redesenhado; sem teste com pessoas.

## [Arrasto sem redesenho total] — 24/11/2026 (N5/KI-03, A03)
- **ANTES (`validacao/bench_ui.py`, 60 `pointermove` sobre um zoom):** **60 redesenhos** da timeline; manipulador p50/p95 = **4,2/8,2 ms** (200 cortes) e **10/18,2 ms** (500 cortes). Perfil de `mutate()` (500 cortes): `drawTimeline` 11,4 ms de 16,1 ms; `snap` (JSON) 0,09 ms — o snapshot de desfazer **não** é o gargalo.
- **ALTERAÇÃO** (`ui/studio.js`): `dragPaint` move só o bloco arrastado (`left/width`) durante o arrasto; redesenho completo apenas ao soltar. SFX/congelar mantêm o caminho antigo.
- **TESTE:** e2e `snap_*` (resultado final idêntico: 3,29 s/3,3 s) + e2e completo sem falhas.
- **RESULTADO:** redesenhos durante o arrasto **60 → 0**; p50/p95 **0,1/0,5 ms** (200) e **0,2/0,8 ms** (500) — de ~18 ms p95 para <1 ms (meta de 16 ms por quadro atendida também com 500 itens). Resultados em `validacao/bench_ui_depois_n5.json`.
- **Não feito:** `mutate()` discreto ainda redesenha tudo (8 ms/200 e 16 ms/500, `drawLeft` 2–3 ms evitável); clipe de 90 s (V09) continua sem medição.

## [Busca de ações — Ctrl+K] — 24/11/2026 (A04/E6)
- **ANTES:** muitas ações só por atalho (que é preciso conhecer) ou escondidas em seções do inspetor; sem busca.
- **ALTERAÇÃO** (`ui/studio.js`, `body.html`, `style.css`): **Ctrl+K** (ou botão ⌕ na barra) abre uma busca no Estúdio com ~30 ações: cortar/zoom/título no trecho, desfazer/refazer, salvar, prévia, reproduzir, navegar entre cortes, recolher a timeline, zonas seguras, abrir qualquer seção do inspetor, atalhos, voltar. Lista **só o que vale agora** (ex.: "Cortar" some sem seleção); ignora acentos e maiúsculas; ↑↓ Enter Esc; mostra o atalho de cada ação. "Exportar" não executa direto: leva o foco ao botão para manter a confirmação (N6).
- **TESTE:** e2e `cmdk_*` (6 verificações) + e2e completo sem falhas/erros de console; `test_interface`, `test_design_tokens`, `test_http` OK.
- **Não feito:** ações do fluxo de legendas/estilos por nome; histórico de ações recentes; teste com pessoas (a descoberta do Ctrl+K depende do botão ⌕ e do diálogo `?`).

## [Guia visual do snap] — 24/11/2026 (A03)
- **ANTES:** o alinhamento magnético funcionava mas era invisível: o usuário não sabia a que o item grudou.
- **ALTERAÇÃO** (`ui/studio.js`, `style.css`): linha vertical ciana no instante do alvo enquanto o item está alinhado (some ao soltar ou com Alt). Move/redimensiona rastreia qual borda (início ou fim) alinhou.
- **TESTE:** e2e `guia_aparece_ao_alinhar` (guia em 4,00 s ±0,05) e `guia_some_ao_soltar`; snap e Alt continuam OK; benchmark de arrasto mantido (<1 ms p95 com 200 itens).

## [Lista de fala sem redesenho desnecessário + medição de 90 s] — 24/11/2026 (N5/V09)
- **ANTES (clipe de 90 s, 100 cortes):** `mutate` ≈ 11 ms; **`drawLeft` 6,2 ms** (lista de ~270 palavras refeita a cada ação; `allCuts()` recalculado por palavra); `drawTimeline` 3,6 ms; snapshot 0,08 ms.
- **ALTERAÇÃO** (`ui/studio.js`): cortes calculados 1× por desenho; **memorização** da lista de fala (chave = linhas, cortes, seleção, âncora, edição); se nada que a fala mostra mudou (zoom, título, velocidade…), o DOM não é refeito.
- **TESTE:** e2e `fala_risca_palavras_cortadas` e `fala_desfazer_limpa_risco` (a memória não fica velha); e2e completo sem falhas; `test_interface`, `test_design_tokens`, `test_http` OK; `bench_ui.py` mede `mutate_zoom` com/sem memo.
- **RESULTADO:** ver `docs/BASELINE.md` §3b (valores medidos; edição de zoom com 100 cortes: p50/p95 8,1/13,2 → 4,2/8,1 ms na medição de perfil).
- **Lacunas:** editar cortes/seleção ainda refaz a fala; sem virtualização; Linux/sintético, sem máquina fraca.
- **Nota de processo:** o commit anterior desta etapa (`5d2af4a`) subiu sem a atualização de docs e com os JSON de benchmark vazios por falha de um servidor de teste; corrigido neste commit seguinte (sem reescrever histórico).
