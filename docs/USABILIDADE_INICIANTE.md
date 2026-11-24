# Roteiro de usabilidade para quem nunca usou o Hook's

**Isto exige pessoas.** Os e2e automáticos conferem estrutura e cliques possíveis; **não substituem** observar alguém usando. Nada aqui foi executado com pessoas ainda.

## Como aplicar (15–25 min por pessoa)
1. Sem explicar o programa. Diga só: "importe este vídeo e faça um clipe vertical com legenda e exporte". O vídeo é da própria pessoa/uma amostra sua (nada sai do computador).
2. Quem observa **não ajuda** (anota quando a pessoa pede ajuda e o que perguntou). Cronometre cada tarefa; conte cliques e erros (clicou no lugar errado, desfez, fechou uma tela sem querer).
3. No fim, 4 perguntas (nota 1–5): foi fácil? soube o que fazer em seguida? confiou que a exportação sairia como a prévia? usaria de novo?

## Tarefas (uma linha por pessoa e tarefa na planilha de coleta abaixo)
| # | Tarefa | Sucesso sem ajuda? | Tempo (s) | Cliques | Erros | Pediu ajuda? | Onde se confundiu | Nota 1–5 |
|---|---|---|---|---|---|---|---|---|
| T01 | Abrir o Hook's e achar onde importar | | | | | | | |
| T02 | Importar um vídeo | | | | | | | |
| T03 | Selecionar um trecho (abrir um corte) | | | | | | | |
| T04 | Ajustar o início/fim de um corte | | | | | | | |
| T05 | Inserir legenda (colar texto ou importar arquivo) | | | | | | | |
| T06 | Corrigir uma frase da legenda | | | | | | | |
| T07 | Ajustar o enquadramento (zoom/posição) | | | | | | | |
| T08 | Conferir a prévia e dizer se está como queria | | | | | | | |
| T09 | Salvar/sair e reabrir o projeto | | | | | | | |
| T10 | Exportar e achar o arquivo gerado | | | | | | | |

## O que já é medido automaticamente (apoio, não prova)
Estrutura do fluxo Importar → Editar → Conferir → Exportar (e2e `etapa_*`), quantidade de controles por seleção (`inspetor_*`: 4–8), teclas para chegar a cada ação pelo Ctrl+K (média 1,6 letras), tempo de abrir o Estúdio, de gerar a prévia e de arrastar na timeline (`docs/BASELINE.md`).

## Critério para chamar uma tarefa de "intuitiva"
≥ 80% das pessoas concluem **sem ajuda** e sem mais de 1 erro, com 5+ pessoas de perfis diferentes (iniciante absoluto, casual, experiente, computador fraco, quem comete erros). Abaixo disso a tarefa vira item de correção, não de nova função.
