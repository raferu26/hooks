# Checkpoint V6.1 — 0.8.1-beta.1

Branch local `v6.1`, criada a partir do checkpoint V6 `0.8.0-beta.1`. O commit-base da V6 permanece intacto na branch local `main`.

## Incluído

- preferência de captura até 1440p com alternativas reais do Streamlink;
- resolução vertical 1080×1920;
- preservação de fontes até 2560×1440 na montagem entre segmentos;
- preservação de 60 fps quando a fonte real tem pelo menos 50 fps;
- escala Lanczos e codificação H.264 High com CRF 18/preset medium;
- indicação no painel da resolução real e dos pixels disponíveis no recorte da webcam;
- ranking com humor, tensão, desfecho e crescendo de áudio;
- deduplicação conservadora de recodificações por imagem, transcrição e duração;
- proteção de duração e resolução após a renderização.

## Validação neste ambiente

- 72 testes automatizados da primeira etapa da V6.1 passaram.
- O ambiente de desenvolvimento desta sessão não possui FFmpeg/ffprobe acessíveis, portanto a renderização sintética 1440p → 1080×1920 ainda precisa do teste de integração no computador que executará o LiveClips.
- Captura real 1440p depende de a plataforma disponibilizar essa resolução para a live específica.

## Rollback

Trocar da branch `v6.1` para `main` retorna exatamente ao pacote V6 importado. O ZIP original e sua cópia de segurança não foram alterados.
