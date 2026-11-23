# Colocar o servidor do Hook’s no ar

Servidor: `python -m hooks_cloud` (Python 3.10+; só precisa de `cryptography`, já em `requirements.txt`). Ele escuta em `127.0.0.1:8800` e **deve ficar atrás de HTTPS** (proxy reverso). **Contratar hospedagem, domínio e SMTP gera custo: aprove antes.**

## Teste local (sem custo)
`SERVIDOR_SAAS.bat` — cria a pasta de dados em `%USERPROFILE%\HooksCloud`, pede o admin na primeira vez e abre em http://127.0.0.1:8800/admin. Para ver dados de exemplo: `python -m hooks_cloud semear-demo`.

## Comandos
```
python -m hooks_cloud --pasta /dados/hooks iniciar --host 127.0.0.1 --porta 8800
python -m hooks_cloud --pasta /dados/hooks criar-admin --email voce@dominio.com --nome Rafael --papel dono
python -m hooks_cloud --pasta /dados/hooks chave-publica
python -m hooks_cloud --pasta /dados/hooks tarefas      # roda as tarefas periódicas uma vez, à mão
python -m hooks_cloud --pasta /dados/hooks backup --destino /backups/hooks.sqlite3
```
`criar-admin` lê a senha de `HOOKS_ADMIN_PASSWORD` ou pergunta (mín. 10 caracteres). Depois entre em `/admin` e **ative o TOTP** do dono.

## Variáveis de ambiente
| Variável | Para quê |
|---|---|
| `HOOKS_CLOUD_ROOT` | Pasta de dados (banco SQLite, chave privada, backups). Padrão `~/HooksCloud`. |
| `HOOKS_SMTP_HOST`, `HOOKS_SMTP_PORT` (587), `HOOKS_SMTP_USER`, `HOOKS_SMTP_PASS`, `HOOKS_SMTP_FROM` | Envio de e-mails. Sem isso a fila acumula e nada sai. |
| `HOOKS_ASAAS_KEY`, `HOOKS_ASAAS_ENV` (`sandbox` por padrão) | Chave da API do Asaas. **Não use em produção antes de testar no sandbox.** |
| `HOOKS_ASAAS_WEBHOOK_TOKEN` | Token do webhook: 32–255 caracteres, sem espaços, diferente da chave de API (regra do Asaas). Cadastre o mesmo valor no Asaas. |

Configurações do painel (**Configurações**): `public_url` (ex.: `https://conta.seudominio.com`, **obrigatório em produção** — define links de e-mail e cookie Secure), `support_email`, `pix_key`, `pix_name`, `trial_days`, `grace_days`, `billing_provider` (`manual`/`asaas`), `download_url`, `trust_proxy` (ligue **só** se o proxy reverso sobrescrever `X-Forwarded-For`; senão o limite por IP pode ser burlado).

## Caddy (HTTPS automático)
```
conta.seudominio.com {
    reverse_proxy 127.0.0.1:8800
}
```
Webhook do Asaas: `https://conta.seudominio.com/webhooks/asaas`. A documentação do Asaas recomenda também liberar só os IPs oficiais deles.

## systemd (Linux)
```
[Unit]
Description=Hook's cloud
After=network.target

[Service]
User=hooks
WorkingDirectory=/opt/hooks
EnvironmentFile=/etc/hooks.env
ExecStart=/opt/hooks/.venv/bin/python -m hooks_cloud --pasta /var/lib/hooks iniciar
Restart=on-failure

[Install]
WantedBy=multi-user.target
```
O próprio servidor roda as tarefas periódicas (lembretes, fila de e-mails, atraso) a cada 15 minutos enquanto estiver de pé. O comando `tarefas` só serve para rodar uma vez à mão.

## Docker (exemplo mínimo)
```
FROM python:3.12-slim
WORKDIR /app
COPY hooks_cloud ./hooks_cloud
RUN pip install --no-cache-dir "cryptography>=42"
ENV HOOKS_CLOUD_ROOT=/data
VOLUME /data
CMD ["python","-m","hooks_cloud","iniciar","--host","0.0.0.0"]
```
Não exponha a porta 8800 direto à internet: só pelo proxy HTTPS.

## Ligar o app do cliente ao servidor
1. `python -m hooks_cloud chave-publica` → copie `kid` e a chave.
2. Crie `cloud_config.json` (modelo em `cloud_config.exemplo.json`) na pasta do pacote **ou** em `C:\LiveClips`; o da pasta de dados tem prioridade.
3. `enforce:true` liga login e limites. Sem `enforce`, `server_url` ou `public_keys` o app fica em modo livre.
4. `server_url` precisa ser `https://` (exceto localhost).

## Backup e segredos
- O servidor faz **backup diário automático** do banco em `backups/auto_*.sqlite3` (guarda os 14 últimos). Isso **não** inclui a chave privada nem protege contra perder o servidor inteiro: copie `backups/` e `chave_privada.pem` para outro lugar.
- Faça backup do banco (`backup`) e **da chave privada** na pasta de dados. **Perder a chave privada obriga a gerar outra e republicar o app com a chave pública nova** (todos os tokens antigos deixam de valer).
- Copie o backup para **outro disco/serviço**; backup no mesmo servidor não protege contra perda do servidor.
- Teste a restauração ao menos uma vez antes de vender.

## Antes da primeira venda (checklist)
- [ ] CNPJ e razão social nos termos/privacidade; advogado revisou termos, privacidade e `DPA_RASCUNHO.md`
- [ ] HTTPS ativo; `public_url` correto; `trust_proxy` conforme o proxy
- [ ] SMTP real testado (cadastro, recuperação de senha)
- [ ] Planos com preço e limites definidos e ativados
- [ ] Pix manual testado ponta a ponta com um pagamento real de valor baixo
- [ ] Asaas só depois de testar no sandbox
- [ ] Backup automático + restauração testada
- [ ] Instalador testado em Windows limpo; decisão sobre assinatura de código
- [ ] Rotina para emitir NFS-e (Emissor Nacional)
