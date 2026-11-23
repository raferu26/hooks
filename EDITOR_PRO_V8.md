# Editor profissional V8 (0.10.0-beta.1)

Esta versão mexe **só na edição**: curvas de zoom, identidade de cada estilo, legendas, cor, montagem do vídeo e áudio. Captura, análise, ranking e história (V7.1) não foram alterados.

## O que mudou

| Área | V7 | V8 |
|---|---|---|
| Estilos | Mudavam só limiares de zoom/pausa e pesos do ranking; `reframe` e `pace` não tinham efeito | Cada estilo tem **look** próprio: curva de zoom, cor, legenda automática e margem de respiro real (`breath`). Campo morto `reframe` removido |
| Zoom | Todos os punches usavam o maior alvo, com velocidade fixa | Cada punch tem alvo e curva próprios (`smooth`, `snap`, `pop`, `beat`); `storytelling` e `cinemático` têm avanço lento contínuo |
| Qualidade do zoom | zoompan direto no tamanho final | Supersample 2× na faixa da webcam (1,5× no quadro vertical inteiro) |
| Cor | Só aparecia nas demonstrações, não no corte real | Aplicada de verdade (contraste/saturação/nitidez/vinheta leves). Estilo Limpo fica neutro. Chave "Cor do estilo" no perfil |
| Legendas | Destaque piscava nos intervalos entre palavras | Destaque contínuo; novos estilos `impact` (caixa alta), `pop` e `box`; entrada animada; ênfase na palavra falada no pico; opção **Automática** segue o estilo |
| Render | 2 a 3 codificações (assemble → compactado → final) | **Uma** codificação: trims, união, layout, cor, legenda e áudio no mesmo filtergraph. Se falhar, volta sozinho ao método V7 e registra o motivo no manifesto |
| Vídeos longos | Decodificava desde o início do arquivo | Busca grossa na entrada para arquivos > 3 min |
| Áudio | `loudnorm` em uma passada | Medição prévia + ganho linear **quando o pico permite**; senão mantém o método V7 |
| Demonstrações | Imagens com filtros próprios | Usam o mesmo look, curva e legenda do render real |

## Looks por estilo

Definidos em `liveclips/editing.py` (`LOOKS`). As intensidades de cor são escolhas de projeto, cerca de 65% das amostras antigas do painel; ajuste ali se preferir.

| Estilo | Curva | Avanço lento | Legenda (Automática) | Cor |
|---|---|---|---|---|
| Limpo | smooth | — | clean | neutra |
| Gameplay | snap | — | impact | saturação 1,12 · contraste 1,06 · nitidez |
| Reação | pop | — | dynamic | leve |
| Podcast | smooth | — | clean | dessaturada .90 |
| Entrevista | smooth | — | minimal | dessaturada .85 |
| Hype | beat | — | impact | saturação 1,28 · contraste 1,11 · nitidez |
| Criativo | pop | — | pop | saturação 1,18 |
| Storytelling | smooth | 1,035 | clean | neutra+ |
| Educacional | smooth | — | box | .92 |
| Comentário | snap | — | dynamic | neutra+ |
| Meme | beat | — | impact | saturação 1,25 |
| Cinemático | smooth | 1,05 | minimal | .82 · vinheta |
| Momentos engraçados | pop | — | dynamic | leve |

Perfis já salvos mantêm a legenda que tinham (`dynamic` etc.). Perfis novos começam em **Automática**.

## Regra de loudness

O ganho linear só é usado quando o pico verdadeiro resultante cabe no limite (−1,5 dBTP com 0,3 dB de folga para o AAC). Sem margem, o método V7 é mantido. Motivo: em teste sintético com ruído de pico alto, o modo dinâmico de duas passadas deixou o pico verdadeiro entre −0,8 e −0,1 dBTP após o AAC, pior que o método V7 (−1,6 a −1,1). O manifesto registra o modo usado e o motivo.

## Rollback

- Método antigo por corte: `media.render(..., pipeline='legacy')` (o modo `auto` já faz isso sozinho se o FFmpeg falhar).
- Versão anterior: tag `v0.9.0-beta.1` (V7) ou o ZIP 0.9.0. O `renderer_version` mudou, então cortes exportados antes serão regerados.

## Medições (material sintético, 2 CPUs)

- Zoom com supersample 2×: PSNR 36,2 dB contra a referência 4×; sem supersample, 27,0 dB. Custo: ~0,35 s a mais por 4 s de faixa 1080×640.
- Clipe de 20 s com 2 cortes: 22,1 s (uma passada) contra 26,1 s (método V7), uma amostra, não é benchmark.
- Sincronismo: flashes de vídeo nas posições esperadas após os cortes; defasagem áudio/vídeo ≤ 40 ms nos dois métodos. O método V7 apareceu 1 quadro atrasado nessa fonte.
- Busca grossa verificada em mp4 e `.ts` com trecho em 300 s: quadros exatos.

## Limites

- Nada foi validado com capturas reais de live, fala real ou visualmente por uma pessoa em clipes reais; os testes usam fontes sintéticas.
- A margem de segurança das legendas (260/1280) não foi conferida contra a interface do TikTok.
- Não implementado: gancho/teaser reordenando trechos, transições entre partes, speed ramps, biblioteca de B-roll, pré-visualização A/B.
- A interface foi só checada quanto à sintaxe do JavaScript; abra o perfil e teste os controles novos.

## Testes

`python -m unittest discover -s tests -t .` → 150 testes (119 anteriores + 31 novos; 3 testes antigos foram ajustados ao novo formato do zoom e passaram a exercitar `pipeline='legacy'`). Os testes com FFmpeg real são ignorados se FFmpeg, ffprobe ou NumPy faltarem.
