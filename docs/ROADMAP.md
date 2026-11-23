# ROADMAP — continuidade (Etapas 0–6 do handoff)

Fonte detalhada dos itens (C01…F09): `docs/handoff/HOOKS_ROADMAP.md`. Este arquivo registra **estado verificado** e **dependências**.
Estado: ✔ feito e verificado · ◐ parcial · ○ pendente · ⛔ bloqueado (precisa do Rafael/Windows/GPU).

| Etapa | Item | Estado | Depende de | Observação |
|---|---|---|---|---|
| 0 | Versão real identificada (0.19.0-beta.1, 306 arquivos) | ✔ | — | `docs/BASELINE.md` |
| 0 | Git + ponto de recuperação (tag `baseline-0.19.0-beta.1`, ZIPs em `../_recovery`) | ✔ | — | C04 |
| 0 | Fontes da UI no repo, build reproduzível byte a byte | ✔ | — | C03 |
| 0 | Documentação de continuidade | ✔ | — | este diretório |
| 0 | Linha de base de testes e benchmarks | ◐ | suíte completa | `docs/BASELINE.md` |
| 1 | Auditar P01–P10 / N1–N6 | ◐ | e2e | `docs/UX_MATRIX.md` |
| 1 | Corrigir regressões confirmadas | ○ | matriz | ver `KNOWN_ISSUES.md` |
| 2 | Painéis redimensionáveis, transcrição sob demanda (E5) | ○ | — | CSS/JS; testar 1024–1920 px |
| 2 | Design system: tokens, áreas clicáveis, contraste AA (E7) | ○ | — | baixo risco |
| 2 | Reorganizar os 11 Ajustes (A06) | ○ | princípio "nada some" | mapa de migração |
| 3 | Timeline: snap, ripple, arrasto sem redesenho total (E3/A03) | ◐ | benchmark N5 | `validacao/bench_ui.py` |
| 3 | Prévia em camadas (E8/A02) | ○ | protótipo; `timing_for` | alto risco; prototipar primeiro |
| 3 | Atalhos: Ctrl+K, mapa único (E6/A04) | ◐ | — | |
| 4 | Transições xfade, J/L cut (M02) | ○ | `plan.py`/`Remap` | |
| 4 | EQ/compressor/de-esser clássicos (M04) | ○ | teste em fala real | |
| 4 | Layout por trecho (M07), reposicionar webcam (M03) | ○ | A02 | |
| 4 | Consistência prévia × exportação | ◐ | `test_corpus_cortes` | legenda HTML ≈ libass (V04) |
| 5 | Medição de RAM/CPU/GPU, vídeos longos, estabilidade | ○ | benchmarks | |
| 5 | Validação Windows e GPU (C01/C02) | ⛔ | PC do Rafael | |
| — | Decisão A01: Sem IA como padrão | ⛔ | Rafael | plano em `AI_DEPENDENCIES.md` |
| 6 | Instalador, atualização, licenciamento, SaaS hospedado | ⛔ | Etapas 1–5; aprovação de custo | F01–F06 |
| — | Validar escolha de momentos com lives reais (C05), YouTube real (C06) | ⛔ | dados do Rafael | |

## Regras de sequência
1. Nada da Etapa 6 antes de estabilizar 1–5.
2. A02 (prévia em camadas) só depois de medir o custo atual (BASELINE) e prototipar contra `timing_for`.
3. Cada item: um commit pequeno + teste + linha no CHANGELOG.
