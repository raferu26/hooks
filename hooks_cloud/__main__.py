"""Comandos: iniciar, criar-admin, chave-publica, vincular, tarefas, backup, semear-demo."""
import argparse
import getpass
import json
import os
from pathlib import Path
import sys
import time

from . import __version__
from .web import Cloud,serve


def default_root():
    return os.environ.get('HOOKS_CLOUD_ROOT') or str(Path.home()/'HooksCloud')


def main(argv=None):
    parser=argparse.ArgumentParser(prog='hooks_cloud',description='Servidor de contas, licenças e cobrança do Hook’s')
    parser.add_argument('--pasta',default=default_root(),help='Pasta dos dados do servidor (banco, chave privada, backups).')
    sub=parser.add_subparsers(dest='cmd',required=True)
    run=sub.add_parser('iniciar');run.add_argument('--host',default='127.0.0.1');run.add_argument('--porta',type=int,default=8800)
    adm=sub.add_parser('criar-admin');adm.add_argument('--email',required=True);adm.add_argument('--nome',default='Dono');adm.add_argument('--papel',default='dono',choices=['dono','financeiro','suporte'])
    sub.add_parser('chave-publica');sub.add_parser('tarefas')
    bk=sub.add_parser('backup');bk.add_argument('--destino')
    sub.add_parser('semear-demo')
    link=sub.add_parser('vincular',help='Escreve o cloud_config.json do programa Hook’s apontando para este servidor.')
    link.add_argument('--programa',required=True,help='Pasta de dados do Hook’s (ex.: C:\\LiveClips).')
    link.add_argument('--url',default='http://127.0.0.1:8800')
    link.add_argument('--desligar',action='store_true',help='Volta o programa para o modo livre (sem login).')
    args=parser.parse_args(argv)
    cloud=Cloud(args.pasta)
    if args.cmd=='criar-admin':
        password=os.environ.get('HOOKS_ADMIN_PASSWORD') or getpass.getpass('Senha do administrador (mínimo 10 caracteres): ')
        cloud.admin.create_admin(args.email,args.nome,password,args.papel)
        print('Administrador criado:',args.email,'·',args.papel);return 0
    if args.cmd=='chave-publica':
        print(json.dumps(dict(kid=cloud.keys.kid,public_keys={cloud.keys.kid:cloud.keys.public_b64}),indent=2));return 0
    if args.cmd=='vincular':
        target=Path(args.programa)/'cloud_config.json'
        target.parent.mkdir(parents=True,exist_ok=True)
        if args.desligar:
            if target.exists():target.replace(target.with_name('cloud_config.desligado.json'))
            print('Modo livre restaurado (sem login). Reinicie o Hook’s.');return 0
        url=args.url.rstrip('/')
        config=dict(server_url=url,public_keys={cloud.keys.kid:cloud.keys.public_b64},enforce=True,
                    terms_url=url+'/termos',privacy_url=url+'/privacidade',support_url='',portal_url=url+'/conta')
        tmp=target.with_suffix('.tmp');tmp.write_text(json.dumps(config,indent=2,ensure_ascii=False),encoding='utf-8');tmp.replace(target)
        print('Hook’s vinculado a',url,'em',target,'. Reinicie o Hook’s: a aba Assinatura (login) aparece.');return 0
    if args.cmd=='tarefas':print(cloud.service.run_jobs());return 0
    if args.cmd=='backup':
        target=Path(args.destino) if args.destino else Path(args.pasta)/'backups'/time.strftime('hooks_cloud_%Y%m%d_%H%M%S.sqlite3')
        target.parent.mkdir(parents=True,exist_ok=True);print('Backup criado:',cloud.db.backup(target));return 0
    if args.cmd=='semear-demo':
        from .demo import seed
        print(seed(cloud));return 0
    server=serve(cloud,args.host,args.porta);cloud.start_jobs()
    if not cloud.db.rows('SELECT id FROM admins LIMIT 1'):
        print('ATENÇÃO: ainda não existe administrador. Rode: python -m hooks_cloud criar-admin --email voce@exemplo.com',flush=True)
    print(f'Hook’s Cloud {__version__} em http://{args.host}:{args.porta}/admin  (portal do cliente: /conta)',flush=True)
    print('Pasta de dados:',cloud.root,flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:cloud.stop.set();server.server_close()
    return 0


if __name__=='__main__':sys.exit(main())
