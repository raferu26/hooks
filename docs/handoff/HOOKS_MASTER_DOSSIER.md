# HOOKS — DOSSIÊ MESTRE (reconstrução histórica, memória técnica e transferência para o Claude Code)

Elaborado em 23/11/2026 (noite), a partir das fontes **efetivamente acessíveis** nesta sessão. É documentação: nenhum código do Hook's foi alterado para produzi-lo.

**Pacote:** este arquivo é a referência histórica aprofundada. Os demais: `HOOKS_TECHNICAL_HANDOFF.md` (estado operacional e arquitetura), `HOOKS_HISTORY_AND_DECISIONS.md` (tabela de versões e ADRs), `HOOKS_FEATURE_INVENTORY.md` (capacidades), `HOOKS_ROADMAP.md` (futuro), `CLAUDE.md` (regras permanentes), `HOOKS_OPEN_QUESTIONS.md` (lacunas). Para não duplicar, a **tabela completa de versões** e o **registro de decisões** vivem no `HISTORY_AND_DECISIONS`; o **inventário** no `FEATURE_INVENTORY`; a **arquitetura e os diagramas** no `TECHNICAL_HANDOFF`.

Legenda: **[HISTÓRICO CONFIRMADO]** · **[VERIFICADO NO CÓDIGO]** · **[TESTADO]** · **[DECISÃO APROVADA]** · **[PLANEJADO]** · **[IMPLEMENTAÇÃO PARCIAL]** · **[OBSOLETO]** · **[INFERÊNCIA]** · **[NÃO VERIFICADO]**.

As cinco perguntas: **De onde viemos?** Partes I–II. **O que construímos?** Partes III–IV. **Por que decidimos assim?** Parte V e §Erros. **Onde estamos?** Partes VI–IX, XII. **Para onde vamos?** Partes X, XIII.

---

## 0. Fontes examinadas e o que NÃO consegui recuperar

### Fontes acessíveis (todas lidas ou medidas)
| Fonte | O que contém |
|---|---|
| 15 ZIPs de código: `0.9.0`, `0.10.0` (pasta), `0.11.0`, `0.12.0`, `0.13.0`, `0.14.0`, `0.15.0-beta.3`, `0.16.0-beta.1/2`, `0.17.0`, `0.17.1`, `0.18.0`, `0.18.1`, `0.18.2`, `0.19.0` | Extraídos e medidos (linhas de Python, módulos, testes, tamanho da interface) |
| Árvores `v8`, `v9` (=0.18.2 preservada), `v10` (=0.19), `ui`, `ui10`, `validacao`, `exp` (experimentos) | Código e documentos |
| `CHECKPOINT_V6 … V6_9`, `V7`, `V7_1`, `V8`, `EDITOR_PROFISSIONAL_V7`, `EDITOR_PRO_V8` | Estado das versões 0.8.x–0.10 |
| `ESTUDIO_0_11/12/13`, `CHECKUP_0_14`, `INTELIGENCIA_0_14`, `PISTAS_0_15`, `APLICATIVO_0_16`, `SAAS_0_16`, `PENDENCIAS_0_16/0_17_1`, `REFINAMENTO_0_17/0_17_1`, `PROGRESSO_P00_P27`, `VALIDACAO_COMPLEMENTAR`, `CORRECOES_0_18_2`, `NOVIDADES_0_18/0_19`, `ROTEIRO_TESTE_USUARIOS_0_19`, `DPA_RASCUNHO`, `DEPLOY_SERVIDOR` | Documentos de estado de cada versão |
| Kits de prompts enviados por você: editor (18/11), inteligência e operação (19/11), "edição sem IA" P00–P27 (22/11), prompts de performance e de QA multi-perfil (23/11), redefinição Desktop SaaS Local-First (23/11), "Missão 10/10" (23/11), aprovação do redesign (23/11 15:04) | Pedidos e decisões |
| Dossiês em PDF do editor e da inteligência (nos uploads), `Memoria_Editorial_LiveClips.json` | Especificações propostas (não código) |
| Auditoria de UX da 0.18.2 salva no Docs (26 mil caracteres lidos) | P01–P10, N1–N6, roadmap E0–E10, wireframe |
| Memória do assistente sobre o projeto | Decisões do Rafael com datas |
| Testes: reexecutei hoje 24 testes-chave (OK) | Estado atual |

### Lacunas explícitas [não preenchidas por suposição]
1. **Conversa de origem** (outro assistente, antes da V6): inacessível. Ver `OPEN_QUESTIONS` H01.
2. **Relatório da auditoria de arquitetura** (23/11, Docs): link não preservado (H03). A decisão local-first está confirmada pela memória e pelo prompt; a avaliação de stack não.
3. **Relatórios consolidados das auditorias de desempenho e de QA multi-perfil** pedidas em 23/11: o prompt está acessível; um relatório correspondente não foi localizado (H04). Há, porém, medições de desempenho na 0.17 e na 0.19.
4. **Histórico git** do repositório original (branches/tags) e as capturas de tela temporárias do redesign.
5. As conversas deste ambiente não são pesquisáveis para o tema Hooks (a busca de conversas só retornou chats de tráfego pago); portanto não reconstruí mensagens literais fora dos arquivos acima.

Não afirmo ter recuperado 100% do histórico.

---

# PARTE I — HISTÓRIA

(A tabela versão a versão está em `HOOKS_HISTORY_AND_DECISIONS.md` §1.)

### Fase 0 — Origem (≤ 16/11/2026) [HISTÓRICO CONFIRMADO em parte]
- **Nome:** "Agente Clipador" / **LiveClips**; código-base `liveclips-v6-main` (V6). **Objetivo:** clipar lives de streamers e entregar cortes verticais.
- **Estado inicial (0.8.0-beta.1):** captura segmentada por Streamlink, transcrição, ranking por fala/áudio/movimento, prévia horizontal, exportação TikTok 1080×1920 com webcam em cima e jogo embaixo. Teste manual acompanhado em 16/11: uma live gerou 12 sugestões; prévia, aprovação e exportação foram confirmadas pelo usuário. 65 testes.
- **Solicitações:** controle de gravação, qualidade até 1440p, vários streamers, exportação sem fila.
- **Lacuna:** como e por que o projeto começou, e as decisões anteriores ao V6.

### Fase 1 — Agente de corte (0.8.1–0.8.9, ~16–18/11)
Qualidade de captura e saída (1440p, 60 fps, Lanczos, CRF 18); Twitch com chat; movimentos faciais; aprendizado por streamer; modos live e vídeo/podcast; vídeo por link; dois enquadramentos; análise progressiva e corte manual; backups e restauração; MediaPipe local; interface reformulada. **Resultado:** 95+ testes; ainda sem edição profissional. **Lição de honestidade já presente:** "o agente observa movimentos; não lê emoção" (V6.8).

### Fase 2 — Editor profissional (0.9.0 e 0.10.0, 18/11)
Mudança de foco: "a análise existe para informar a montagem". 13 estilos; plano por corte com decisões individuais e reversíveis; pausa segura; imagem/SFX/música; manifesto. V8: looks, curvas de zoom, render em uma passada com recuo, loudness medido. Preservou captura e ranking. **Referências usadas:** documentação FFmpeg, Adobe, YouTube, TikTok e dois fóruns como inspiração (declarado "não autoridade única"). Código de referência de terceiros: ReaCut (MIT), créditos em `THIRD_PARTY_NOTICES.md`.

### Fase 3 — Estúdio (0.11–0.13, 18–19/11)
Tela de edição com fala, prévia, ferramentas e trilhas; layouts; velocidade/congelar/replay; música por link; formatos extras; pacote de publicação; agentes (juiz, Ollama opcional); prévia ao vivo de legenda; kit de marca; QC na exportação; diagnóstico e `ATUALIZAR.bat`; **plano versionado** (`plan.py`), registro de capacidades, memória editorial, revisão ciente do plano, edição por conversa. O projeto passa a se chamar **Hook's** (decisão de 19/11, só nome e logo; o pacote continua `liveclips`) [HISTÓRICO CONFIRMADO: memória; INFERÊNCIA sobre o momento exato]. **Declaração central da 0.13:** nenhum item validado com conteúdo real; "implementado ≠ integrado ≠ validado".

### Fase 4 — Operação real (0.14–0.15, 19/11)
Um **incidente real** (live gravando, cortes que não chegavam, nenhum aviso) gerou o `CHECKUP_0_14`: 7 problemas e correções (falha de análise não derruba mais o cadastro; fallback CUDA; aviso de fim de captura; barra da live; prioridade da live aberta; relógio por etapa). Camada de inteligência N01–N32 (1 disponível, 21 parciais, 2 laboratório, 8 ausentes). Em seguida, **pistas de trabalho** para até 4 lives e webcam automática. Objetivo declarado por você: clipar até 4 lives ao mesmo tempo, editando e exportando sem fila.

### Fase 5 — Produto comercial (0.16–0.17.1, 22/11)
Base SaaS (`hooks_cloud`), licença assinada, atalho/janela de aplicativo; refinamento de velocidade (painel 0,57→0,07 s, banco 2,2→0,04 s); rejeição com motivo; QC visual; teclado e revisão em lote; pasta de entrega; robustez (limpeza de renders incompletos, backup verificado). Teste de robustez com ~14.500 entradas inválidas.

### Fase 6 — Edição sem IA e correções (0.18.0–0.18.2, 22–23/11)
O kit P00–P27 cria módulos clássicos (marcadores, análise técnica, sincronismo, legendas importadas, cor/LUT, estabilização, capas, gráficos 2D, multiformato, cache, OTIO) e o **modo Sem IA**. 0.18.1 adiciona validação com corpus sintético e gabarito (e corrige título cobrindo a webcam e margem de legenda). 0.18.2 corrige o **YouTube** (vídeo comum gravava 0 bytes) e torna o SaaS visível (`SAAS_LOCAL.bat`).

### Fase 7 — Auditoria de UX, aprovação e redesign (23/11)
Seu feedback de um usuário: "muitas opções, muitas abas… menos é mais". A auditoria da 0.18.2 achou P01–P10 e N1–N6 (Parte VI). Você aprovou a arquitetura (inspetor contextual, 3 pistas, 4 modos de qualidade reais, "Sugestões", ordem E0→E1→E2) e o requisito SEM IA. A 0.19.0-beta.1 foi entregue com E0–E2 e o inspetor/pistas.

---

# PARTE II — VERSÕES
Ver `HOOKS_HISTORY_AND_DECISIONS.md` §1 (15 versões medidas). Resumo analítico:
- **Grandes marcos:** V7/V8 (editor), 0.11 (Estúdio), 0.13 (plano versionado), 0.14 (checkup), 0.15 (pistas), 0.16 (SaaS), 0.18 (P00–P27 + Sem IA), 0.19 (redesign).
- **Crescimento medido:** 3 542 → 20 480 linhas Python; 18 → 96 módulos; 117 → 1 192 definições de teste; interface 74 → 289 KB.
- **Problemas que reapareceram:** configurações que não mudavam o resultado (modo de qualidade, margem de legenda); documentação de estado desatualizada; validação só sintética; dependências de Windows nunca testadas.
- **Funcionalidades abandonadas:** só o campo `reframe` (morto). **Revertida/ajustada:** segunda passagem de legenda passou de "desligada" a "padrão" na 0.17 (com migração que religou perfis uma vez, efeito colateral documentado).
- **Números de versão em propostas:** os kits citam "V9" e outros números que **não** correspondem a versões entregues (por exemplo, "Na V9 entram título na tela e corte do começo fraco", num trecho antigo); só ZIPs e documentos de estado contam.

---

# PARTE III — INVENTÁRIO
Ver `HOOKS_FEATURE_INVENTORY.md`. Síntese: o Hook's tem captura de lives e vídeos, análise (transcrição, energia, movimento, sinais técnicos), seleção explicável, Estúdio de edição (cortes, zoom, títulos, imagens, velocidade, replay, legendas, música, SFX, layouts, cor), exportação multi-formato com 4 modos de qualidade, QC visual e sonoro, pacote com OTIO, pasta de entrega, backup, diagnóstico, SaaS de licença. O que depende de modelo de IA: **transcrição (Whisper), rosto/webcam (MediaPipe), ruído neural (RNNoise), avaliador de ganchos (Ollama)** — todos locais; o resto é algoritmo clássico ou regra.

# PARTE IV — ARQUITETURA
Ver `HOOKS_TECHNICAL_HANDOFF.md` §3 (visão geral, fluxo de 9 passos, multimídia, estados de salvamento/prévia, exportação — diagramas Mermaid). Ponto-chave verificado: o produto é um **servidor HTTP local em Python (stdlib) + interface HTML única + janela Edge/Chrome em modo app**, não um aplicativo Tauri/Electron. A troca de stack foi avaliada no pedido de 23/11, mas **nada foi implementado nesse sentido**.

---

# PARTE V — DECISÕES
Ver `HOOKS_HISTORY_AND_DECISIONS.md` §3 (D01–D14), incluindo o capítulo **D10 — Mudança estratégica sobre IA**. Resumo da contradição histórica: até a 0.17 o produto era descrito como um "agente" com IA local opcional e os kits de 19/11 pediam compreensão de contexto, reações e microexpressões; a partir de 22–23/11 a direção vigente é **editor desktop sem dependência de IA**. A decisão vigente não apaga o histórico: o código ainda contém Whisper, MediaPipe, RNNoise e Ollama como opcionais, e a pergunta "tornar Sem IA o padrão" está **aguardando a sua decisão**.

---

# PARTE VI — AUDITORIAS E PROBLEMAS

### Auditorias existentes (resumo)
| Auditoria | Quando | Resultado |
|---|---|---|
| Checkup do incidente real | 0.14, 19/11 | 7 problemas corrigidos (CHECKUP_0_14) |
| Auditoria da 0.16 / 0.17.1 | 22/11 | Servidor: 55 verificações de segurança; ~14.500 entradas inválidas → 4 rotas 500 e 10 ações quebradas (corrigidas); backup diário; ícone |
| Refinamento de velocidade | 0.17 | Medidas antes/depois (Parte IX) |
| Validação complementar | 0.18.1, 23/11 | Corpus sintético com gabarito; achou título cobrindo webcam e margem de legenda errada |
| Auditoria de UX da 0.18.2 | 23/11 | P01–P10, N1–N6 |
| Auditoria de arquitetura (Desktop SaaS Local-First) | 23/11 | **Relatório não localizado** (lacuna) |
| Auditorias de desempenho e QA multi-perfil | 23/11 | Prompts recebidos; **relatórios não localizados** (lacuna) |
| Investigações de regressão | contínuo | Suíte automatizada; pyflakes |

### Auditoria da 0.18.2-beta.1 — problema a problema
Fonte: documento de auditoria no Docs (`https://claude.ai/artifact/8Dxyu3NgixbGWNn1dmeexp`), evidências de código e a 0.19.

| ID | Problema | Arquivos | Evidência | Grav. | Solução proposta | Aprovação | Implementado na 0.19 | Testes | Estado |
|---|---|---|---|---|---|---|---|---|---|
| P01 | Excesso de abas (8 + Publicar; ferramentas da mesma tarefa em abas diferentes) | `studio.js` `tabsFor/drawRight` | 8 abas contadas | Alta | Inspetor contextual por seleção | **Sim** (15:04) | Sim: item selecionado no topo + 9 seções recolhíveis com resumo; "Todas as funções mantidas" | `test_interface`, e2e (28) | **CONCLUÍDO** (sem teste com pessoas) |
| P02 | Preview pequeno (3 colunas fixas) | `style.css .smain` | ~7% da tela em 1440×900 | Alta | Preview dominante, painéis recolhíveis/redimensionáveis | Sim | Parcial: 17,2% (354×629); colunas ainda fixas, sem redimensionar; transcrição ainda sempre aberta | e2e (medida) | **PARCIAL** |
| P03 | Prévia lenta (render do clipe inteiro) | `engine.py`, `store.py` | Toda mudança = render | Alta | Prévia em 3 camadas | Sim ("demais etapas") | Mitigação: prévia anterior continua tocando; auto-prévia em segundo plano (~9–10 s p/ 14 s). **Camadas L1/L2/L3 não feitas** | e2e | **PARCIAL / E8 pendente** |
| P04 | Salvar apagava prévia e subia versão; Ctrl+S renderizava | `store.save_project`, `studio.js` | `preview_path=''` ao salvar | Alta | Separar versão do projeto de prévia; autosave | Sim (E1) | Sim | `test_salvar_previa` (9) | **CONCLUÍDO** |
| P05 | Timeline sobrecarregada (8 pistas fixas, redesenho total) | `drawTimeline` | 7/8 pistas vazias no corte de teste | Média | Pistas por uso, snap, atualização parcial | Sim (3 pistas) | Parcial: 3 principais + extras sob demanda (7 em "Todas as pistas"); sem snap/ripple; redesenho ainda grande | e2e | **PARCIAL** |
| P06 | Hierarquia visual (tipografia 10–12 px, sem tokens) | `style.css` | Rótulos de 11 px | Média | Design system | Sim (E7) | Não feito além de ajustes incidentais | — | **PENDENTE** |
| P07 | Fluxo fragmentado (sem etapa visível) | Home `.flow`, Estúdio | — | Média | Etapas e ação primária única | Sim | Parcial: existe `#stFlow` na barra (oculto <1180 px); botão Exportar como ação principal | e2e | **PARCIAL** [NÃO VERIFICADO em detalhe] |
| P08 | Feedback de salvamento insuficiente | `drawBar` | Só 3 estados | Média | Máquina de estados | Sim | Sim: Salvo/Salvando/Alterações não salvas/Não salvou; prévia: atualizada/gerando/anterior/falhou | e2e, `test_salvar_previa` | **CONCLUÍDO** |
| P09 | Atalhos (sem ajuda; Ctrl+Z em campo de texto) | bloco `keydown` | Ordem do código | Média | Mapa único, ajuda, guarda de campo | Sim (E6) | Parcial: diálogo `?`, ← →, +/−, P; guarda de campo verificada no código (`typing` retorna antes); sem Ctrl+K nem mapa pesquisável | e2e | **PARCIAL** |
| P10 | Modos de qualidade idênticos | `media._video_codec`, `hardware.choose`, `telemetry` | 4 modos → `libx264 medium crf 18` (reproduzido) | Alta | Modos reais; não presumir equivalência CPU/GPU | Sim (E2) | Sim em CPU; GPU não validada | `test_modos_qualidade` (9), `medir_modos.py` | **CONCLUÍDO (CPU) / GPU NÃO VALIDADA** |
| N1 | Barra superior quebrava | `.sbar` | Captura | Média | Barra compacta | — | Sim | e2e 1440/1280/1024 px | **CONCLUÍDO** |
| N2 | Dois controles de reprodução | `<video controls>` + botão | Captura | Baixa | Um só | — | Sim | e2e | **CONCLUÍDO** |
| N3 | "Agente" sugere IA | abas/Ajustes | `agents.py` é determinístico | Média | Renomear | **Sim** ("Sugestões") | Sim (Estúdio e Ajustes) | `test_interface` | **CONCLUÍDO** |
| N4 | Autosave ensinando memória | `store._learn_from_save` | — | Alta | Aprender só em aprovação/saída | Sim | Sim: `learn=False` no autosave; aprendizado único com diff inteiro | `test_salvar_previa` | **CONCLUÍDO** |
| N5 | Redesenho/instantâneos JSON grandes | `drawTimeline`, `mutate` | [Hipótese] | Média | Medir e otimizar | Sim | Parcial: seções fechadas não desenham; timeline só pistas visíveis; **sem medição em clipes de 90 s** | e2e | **PARCIAL** |
| N6 | Ctrl+Enter aprovava sem confirmação | atalho | — | Baixa | Confirmação leve | Sim | Sim: segundo Ctrl+Enter em 2,5 s | e2e | **CONCLUÍDO** |

Corrigido sem constar da lista: trocar de corte com alterações era bloqueado ("Salve antes") → agora salva e troca; salvar o mesmo projeto deixava a prévia como desatualizada → continua atual.

Outras correções da fase: YouTube 0 bytes (0.18.2), aba Assinatura vazia sem streamer (0.18.2), título sobre a webcam e margem 260→340 (0.18.1).

---

# PARTE VII — REDESIGN

### Interface antiga (0.18.2) [VERIFICADO]
Estúdio com 8 abas (Estilo, Legendas, Títulos, Música, Efeitos, Quadro, Agente, Por quê) + Publicar; três colunas fixas (fala 260–330 px, vídeo, ferramentas 360–420 px com trilho de 64 px); vídeo em ~232×413 px (~7%); timeline de 8 pistas sempre desenhadas (280 px); Ctrl+S gerava prévia. Ajustes: 11 seções. Feedback do usuário: "muitas opções, muitas abas… menos é mais".

### Redesign aprovado e implementado
Princípios (da auditoria, aprovados): **a seleção manda**; três níveis (essencial, ferramentas do item, "mais opções"); fluxo Importar→Editar→Conferir→Exportar; vídeo primeiro; nada some (mapa de migração); manter tema escuro e rosa `#ff4d8d` como única ação primária. Rejeitada, com justificativa, a divisão fixa "Editar/Aparência/Exportar" sugerida no prompt: recriaria o problema.

Resultado na 0.19 (medido, 1440×900, sintético): vídeo 354×629 (17,2%); abrir o Estúdio ~140 ms; zoom visível em 60–70 ms; autosave ~1,6 s; nova prévia 9–10 s para 14 s; barra em uma linha a 1440/1280/1024.

### Roadmap E0–E10 — estado real
| Etapa | Estado |
|---|---|
| E0 Linha de base | CONCLUÍDA |
| E1 Salvar e prévia | CONCLUÍDA |
| E2 Qualidade de exportação | CONCLUÍDA em CPU; GPU NÃO VERIFICADA |
| E3 Timeline | PARCIAL |
| E4 Inspetor contextual | CONCLUÍDA (rotulada "E3" no NOVIDADES_0_19) |
| E5 Layout | PARCIAL |
| E6 Atalhos | PARCIAL |
| E7 Design system | PENDENTE |
| E8 Prévia em camadas | PENDENTE |
| E9 Recursos de edição | PENDENTE |
| E10 Validação | PARCIAL (automação e roteiro prontos; pessoas, Windows e GPU pendentes) |

Mudança posterior no roadmap: a implementação agrupou "timeline com 3 pistas", "inspetor" e "Sugestões" numa só etapa (a numeração do NOVIDADES diverge da auditoria). Nenhuma decisão aprovada foi reordenada.

---

# PARTE VIII — TESTES

| Conjunto | Onde | O que testa / como rodar | Resultado registrado | Limites |
|---|---|---|---|---|
| Suíte unitária/integração | `tests/test_*.py` (105 arquivos de teste, ~1 192 defs; 1 212 execuções) | `PYTHONPATH=. python3 -W ignore -m unittest discover -s tests -t .` (~39 min) | 0.19: 1211 OK + 1 falha corrigida depois (relato da sessão anterior); não houve nova rodada completa depois do ajuste | Linux, mídia sintética, modelo de voz falso |
| Histórico de contagem | ZIPs | 65 (0.8.0) → 117 (0.9) → 150 (0.10) → 239 (0.11) → 348 → 513 (0.13) → 625 → 667 → 780 → 840 → 891 → 1091 (0.18.0) → 1165 → 1174 → 1192 | Contagens estáticas de `def test_` | Não são resultados de execução |
| Sem IA | `test_noai_mode` | Bloqueia import de faster_whisper, mediapipe, torch, onnxruntime, tensorflow | **Rodado hoje: OK** | Só a análise |
| Salvar/prévia e modos | `test_salvar_previa` (9), `test_modos_qualidade` (9) | Ver nomes | **Rodados hoje: 24 OK em 68 s** (junto com sem IA) | CPU apenas |
| Corpus com gabarito | `test_corpus_cortes`, `tests/corpus.py`, `medidas.py` | Intervalo preservado (3,03 s ≥ 2,8), sincronismo 20 ms (≤80), legenda × voz −20 ms (≤150), rosto 0,99, 29 px/quadro, −16,0 LUFS, prévia × exportação (diferença ≤5,6, limite 14) | OK em 0.18.1 | Sintético |
| Interface/e2e | `tests/smoke_ui.py`, `validacao/e2e_estudio_0_19.py` | Playwright + Chrome | 28 verificações OK; sem erro de console | Mídia sintética; ambiente Linux |
| Servidor SaaS | `test_cloud`, `test_cloud_migrations`, `test_licensing`, `test_saas_visivel` | 55 verificações em processo real; ~14.500 entradas inválidas; app+servidor separados | OK (0.16/0.17.1); visibilidade OK (0.18.2) | Sem HTTPS/Asaas/SMTP reais |
| Instaladores | `test_instaladores`, `test_desktop` | Lógica de `.bat` e do lançador | OK | **Windows real não testado** |
| Compatibilidade | teste manual da 0.19 | Dados 0.18.2 abrem na 0.19, editam, exportam em Qualidade | OK | Um projeto |
| Desempenho | `test_performance`, `test_scale`, medidas 0.17/0.19 | Ver Parte IX | OK | Sintético |
| Qualidade objetiva | `validacao/medir_modos.py` | SSIM/PSNR/tempo por modo | SSIM 0,854/0,964/0,975/0,981; PSNR 33,8/39,4/40,8/42,0 dB; 7,4/9,2/90,9/168 s | Fonte sintética extrema |
| Físicos | `ROTEIRO_TESTE_USUARIOS_0_19.md`, `TESTE_GUIADO.md` | Pessoas reais, Windows, GPU | **Nenhum executado** | — |

Não declaro que a suíte passa "na versão atual" além do que está acima: a última rodada completa foi a da 0.19 (com 1 falha depois corrigida e retestada por módulo).

---

# PARTE IX — DESEMPENHO E OTIMIZAÇÕES

| Tema | Problema | Mudança | Medido? | Gargalo restante |
|---|---|---|---|---|
| Render | 2–3 codificações (V7) | Uma passada com recuo (V8) | Qualitativo | — |
| Fila | Um trabalhador (exportar travava análise) | Pistas (0.15) | Estrutural | Transcrição serializada pelo `ModelGate` |
| Painel | 0,57 s por estado a cada 2,5 s | Cache de fatos fechados, consulta agregada, `X-State-Tag` | **0,57→0,07 s** (sintético) | — |
| Propor corte | Checagem de duplicado 0,37 s | `fingerprint` + filtro SQL | **0,37→0,014 s** | — |
| Banco | Abertura 2,2 s | Índices + migração única | **2,2→0,04 s** | — |
| Backup | Manual | Thread própria, verificado | — | — |
| 2ª passagem | Recarregava o modelo | Cache de modelo | — | — |
| Estúdio 0.19 | Vídeo pequeno; prévia some | Layout; prévia anterior; autosave | Abrir ~140 ms; zoom 60–70 ms; autosave ~1,6 s; prévia 9–10 s/14 s | Prévia = clipe inteiro; N5 não medido em 90 s |
| Exportação | Modos idênticos | 4 modos | Qualidade/Entrega 12×/23× mais lentos que Equilibrado **na fonte sintética extrema** | Medir em vídeo real e GPU |
| Disco | Sobras de render | Limpeza ao abrir; render atômico | Teste de interrupção | Retenção de buffer só simulada |

Propostas **não** implementadas: prévia em camadas, reprodução direta da fonte com cortes aplicados no navegador, proxy de edição, medição por etapa mais fina, pool de threads para FFmpeg. Nenhum ganho percentual foi inventado: todos os números acima vêm de medições citadas nos documentos de cada versão.

---

# PARTE X — EVOLUÇÃO COMERCIAL E SAAS

1. **Arquitetura SaaS tradicional (processamento na nuvem):** considerada no pedido de 19–22/11 ("transformar em SaaS funcional pronto para vender"; começar por super admin para ver quem pagou). Nunca implementada como processamento remoto.
2. **Local-first:** já a suposição adotada em `SAAS_0_16.md` (22/11) — "só conta, plano, licença, cobrança e uso ficam no servidor; nada de vídeo vai para a nuvem" — e **confirmada por você em 23/11** [DECISÃO APROVADA]: app desktop instalado, assinatura, sem serviços de IA em nuvem.
3. **Final proposta:** app desktop com backend enxuto (contas, login, assinatura, licença, dispositivos, atualizações, admin). Implementado até aqui: contas, planos, licença Ed25519, uso, cobrança Pix/Asaas (desligado), admin com TOTP, portal, LGPD mecânica, e-mails em fila. **Não existe:** instalador `.exe`, atualização automática, proteção de código, hospedagem.

**Por que local-first:** custo e latência de processar vídeo na nuvem, privacidade do conteúdo, aproveitar o hardware do cliente e evitar custo recorrente de inferência (seu argumento de 23/11).

**Riscos pendentes:** distribuição (ZIP + Python + `INSTALAR.bat`: exige Python 3.11), código legível e portanto copiável, licenciamento só offline por 72 h, pagamentos sem teste real, custos de hospedagem (precisa da sua aprovação), jurídico (termos, DPA em rascunho, gravar lives de terceiros), atualização automática, segurança do app local, funcionamento offline (licença vale 72 h). **O SaaS não está em produção**: é código testado em Linux e `SAAS_LOCAL.bat`.

---

# PARTE XI — ERROS QUE NÃO DEVEMOS REPETIR

| Padrão | Exemplo histórico | Causa | Consequência | Medida preventiva | Teste/processo |
|---|---|---|---|---|---|
| Configuração que não é aplicada | Modo de qualidade sem efeito (P10); margem de legenda 260 dizendo que bastava | Parâmetro lido só no plano B; ajuda contraditória | Resultado ≠ promessa | Toda opção deve alterar o comando/arquivo | `test_ligacao_modulos`, `test_modos_qualidade`, regressão da margem |
| Corrigir uma coisa quebrando outra | Prévia some ao salvar; 1 falha de teste ao renomear "Agente" | Acoplamento versão×prévia; teste exigia texto | Regressão | Testes de regressão por fluxo; atualizar testes com a decisão | `test_salvar_previa`, `test_interface` |
| Sobrescrever/uso de nome sem import | `intelligence.py` sobrescrito; `time` sem import em `app.py` | Edição em lote | Tela inteira cairia | pyflakes e invariantes de estado antes do pacote | `StateInvariantTests`, `python -m pyflakes liveclips` |
| Preview ≠ exportação | Legenda HTML vs libass; título sobre a webcam | Dois mecanismos de desenho | Surpresa na exportação | Rotular "aproximada"; testes de quadro | `test_corpus_cortes` |
| Estado persistente apagado por efeito colateral | Salvar zerava `preview_path` | Prévia amarrada à versão | Perda de trabalho | Separar entidades | idem |
| Aprendizado a partir de passos intermediários | Autosave gravando preferências | Hook no salvamento | Memória poluída | `learn=False` no autosave | `test_salvar_previa` |
| Falha de uma etapa derrubando a sessão | "0/1 partes" com live gravando | Sessão em erro parava de cadastrar pedaços | Perda de cortes durante a live | Isolar falhas; reintentos | `CheckUp 0.14` |
| Entradas inválidas virando 500 | 4 rotas e 10 ações | Sem validação | Erros opacos | Rede de segurança 400 + fuzz | `test_entradas_extremas` |
| Validação só sintética tratada como real | Documentos 0.13–0.19 | Sem Windows/GPU/live | Falsa confiança | Declarar "não validado"; classificar estados | Este dossiê; roteiros físicos |
| Número de teste recalibrado para passar | Loudness 8→9 dB | Calibração do preset | Risco de mascarar defeito | Registrar e justificar | `VALIDACAO_COMPLEMENTAR` |
| Falta de versionamento | Árvore de trabalho sem git; fontes de UI fora do ZIP | Trabalho por cópias | Rollback manual; perda de contexto | C03/C04 do roadmap | Repo + build reprodutível |
| Perda de contexto entre versões | Documentos de estado antigos contradizem os novos | Muitos `.md` soltos | Confusão | Um índice (este pacote) e "NOVIDADES" por versão | `HOOKS_TECHNICAL_HANDOFF` |
| Complexidade sem benefício | 8 abas, 8 pistas fixas, 11 seções de Ajustes | Crescimento por acréscimo | Carga cognitiva | "Seleção manda"; revisão de Ajustes | A06 |
| Desempenho sacrificado por recurso | Prévia = clipe inteiro; undo com JSON completo | Simplicidade inicial | Lentidão | Medir antes; prévia em camadas | A02/A03 |
| Dependência desnecessária/IA | Whisper/MediaPipe como padrão | Origem agente | Conflito com direção "sem IA" | Decisão A01 | `test_noai_mode` |

**Regras operacionais para o Claude Code** (também em `CLAUDE.md`): medir antes de otimizar; testar por módulo e rodar a suíte inteira antes de entregar; não mexer em dados do usuário; versão nova = cópia; nunca declarar "10/10"; cada configuração visível deve ter teste que prove efeito; atualizar os documentos de estado a cada versão; parar e perguntar em custo, escopo, perda de função.

---

# PARTE XII — ESTADO ATUAL REAL

- **Última versão:** 0.19.0-beta.1. Rollback: 0.18.2-beta.1 intacta.
- **Redesign solicitado:** E0, E1, E2 e inspetor/3 pistas/Sugestões **implementados e testados em Linux**; E5–E10 parciais/pendentes. Não está "em andamento" no sentido de arquivos pela metade: a entrega foi concluída e empacotada.
- **O que foi modificado na 0.19:** `store.py`, `app.py`, `engine.py`, `editing.py`, `hardware.py`, `telemetry.py`, `media.py`, versões; UI (`studio.js`, `body.html`, `style.css`, `agents.js`, `live.js`); testes novos e ajustados; docs `NOVIDADES_0_19.md`, `ROTEIRO_TESTE_USUARIOS_0_19.md`, `validacao/*`.
- **Testes:** ver Parte VIII. **Falhando:** nenhum conhecido.
- **Próxima ação recomendada:** (1) pôr as fontes da UI e o código sob git (C03/C04); (2) com o Rafael, rodar C01/C02 no Windows (informar a placa de vídeo e enviar 2–3 clipes); (3) depois seguir o roadmap.
- **Riscos relevantes:** nada validado fora do ambiente de desenvolvimento; ausência de git; fontes da UI fora do ZIP; dependência de Python no PC do cliente; SaaS não hospedado.
- **Limitações conhecidas:** ver `TECHNICAL_HANDOFF` §4.
- **Erro de comunicação a evitar:** a mensagem da sessão anterior dizia "Suíte: 1212 testes, passou"; o correto é 1211 OK + 1 falha corrigida e retestada por módulo, sem nova rodada completa.

---

# PARTE XIII — ROADMAP
Ver `HOOKS_ROADMAP.md` (C01–C06 crítica; A01–A09 alta; M01–M10 média; F01–F09 futura; estado de E0–E10).

---

# VERIFICAÇÃO DE COMPLETUDE (autoauditoria)

1. Fases acessíveis examinadas? Sim para 0.8.0→0.19; **não** a origem (H01). 2. Versões identificáveis? 15 ZIPs + checkpoints 0.8.1–0.8.9; V7.1 sem número exato (H05). 3. Decisões principais? D01–D14. 4. Mudanças de direção explicadas? IA (D10), local-first (D01), numeração de etapas. 5. Funcionalidades identificadas? Sim, por módulo. 6. Planejado × existente diferenciado? Sim (tags). 7. Bugs conhecidos? Sim (Parte VI, Handoff §4). 8. Testes e limitações? Sim. 9. Estado atual verificado? Parcialmente: contagens e módulos medidos; 24 testes rodados hoje; suíte completa **não** rerrodada. 10. Última implementação considerada? Sim. 11. Roadmap coerente com decisões aprovadas? Sim; discrepâncias de numeração E3/E4 registradas. 12. Afirmações sem evidência? As marcadas [INFERÊNCIA]/[NÃO VERIFICADO]. 13. Contradições? Registradas em `OPEN_QUESTIONS` §D (docstring 0.13, "E3" vs "E4", números antigos de testes). 14. CLAUDE.md alinhado? Sim (sem IA, local-first, regras). 15. Claude Code acha arquivos e comandos? Sim; atenção aos caminhos absolutos em `ui10/*.sh`. 16. Lacunas explícitas? Seção 0 e `OPEN_QUESTIONS`. 17. Segredos? Varredura feita antes do ZIP (ver nota de entrega); o pacote não contém tokens, chaves privadas nem dados de usuário — registrada a varredura por padrões comuns, **não** uma auditoria exaustiva.
