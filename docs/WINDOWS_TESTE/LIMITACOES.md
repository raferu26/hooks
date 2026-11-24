# Limitações conhecidas desta versão de teste

## Do teste
- **Nunca foi executada no Windows** antes do seu teste. Foi verificada em Linux (Python 3.11, mesmas versões de bibliotecas) e por análise estática.
- Não é um instalador `.exe`: é uma pasta com scripts `.bat` e um ambiente Python criado na sua máquina (offline, a partir da pasta `wheels`). O `winget` pode baixar Python 3.11 e FFmpeg se faltarem.
- **GPU (NVENC/QSV/AMF)**: nunca testada em placa real. O autoteste mostra quais codificadores de GPU realmente funcionam; se um falhar, o app volta para a CPU.
- Só mídia sintética foi usada nos testes automáticos. **Vídeos reais** e a qualidade percebida do áudio/legenda ainda não foram avaliados.
- Fontes: a legenda usa **Arial**. Se o seu FFmpeg não achar a fonte, o autoteste "legenda_libass" avisa.
- A medição de desempenho do pacote usa um clipe **sintético**, não o seu vídeo.

## De recursos (variante sem IA)
- **Legenda automática (transcrição)**: **não existe** nesta variante (e não terá substituto automático). Use "Legenda a partir de texto…" (colar texto, distribuir pelas pausas, marcar com Enter) ou importe SRT/VTT/ASS. Os tempos por energia são **estimados**, não transcrição nem alinhamento fonético.
- **Reconhecer rosto/webcam e movimento facial**: não instalado. Marque a webcam à mão. (O código ainda contém o detector de rosto clássico pré-treinado do OpenCV — Haar — em enquadramento dinâmico e "quem fala"; ele **está na lista de remoção**, ainda não removido.)
- **Limpeza de voz "neural" (RNNoise)** e **Ollama**: não instalados; a limpeza usa filtros clássicos do FFmpeg (afftdn + afwtdn).
- **Sugestão de cortes**: por energia de áudio, movimento, marcadores e sinais técnicos (rotulada como heurística); não entende o conteúdo.
- Importar vídeo do **YouTube** exige Deno/Node (não incluído) e não foi testado com o YouTube real.
- `voice_preset` continua **desligado** por padrão (decisão aguardando teste de áudio com amostras reais).

## O que ainda depende de modelos de IA na versão de referência (não incluído aqui)
faster-whisper (transcrição), MediaPipe (movimento facial e webcam automática), RNNoise (opcional), Ollama (opcional). Plano de remoção: `docs/SEM_IA_MIGRACAO.md` do repositório.

## Layout de reação (novo na 0.20.0-beta.2, experimental)
- Testado só em Linux, com mídia sintética. **Não** foi testado com o vídeo real de reação (Coringa/Caiox), no Windows, nem com GPU.
- Webcam em **arquivo separado** e escolha/deslocamento de áudio: não existe ainda. As duas regiões vêm do mesmo vídeo.
- Zoom automático fica desligado quando há composição; formatos 1:1, 4:5 e 16:9 não usam a composição (só 9:16).
- As sugestões de troca de layout são **só movimento de pixels** (conteúdo parado + webcam se mexendo): não sabem se o vídeo foi pausado.
- A prévia imediata (miniatura) serve para posicionar; a nitidez real é a da exportação.
- Roteiro de teste: `ROTEIRO_LAYOUT_REACAO.md`. Detalhes técnicos: `docs/COMPOSICAO_REACAO.md`.
