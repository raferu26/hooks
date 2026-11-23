# Hook’s 0.17.0-beta.1 — Refinamento geral

Feito no ambiente de desenvolvimento (Linux). **Nada disto foi rodado no seu Windows nem com uma live real.** Os números de velocidade abaixo foram medidos numa base sintética de teste, nesta máquina de desenvolvimento; no seu PC os valores absolutos serão outros (a proporção deve se manter, mas isso é [Provável], não [Verificado]).

## 1. O que mudou

### Velocidade e peso
| Ponto | Antes | Depois | Como |
|---|---|---|---|
| Montar o estado do painel (a cada 2,5 s) | 0,57 s | 0,07 s | fatos de sessão fechada em cache; uma consulta agregada no lugar de várias; lista do painel limitada |
| Painel quando nada mudou | reenviava e redesenhava tudo | resposta “sem mudança” e nenhum redesenho | cabeçalho `X-State-Tag` |
| Propor um corte (checagem de duplicado) | 0,37 s | 0,014 s | coluna `fingerprint` + filtro no SQL antes da comparação fina |
| Abertura do banco | 2,2 s | 0,04 s | índices novos e migração feita uma vez |
| Backup automático | manual | em segundo plano, sem travar o painel | thread própria |
| Modelo de voz da 2ª passagem | recarregava | fica de reserva em memória | cache de modelo |

### Escolha do momento
- **Rejeição em um clique com motivo** (momento fraco, sem contexto, começo ruim, final ruim, repetido, legenda errada, imagem ou áudio ruim, sensível, outro). O motivo fica gravado no corte.
- **Taxa de aceitação por live** aparece no subtítulo da biblioteca.
- O motivo **ainda não realimenta o agente que escolhe os momentos**. Hoje ele só é coletado e mostrado. Motivo: com poucos cortes rejeitados, ajustar sozinho o começo e o fim seria ruído. Com 2–3 lives reais dá para ver se “começo ruim” e “final ruim” se concentram e aí ligar isso.

### Legenda
- **Transcrição precisa antes de exportar passa a ser o padrão** (2ª passagem com o modelo `small`).
- **Correções fixas por streamer** (`errado => certo`, uma por linha), valem também nos cortes que já existem; o tempo de cada palavra não muda.
- **Efeito colateral da migração:** perfis que estavam em “Desligada” só porque era o padrão antigo foram ligados **uma vez**. A primeira exportação pode baixar o modelo (precisa de internet) e a exportação fica mais lenta. Quem quiser desligar escolhe “Desligada” de novo e a escolha é respeitada.

### Qualidade depois da exportação (QC visual)
Roda sobre o arquivo exportado, não sobre o plano:
- legenda desenhada de verdade fora das zonas livres ou cortada; velocidade de leitura;
- rosto cortado na borda, quadro congelado, começo mudo ou parado, estouro de volume, dessincronia áudio × imagem;
- 3 imagens de amostra do vídeo pronto na aba Publicar;
- selo **“revisar · N”** no cartão e filtro **Conferir** na biblioteca;
- tempo de render medido e mostrado (“Exportado em 12 s para um vídeo de 15 s”).
Os limites (por exemplo, 2 s de congelamento) são valores iniciais meus [Hipótese]; precisam de lives reais para calibrar. As zonas do TikTok são aproximadas, não oficiais.

### Edição: áreas a borrar (privacidade)
- Em **Ajustes → Webcam e quadro → Marcar área a borrar**: até 6 retângulos sobre a imagem da sessão, com nome (chat, doação…).
- O borrão é aplicado **na imagem de origem, antes de corte, zoom e layout**; por isso não reaparece em nenhum plano, e vale nos formatos 1:1, 4:5 e 16:9.
- Vale em **todos os caminhos de render**, inclusive o plano B e a cópia de revisão. Um teste automático confere pixel a pixel (a área perde o detalhe, o resto fica idêntico).
- Vale para os cortes que já existem (o perfil é lido na hora de exportar) e muda a assinatura do corte, então um corte já exportado pede nova exportação.
- **Posição fixa.** Se a janela da live mudar de lugar no meio da transmissão, o borrão fica no lugar antigo. Borrão que acompanha o objeto **não foi feito**.
- Estimativa de uso: o borrão é um filtro extra por área; não medi o custo em tempo de render no vídeo real.

## 2. O que eu avaliei e NÃO fiz (e por quê)
| Item | Situação |
|---|---|
| Reenquadrar seguindo a pessoa na live | Em **vídeo/podcast** já existe (`dinâmico` e `quem fala`). Na **live** o recorte da webcam é fixo; seguir o rosto lá sem live real para testar tem risco de “balançar” a imagem. Não feito. |
| Peso do chat na escolha | **Já existia**: chat da Twitch entra como sinal auxiliar (peso 0,6) e nunca decide sozinho. Outras plataformas não têm captura de chat. |
| Começo e fim melhores | Já há refinamento de começo e fim (`judge`, `expand_context`). Falta realimentar com os motivos de rejeição (acima). |
| Layout por trecho, estabilização, corte J/L, final em loop, setas, cor por trecho, borrão que acompanha | **Não feitos.** São mudanças no mesmo filtro único do FFmpeg; sem Windows e sem vídeos reais para comparar antes/depois, eu arriscaria piorar o que hoje funciona. Se você escolher 1 ou 2 desses, faço em seguida com um vídeo seu de exemplo. |

## 3. Decisões de arquitetura (cenários simulados)
1. **Polling a cada 2,5 s × SSE/WebSocket.** Com a resposta “sem mudança” o polling custa quase nada. SSE reduziria o atraso, mas exige reconexão, tratamento de abas abertas e mais código no servidor padrão. **Mantido o polling.** Revisar se houver várias abas ou necessidade de menos de 1 s de atraso.
2. **SQLite local.** Um usuário, uma máquina, base pequena. Postgres só no servidor SaaS. **Mantido.**
3. **Processar na nuvem × no PC do cliente.** Vídeo de live é pesado de subir, tem questão de privacidade e custo de CPU. **Mantido local**; a nuvem fica com conta, licença e cobrança.
4. **Janela do navegador (Edge/Chrome) × pywebview × Electron.** pywebview depende do WebView2 e complica o empacotamento; Electron adiciona mais de 100 MB. **Mantido o modo aplicativo do navegador**; reavaliar junto com o instalador .exe.
5. **Modelo de voz.** `small` na 2ª passagem é equilíbrio entre precisão e tempo; `turbo` só compensa com placa NVIDIA. Não medi tempo no seu PC.
6. **Um único passe de FFmpeg.** Já era assim; o borrão entrou nesse mesmo passe, sem recodificar duas vezes.

## 4. Como testar no seu PC (ordem)
1. Abra o Hook’s e crie um corte de uma gravação sua.
2. Ajustes → Webcam e quadro: marque uma área a borrar sobre o chat; exporte; confira o vídeo e as 3 imagens na aba Publicar.
3. Rejeite um corte pelo menu de motivo; veja a taxa na biblioteca.
4. Em Legendas, escreva uma correção (`kringa => Coringa`) e confira no Estúdio.
5. Me mande o pacote de diagnóstico se algo falhar.
