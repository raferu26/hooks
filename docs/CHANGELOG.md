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

## [Fala: atualizar o risco no lugar ao editar cortes] — 24/11/2026 (N5)
- **ANTES:** editar cortes refazia a lista de fala inteira (~270 palavras): mutate p50/p95 = 8,5/13 ms (100 cortes) e 15,4/19 ms (200 cortes) no clipe de 90 s.
- **ALTERAÇÃO** (`ui/studio.js`): se só os cortes mudaram (linhas, seleção, âncora, edição iguais), troca a classe `cutw` das palavras existentes sem recriar o DOM.
- **TESTE:** e2e `fala_nao_refaz_lista_ao_cortar`, `fala_atualiza_risco_no_lugar`, `fala_desfaz_risco_no_lugar` (+ os anteriores) e e2e completo sem falhas.
- **RESULTADO:** mutate p50/p95 **5,7/7,1 ms (100 cortes)**, **6,7/10,5 ms (200)**, 13,7/20,5 ms (500). Tabela em `docs/BASELINE.md` §3b.
- **Lacuna:** mudar a seleção de palavras ainda recria a lista; sem virtualização.

## [Ctrl+K: ordenação por relevância + medidor de eficiência] — 24/11/2026 (A04)
- **ANTES (`validacao/medir_ctrlk.py`, 31 ações):** menor nº de letras para a ação ser a 1ª da lista: média **2,2**; 28/31 em ≤3 letras; **"Abrir seção: Legendas" nunca era a primeira** (perdia para "Ligar/desligar legendas ao vivo").
- **ALTERAÇÃO** (`ui/studio.js`): ordem = nome começa com a busca → palavra começa com a busca → contém; empate pelo nome mais curto.
- **TESTE:** e2e `cmdk_*` (7) e e2e completo sem falhas.
- **RESULTADO:** média **1,6 letras**; **31/31** em ≤3 letras (Ctrl+K + 1–3 letras + Enter = 4–6 teclas); nenhuma ação inalcançável como 1ª.
- **Não medido:** descoberta pelo usuário (depende do botão ⌕ e do diálogo `?`); comparação de cliques com a navegação por mouse; pessoas.

## [Áudio clássico: limpeza de ruído híbrida e ducking mais firme] — 24/11/2026 (qualidade de áudio, sem IA)
- **ANTES (`validacao/medir_audio.py`, sinal sintético com referência limpa):** limpeza leve = passa-alta + `afftdn` (piso −48,2 dBFS em 24 s); ducking da música **3,9 dB** (limiar −24 dBFS ficava acima das falas baixas); consistência de volume com preset `off`: VOL σ 2,8 dB.
- **ALTERAÇÃO** (`liveclips/media.py`): `denoise_filter()` = `afftdn` + `afwtdn` adaptativo 70% (fallback só `afftdn` se o FFmpeg não tiver `afwtdn`); `sidechaincompress` thr .06/ratio 8/20·350 ms → **thr .03/ratio 10/15·400 ms**. Nenhum modelo, nenhuma dependência nova. RNNoise permanece como estava (plano de saída em `SEM_IA_MIGRACAO.md`).
- **TESTE:** `tests/test_audio_dsp.py` (4: ruído ≥4 dB melhor sem piorar a fala, fallback, queda do ducking ≥6 dB, pico ≤ −1 dBTP) + 59 testes relacionados OK (`test_pro_audio`, `test_voice_chain`, `test_ligacao_modulos`, `test_modos_qualidade`, `test_corpus_cortes`, `test_audio_dsp`; 2 ignorados por modelo RNNoise não baixado).
- **RESULTADO:** piso de ruído **−48,2 → −53,4 dBFS** em 24 s (híbrido removeu 6,0/6,0/9,1/9,7 dB a mais em 6/12/24/60 s), SDR da fala igual (±0,05), +0,04 s de processamento por 24 s de áudio; ducking **3,9 → 7,3 dB**; pico verdadeiro ≤ −1,5 dBTP. Detalhes e limites em `docs/AUDIO.md`.
- **Achado/decisão pendente:** preset de voz `natural` reduz VOL σ de 2,8 para 1,0 dB; hoje o padrão é `off`.
- **Não validado:** fala real, ruído não estacionário, Windows (versão do FFmpeg), percepção por pessoas.

## [Fidelidade prévia × exportação final — medição] — 24/11/2026
- **Medição** (corte de 28 s, vídeo sintético, modo Equilibrado, CPU): SSIM do final (1080×1920 reduzido a 540×960) contra o **rascunho novo** = **0,9759**; contra o **rascunho antigo** (mesmo trecho, filtros de 0.19) = **0,9757**. A otimização do rascunho **não** reduziu a fidelidade ao arquivo final (diferença 0,0002). Tempos: prévia 6,5 s; exportação 35,1 s.
- **Limites:** fonte sintética; legenda/título do final não aparecem no rascunho (a prévia usa legenda ao vivo em HTML — comparação lado a lado com libass segue pendente, V04); GPU não testada.

## [Validação do PR #1] — 24/11/2026
- **Suíte completa** na `feature/paleta-de-comandos` (commit `4230cc4`, Linux, Python 3.13, FFmpeg 6.1.1, OpenCV/yt-dlp/streamlink instalados): **1228 testes, 0 falhas, 0 erros, 4 ignorados** (2× RNNoise e 2× detector de rosto: modelos não baixados — componentes de ML do plano sem IA). Duração 41,6 min. Inclui `test_interface`, `test_design_tokens`, `test_http`, `test_audio_dsp`, `test_sem_ia_guard`, `test_deps` e `test_corpus_cortes`.
- **Revisão do diff vs `main`:** 22 arquivos (+1051/−24); código Python alterado só em `liveclips/media.py` (+13/−3: `denoise_filter()` e parâmetros do `sidechaincompress`); o resto é interface (`ui/*` + `index.html` regenerado, que **confere byte a byte** com as fontes), testes, medidores, resultados JSON e docs.
- **Arquivos sensíveis:** nenhum nome suspeito (token/segredo/credencial/.env/chaves/banco/vídeo/áudio/zip) e nenhum padrão de segredo (ghp_, github_pat_, AKIA, chave privada, sk-, Bearer) nas linhas adicionadas; sem `console.log`/`debugger`/TODO novos.
- **Regressões:** nenhuma encontrada. Riscos conhecidos que **não** são cobertos: Windows, GPU, vídeo/áudio reais; a limpeza de ruído híbrida e o ducking mais firme só foram medidos em áudio sintético.
## [Beta Windows: empacotamento verificado] — 24/11/2026 (branch `feature/windows-beta`)
- **ALTERAÇÃO:** `tools/empacotar_release.py` gera `Hooks-<versão>.zip` + `.sha256` **a partir do git** (árvore limpa), com `MANIFESTO.sha256`, e verifica: ZIP íntegro, hashes, `.bat` CRLF, `chcp 65001`, sem segredos/vídeos/banco/venv/tests/validação, arquivos exigidos. `INSTALAR.bat` **deixa de baixar o modelo facial** (regra "sem download silencioso de modelo"; o app já funciona sem ele). `docs/WINDOWS_BETA.md`: procedimento e roteiro de teste físico W01–W10.
- **TESTE:** `tests/test_release_pack.py` (4 OK); pacote real da 0.19.0 gerado com as 7 verificações OK.
- **NÃO validado:** execução em Windows (nada foi rodado lá); o ZIP ainda é da versão 0.19.0-beta.1 — a versão da próxima beta será definida ao integrar o PR #1.

## [Beta Windows: verificações estáticas e de rede] — 24/11/2026 (branch `feature/windows-beta`)
- **Medido:** wheels win_amd64/cp311 de todas as dependências resolvem (345 MB; ~74% da pilha vem de IA — argumento de tamanho/instalação para a remoção planejada); numpy fica em 1.26.4 no Windows (testes em Linux usaram 2.5.5).
- **Corrigido:** `music.py` chamava o FFmpeg sem `creationflags` (janela de console piscando no Windows).
- **TESTE:** `tests/test_windows_static.py` (5: console oculto em todas as chamadas, `fcntl` protegido, sem caminhos Unix, `.bat` CRLF/chcp, versões pinadas); `tests/test_sem_downloads.py` (4: rede confinada a módulos conhecidos, instaladores sem modelos, nenhum fetch na partida); `test_noai_mode` + teste de **nenhuma conexão externa** no modo sem IA (7 OK).
- **Não validado:** execução no Windows, CPU/GPU, Python 3.11 + numpy 1.26.4, antivírus.
