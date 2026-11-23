# Checkpoint V6.6 — 0.8.6-beta.1

Branch `v6.6`, criada da V6.5 com todos os checkpoints anteriores preservados.

## Análise progressiva de vídeos por link

- Corrige a fila em que dezenas de segmentos eram cadastrados antes da primeira transcrição.
- Em modo vídeo, contextos prontos e segmentos já cadastrados têm prioridade sobre o próximo arquivo da fila.
- As primeiras sugestões podem aparecer enquanto o restante do vídeo continua sendo recebido e processado.
- O modo live mantém a prioridade de leitura dos segmentos recém-fechados.
- Pausas preservam todo o trabalho já concluído.

## Edição antes das sugestões automáticas

- Novo botão `Corte manual` na gravação selecionada.
- Libera somente o intervalo contínuo que já foi analisado.
- O usuário escolhe início e fim entre 1 e 90 segundos e abre o corte diretamente na mesa de revisão.
- Transcrição, auditoria editorial, prévia, aprovação, exportação e deduplicação continuam sendo aplicadas.
- O arquivo original não é alterado.
