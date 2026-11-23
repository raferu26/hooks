# Checkpoint V6.2 — 0.8.2-beta.3

Branch local `v6.2`, criada a partir da tag intacta `v0.8.1-beta.1`.

## O que entrou

- teste de link/qualidades antes da captura;
- Twitch com negociação H.264/H.265 e captura oficial opcional do chat;
- picos de chat calculados por volume, pessoas distintas, termos reativos e emotes;
- movimentos faciais breves por regiões, sem classificação inventada de emoção;
- fusão multimodal: chat e rosto só pontuam quando outra pista confirma;
- aprendizado conservador por streamer a partir de aprovações e rejeições;
- versão explicável do seletor `v6.2-narrativa-chat-rosto-aprendizado`;
- 77 testes automatizados aprovados.
- correção do layout vertical: webcam fixa nos 640 px superiores e jogo nos 1280 px inferiores.
- primeira versão do controle de qualidade editorial, presets por streamer, confirmação humana e ficha automática de créditos.

## Rollback

A V6.1 permanece na branch `v6.1` e na tag `v0.8.1-beta.1`. Voltar para essa tag restaura exatamente o checkpoint anterior. Gravações, banco e exports locais não fazem parte do código e devem continuar preservados separadamente.

## Próxima etapa segura

Validar com uma live Twitch real: comparar sugestões com e sem chat conectado, aprovar/rejeitar pelo menos quatro exemplos do mesmo streamer e conferir se os pesos aprendidos melhoram a ordem sem ocultar as razões.
