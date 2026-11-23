import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import threading
import webbrowser

from . import atomic
from . import __version__
from .app import App,server
from .recovery import restore_backup


@contextmanager
def single_instance(root):
    root.mkdir(parents=True,exist_ok=True)
    with (root/'liveclips_v8.lock').open('a+b') as handle:
        handle.seek(0,2)
        if not handle.tell():handle.write(b'0');handle.flush()
        handle.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError('O Hook’s já está aberto para esta pasta. Use o painel existente.') from exc
        yield


def main():
    import sys
    if len(sys.argv)>1 and sys.argv[1]=='bench':
        from .bench import main as bench_main
        raise SystemExit(bench_main(sys.argv[2:]))
    if len(sys.argv)>1 and sys.argv[1]=='diag':
        from . import media,support
        from .store import Store
        root=Path(os.environ.get('LIVECLIPS_ROOT',r'C:\LiveClips' if os.name=='nt' else str(Path.home()/'LiveClips'))).resolve()
        if len(sys.argv)>2:root=Path(sys.argv[2]).resolve()
        file=support.bundle(root,Store(root),__version__,media.tool_status())
        print('Pacote de diagnóstico criado:',file,flush=True);print('Envie esse arquivo para quem está ajudando você.',flush=True)
        return
    parser=argparse.ArgumentParser(description='Hook’s: painel local de revisão')
    parser.add_argument('--root',default=os.environ.get('LIVECLIPS_ROOT',r'C:\LiveClips' if os.name=='nt' else str(Path.home()/'LiveClips')))
    parser.add_argument('--legacy-root',default=os.environ.get('LIVECLIPS_LEGACY_ROOT'))
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--restore',help='Restaura um backup ZIP e encerra sem abrir o painel.')
    args=parser.parse_args()
    root=Path(args.root).resolve()
    with single_instance(root):
        if args.restore:
            result=restore_backup(root,args.restore)
            print('Backup restaurado com segurança.',flush=True)
            if result['safety_backup']:print('Estado anterior preservado em:',result['safety_backup'],flush=True)
            return
        app=App(args.root,args.legacy_root)
        try:
            try:http=server(app,args.port)
            except OSError:http=server(app,0)
            url=f'http://127.0.0.1:{http.server_port}'
            app.quit_callback=lambda:threading.Thread(target=http.shutdown,daemon=True,name='encerrar').start()
            discovery=root/'servidor.json'
            atomic.write_json(discovery,dict(pid=os.getpid(),port=http.server_port,token=app.token,versao=__version__),private=True)
            print('LIVECLIPS',__version__,flush=True)
            print('Abra o painel:',url,flush=True)
            print('Dados em:',app.store.root,flush=True)
            print('Deixe esta janela aberta. Para encerrar o aplicativo e a captura, pressione Ctrl+C.',flush=True)
            if not args.no_browser:webbrowser.open(url)
            try:http.serve_forever(poll_interval=.5)
            except KeyboardInterrupt:print('\nFinalizando captura e salvando estado...',flush=True)
            finally:
                http.server_close()
                try:discovery.unlink()
                except OSError:pass
        finally:app.close()


if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('Não foi possível abrir o Hook’s:',exc,flush=True)
        raise SystemExit(1)
