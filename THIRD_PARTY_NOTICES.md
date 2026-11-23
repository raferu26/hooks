# Créditos de terceiros

## ReaCut (editor de vídeo open source) — licença MIT

O módulo `liveclips/motion.py` e partes do editor da V8 foram **inspirados** na arquitetura do
[ReaCut](https://github.com/Xiangyu-CAS/rea-capcut): keyframes com easing compilados em expressões
do FFmpeg, animação de entrada/permanência dos textos, filtros de cor por contraste/saturação e a
montagem de todos os trechos num único filtergraph. O código foi **reescrito em Python** para o
LiveClips; nenhum arquivo, fonte, imagem ou mídia do ReaCut foi copiado para este pacote.

Aviso de licença do projeto original:

```
MIT License

Copyright (c) 2026 ReaCut contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

O ReaCut é um projeto independente e não tem relação com o CapCut/Jianying.
FFmpeg e libass são ferramentas externas executadas como programas separados, com suas próprias licenças.


## yt-dlp (download de áudio por link)

O LiveClips usa o [yt-dlp](https://github.com/yt-dlp/yt-dlp) como biblioteca para baixar somente o áudio de links informados pelo usuário. Licença: Unlicense (domínio público). Instalado por `requirements.txt`; nenhum código foi copiado para este pacote. Os componentes do extra `[default]` têm licenças próprias (por exemplo, yt-dlp-ejs: Unlicense, MIT e ISC). O download de músicas é responsabilidade do usuário: confira os direitos de uso e os termos da plataforma.


## RNNoise (modelo de redução de ruído opcional)

Se você ativar a redução de ruído neural, o LiveClips baixa uma vez o arquivo `bd.rnnn` ("beguiling-drafter") do repositório [GregorR/rnnoise-models](https://github.com/GregorR/rnnoise-models), confere o SHA-256 e o guarda em `models/`. O modelo não vai dentro do pacote. O autor declara que os arquivos de modelo não têm restrição de direitos autorais; confirme no repositório se isso for importante para o seu uso. O filtro `arnndn` faz parte do FFmpeg, executado como programa separado, com licença própria.

## Fontes do kit de marca

As fontes (.ttf/.otf) que você colocar na pasta `fontes` são suas: o LiveClips não inclui nem distribui nenhuma. Confira a licença de cada fonte antes de usá-la em vídeos publicados.

## OpenTimelineIO (apenas nos testes)

O arquivo `linha_do_tempo.otio` é escrito pelo próprio LiveClips, sem dependência. Os testes automáticos usam a biblioteca `opentimelineio` (Apache-2.0) apenas para conferir que ela consegue ler o arquivo; sem ela instalada, esse teste é ignorado. Nada dela é distribuído com o programa.

## cryptography (assinatura Ed25519 da licença)

O servidor `hooks_cloud` e o módulo de licença do app usam a biblioteca [cryptography](https://github.com/pyca/cryptography) para assinar e verificar a licença (Ed25519). Instalada por `requirements.txt`; nenhum código foi copiado para este pacote. A biblioteca é distribuída sob licença dupla Apache-2.0 ou BSD-3-Clause (confirme no repositório se isso importar para a sua distribuição). Ela inclui/depende do OpenSSL em suas rodas binárias, com licença própria.

## Microsoft Edge / Google Chrome (janela do aplicativo)

O Hook’s não inclui nenhum navegador. O atalho abre a interface local usando o Edge ou o Chrome já instalados no seu computador, em modo aplicativo e com perfil próprio, como programas separados e com suas próprias licenças e termos.
