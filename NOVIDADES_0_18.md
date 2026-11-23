# Hook’s 0.18.0-beta.1 — o que entrou (módulos P00–P27)

Estado por módulo, arquivos, testes e limites ficam em `PROGRESSO_P00_P27.md`. Tudo foi verificado com mídia sintética em Linux; **nada foi testado no Windows nem em live real**. Todos os recursos novos nascem **desligados** (exceto a capa), então o comportamento anterior continua igual até você ligar em Ajustes.

## Como usar o modo sem IA
1. Ajustes → Avançado → Modo de análise → **Sem IA**.
2. Em “Marcadores e legendas prontas”, marque os momentos (atalho “Marcar este momento agora”, ou importe `.json/.csv/.txt`) e, se tiver, importe a legenda (`.srt/.vtt/.ass`).
3. Ajustes → Webcam e quadro: marque a webcam uma vez (e, se quiser rastreio, a região a acompanhar).
4. Ajustes → Edição automática: ligue o que quiser (pausas, replay, voz, cor, capa, formatos extras, gráficos). Depois disso cada corte sai pelo mesmo caminho: marcador → plano → revisão → render → qualidade → entrega.
O modo não carrega nenhum componente de IA. Cortes por marcador vêm da sua marcação; picos técnicos são só heurística, sempre rotulados, e nunca são publicados sozinhos.

## O que o replay automático faz (e não faz)
Em corte com momento marcado, repete a ação e o desfecho (1,5 s antes a 2,5 s depois do marcador) logo após o trecho original, em câmera lenta e mudo (ou em velocidade normal com o som original). No máximo 1 por corte, até 8 s e 25% do corte, respeitando o limite do formato. Se não couber, atravessar uma pausa cortada ou você já tiver replay no projeto, é recusado e o motivo fica no plano. Não escolhe “o melhor momento”: usa só o que você marcou.

## Recuo para versão simples
Se o render falhar, o Hook’s refaz sem os módulos opcionais (voz, cor, LUT, fades, câmera lenta interpolada, estabilização, gráficos) e, se preciso, sem a música/efeito/imagem automáticos; grava o motivo no manifesto e o controle de qualidade avisa. Recurso que você escolheu no Estúdio não some em silêncio.

## O que continua fora do alcance sem IA
Transcrever fala arbitrária, reconhecer emoção ou sarcasmo, achar o momento mais engraçado pelo volume, remover fundo por significado, reenquadrar sem região inicial, separar vozes perfeitamente, ampliar imagem com rede neural, gerar imagem, voz, texto ou música.

## Limites conhecidos desta versão
- Transições: só fade de áudio nas emendas (sem xfade de vídeo nem cortes J/L).
- Proxy de edição: não há; existe cache por conteúdo da análise técnica.
- Estabilização: uma passada (`deshake`); sem vidstab de duas passadas.
- Pacote OTIO validado com a biblioteca OpenTimelineIO, não em Premiere/Resolve/Final Cut/CapCut.
- Gráficos 2D usam a fonte do sistema e não têm editor por item no Estúdio.
- Replay automático não aparece como item editável no Estúdio.
- Receitas de imagem em lote só pela API (sem tela).
