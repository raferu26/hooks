# Checkpoint V6.4 — 0.8.4-beta.1

Branch `v6.4`, criada a partir da V6.3 sem modificar os checkpoints anteriores.

## Vídeo por link

- O usuário escolhe `Link público` ou `Arquivo deste computador` no modo vídeo.
- Links são testados pelo Streamlink e processados pelo mesmo pipe resiliente usado em lives.
- O modo salvo na sessão continua sendo `video`, portanto a exportação não exige webcam e usa quadro integral sobre fundo vertical desfocado.
- Quando o vídeo termina, o pipe fecha a sessão e libera o último contexto para análise.
- O usuário não baixa nem converte o arquivo manualmente; os segmentos recebidos são preservados para transcrição, revisão e exportação.

## Limite físico

Analisar remotamente não significa zero transferência ou zero disco. O vídeo precisa chegar à máquina e os segmentos de trabalho ocupam espaço, como acontece com uma live.
