# Dependências: o que é necessário, o que é de IA, o que sai (medido)

Medições de 24/11/2026. **Windows**: tamanho dos wheels (`pip download --platform win_amd64 --python-version 3.11`). **Instalado**: Linux, Python 3.11.18 + NumPy 1.26.4, soma dos arquivos de cada pacote (a ordem de grandeza vale para o Windows, os números exatos não). Referência = `requirements.txt`; variante = `requirements-sem-ia.txt` (experimental, isolada).

| | Referência | Variante sem IA | Redução |
|---|---|---|---|
| Wheels Windows (cp311 win_amd64) | 345 MB · 69 arquivos | **85 MB · 33 arquivos** | **−75%** |
| Instalado (Linux, py3.11) | 1 322 MB · 38 pacotes só da referência = 1 145 MB | **321 MB** | **−76%** |

## Cada dependência declarada
| Dependência | Necessária no produto sem IA? | Pertence a IA? | Decisão | Recursos afetados | Substituto convencional |
|---|---|---|---|---|---|
| **numpy** (1.26.4) | Sim | Não | fica (fixo em 1.26.4 para casar com o Windows da referência) | sinais, QC, capas, cor, rastreio | — |
| **opencv-contrib-python** 4.10.0.84 (189 MB instalados) | Parcial | Não é IA, mas traz **dados pré-treinados** (cascatas Haar) | **trocada** por `opencv-python-headless` na variante: o código usa só `cv2` básico (resize, Canny, Laplaciano, fluxo óptico LK, VideoCapture); nenhum módulo contrib/dnn (verificado por busca) | capa, correção de cor, rastreio, QC visual | headless cobre; Haar continua disponível no `cv2.data` e **ainda é usado** em reenquadramento/"quem fala"/webcam (item de remoção do plano) |
| **pillow** | Sim | Não | **declarada** (antes vinha por tabela via matplotlib/mediapipe: dependência escondida; `brand`, `cover`, `graphics2d`, `imagerecipe`, `keying` a usam) | marca, capas, gráficos, chave de cor | — |
| **streamlink** 8.6.3 | Sim | Não | fica | captura de lives | — |
| **yt-dlp[default]** | Sim | Não | fica | vídeo/música por link | — |
| **cryptography** | Sim | Não | fica | licença assinada | — |
| **opentimelineio** | Opcional | Não | incluída na variante (o app já avisa se faltar) | arquivo `.otio` do pacote | — |
| **faster-whisper** → ctranslate2 (89 MB), av (137 MB), onnxruntime (76 MB), tokenizers, huggingface-hub, hf-xet, sentencepiece, pyyaml, tqdm, filelock, fsspec… | **Não** | **Sim**: transcrição; baixa modelos do Hugging Face | **fora da variante** | legenda **automática**, 2ª passada, ranking por fala, ganchos/títulos/contexto por texto | legenda por texto colado/arquivo + sincronização manual (PR #3); sem substituto equivalente para transcrição |
| **mediapipe** → jax/jaxlib (341 MB), scipy (114 MB), matplotlib, ml-dtypes, protobuf, absl, flatbuffers, sounddevice… | **Não** | **Sim**: landmarks faciais; baixa `.task` | **fora da variante** | movimento facial no ranking; webcam automática (cai no Haar clássico pré-treinado) | marcar a webcam à mão; movimento por diferença de quadros |
| RNNoise (`.rnnn` baixado) / Ollama | Não | Sim | não estão no `requirements`; código mantido como opcional | limpeza "neural", títulos por LLM | cadeia DSP (afftdn+afwtdn); heurísticas |

## O que a variante deixa de fazer (perda funcional registrada)
1. **Legenda automática por fala**: some. Alternativa: texto colado/importado + distribuição por energia (estimada) + toques.
2. **Webcam automática e movimento facial**: some o sinal facial do ranking; a webcam é marcada à mão.
3. **Segunda passada de legenda, ganchos/títulos por texto falado, contexto/episódios**: dependem de transcrição; só funcionam com legenda importada.
4. Em perfis novos o modo é `sem_ia` (o interruptor é o arquivo `VARIANTE_SEM_IA`); perfis existentes não são alterados.

## Validação desta variante (Linux, Python 3.11 + NumPy 1.26.4)
- Suíte completa executada **sem** as bibliotecas de IA: resultado em `docs/BASELINE.md` §6 e `docs/CHANGELOG.md`.
- `python -m liveclips selfcheck` no pacote extraído: importa todos os módulos, codifica, desenha legenda com libass, sobe o servidor.
- **Não** comprova o Windows: wheels e binários do Windows só se provam lá (roteiro W01–W10).

## Ainda não removido (para a versão comercial final)
Haar (OpenCV, `media.py`/`speaker.py`/`camera_detect.py`), código de MediaPipe/Whisper/RNNoise/Ollama no repositório (guardado por `tests/test_sem_ia_guard.py`). Fases 3–5 de `docs/SEM_IA_MIGRACAO.md` aguardam substitutos validados.
