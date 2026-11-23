# Matriz UX — problemas da auditoria 0.18.2 × estado real na 0.19.0-beta.1
Evidência = leitura do código (`ui/`) e e2e `ui/e2e10.py` (1440×900, Linux, mídia sintética) em 23/11/2026. Sem teste com pessoas.

| ID | PROBLEMA | ESTADO ATUAL | EVIDÊNCIA | TESTE | PRÓXIMA AÇÃO |
|---|---|---|---|---|---|
| P01 | 8 abas | **Resolvido** (inspetor + seções recolhíveis) | e2e `sem_abas`, `secoes`; sem `role=tab` no `#stRight` | e2e | Revisar nomes/ordem das 9 seções com pessoas |
| P02 | Preview pequeno | **Parcial**: 15,6% da tela (era ~7%) | e2e `video_pct_tela`=15.6; `.smain` com colunas fixas (`style.css` 186) | e2e (>12%) | Painéis redimensionáveis/recolhíveis, transcrição sob demanda (E5) |
| P03 | Prévia lenta | **Parcial**: prévia anterior continua; nova em ~11 s p/ 14,5 s; sem camadas | e2e `segundos_ate_previa_nova`=11 | e2e | Protótipo L1 (HTML imediato) sobre `timing_for` (A02) |
| P04 | Salvar ≠ renderizar | **Resolvido** | Ctrl+S → `saveNow()`; autosave `learn=False` | `test_salvar_previa` (9), e2e | — |
| P05 | 8 pistas | **Resolvido** em 3 + extras | e2e `tres_pistas`, `pista_zoom_aparece`, `todas_as_pistas` | e2e | Snap, ripple, arrasto sem redesenho (A03) |
| P06 | Hierarquia visual | **Pendente** | sem tokens de design; tipografia 10–12 px | — | Design system (A05) |
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
