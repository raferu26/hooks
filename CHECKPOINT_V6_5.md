# Checkpoint V6.5 — 0.8.5-beta.1

Branch `v6.5`, criada da V6.4 com todos os checkpoints anteriores preservados.

## Dois enquadramentos por vídeo

- Conservador: quadro completo e fundo vertical desfocado.
- Dinâmico: detecção local de cenas e rostos com OpenCV, aproximação somente em intervalos confiáveis e retorno automático ao quadro integral.
- Grupos que não cabem no recorte, apresentações e cenas sem rosto usam o enquadramento conservador.
- A posição é suavizada entre amostras para reduzir tremores.
- O modo escolhido fica salvo por gravação e é preservado na aprovação.

## Dependência gratuita

`opencv-python-headless` é executado localmente. Não utiliza API, nuvem ou tokens.
