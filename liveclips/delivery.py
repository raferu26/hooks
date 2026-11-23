"""Pasta de entrega: depois de exportar, copia o clipe (e o texto de publicação) para uma pasta escolhida pela pessoa.

Serve, por exemplo, para uma pasta do "Google Drive para computador" (G:\\Meu Drive\\CORINGA): o Hook's só copia para
uma pasta do PC; quem envia para a nuvem é o aplicativo do Drive. Por isso o resultado diz "copiado", nunca "enviado".

Regras: nunca apaga nem sobrescreve arquivo diferente; copia para um arquivo temporário, confere o hash e só então
renomeia; refazer a entrega do mesmo clipe não duplica. Uma falha aqui nunca derruba a exportação."""
import hashlib
import os
import re
import shutil
import time
import unicodedata
from pathlib import Path

PENDING_HINT = ('Não encontrei a pasta de entrega. Se ela é do Google Drive, abra o aplicativo do Drive no computador '
                'e confira se a pasta existe; depois use "Tentar de novo".')


def valid_folder_text(value):
    """Valida o texto salvo no perfil (não exige que a pasta exista agora: o Drive pode estar fechado)."""
    text = str(value or '').strip()
    if not text:
        return ''
    if len(text) > 300 or '\x00' in text:
        raise ValueError('O caminho da pasta de entrega é grande demais ou inválido.')
    absolute = re.match(r'^[A-Za-z]:[\\/]', text) or text.startswith(('\\\\', '/'))
    if not absolute:
        raise ValueError('Use o caminho completo da pasta de entrega, por exemplo G:\\Meu Drive\\CORINGA.')
    if '..' in re.split(r'[\\/]+', text):
        raise ValueError('O caminho da pasta de entrega não pode ter “..”.')
    return text


def safe_name(text, limit=40):
    text = unicodedata.normalize('NFKD', str(text or '')).encode('ascii', 'ignore').decode()
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', ' ', text)
    text = re.sub(r'\s+', '_', text.strip()).strip('._ ')
    return text[:limit].strip('._ ')


def title_of(candidate):
    data = candidate.get('data') or {}
    titles = ((data.get('project') or {}).get('titles') or [])
    for value in ((titles[0] or {}).get('text') if titles else None, (data.get('hook') or {}).get('opening'),
                  data.get('moment_label'), str(data.get('transcript') or '')[:60]):
        if value and str(value).strip():
            return str(value)
    return 'corte'


def base_name(candidate, streamer_name, when=None):
    day = time.strftime('%Y-%m-%d', time.localtime(time.time() if when is None else when))
    parts = [safe_name(streamer_name, 24), day, safe_name(title_of(candidate), 40), candidate['id'][:6]]
    return '_'.join(p for p in parts if p)


def sha(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _copy_checked(source, dest):
    """Copia com arquivo temporário e confere o conteúdo. Retorna o hash. Nunca sobrescreve outro conteúdo."""
    wanted = sha(source)
    number = 1
    final = Path(dest)
    while final.exists():
        if sha(final) == wanted:
            return final, wanted            # já entregue: nada a fazer
        number += 1
        final = Path(dest).with_name(f'{Path(dest).stem}_{number}{Path(dest).suffix}')
    temp = final.with_name(final.name + '.part')
    try:
        shutil.copyfile(source, temp)
        if sha(temp) != wanted:
            raise OSError('A cópia não confere com o original (arquivo corrompido na pasta de destino).')
        os.replace(temp, final)
    finally:
        try:
            if temp.exists():
                temp.unlink()
        except OSError:
            pass
    return final, wanted


def deliver(folder, candidate, video, streamer_name):
    """Retorna dict(status='ok'|'pendente'|'erro', ...). Não levanta exceção."""
    now = round(time.time())
    try:
        folder = valid_folder_text(folder)
        if not folder:
            return dict(status='desligada')
        target = Path(folder)
        if not target.is_dir():
            return dict(status='pendente', folder=folder, error=PENDING_HINT, at=now)
        video = Path(video)
        if not video.is_file():
            return dict(status='erro', folder=folder, error='O vídeo exportado não foi encontrado.', at=now)
        name = base_name(candidate, streamer_name)
        final, digest = _copy_checked(video, target / (name + '.mp4'))
        text = video.parent / 'publicacao.txt'
        if text.is_file():
            _copy_checked(text, final.with_suffix('.txt'))
        for art in sorted(video.parent.glob('capa_9x16.jpg')):   # capa principal acompanha o vídeo
            _copy_checked(art, final.with_name(final.stem + '_capa.jpg'))
        # formatos extras (P23): nomes estáveis ao lado do principal; falha numa cópia extra não invalida a entrega principal
        extras = []
        for fmt in ('1x1', '4x5', '16x9'):
            if not (video.parent / f'clipe_{fmt}.mp4').is_file():
                continue
            for art, suffix in ((video.parent / f'clipe_{fmt}.mp4', f'_{fmt}.mp4'), (video.parent / f'capa_{fmt}.jpg', f'_capa_{fmt}.jpg'),
                                (video.parent / f'legendas_{fmt}.srt', f'_{fmt}.srt')):
                if art.is_file():
                    try:
                        extras.append(_copy_checked(art, final.with_name(final.stem + suffix))[0].name)
                    except OSError:
                        pass
        return dict(status='ok', folder=folder, file=final.name, sha=digest[:16], at=now, **(dict(extras=extras) if extras else {}))
    except (OSError, ValueError) as exc:
        return dict(status='erro', folder=str(folder), error=str(exc)[:300], at=now)
