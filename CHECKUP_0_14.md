# Checkup do Hook's 0.14.0-beta.1

Feito depois de um incidente real: uma live gravando, cortes que não chegavam e nenhum aviso na tela. Cada item abaixo diz o que foi achado, o que mudou e qual teste impede a volta.

## O que foi achado e corrigido

| # | Problema visto | Causa | Correção | Teste |
|---|---|---|---|---|
| 1 | "0/1 partes" com a live gravando | Uma falha de análise marcava a sessão inteira como erro, e uma sessão em erro **deixava de cadastrar os pedaços novos** | Falha tenta de novo sozinha (30 s, 2 min, 5 min). Mesmo com erro final, uma live aberta continua cadastrando os pedaços | `test_qualidade`, `test_camada_contexto.FailurePolicyTests`, `test_multi_live` |
| 2 | Erro `cublas64_12.dll` | A placa NVIDIA só falhava na hora de transcrever (a peça do CUDA faltava), depois do ponto em que o programa já tinha previsto a queda para o processador | Se o CUDA falha na transcrição, passa para o processador e repete uma vez | `CudaFallbackTests`, `test_qualidade` |
| 3 | Gravação parou e nada avisou | Fim da captura por conta própria não deixava registro nem aviso. O seletor ainda mostrava "ao vivo" | Registro `captura_fim.json`, aviso grande com **Retomar gravação**, seletor corrigido | `CaptureEndTests`, `StateInvariantTests` |
| 4 | Não dava para parar nem confirmar a gravação em Cortes | O controle ficava só em Adicionar | Barra da live em Cortes: "Gravando agora", pedaços gravados e analisados, idade do último pedaço, **Parar gravação** | `UiContractTests`, fumaça de navegador |
| 5 | Sessões antigas travavam a live | Rodízio igual para todas as sessões | A live aberta tem prioridade; sessões antigas só trabalham quando a live não tem o que fazer | `test_qualidade.test_open_live_is_analyzed_before_an_old_session` |
| 6 | Etapa "Transcrevendo" parada por 10+ min sem sinal | Sem relógio por etapa | O painel mostra "há N min nesta etapa" e, passando de 10 min, avisa | `test_progress_reports_how_long...` |
| 7 | Análise começava pausada depois de reiniciar | O programa pausa após reiniciar de propósito, mas o aviso só aparecia com pedaços pendentes | O aviso aparece também para live aberta | fumaça de navegador |

## Quase foi pro pacote (pego pela checagem)
- `app.py` usava `time` sem importar. Teria derrubado a tela inteira ao abrir uma live. Achado pelo `pyflakes` e agora coberto por `StateInvariantTests`.
- Em uma etapa anterior, o arquivo `intelligence.py` foi sobrescrito por engano e restaurado a tempo; o módulo novo se chama `camada_contexto.py`.

## Como conferir sempre
- `python -m pyflakes liveclips`: nomes indefinidos.
- `python -m unittest discover -s tests -t .`: suíte completa.
- `python tests/smoke_ui.py PORTA` (servidor rodando, requer playwright): abre cada tela, cada aba do Ajustes e do estúdio, e falha com erro de JavaScript.

## Limites deste checkup (honestos)
- Os testes simulam a gravação com arquivos `.ts` de teste e um modelo de voz de mentira. **Nada foi testado com streamlink, Twitch/YouTube, GPU NVIDIA ou Windows reais.**
- Não sei por que a gravação da DAVA JONAS parou: pode ter sido o fim da live ou queda de conexão. Agora o programa registra e avisa, mas a causa daquele caso só aparece no `captura.log` da sessão.
- Um último pedaço menor que 128 KB nunca é cadastrado (regra antiga mantida).
- Exportações pesadas aprovadas continuam passando na frente da análise na fila (regra antiga mantida).
- Não existe teste automático de lentidão: o tempo por etapa é só informado, não medido contra um limite.

## Correção posterior: barra de gravação cobrindo a tela
- Causa: a barra usava a classe `live`, que no CSS já era a legenda do editor (`position:absolute; inset:0; pointer-events:none`). A barra cobria a tela e bloqueava os cliques, inclusive no "Parar gravação". A bolinha verde do status também usava a mesma classe.
- Correção: classes renomeadas para `banner.rec` e `dot.on`.
- Teste novo: `UiContractTests.test_live_bar_classes_do_not_collide_with_absolute_overlay_css` (falha se a classe velha voltar). Verificado em navegador simulado: menu, Adicionar, Ajustes, Cortes e botão Parar respondem com gravação ativa. Não testado no seu PC real.
