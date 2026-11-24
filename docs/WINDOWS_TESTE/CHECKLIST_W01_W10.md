# Checklist do teste no Windows (W01–W10)
Preencha: **OK**, **FALHOU** ou **NÃO TESTEI**, e anote tempo/observação. Nada aqui foi validado no Windows antes: você é o primeiro teste.

**Seu computador** (o COLETAR_RELATORIO preenche isto sozinho; anote só o que souber): Windows ____ · CPU ____ · RAM ____ · placa de vídeo ____ · disco (SSD/HD) ____

| # | O que fazer | Esperado | Resultado | Observações (tempo, erro, o que estranhou) |
|---|---|---|---|---|
| W01 | Rodar `INSTALAR_TESTE.bat` | Termina sem erro; mostra "Resultado: N/N passos OK" no autoteste; atalho Hook's criado | | |
| W02 | Abrir o atalho Hook's | Janela própria abre em poucos segundos, **sem janela preta de console**; "Build" aparece no rodapé da barra lateral (anote o texto) | | tempo para abrir: ___ s |
| W03 | Importar **um vídeo real seu** (Adicionar → Arquivo do computador) | Análise termina; aparecem cortes sugeridos ou o vídeo para criar corte manual | | duração do vídeo ___ · tempo de análise ___ |
| W04 | Abrir um corte no Estúdio, mudar início/fim, **criar** um corte manual, **cortar** um trecho (selecionar + `C`), desfazer (`Ctrl+Z`) | Tudo responde na hora; desfazer volta | | |
| W05 | **Timeline**: arrastar blocos, zoom (+/−), snap (grudar; segurar `Alt` desliga), recolher a timeline (`F`), arrastar o divisor, `Ctrl+K` | Fluido, sem travar; atalhos funcionam | | |
| W06 | **Legendas**: em Legendas → "Legenda a partir de texto…", colar 3–5 frases, **Distribuir pelo áudio**, depois **marcar início ao tocar** (Enter), corrigir uma frase, arrastar um bloco | Frases aparecem na prévia na hora; o diálogo avisa que os tempos são **estimados** | | achou intuitivo? 1–5: ___ |
| W07 | **Prévia**: gerar/atualizar a prévia (`P`); comparar a legenda da prévia com a do vídeo exportado depois | Prévia em segundos; legenda parecida | | tempo da prévia: ___ s |
| W08 | **Exportar** o corte nos modos Rápido, Equilibrado, Qualidade e Entrega (um por vez) | Arquivos 1080×1920 abrem em outro player; áudio sincronizado; legenda e título no lugar | | tempos: R ___ E ___ Q ___ En ___ · imagem boa? |
| W09 | `MEDIR_DESEMPENHO.bat` e, durante uma exportação real, olhar o **Gerenciador de Tarefas** (CPU, memória, GPU) | Gera `relatorio_desempenho.json` | | CPU % ___ · RAM ___ · GPU % ___ |
| W10 | "Encerrar Hook's", reabrir (projetos continuam?), rodar `AUTOTESTE.bat`, depois `COLETAR_RELATORIO.bat` | Projetos voltam; relatório criado em `RELATORIOS` | | |

## Perguntas rápidas (quem nunca usou o Hook's responde sem ajuda)
1. Consegui importar, cortar, legendar e exportar sem pedir ajuda? ____
2. Onde me perdi? ____
3. O que achei lento? ____
4. O que achei bonito/feio na legenda exportada, em comparação com a prévia? ____
