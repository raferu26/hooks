# Hook’s 0.16.0-beta.1 — base de SaaS (contas, planos, licença, cobrança)

Esta versão transforma o Hook’s em algo que **pode ser vendido com plano e limites**. Leia este arquivo primeiro: ele diz o que foi feito, com que suposições, o que foi testado e o que **não** foi.

## Suposições que adotei (você não respondeu às perguntas)

1. **Modelo A/C:** o Hook’s continua rodando no PC do cliente (gravação, análise e edição locais). Só **conta, plano, licença, cobrança e contagem de uso** ficam num servidor seu. Nada de vídeo vai para a nuvem.
2. **Cobrança manual por Pix no beta.** O Asaas está implementado, mas desligado por padrão (veja “O que não foi validado”).
3. **Sem CNPJ definido.** Os textos legais têm campos `[PREENCHER]`.

Se alguma suposição estiver errada (ex.: você quer processar na nuvem), a arquitetura muda bastante: me diga antes de vender.

## O que existe agora

### Servidor `hooks_cloud` (pasta nova, só biblioteca padrão + `cryptography`)
- **Contas:** cadastro, login, recuperação de senha por link (expira, uso único), senha com scrypt, limite de tentativas, política de senha (rejeita senhas comuns).
- **Planos editáveis no painel:** preço, lives simultâneas, horas de análise/mês, clipes/mês, streamers, dispositivos. Os 4 planos de partida vêm **inativos e com preço 0** (os números são ilustrativos).
- **Ciclo de vida:** teste → ativa → atraso (carência) → suspensa/cancelada/expirada, com cortesia, ajuste manual, extensão de carência e cancelamento pelo cliente.
- **Licença assinada (Ed25519):** o app recebe um token com estado, limites e uso. Vale 72 h; sem internet o app continua até o token vencer. Chave privada fica só no servidor; o app só tem a pública.
- **Medição de uso:** `analise_s` (segundos analisados), `clipe`, `live`. Eventos idempotentes (reenviar não duplica).
- **Cobrança:** Pix manual (chave Pix, código por cliente, você confirma no painel) e integração Asaas com webhook autenticado por token (cabeçalho `asaas-access-token`, conforme a documentação do Asaas).
- **Painel do dono (`/admin`):** clientes, planos, pagamentos, uso, fila de e-mails, pedidos LGPD, auditoria, webhooks recebidos, administradores com TOTP e papéis (dono/financeiro/suporte), backup.
- **Portal do cliente (`/conta`):** plano, uso do mês, pagar/renovar, trocar plano, cancelar, exportar e apagar dados.
- **LGPD (mecânica):** exportação dos dados, pedido de exclusão com prazo de 15 dias registrado, trilha de auditoria. Os textos jurídicos são **rascunho**.
- **E-mails de ciclo de vida** (boas-vindas, fim de teste, lembrete de renovação, atraso, cancelamento) via fila com deduplicação; só saem se o SMTP estiver configurado.
- **Segurança:** CSRF, cookies HttpOnly/SameSite=Strict (+Secure em HTTPS), CSP, limite de requisições, comparação em tempo constante, logs sem senha/token.

### Hook’s (cliente) — `liveclips/licensing.py`
- Login/cadastro dentro do painel (aba **Assinatura**), aviso de teste/atraso/limite.
- **Modo livre:** sem `cloud_config.json` com `enforce:true`, `server_url` e `public_keys`, o app funciona exatamente como na 0.15 (sem login, sem limites). Nada muda para quem já usa.
- Regras de produto (decididas por mim, mude se quiser):
  - **Live em andamento nunca é cortada.**
  - **Horas esgotadas** pausam só a **análise**; a gravação continua e a análise retoma quando renovar.
  - **Clipes** são checados na **aprovação** (aprovados + exportando contam).
  - Reanalisar o mesmo trecho **não cobra de novo**.
  - Lives simultâneas = menor valor entre sua configuração e o plano.
  - Relógio voltado para trás (> 10 min) bloqueia até sincronizar.

## Atalho e janela própria
Veja `APLICATIVO_0_16.md`.

## Como ativar (resumo; detalhes em `DEPLOY_SERVIDOR.md`)
1. Rode o servidor (`SERVIDOR_SAAS.bat` para testar local), crie o admin, defina preços e ative os planos.
2. Copie a chave pública (`chave-publica`) para `cloud_config.json` (modelo em `cloud_config.exemplo.json`).
3. Gere o instalador/zip do cliente com esse arquivo.

## Testes feitos (todos locais e simulados)
- `tests/test_cloud.py` (56) — servidor: segurança, contas, licença, cobrança/webhook, painel, privacidade, e-mails, HTTP ponta a ponta.
- `tests/test_licensing.py` (31) — cliente contra servidor real em porta efêmera, limites, outbox, relógio, offline.
- `tests/test_interface.py` — tela de assinatura; teste de navegador (Playwright) do painel admin, portal e Hook’s.
- Suíte completa anterior reexecutada (resultado no final da entrega).

## O que **não** foi validado — leia antes de vender
- **Asaas:** não testei em sandbox real. Pontos que a documentação consultada não me deixou 100% certo e que precisam de teste: URL de produção, campo do link de pagamento, rota exata para cancelar assinatura. Até testar, use **Pix manual**.
- **Nada foi testado em PC Windows real** com cliente de verdade, nem com SMTP real, domínio ou HTTPS reais.
- **Textos legais** (`termos.md`, `privacidade.md`, `DPA_RASCUNHO.md`): rascunhos sem revisão de advogado.
- **Contorno local:** o app roda na máquina do cliente; quem souber editar o código pode burlar limites. A licença assinada e o servidor dificultam o uso casual, não impedem um usuário técnico. Para proteção forte, o que precisa ser cobrado teria de rodar na nuvem.
- **Pix Automático** (cobrança recorrente sem ação do cliente) pelo Asaas exige, segundo a documentação do Asaas que consultei, CNPJ com tempo mínimo de abertura; **não implementei**.
- **Assinatura de código do instalador:** sem ela o Windows SmartScreen avisa o cliente. Certificado OV/EV tem custo anual e Azure Artifact Signing é limitado por região — decisão e gasto são seus.
- **Nota fiscal:** não automatizei. Desde 01/11/2026 ME/EPP do Simples emitem NFS-e pelo Emissor Nacional (Resolução CGSN 191/2026). Emissão manual no portal ou integração futura.

## Fora desta versão (de propósito)
Processamento na nuvem, cupons, assentos de equipe, outros gateways além do Asaas, cartão recorrente próprio, atualização automática do app, emissão automática de NFS-e, multi-idioma, afiliados.

## Decisões que dependem de você
CNPJ/razão social; preços e limites finais; hospedagem (custo mensal); domínio; SMTP; chave Pix; conta e plano no Asaas; advogado para termos/privacidade/DPA; certificado de assinatura de código.

## Fontes consultadas
- Resolução CGSN 191/2026 (NFS-e nacional, 1º/11/2026): https://fenacon.org.br/noticias/simples-nacional-nfs-e-nacional-sera-obrigatoria-para-me-e-epp-a-partir-de-1o-de-novembro-de-2026/
- Asaas — webhooks e cabeçalho `asaas-access-token`: https://docs.asaas.com/docs/about-webhooks e https://docs.asaas.com/docs/criar-novo-webhook-pela-api
