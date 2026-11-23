# CHANGELOG (a partir da migração para o Claude Code)
Histórico anterior à migração é **herdado e não reverificado**: ver `docs/handoff/HOOKS_HISTORY_AND_DECISIONS.md`. Aqui só entra o que foi feito e verificado neste repositório.

## [Linha de base] — 23/11/2026
- **Ponto de recuperação:** commit `dc8e371` / tag `baseline-0.19.0-beta.1` = ZIP recebido sem alterações. ZIPs originais com SHA-256 em `../_recovery/`.
- **Adicionado:** `ui/` (fontes da UI, build reproduzível byte a byte, scripts sem caminhos absolutos); `CLAUDE.md`; `docs/*`; `validacao/bench_ui.py`; `requirements-dev.txt`; variante `HOOKS_SEED_LONG` no `ui/seed.py`.
- **Alterado:** `ui/build.sh`, `run.py`, `seed.py`, `fresh.sh` para caminhos relativos.
- **Medido:** suíte, e2e, timeline, modos (ver `docs/BASELINE.md`). **Nenhum código do produto foi alterado.**
- **Decisão A01 (Rafael, 23/11):** Hook's definitivamente sem IA; transição planejada, sem remoção antes de documentar perdas, testes e aprovação (`docs/AI_DEPENDENCIES.md`).
