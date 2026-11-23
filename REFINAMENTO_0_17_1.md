# Hook’s 0.17.1-beta.1 — o que entrou depois da 0.17.0

Continua o `REFINAMENTO_0_17.md` (que segue valendo). Feito no ambiente de desenvolvimento (Linux). **Nada foi rodado no seu Windows nem com uma live real.** Onde digo “testado”, foi com vídeos sintéticos e testes automáticos.

## 1. Teclado e revisão em lote
- Na biblioteca: setas ou J/K navegam, **X** seleciona, **A** aprova, **R** rejeita, **Enter** abre. Há uma barra de lote para aprovar ou rejeitar vários de uma vez.
- Lote só mexe em cortes **pendentes**, cada um passa pelas mesmas regras da aprovação individual (cota do plano, análise completa, confirmação editorial, música sem autorização é pulada). Máximo de 50 por vez; o que falhar aparece com o motivo.
- No Estúdio: `]` e `[` mudam de corte, `r` rejeita (menu numerado, dígitos escolhem o motivo), Ctrl+Enter aprova.

## 2. Pasta de entrega (Google Drive pelo aplicativo do computador)
- **Ajustes → Pasta de entrega**: depois de exportar, o Hook’s **copia** o vídeo e o texto de publicação para a pasta que você indicar (por exemplo `G:\Meu Drive\CORINGA`).
- A cópia é conferida por hash, nunca sobrescreve um arquivo diferente (o novo ganha `_2`) e não duplica se repetir. Aparece “copiado”, não “enviado”: quem envia para a nuvem é o aplicativo do Drive, que precisa estar aberto.
- Botão “Copiar agora os cortes já prontos” para o que foi exportado antes de configurar.
- **Integração direta com a API do Drive (Caminho B) não foi feita.** Motivos [Verificado em documentação do Google]: o escopo `drive.file` não enxerga pastas criadas à mão; escopos mais amplos são “restritos” e exigem verificação do aplicativo; em modo de teste o token expira em 7 dias; exige projeto no Google Cloud. Não dá para testar aqui. Recomendação: ficar com o Caminho A; se quiser B depois, o Hook’s cria a própria pasta no Drive.

## 3. Robustez
- **Queda de energia/fechar à força:** ao abrir, o Hook’s apaga pastas temporárias de render incompletas (`render_*`) e registra a limpeza. Testes com interrupção simulada no meio de render, de cópia e de backup.
- **Backup verificado:** depois de gravar o ZIP, ele é reaberto, o banco é extraído e conferido, e as contagens de cada tabela são comparadas. Se algo não bater, o arquivo é apagado e o erro aparece (antes só se conferia o banco antes de zipar).
- **Pré-voo (“Adicionar”)** agora também avisa: modelo de voz ainda não baixado (com ou sem internet), pasta de entrega ausente, e uma **estimativa neste computador** (GB por hora de live, minutos de transcrição por hora, tempo de exportação em relação à duração do corte). A estimativa só aparece com medições reais; sem dados, não há chute.
- **Justiça entre exportação e análise** no modo “pista única”: a cada 3 trabalhos de edição seguidos, a análise anda um passo (antes, uma fila de aprovados podia segurar a análise indefinidamente). No modo recomendado (pistas separadas) isso já não acontecia.
- **Teste de carga:** base com milhares de cortes mantém o painel em ~0,05 s e memória estável.
- **Servidor (SaaS):** rotina de **migração de banco por versão**: cópia de segurança antes, cada versão em transação própria (falhou, desfaz), recusa abrir banco criado por servidor mais novo. Hoje só existe a versão 1; a rotina está pronta e testada com migrações de exemplo, mas **nenhuma migração real foi escrita**.

## 4. Privacidade (da 0.17.0, completado)
- Corrigido: ao refazer a legenda (2ª passagem), o corte voltava a ler o perfil gravado e **perdia o borrão, a marca e o recorte da webcam**. Corrigido e com teste de regressão.

## 5. Primeiro uso, carregamento e demonstração
- **Tela de boas-vindas** com os 3 passos e o botão **“Ver com um vídeo de exemplo”**: cria o streamer “Exemplo” com um vídeo de teste de 70 s gerado pelo FFmpeg e um corte já sugerido, com legenda fictícia. Não usa internet nem modelo de voz. Testado: aprova e exporta sem Whisper.
- **Tela de carregamento** ao abrir, com mensagem e botão “Tentar de novo” se o Hook’s não responder.

## 6. Aprendizado
- **Taxa de aprovação por semana** (Ajustes → Agentes): aprovados ÷ decididos, por semana em que o corte foi sugerido, últimas 12 semanas. Cortes pendentes não contam. É a semana da **sugestão**, não da decisão (o banco não guarda a data da decisão).

## 7. Acessibilidade e mensagens
- Auditoria automática **axe-core** (WCAG 2.1 AA) em Cortes, Adicionar, Músicas, todas as abas de Ajustes e o Estúdio: de 1–3 problemas por tela para **0**. Corrigido: níveis de título, campos do Estúdio sem rótulo (contraste, saturação, brilho e outros), área de avisos sem região.
- Contraste de cores: nenhuma violação encontrada pela auditoria nas telas testadas. Auditoria automática pega só parte dos problemas; **não testei com leitor de tela** (NVDA etc.).
- **Mensagens de erro:** “KeyError”, “[Errno 13]” e disco cheio agora viram frases em português que dizem o que fazer.
- Limpeza de código: ~30 importações e variáveis sem uso removidas (sem mudança de comportamento).

## 8. O que NÃO foi feito
| Item | Motivo |
|---|---|
| Ícone na bandeja do Windows | não dá para testar sem Windows; risco de deixar processo preso |
| Caminho B do Drive (API) | ver seção 2 |
| Realimentar o agente com os motivos de rejeição | continua faltando amostra de lives reais |
| Calibrar limites do QC visual | idem |
| Migração real do banco do servidor | não há mudança de estrutura ainda |

## 9. Como testar no seu PC
1. Abra o Hook’s com um streamer novo (ou apague o seu de teste): clique em **Ver com um vídeo de exemplo**, abra o corte, aprove e confira a exportação.
2. **Ajustes → Pasta de entrega**: cole o caminho da pasta do Drive; exporte; confira se o arquivo aparece na pasta e na nuvem.
3. Aba **Adicionar**: veja se o pré-voo mostra o modelo de voz e a estimativa.
4. Na biblioteca, selecione 3 cortes com **X** e aprove em lote.
5. Se algo falhar, gere o pacote de diagnóstico.
