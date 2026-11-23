# Pistas de trabalho (0.15.0-beta.1)

Objetivo: gravar até 4 lives ao mesmo tempo e continuar editando e exportando sem fila única.

## O que mudou
- O engine tem uma **pista** (um trabalhador) para cada tipo de trabalho: análise das lives, edição/prévias, exportação (1 ou 2) e revisão de legenda. A captura já era separada.
- Exportar não segura mais a análise nem a prévia que você está editando. Nenhum corte é processado por duas pistas ao mesmo tempo (reserva por corte).
- O modelo de voz é único: uma transcrição por vez. A análise das lives passa na frente da revisão de legenda.
- **Capacidade medida:** o programa mede quantos segundos leva para transcrever cada segundo de live. Com 2+ lives abertas e `lives × medida > 0,8`, mostra o aviso "seu computador não acompanha".
- Cada live mostra "análise N min atrás da live" quando há 3+ pedaços esperando.
- **Checagem antes de gravar** (tela Adicionar): webcam marcada, transcrição em GPU/CPU, espaço em disco, ferramentas, limite de lives.
- Aviso permanente em Cortes quando a webcam não está marcada; o erro de prévia traz o botão "Marcar a webcam".
- Último pedaço curto de uma live encerrada (menos de 128 KB, mas com 3 s ou mais de vídeo legível) passa a ser registrado.
- Pacote de diagnóstico: inclui modo, pistas, capacidade medida, situação das sessões e `captura.log` das últimas 8 sessões.
- Ajustes → Sistema → Desempenho: pistas separadas (padrão) ou pista única (modo antigo); 1 ou 2 exportações ao mesmo tempo.

## Limites (honestos)
- Tudo testado com modelo falso e vídeos gerados; nada validado com 4 lives reais, GPU ou Windows.
- Em processador fraco (ex.: i7-3770, 4 núcleos), as pistas rodam em paralelo mas dividem os mesmos núcleos: nenhuma para, mas todas ficam mais lentas. A transcrição continua sendo o gargalo com várias lives.
- Mudar o modelo de voz no meio de uma live faz reanalisar o que já foi gravado.
- Duas exportações ao mesmo tempo só compensam com placa NVIDIA.

## Webcam automática (beta.3)
- Quando o streamer não tem webcam marcada, o Hook's tenta achar sozinho com os primeiros pedaços da live (1º, 5º e 10º pedaço, até 3 tentativas).
- Como: tira ~12 quadros, procura um rosto que apareça no mesmo lugar em vários quadros (MediaPipe; se não der, o detector do OpenCV), estima o retângulo da câmera e encosta as bordas na moldura.
- Confiança **alta** e nada analisado ainda: aplica sozinho (aparece nos eventos). Confiança **média**, ou análise já feita: vira um aviso em Cortes com "Usar esta webcam / Ver e ajustar / Dispensar" (aplicar refaz a análise).
- Ajustes → Webcam e quadro → "Localizar a webcam automaticamente" preenche o retângulo para você conferir e salvar.
- Correção: a prévia e a exportação usavam uma cópia antiga do perfil (sem webcam) e continuavam falhando depois de marcá-la. Agora usam a webcam atual.
- Limite: é heurístico e **não foi validado com rostos e lives reais** (só com quadros sintéticos e detector simulado). Sempre confira o retângulo.
