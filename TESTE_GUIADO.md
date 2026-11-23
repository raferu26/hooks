# Primeiro teste da 0.12

Comece com duas lives. A capacidade de cinco capturas existe no programa; a quantidade que o seu PC consegue acompanhar precisa ser medida.

1. Extraia numa pasta nova **LiveClips V7** e execute **INSTALAR.bat**. Confirme que Python, Streamlink, FFmpeg, ffprobe e o modelo facial aparecem como `[OK]`.
2. Abra **ABRIR_LIVECLIPS.bat**, clique em **Backup** e confira um ZIP em `C:\LiveClips\backups`.
3. Cadastre **CORINGA** e um segundo streamer. Em cada perfil, mantenha inicialmente **Base**, **480p** e reserva de disco de pelo menos **3 GB**.
4. Inicie a primeira live pelo perfil correto, com a opção de análise marcada. Aguarde aparecerem segmentos completos.
5. Abra o segundo perfil e inicie a outra live. Confira **Lives em captura · 2/5** e os nomes dos dois.
6. Use **Abrir pasta** em cada sessão e confira que os novos arquivos estão dentro do streamer correspondente. A linha do processamento indica o streamer atendido.
7. Deixe rodar alguns minutos. O contexto aguarda o próximo segmento completo e depois a transcrição; um aviso de espera, sem erro, pode ser normal.
8. Quando houver sugestões, gere a prévia. Procure um corte que atravesse dois arquivos e confirme que imagem e áudio começam imediatamente, sem perder segundos.
9. Ajuste início/fim, gere outra prévia e aprove. Aguarde **Pronto** e confira `cortes\PASTA_DO_CORTE\clipe.mp4`, vídeo vertical e sincronismo.
10. Troque a prioridade ou o estilo do perfil. Confirme o aviso de reclassificação; revisados/exportados devem permanecer e as sugestões novas devem surgir ao retomar a análise.
11. Em uma sessão concluída, use **Arquivar** e depois **Reativar**. Confirme que nenhum original ou corte foi apagado.
12. Encerre somente a primeira live. Confira que a segunda continua criando segmentos e que a primeira ainda pode terminar a análise.
13. Rejeite uma sugestão indesejada. Confirme que ela não reaparece e que um momento aprovado não gera outra entrega na retomada.
14. Encerre a segunda live, espere tarefas em andamento terminarem e feche com **Ctrl+C**. Reabra e confira perfis, revisões, backups e arquivos.
15. No perfil, alterne a prioridade entre humor, opinião, história e equilíbrio. Retome a análise e confira se as sugestões automáticas pendentes são reclassificadas sem apagar cortes revisados.
16. Teste as sensibilidades comportamentais precisa, equilibrada e sensível. Confira que os motivos descrevem movimentos observáveis e nunca afirmam conhecer a emoção da pessoa.
17. Use uma gravação sem picos claros. Se aparecer uma oportunidade exploratória, confirme o aviso de baixa confiança e que existem no máximo cinco pendentes por sessão.
18. No estilo criativo, gere duas prévias do mesmo intervalo depois de mudar o plano de edição. Confirme que a segunda renderização não reutiliza o arquivo da primeira.
19. Percorra as quatro etapas exibidas no topo. Confira que a etapa ativa muda conforme a gravação é analisada, revisada e exportada.
20. Abra **Mais opções** e **Gerenciar**. Confira que as funções anteriores continuam acessíveis, sem ocupar a área principal.
21. Reduza a janela até a largura de um celular. Confira leitura, botões, filtros, lista de cortes e editor sem rolagem horizontal obrigatória.
22. Abra **Perfil e estilo**, percorra os treze presets e dê play em cada demonstração. Confira nome, ritmo, intensidade e indicação de uso.
23. Escolha Podcast ou Gameplay e abra uma sugestão. Confira o plano de edição e desligue uma decisão. Salve, reabra e confirme que sua escolha permaneceu.
24. Num trecho com pausa longa entre palavras, confira que o agente propõe encurtar somente a parte central da pausa. A fala anterior e a seguinte não podem ser cortadas.
25. Ative música sem confirmar autorização; o perfil deve recusar. Depois use uma música autorizada, exporte e confira voz audível, trilha baixa e registro no manifesto.
26. Exporte um corte com imagem ou efeito fornecido. Confira sincronismo, duração e a comparação lado a lado entre original e editado.
27. Escolha um corte de reação com fala após o pico. Confira preparação, clímax e frase final; a frase final não deve pertencer a outro assunto.
28. Se surgirem 30, 45 e 60 segundos, clique em cada versão e gere a prévia. Confira início e fim da fala. Em contexto curto, confirme que o programa não inventa uma alternativa.

Se uma origem for movida, use **Localizar original** e selecione o arquivo/pasta correto. O LiveClips só aceita o novo local quando os bytes conhecidos correspondem aos SHA-256 registrados.

Se houver erro, anote o streamer e a mensagem. Cada sessão guarda `captura.log`; **Atividade recente** ajuda a identificar a causa. Preserve os originais para investigar.

Depois de confirmar duas lives, aumente para três e observe atraso da análise, uso do PC e espaço antes de chegar a cinco. As capturas funcionam em paralelo, mas tarefas pesadas compartilham uma fila.
27. V8: no perfil, abra os treze estilos e confira que a demonstração agora mostra cor, zoom e legenda próprios de cada um.
28. V8: deixe a legenda em **Automática**, exporte um corte em Hype e outro em Podcast e compare a legenda, a cor e o formato do zoom.
29. V8: assista a um corte com legenda e confirme que o destaque da palavra não pisca entre as palavras.
30. V8: desligue **Cor do estilo**, exporte de novo e confirme que a imagem fica sem a correção.
31. V8: abra `manifesto.json` do corte e confira `pipeline`, `loudness` e `look`. Se aparecer `fallback`, envie o texto desse campo.
27. (0.12) Em um perfil, cadastre logo, abertura e uma fonte do kit de marca. Exporte e confira posição do logo, abertura/encerramento e fonte da legenda.
28. (0.12) No estúdio, edite uma legenda e um título e veja a mudança ao vivo na prévia; mude zoom ou layout e confirme que pede **Aplicar mudanças**.
29. (0.12) Importe um CSV de desempenho: confira a prévia antes de confirmar.
30. (0.12) Gere um diagnóstico (GERAR_DIAGNOSTICO.bat) e confirme que o ZIP não contém vídeos nem banco.
31. (0.12) Rode o benchmark com o seu gabarito de pelo menos 20 momentos.
32. (0.13) Exporte um corte e abra, na pasta do clipe, `plano.json` e `revisao.json`. Confira que a duração do plano bate com o vídeo e leia o resumo da revisão.
33. (0.13) No Estúdio, aba **Por quê**: confira o estado de entrega, as decisões do agente e os trechos protegidos. Clique em **Aprovar esta versão** e depois em **Montar pacote**; o estado deve virar "pronto para publicar" e nada deve ser publicado.
34. (0.13) Depois de aprovar, mude qualquer byte do vídeo exportado e recarregue a aba **Por quê**: o estado deve voltar para "pronto para revisão".
35. (0.13) Na aba **Agente**, peça "replay de 12 a 15 em câmera lenta" e depois "desfaz". Confira que a prévia só muda quando você clica em **Aplicar mudanças**.
36. (0.13) Peça "corta de 5 a 25" em um corte curto: deve pedir confirmação antes de aplicar.
37. (0.13) Em Ajustes → Agentes, adicione um termo ao vocabulário, exporte e veja se a legenda usa a grafia correta. Depois use **Esquecer** e confirme que ele sai.
38. (0.13) Salve um corte removendo um zoom ou um efeito sonoro. Em Ajustes → Agentes, confira que isso virou uma memória **local**, e não uma regra do streamer.
39. (0.13) Importe um vídeo sem áudio ou com taxa de quadros variável e confira o aviso na importação.
40. (0.13) Troque o modo de qualidade para **Qualidade**, exporte o mesmo corte e compare tempo e tamanho com o modo **Equilibrado**.
41. (0.13) Abra o `linha_do_tempo.otio` em um editor que leia OpenTimelineIO e confira a ordem e a duração dos trechos (não foi testado em editor real).


## 0.14 — conferindo a leitura de contexto
1. Deixe a análise rodando numa sessão com falas como "eu garanto que passo essa fase" seguidas de uma tentativa.
2. Abra um corte e vá em **Estúdio → Por quê**: veja "O que foi entendido do trecho". Cortes com promessa sem desfecho aparecem como **aguardando contexto**.
3. Em **Marcar momento perdido**, informe início e fim (em segundos da sessão) de algo que o programa não sugeriu.
4. Reações sem fala aparecem como **exploratório**. Elas são hipóteses: confira antes de aprovar.
