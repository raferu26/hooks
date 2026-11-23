# KNOWN_ISSUES — problemas reproduzidos ou confirmados na 0.19.0-beta.1
Só entram itens **verificados nesta migração**. Pendências de validação física estão em `BASELINE.md §5`. Gravidade: A alta · M média · B baixa.

| ID | Grav. | Problema | Reprodução | Arquivos | Causa (hipótese marcada) | Estado | Teste |
|---|---|---|---|---|---|---|---|
| KI-01 | M | Área do vídeo no Estúdio é 15,6–17,2% da tela (P02); limitada pela altura; mitigado com a tecla F (+46%) | `ui/fresh.sh 8790 && PORT=8790 python3 ui/e2e10.py` → `video_pct_tela` | `ui/style.css` (`.smain`), `studio.js` | Grid com 3 colunas de largura fixa | Mitigado | e2e (`foco_*`) |
| KI-02 | M | Prévia = render do clipe inteiro (11 s → **5–6 s** para 14,5 s após otimização do rascunho); ainda sem camadas | e2e `segundos_ate_previa_nova` | `engine.py`, `media.py`, `store.py` | Sem prévia em camadas | Aberto (E8) | e2e |
| KI-03 | M | Redesenho completo da timeline e snapshot JSON a cada ação; custo ~linear: p95 24 ms com 500 itens | `validacao/bench_ui.py 500` | `ui/studio.js` `mutate/drawTimeline` | Reconstrução total | Aberto | `bench_ui.py` |
| KI-04 | B | `medir_modos.py` grava `src.mp4`, `rapido.mp4`… no diretório atual | rodar na raiz do repo | `validacao/medir_modos.py` | Caminhos relativos ao cwd | Em correção | — |
| KI-05 | B | `requirements.txt` não cobre o ambiente de testes (cv2/yt_dlp/otio/playwright) e não fixa numpy | suíte limpa → 36 falhas/erros | `requirements*.txt` | Dependências de teste não listadas | Mitigado: `requirements-dev.txt` | `BASELINE §1` |
| KI-06 | B | Docstring de `liveclips/__init__.py` diz 0.13; imports sem uso (`json` em `capture.py`/`__main__.py`; `remap_for`, `auto_replays` em `app.py`) | `python -m pyflakes liveclips` | os citados | Resíduo de versões | Aberto | pyflakes |
| KI-07 | B | Seed longo (`HOOKS_SEED_LONG=1`) rende só 1 candidato de 25 s (deduplicação), então 90 s/V09 não é medido | `bash ui/fresh.sh` com a variável | `ui/seed.py` | Candidatos sobrepostos são fundidos [hipótese] | Aberto | — |
| KI-08 | M | Dependências de ML (Whisper, MediaPipe, RNNoise, Ollama) ativas por padrão e baixam modelos de rede externa | `docs/SEM_IA_MIGRACAO.md` | `engine.py`, `behavior.py`, `denoise.py` | Origem "agente"; decisão A01 tomada, transição pendente | Plano aprovado em `SEM_IA_MIGRACAO.md` (fase 0 feita) | `test_noai_mode`, `test_sem_ia_guard` |
| KI-09 | M | Nada validado em Windows/GPU/live/YouTube/pessoas | `BASELINE §5` | — | Ambiente | Aberto | — |
