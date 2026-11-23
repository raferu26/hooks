# Hook's 0.14.0-beta.1 — Inteligência de ações e reações

Este documento diz, item por item do dossiê (N01–N32), o que o código **faz hoje**. Regra: estar no dossiê não é estar implementado, e implementado não é validado.

**Nada foi validado em conteúdo real de live.** Todos os testes usam dados sintéticos. As notas do programa continuam heurísticas (`heuristico_nao_calibrado`), não probabilidades.

Resumo: 1 disponível · 21 parcial · 2 laboratório · 8 ausente.

| Item | O que é | Estado | Onde está | Limite honesto |
|---|---|---|---|---|
| N01 | Fechamento explícito de segmentos | Ausente | — | Segue valendo a regra antiga (arquivo estável > 25 s, último só com sessão encerrada). |
| N02 | Reconexão com épocas de captura | Ausente | — | — |
| N03 | Referências e retenção do buffer | Parcial | retention.plan | Só simula a limpeza e protege mídia de cortes ativos; não apaga nada e não considera editor/revisões. |
| N04 | Mapa de relógios | Parcial | clockmap.py, chat.py | Declara a incerteza do chat (padrão 5 s ou latência do provedor). Deslocamento só com chat_clock.json; não alinha sozinho. |
| N05 | Filas separadas com orçamento | Parcial | engine.waiting_note | Só informa que a live espera a vez; continua um único trabalhador, sem fila separada. |
| N06 | Identidade e retomada de jobs | Ausente | — | Sem lease/idempotência nova. |
| N07 | Estado semântico da sessão | Parcial | context_store.py, studio_api.context_action | Fatos/hipóteses com proveniência e escopo; participantes e tópicos NÃO são extraídos sozinhos. |
| N08 | Episódios abertos e desfecho | Parcial | episodes.py, dimensions.py, handoff.py | Regras de texto em português; o corte espera se há promessa sem desfecho. Não validado em conteúdo real. |
| N09 | Relações entre acontecimentos | Parcial | episodes.py, fusion.associate | Relação temporal nunca é causa; alternativas ficam listadas. |
| N10 | Recuperação de contexto distante | Parcial | context_search.py | Busca textual/estruturada até 15 min antes; referência ambígua vai para decisão humana. |
| N11 | Percepção do gameplay ou vídeo | Ausente | — | Sem modelo de visão: o jogo só entra como flashes/rajadas de pixel. |
| N12 | Candidatos silenciosos | Laboratório | silent_path.py | Até 2 por contexto, sempre rotulados como exploratórios; bocejo, movimento global e pista isolada fraca são descartados com motivo. |
| N13 | Refinamento de limites | Parcial | timeline.expand_context, context_search.required_context | Os limites principais não mudaram; o contexto exigido é listado e bloqueia o estado "pronto". |
| N14 | Ranking por dimensões | Parcial | dimensions.py | As dimensões são calculadas e mostradas, mas a ordem dos cortes continua pelo escore antigo. |
| N15 | Diversidade semântica | Parcial | dimensions.novelty | Medida de novidade por sobreposição de tempo/texto; deduplicação antiga mantida. |
| N16 | Qualidade da face | Parcial | face_quality.py | Cobertura, tamanho do rosto e amostragem. Desfoque e oclusão NÃO são medidos. |
| N17 | Rastreamento e baseline por atividade | Parcial | behavior.py | Baseline separado falando/ouvindo (≥ 8 amostras) e pose reiniciada após perda do rosto. Sem identidade entre pessoas. |
| N18 | Buffer facial e análise densa | Laboratório | signals.refine_dense | Função existe (4–30 fps, só no trecho); não é chamada automaticamente e o ganho de recall não foi medido. |
| N19 | Início, ápice e retorno | Parcial | behavior.py | Eventos têm onset/apex/offset e incerteza igual ao passo de amostragem (0,25 s a 4 fps). |
| N20 | Eventos de áudio e prosódia | Ausente | — | Só energia de som; não distingue risada de som do jogo. |
| N21 | Fusão com origem e dependência | Parcial | fusion.py | Movimento, rosto e comportamento da webcam contam como UMA fonte. Atribuição ao streamer fica "não verificada". |
| N22 | Raciocinador contextual local | Ausente | — | O Ollama segue só no rerank/títulos de antes. |
| N23 | Calibração e abstenção | Parcial | calibration.py, fusion.py | Estados de abstenção existem. Notas = "heurístico_nao_calibrado"; calibrar exige ≥ 30 casos reservados. |
| N24 | Memória episódica com proveniência | Disponível | context_store.py | Fato exige evidência; correção versiona, lista dependentes e permite reverter. |
| N25 | Casos de erro e momentos perdidos | Parcial | context_store.add_case, app.record_case, studio.js | Aprovar/rejeitar e "momento perdido" viram casos; ninguém os usa para ajustar nada automaticamente. |
| N26 | Avaliação causal por replay | Parcial | replay.py | Verificador de "olhar o futuro" pronto; não foi rodado com gravações reais. |
| N27 | Comparação humana e ablação | Parcial | replay.ablate/evaluate | Mede cobertura contra casos humanos; sem casos, não calcula número. |
| N28 | Observabilidade por evento | Parcial | context_store.trace, camada_contexto.py | Registra a etapa de sugestão por corte; não acompanha render/entrega. |
| N29 | Painel de contexto e revisão | Parcial | studio.js (aba "Por quê") | Mostra dimensões, abstenções, episódios, contexto exigido e correção; sem exibir evidência bruta quadro a quadro. |
| N30 | Distribuição opcional por conectores | Ausente | — | Pacote manual mantido. |
| N31 | Métricas com definição e escopo | Ausente | — | — |
| N32 | Recuperação verificável do ambiente e da mídia | Parcial | recovery.verify_restore | Verifica um backup em pasta isolada e lista mídia ausente; ainda não há botão na interface. |

## Como o fluxo funciona agora

1. Cada vez que o programa conecta o contexto de um segmento, ele grava episódios (promessa, tentativa, desafio) no banco `contexto.sqlite3`.
2. Cada corte sugerido recebe uma leitura: fontes independentes, conflitos (câmera/cabeça mexendo junto, som sem fala), qualidade do rosto, dimensões separadas e o contexto anterior que ele pressupõe.
3. Corte com promessa sem desfecho ou contexto exigido fora dele fica **aguardando contexto**. Isso aparece no cartão e na aba **Por quê** do estúdio.
4. Reações sem fala viram candidatos **exploratórios** (no máximo 2 por contexto): bocejo, movimento global e pista isolada fraca são descartados, com o motivo registrado.
5. Aprovar, rejeitar e **Marcar momento perdido** viram casos guardados para avaliação futura. Nada muda sozinho por causa deles.

## O que NÃO foi feito

- Sem modelo de visão para o jogo (N11) e sem classificação de som (N20).
- Raciocinador local (N22), filas/leases (N05/N06), fechamento explícito e épocas de reconexão (N01/N02), conectores (N30) e métricas com escopo (N31) ficaram de fora.
- A ordem dos cortes ainda usa o escore antigo; as dimensões são informação para você, não ordenação.
- Face em alta frequência (`refine_dense`) existe, mas não é chamada sozinha.

## Como testar sem esperar uma live

Rode `python -m unittest tests.test_fusion_silent tests.test_camada_contexto tests.test_context tests.test_operacao`. Para ver no programa: abra um corte, estúdio → **Por quê**.
