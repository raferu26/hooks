# Acordo de tratamento de dados (DPA) — RASCUNHO

**RASCUNHO PARA REVISÃO JURÍDICA. Não foi revisado por advogado e não deve ser usado como está.** Os trechos `[PREENCHER]` dependem de decisões suas e do advogado.

Serve para o caso em que o cliente é uma empresa/agência que coloca dados de **terceiros** (por exemplo, falas e imagens de streamers) no Hook’s. Na LGPD, o cliente costuma ser o **controlador** desses dados e você, como operador do servidor, só trata o que é necessário para conta, plano e cobrança. A análise de vídeo/áudio ocorre no computador do cliente e **não** é enviada ao seu servidor.

## 1. Partes
Controlador: [PREENCHER: razão social do cliente, CNPJ]. Operador: [PREENCHER: sua razão social, CNPJ].

## 2. Dados que o servidor trata
- Cadastro: nome, e-mail, senha (somente hash), plano, datas de cobrança.
- Uso: segundos analisados, quantidade de clipes e de lives, por período.
- Dispositivo: identificador técnico derivado da máquina (hash), para limitar dispositivos.
- Cobrança: valores, status, identificadores de pagamento. [PREENCHER: dados enviados ao gateway.]
- O servidor **não** recebe vídeo, áudio, transcrição nem imagens.

## 3. Finalidade e instruções
Prestar o serviço contratado, aplicar limites do plano, cobrar, dar suporte e cumprir obrigações legais. Qualquer outra finalidade exige instrução escrita do controlador.

## 4. Segurança
Descreva as medidas reais em vigor no momento da assinatura (HTTPS, hash de senha, controle de acesso do painel com TOTP, trilha de auditoria, backup). [PREENCHER: apenas o que de fato estiver implantado.]

## 5. Subprocessadores
Hospedagem: [PREENCHER]. E-mail: [PREENCHER]. Cobrança: [PREENCHER — por exemplo Asaas, se ativado]. Aviso prévio de mudanças: [PREENCHER prazo].

## 6. Direitos dos titulares e incidentes
Apoio ao controlador nos pedidos de acesso, correção e exclusão (o painel registra e exporta). Comunicação de incidente em [PREENCHER prazo] após ciência.

## 7. Retenção e término
Exclusão ou devolução dos dados em [PREENCHER prazo] após o fim do contrato, salvo obrigação legal de guarda (ex.: registros fiscais). [PREENCHER: confirmar prazos com contador/advogado.]

## 8. Encarregado (DPO) e foro
Encarregado: [PREENCHER]. Foro: [PREENCHER].
