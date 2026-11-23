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
- **RESULTADO (Linux, sintético, sem teimar a timeline):** 1280×720 **233×414 → 280×497 (+44% de área)**; 1366×768 → 307×545 (+20%); 1440×900 → 381×677 (+16%); 1920×1080 → 482×857 (+12%). Razão 0,5625 em todos; sem rolagem horizontal. Arrastando o divisor 40 px, o vídeo cresce mais (medido no e2e).
- **Limite honesto:** em telas altas o ganho é pequeno porque o vídeo vertical já usa ~83% da altura útil; mais espaço exige reduzir timeline/barra (o divisor permite).
- **Não validado:** telas reais, escalas de DPI do Windows, pessoas.
