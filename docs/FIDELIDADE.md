# Fidelidade prévia × exportação — o que é perceptível

Medido em Linux, vídeo/áudio sintéticos, CPU, modo Equilibrado (corte de 28 s). **Prioriza o que o usuário vê**, não a pontuação SSIM.

| Dimensão | Medida | Diferença perceptível? | Estado |
|---|---|---|---|
| **Legenda — tamanho** | ao vivo (HTML) × exportação (libass), mesma fonte/número: ~11% maior na prévia → razão **1,000** (estilo padrão) | **Sim (corrigido)**: texto e quebras de linha diferentes | `legenda_fidelidade.py`, e2e `legenda_*` |
| Legenda — fonte | prévia usava Segoe UI, exportação Arial | Sim (corrigido; prévia = Arial) | corrigido |
| Legenda — posição (base) | diferença **+0,09 ponto %** da altura | Não | ok |
| Legenda — estilo bold | prévia em CAIXA ALTA, exportação não | **Sim (corrigido)** | corrigido |
| Legenda — outros estilos | resíduo de até ±11% no tamanho; impact/box quebram em blocos só na exportação | **Sim (impact/box)** | **KI-12 aberto** |
| Contraste e cor | média RGB final [126,128,126] × rascunho [126,128,127]; desvio da luma 95,9 × 95,7 | Não | ok |
| Nitidez | detalhe fino do rascunho = **0,56×** o do final (CRF 30 ultrafast, 540×960) | **Sim: a prévia é visivelmente mais "mole"**; é esperado em rascunho | aceito; rotular como aproximada |
| Quadro geral | SSIM final × rascunho **0,976**; erro médio 3,2/255 | Pouco | ok |
| Enquadramento/zoom | coberto por `test_corpus_cortes` (rosto, deslocamento por quadro, intervalo preservado) e SSIM | não medido de forma isolada | pendente em vídeo real |
| Sincronização A/V | corpus: voz × legenda −20 ms (limite 150); **não medível** neste clipe (áudio de tom constante) | — | pendente com áudio real |
| Títulos (`.ttl`) | **não medidos** (a renderização ASS dos títulos precisa de outro formato de entrada no medidor) | desconhecido | pendente |
| Fonte do Windows (Arial real), fontes de marca | não medidos (Linux resolve Arial → Liberation Sans, métrica compatível) | provavelmente igual | pendente no Windows |

## Conclusões práticas
1. A maior discrepância visível **não era qualidade de imagem, era a legenda**: a prévia mostrava o texto maior e quebrando em outro lugar. Corrigido para o estilo padrão.
2. A prévia é **mais macia** que o final; isso é do rascunho (540×960, CRF 30) e não deve ser "consertado" além de rotulá-la como aproximada (a otimização desta rodada manteve o SSIM).
3. Próximo: estilos com quebra em blocos (KI-12) e títulos; depois medir em vídeo real e no Windows.
