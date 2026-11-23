# Checkpoint V6.8 — 0.8.8-beta.1

## Objetivo

Evoluir o agente de corte sem substituir a base confiável da V6.7. Esta versão preserva captura por link, YouTube, Twitch, vídeo/podcast, exportação, backups e recuperação já existentes.

## Entregue

- taxonomia editorial ampliada para nove tipos de momento;
- notas narrativas de gancho, preparação, clímax e encerramento;
- fusão conservadora de transcrição, áudio, vídeo, chat e comportamento observável;
- Face Landmarker local e opcional, com fallback seguro quando indisponível;
- MediaPipe fixado em uma versão anterior à telemetria observada nas distribuições mais recentes;
- linha de base relativa à pessoa para reduzir falsos picos faciais;
- sensibilidade comportamental e vocabulário por streamer;
- oportunidades exploratórias limitadas e rotuladas como baixa confiança;
- aproximação criativa sutil somente com confirmação multimodal;
- assinatura de renderização inclui plano de edição e versão do renderizador;
- tentativas extras e IPv4 no Streamlink para reduzir falhas transitórias.

## Limites honestos

O agente observa movimentos; não lê mente, personalidade ou emoção verdadeira. Webcam pequena, baixa taxa de quadros, compressão e rosto parcialmente oculto reduzem a precisão. Traduções, conteúdo sério, direitos autorais e sugestões de baixa confiança continuam exigindo revisão humana.

## Rollback

- `v0.8.7-beta.1`: versão estável anterior.
- `v6.8-agent-core-pre-home-merge`: núcleo da V6.8 antes do reaproveitamento seletivo.
- `v0.8.8-beta.1`: entrega deste checkpoint.

Nenhum banco, perfil, vídeo ou modelo local faz parte do código versionado.
