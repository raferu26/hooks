# Estúdio 0.11 — o que mudou, como testar e o que ainda é limite

## Novo
- Estúdio de edição (fala + prévia + ferramentas + linha do tempo com trilhas: Fala, Cortes, Zoom, Títulos, Extras, Ritmo, Imagens, Música).
- Layouts de live: câmera em cima / dividido / jogo com câmera no canto (4 cantos) / só câmera. Vídeos: ajustar / preencher com foco horizontal.
- Velocidade (0,5× a 4×; câmera lenta por duplicação de quadros, sem interpolação), congelar imagem, 6 efeitos sonoros próprios, imagens e memes (PNG/JPG/WEBP) com posição, tamanho e opacidade.
- Música por link (yt-dlp) ou arquivo; batidas, volume sob a voz.
- Limpeza de voz (opcional), título e abertura (teaser), nota de gancho.
- Formatos 1:1, 4:5 e 16:9 junto do vertical (legenda reposicionada por formato).
- Pacote de publicação (publicacao.txt) e desempenho por clipe; ranking que aprende (peso limitado a 0,80–1,25).
- Ajustes: modelo de voz (tiny→turbo), GPU automática, codificador de vídeo, hashtags fixas, Ollama opcional, botão "Testar este computador".

## O que foi testado aqui (mídia sintética)
- Renderização real com FFmpeg dos layouts, velocidade, congelar, imagens, SFX, formatos extras, rascunho e exportação final.
- API, banco, aprendizado e a interface no Chrome (Playwright), do Estúdio até a exportação 1080×1920 + 1080×1080 + 1920×1080.

## O que só você consegue validar
1. **Música por link do YouTube**: o ambiente de teste não alcança o YouTube; só foi testado com download simulado. Precisa de yt-dlp atualizado e de Deno ou Node no PC (o INSTALAR.bat tenta instalar). Se falhar: `pip install -U "yt-dlp[default]"` ou envie o arquivo de áudio.
2. **Música comercial no TikTok** pode ser silenciada ou reivindicada. O sistema só confirma que você declarou ter o direito.
3. **Placa de vídeo**: transcrição CUDA exige cuBLAS/cuDNN instalados; NVENC/QuickSync/AMF não puderam ser testados. As opções de QSV/AMF são [Provável]. O padrão é o processador e há volta automática se a placa falhar. O modelo "turbo" exige faster-whisper recente.
4. **Ollama**: caminho implementado, não testado sem o Ollama instalado. Só reordena, nunca cria nem apaga cortes.
5. **Qualidade real de conteúdo**: tudo foi verificado com vídeo/áudio sintéticos. Faça o TESTE_GUIADO.md com uma live ou podcast de verdade.

## Limites conhecidos
- Não publica nem agenda no TikTok (a plataforma exige fluxo próprio); entrega o pacote pronto.
- Câmera lenta sem interpolação de quadros.
- A aba de ferramentas quebra em 3 linhas quando todas as abas aparecem.
- Sem final que "fecha o loop" automaticamente.
