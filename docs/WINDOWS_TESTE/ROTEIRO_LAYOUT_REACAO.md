# Roteiro — Layout de reação com um vídeo real (Windows)

Pré-requisito: pacote de teste com a branch `feature/layout-reacoes` (ainda **não** empacotado). Use um vídeo horizontal de reação **seu**
(ex.: streamer reagindo a outro vídeo). Este roteiro só vale como "testado com o vídeo real" depois que você rodar e preencher.

Anote: versão/commit (rodapé da barra lateral), tempo de cada passo, RAM/CPU/GPU (Gerenciador de Tarefas ou `monitorar_uso.py`).

1. Importe o vídeo horizontal. Abra um corte no Estúdio.
2. Seção **Layout e imagens** → **Layout de reação** → **Webcam ampliada**.
3. No seletor aberto, confira que o quadro é o ORIGINAL (horizontal). Arraste um retângulo sobre a webcam. Confirmar.
4. Marque o **Conteúdo reagido**. Confirmar. A mini prévia aparece. Anote se a webcam e o conteúdo estão onde você marcou.
5. Ajuste a "Altura da webcam" e o enquadramento (Preencher / Mostrar inteiro). Anote cortes indesejados (aviso ⚠).
6. Aperte **P** (prévia em vídeo). Em um trecho em que o conteúdo está **parado** e o streamer fala, confira se a webcam continua se mexendo.
7. Selecione um intervalo na linha do tempo → **＋ Cena na seleção** (Foco na reação). Teste "Corte direto" e "Suave". Volte ao anterior.
8. Clique **Sugerir momentos…**: confira se os trechos fazem sentido (é só movimento de pixels). Aprove/ignore.
9. Se aparecer uma webcam extra dentro do conteúdo: **Ocultar uma região** (desfocar/cobrir) e confira a prévia.
10. Insira/edite legenda. Confira que não cobre a webcam (ajuste a distância em Legendas).
11. Salve (automático), feche e reabra o corte: o layout, as regiões e as cenas voltam?
12. Exporte (Equilibrado e Qualidade). Compare no player: webcam visível, proporções, sincronia do áudio, **um** áudio só, sem eco.
13. Anote o tempo de exportação, RAM de pico, CPU/GPU, e qualquer travamento ou texto cortado na interface.

Registre falhas em `REGISTRO_DE_PROBLEMAS.md` e rode `COLETAR_RELATORIO.bat`.
