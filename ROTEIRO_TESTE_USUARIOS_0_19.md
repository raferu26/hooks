# Roteiro de teste com pessoas — Estúdio 0.19

Objetivo: descobrir onde uma pessoa que **nunca usou o Hook's** trava, erra ou desiste ao editar um corte.
Este roteiro não pode ser executado pelo assistente: ele precisa de pessoas reais. Os números da seção
"Medido automaticamente" servem só de referência técnica, não substituem o teste.

## Quem chamar
- 5 pessoas, sendo pelo menos 3 que nunca abriram o Hook's e 1 que já edita vídeo (CapCut, Premiere etc.).
- Pelo menos 1 pessoa usando notebook com tela de 1366×768 ou 1280×720.
- Ninguém da equipe que construiu o programa.

## Preparação (10 min, uma vez)
1. Hook's 0.19 instalado, com um streamer e uma sessão que já tenha 3 cortes sugeridos.
2. Gravação de tela ligada (com áudio, se a pessoa permitir). Peça autorização por escrito para gravar.
3. Cronômetro. Folha de anotação com as colunas: tarefa, tempo, conseguiu (sim / com ajuda / não), erros, frase dita.
4. Não explique a interface. Diga só: "pense em voz alta; se travar, diga o que está procurando".

## Tarefas (na ordem, sem ajuda)
| # | Tarefa dita à pessoa | Sucesso quando | Tempo-alvo |
|---|---|---|---|
| 1 | "Abra o primeiro corte para editar." | Estúdio aberto | 20 s |
| 2 | "Assista ao corte." | Vídeo tocando | 15 s |
| 3 | "Tire do vídeo o trecho em que ele fala '…' (escolha uma frase)." | Corte manual criado no trecho certo | 60 s |
| 4 | "Dê um zoom na reação logo depois." | Zoom criado | 45 s |
| 5 | "Troque o estilo da legenda para uma que você ache melhor." | Estilo da legenda mudou | 45 s |
| 6 | "Coloque um título nos primeiros segundos." | Título visível no vídeo | 60 s |
| 7 | "Desfaça a última coisa que você fez." | Item desfeito | 15 s |
| 8 | "Veja como ficou o vídeo com tudo isso." | Prévia nova tocando | 30 s após a última edição |
| 9 | "Exporte este corte com a melhor qualidade possível." | Exportação na fila em modo Qualidade ou Entrega | 45 s |
| 10 | "Volte para a lista de cortes." | Biblioteca aberta, nada perdido | 15 s |

## Perguntas no final (anote as palavras exatas)
1. Em algum momento você não sabia se o que fez tinha sido salvo? Quando?
2. O vídeo travou ou sumiu em algum momento? Isso te atrapalhou?
3. O que você procurou e não achou?
4. De 1 a 5, quão difícil foi? Por quê?
5. Algum nome na tela não fez sentido? (ex.: "Sugestões", "Por quê", "Prévia anterior", "Equilibrado")

## Como decidir o que corrigir
- Uma tarefa em que 2 ou mais pessoas falham ou pedem ajuda é problema **grave**: corrigir antes de lançar.
- Uma tarefa acima de 2× o tempo-alvo em 3 ou mais pessoas é problema **médio**.
- Frases repetidas por 2 ou mais pessoas viram item da lista, mesmo sem falha.
- Não conte acertos de quem já conhece o Hook's.

## Medido automaticamente (ambiente de teste, Linux, Chrome headless, 1440×900, mídia sintética de 14 s)
Script: `validacao/e2e_estudio_0_19.py`. Não mede compreensão, só a mecânica.
- Abrir o Estúdio: ~140 ms após o clique.
- Zoom aplicado após o clique no botão: ~60–70 ms.
- Salvamento: automático em ~1,6 s após a última alteração, sem perder o desfazer.
- Prévia nova: gerada sozinha ~9–10 s depois de editar; a prévia anterior continua tocando nesse intervalo.
- Área do vídeo: 17,2% da tela (354×629 px) com 3 pistas na linha do tempo.
- Barra superior em uma linha a 1440, 1280 e 1024 px de largura.
