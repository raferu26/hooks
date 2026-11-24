# Matriz UX — problemas da auditoria 0.18.2 × estado real na 0.19.0-beta.1
Evidência = leitura do código (`ui/`) e e2e `ui/e2e10.py` (1440×900, Linux, mídia sintética) em 23/11/2026. Sem teste com pessoas.

| ID | PROBLEMA | ESTADO ATUAL | EVIDÊNCIA | TESTE | PRÓXIMA AÇÃO |
|---|---|---|---|---|---|
| P01 | 8 abas | **Resolvido** (inspetor + seções recolhíveis) | e2e `sem_abas`, `secoes`; sem `role=tab` no `#stRight` | e2e | Revisar nomes/ordem das 9 seções com pessoas |
| P02 | Preview pequeno | **Melhorado**: 15–20% da janela (era 10–18%); controles ao lado; divisor da timeline; F recolhe | `validacao/medir_layout.py`; e2e `divisor_*`, `foco_*` | e2e | Medir com pessoas; avaliar barra superior mais baixa |
| P03 | Prévia lenta | **Melhorado**: 11 s → 5–6 s (clipe 14,5 s); 15,8 → 6,6 s (28 s de vídeo); sem camadas L1/L2 | profiling + e2e `segundos_ate_previa_nova` | e2e, 126 testes de render | Avaliar sobreposição imediata (L1) após medir a latência restante |
| P04 | Salvar ≠ renderizar | **Resolvido** | Ctrl+S → `saveNow()`; autosave `learn=False` | `test_salvar_previa` (9), e2e | — |
| P05 | 8 pistas | **Resolvido** em 3 + extras | e2e `tres_pistas`, `pista_zoom_aparece`, `todas_as_pistas` | e2e | Ripple e arrasto sem redesenho (snap já feito) |
| P06 | Hierarquia visual | **Parcial**: escala tipográfica (4 tamanhos), mínimo 12 px, alvos ≥28 px | `validacao/medir_design.py` (17→0 fontes <12 px; 18→0 alvos <28 px) | `test_design_tokens` | Hierarquia por cor/peso, espaçamento 4 px, contraste dos blocos da timeline |
| P07 | Fluxo fragmentado | **Parcial** (`#stFlow` oculto <1180 px) | `style.css` 305 | e2e parcial | Revisar fluxo Importar→Editar→Conferir→Exportar |
| P08 | Feedback de estado | **Resolvido** (Salvo/Salvando/…/Prévia anterior) | e2e `estado_nao_salvo`, `autosave_salvo`, `previa_marcada_anterior` | e2e | — |
| P09 | Atalhos | **Parcial**: guarda de campo, `?`, Ctrl+Z/Y | `studio.js` 421–440 | e2e `ctrl_z`, `atalhos_dialogo` | Ctrl+K e mapa pesquisável (A04) |
| P10 | Modos de qualidade | **Resolvido em CPU**; GPU não validada | medição: 4 comandos distintos (BASELINE §4) | `test_modos_qualidade` (9) | Validar NVENC/QSV/AMF (C02, precisa de GPU) |
| N1 | Barra quebrava | **Resolvido** | 47,8 px; 1280/1024 OK | e2e | — |
| N2 | 2 controles de reprodução | **Resolvido** | `<video id=stVideo>` sem `controls` | e2e | — |
| N3 | "Agente" | **Resolvido** | `grep Agente` vazio | `test_interface`, e2e | — |
| N4 | Autosave ensinava | **Resolvido** | `learn=False` | `test_salvar_previa` | — |
| N5 | Redesenho completo | **Parcial**: medido 7,7 ms (200) / 14 ms (500) p50 | BASELINE §3 | `validacao/bench_ui.py` | Redesenho parcial; medir 90 s (V09) |
| N6 | Ctrl+Enter sem confirmação | **Resolvido** | 2º Ctrl+Enter em 2,5 s | e2e `ctrl_enter_pede_confirmacao` | — |
