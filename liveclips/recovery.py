"""Backups pequenos e restauráveis do banco e dos perfis do LiveClips."""
import datetime as dt
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import zipfile


SCHEMA=1


def _safe_label(value):
    text=''.join(c if c.isalnum() or c in '-_' else '-' for c in str(value).strip())
    return text[:30] or 'manual'


def _check_database(path):
    connection=sqlite3.connect(path)
    try:result=connection.execute('PRAGMA integrity_check').fetchone()[0]
    finally:connection.close()
    if result!='ok':raise ValueError('O banco do backup não passou na verificação de integridade.')


def _table_counts(db):
    connection=sqlite3.connect(db)
    try:
        return {t:connection.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for (t,) in
                connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()}
    finally:connection.close()


def _verify_written(archive,expected_counts):
    """Reabre o ZIP que acabou de ser gravado: o arquivo no disco precisa estar íntegro e ter os mesmos dados do banco.
    Um backup que nunca foi lido de volta só prova que foi escrito, não que dá para restaurar."""
    with zipfile.ZipFile(archive) as bundle:
        broken=bundle.testzip()
        if broken:raise ValueError(f'O backup gravado está corrompido ({broken}).')
        with tempfile.TemporaryDirectory(prefix='conferir_') as temporary:
            bundle.extract('liveclips_v8.sqlite3',temporary)
            check=Path(temporary)/'liveclips_v8.sqlite3'
            _check_database(check)
            if _table_counts(check)!=expected_counts:raise ValueError('O backup gravado não tem os mesmos dados do banco.')


def create_backup(root,label='manual',keep=5):
    """Cria um ZIP consistente sem copiar as gravações pesadas."""
    root=Path(root).resolve();database=root/'liveclips_v8.sqlite3'
    if not database.is_file():raise ValueError('O banco do Hook’s ainda não existe.')
    backups=root/'backups';backups.mkdir(parents=True,exist_ok=True)
    label=_safe_label(label);stamp=dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    destination=backups/f'LiveClips-{label}-{stamp}.zip'
    with tempfile.TemporaryDirectory(prefix='backup_',dir=backups) as temporary:
        snapshot=Path(temporary)/'liveclips_v8.sqlite3'
        source=sqlite3.connect(database);target=sqlite3.connect(snapshot)
        try:source.backup(target)
        finally:target.close();source.close()
        _check_database(snapshot)
        snapshot_counts=_table_counts(snapshot)
        manifest={'schema':SCHEMA,'created':dt.datetime.now().astimezone().isoformat(),
                  'label':label,'database':'liveclips_v8.sqlite3','includes_media':False}
        pending=destination.with_suffix('.tmp')
        with zipfile.ZipFile(pending,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as archive:
            archive.write(snapshot,'liveclips_v8.sqlite3')
            archive.writestr('manifesto.json',json.dumps(manifest,ensure_ascii=False,indent=2))
            for profile in sorted(root.glob('*/perfil_v8.json')):
                archive.write(profile,'perfis/'+profile.parent.name+'/perfil_v8.json')
        pending.replace(destination)
    try:_verify_written(destination,snapshot_counts)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    automatic=sorted(backups.glob(f'LiveClips-{label}-*.zip'),key=lambda path:path.stat().st_mtime,reverse=True)
    for old in automatic[max(1,int(keep)):]:old.unlink(missing_ok=True)
    return destination


def inspect_backup(archive):
    archive=Path(archive).expanduser().resolve()
    if not archive.is_file() or archive.suffix.casefold()!='.zip':raise ValueError('Escolha um backup ZIP existente.')
    with zipfile.ZipFile(archive) as source:
        names=set(source.namelist())
        if not {'manifesto.json','liveclips_v8.sqlite3'}<=names:raise ValueError('Este arquivo não é um backup válido do Hook’s.')
        manifest=json.loads(source.read('manifesto.json'))
        if manifest.get('schema')!=SCHEMA:raise ValueError('A versão deste backup não é compatível.')
        for name in names:
            pure=Path(name)
            if pure.is_absolute() or '..' in pure.parts:raise ValueError('O backup contém um caminho inseguro.')
    return manifest


def restore_backup(root,archive):
    """Restaura somente com o aplicativo fechado, preservando antes o estado atual."""
    root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
    archive=Path(archive).expanduser().resolve();manifest=inspect_backup(archive)
    safety=create_backup(root,'antes-restaurar',keep=10) if (root/'liveclips_v8.sqlite3').is_file() else None
    with tempfile.TemporaryDirectory(prefix='restaurar_',dir=root) as temporary:
        temporary=Path(temporary)
        with zipfile.ZipFile(archive) as source:source.extract('liveclips_v8.sqlite3',temporary)
        restored=temporary/'liveclips_v8.sqlite3';_check_database(restored)
        for suffix in ('-wal','-shm'):(root/('liveclips_v8.sqlite3'+suffix)).unlink(missing_ok=True)
        shutil.copy2(restored,root/'liveclips_v8.sqlite3.tmp')
        (root/'liveclips_v8.sqlite3.tmp').replace(root/'liveclips_v8.sqlite3')
        with zipfile.ZipFile(archive) as source:
            for name in source.namelist():
                parts=Path(name).parts
                if len(parts)==3 and parts[0]=='perfis' and parts[2]=='perfil_v8.json':
                    target=root/parts[1]/'perfil_v8.json';target.parent.mkdir(parents=True,exist_ok=True)
                    with source.open(name) as incoming,target.open('wb') as output:shutil.copyfileobj(incoming,output)
    return {'manifest':manifest,'safety_backup':str(safety) if safety else ''}


def verify_restore(archive):
    """Abre o backup num diretório isolado (sem tocar no atual) e diz o que é recuperável e o que ficaria faltando."""
    import sqlite3
    archive = Path(archive).expanduser().resolve()
    manifest = inspect_backup(archive)
    with tempfile.TemporaryDirectory(prefix='verificar_') as temporary:
        with zipfile.ZipFile(archive) as source:
            source.extract('liveclips_v8.sqlite3', temporary)
        db = Path(temporary) / 'liveclips_v8.sqlite3'
        _check_database(db)
        con = sqlite3.connect(str(db))
        try:
            counts = {t: con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in ('streamers', 'sessions', 'segments', 'candidates')
                      if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone()}
            paths = [r[0] for r in con.execute('SELECT path FROM segments')] if 'segments' in counts else []
        finally:
            con.close()
    present = [p for p in paths if Path(p).is_file()]
    return dict(manifesto=manifest, tabelas=counts, midias_referenciadas=len(paths), midias_presentes=len(present),
                midias_ausentes=[p for p in paths if p not in present][:50],
                nota='O backup guarda o banco e os perfis; vídeos originais não vão dentro dele. Ausentes = precisam estar no disco.')
