# Auditoria da 0.16.0-beta.2 — o que falta e o que foi testado

Feita em 22/11/2026 no ambiente de desenvolvimento (Linux). **Nada disto foi rodado no seu Windows**: a conversa não estava conectada ao seu PC.

## 1. O que foi testado (e passou)
| Área | Como | Resultado |
|---|---|---|
| Suíte automática | ~800 testes (app, estúdio, captura simulada, licença, servidor SaaS, lançador) | passou |
| Telas do Hook’s | navegador automatizado em cada tela, aba de Ajustes e aba do Estúdio, com cortes de teste | sem erro de JavaScript |
| Botão Encerrar | navegador automatizado + processo real | encerra o servidor e apaga o arquivo de descoberta |
| Servidor SaaS em processo real | 55 verificações: cabeçalhos de segurança, rotas protegidas, cookies, CSRF, limite de tentativas, webhook sem token/com token errado, corpo de 12 MB, travessia de pastas, 60 pedidos simultâneos, permissão da chave privada | passou |
| Entradas inválidas | ~14.500 pedidos com lixo em cada campo de cada ação do painel | **achou 4 rotas com erro 500 e mais 10 ações que quebravam com identificador ou plano em formato errado (todas corrigidas)**; depois, 0 erros 5xx |
| App + servidor em processos separados | `cloud_config.json` gerado pelo passo-a-passo do `DEPLOY_SERVIDOR.md`: sem login bloqueia importação; cadastro pelo app libera o teste com os limites do plano; computador aparece no servidor | passou |
| Painel admin e portal | navegação por todas as telas do admin e abertura do portal em navegador | sem erro de JavaScript |

## 2. Corrigido nesta rodada
1. Painel admin: campos inválidos (estender teste, cortesia, tolerância, valor recebido, reprocessar webhook, marcar e-mail como enviado, paginação) davam erro 500; agora dão mensagem clara (400).
2. Painel admin: identificador (ou plano) em formato errado quebrava 10 ações; agora responde 400.
3. Rede de segurança: qualquer entrada inválida que escape vira 400 e fica na auditoria como `entrada_invalida`.
4. Servidor: **backup diário automático** (antes só existia o manual).
5. Servidor: ícone do site (antes dava 404 no navegador).
6. `smoke_ui.py` passou a ignorar botões ocultos.

## 3. Lista completa do que falta

### A. Bloqueia a primeira venda (depende de você ou de terceiros)
1. **Validar com live real.** Não existe número de acerto dos cortes (quantos clipes sugeridos você postaria). É o ponto de maior risco do produto.
2. **Testar atalho e janela no Windows real** (ícone, janela sem console, ícone na barra, encerramento ao fechar). Veja `APLICATIVO_0_16.md`.
3. **Pagamento:** testar Pix manual de ponta a ponta com um valor real baixo; testar Asaas no sandbox (URL de produção, campo do link de pagamento e rota de cancelar assinatura estão sem confirmação).
4. **Jurídico:** termos, privacidade e DPA com advogado; CNPJ e razão social; consultar sobre gravar lives de terceiros (direito autoral e termos das plataformas).
5. **Infraestrutura:** hospedagem, domínio, HTTPS e SMTP reais (têm custo: precisa do seu aval); testar e-mail de cadastro e de recuperação de senha.
6. **Backup fora do servidor** (cópia do `backups/` e da `chave_privada.pem`) e **teste de restauração**.
7. **Nota fiscal:** NFS-e pelo Emissor Nacional (obrigatória para ME/EPP do Simples desde 01/11/2026), manual ou integrada.

### B. Produto (eu posso fazer)
8. **Instalador .exe de verdade**: sem Python separado, desinstalador, atualização automática e assinatura digital (certificado tem custo anual). Projeto à parte, precisa de Windows para montar e testar.
9. **Primeiro uso guiado:** depois do cadastro, tela de boas-vindas, checagem do PC e aviso se a máquina é fraca demais para acompanhar uma live. [Hipótese: não sei o piso de máquina; só medindo no seu PC.]
10. **Abertura mais amigável:** tela de carregamento enquanto o servidor sobe (o primeiro start é lento e dá vontade de clicar de novo) e ícone na bandeja do sistema quando o Hook’s fica em segundo plano.
11. **Relatório de falhas opcional** (com consentimento) enviado ao servidor, com tela “erros recentes” no admin, para dar suporte sem pedir o pacote de diagnóstico à mão.
12. **Pendências do checkup 0.14:** último pedaço de gravação menor que 128 KB nunca é cadastrado; exportação aprovada passa na frente da análise na fila; não há teste de lentidão por etapa.
13. **Medir qualidade dentro do app:** taxa de aprovação dos cortes por live e por streamer, para você ver se está melhorando.
14. **Migrações de banco do servidor:** hoje só existe um número de versão do esquema, sem rotina de migração. Precisa antes de qualquer mudança de tabela em produção.
15. **Reconciliação do Pix manual:** hoje você confirma cada pagamento à mão no painel.
16. **Servidor, extras:** cobrança recorrente sem ação do cliente (Pix Automático exige CNPJ com tempo mínimo no Asaas; cartão), cupons, equipe/assentos, troca de e-mail e 2FA para o cliente, relatório de cancelamento (churn), monitoramento externo e alerta de queda.
17. **Entrega dos clipes:** publicar ou agendar no TikTok/Shorts não existe (o app entrega clipe e texto prontos). Decisão de produto.
18. **Limpeza de código:** 11 variáveis não usadas e imports sobrando (sem risco, só higiene).

### C. Limites conhecidos (não têm correção barata)
19. **Contorno local dos limites:** o app roda na máquina do cliente; um usuário técnico consegue burlar cotas. A licença assinada barra o uso casual. Proteção forte exigiria rodar a parte cobrada na nuvem.
20. **Qualidade heurística:** detecção de webcam/rosto, camada de contexto e “momentos perdidos” só foram testadas com dados sintéticos.
21. **Dependência de Edge ou Chrome** para a janela do aplicativo (abre no navegador padrão se não achar).

## 4. Ordem sugerida
1) Você abre o atalho e me diz o resultado dos 4 pontos do `APLICATIVO_0_16.md`. 2) Rodada com 2–3 lives reais + pacote de diagnóstico (itens 1, 12, 13). 3) Itens 9–11 e 14. 4) Só depois: instalador (8) e infraestrutura/jurídico (4–6) em paralelo.
