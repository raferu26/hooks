"""Imagens enviadas pelo usuário (memes, logos, selos) para usar como sobreposição nos clipes.

O arquivo é conferido pelo conteúdo (não só pela extensão), medido com o ffprobe e copiado
para `<dados>/imagens/`. O navegador só recebe o identificador, nunca o caminho.
"""
import hashlib
import json
from pathlib import Path
import re
import time

from . import media

MAX_IMAGE = 15 * 1024 ** 2
ID_RE = re.compile(r'^[a-f0-9]{16}$')
SIGNATURES = (('.png', b'\x89PNG\r\n\x1a\n'), ('.jpg', b'\xff\xd8\xff'), ('.webp', b'RIFF'))


class AssetError(ValueError):
    pass


def folder(root):
    path = Path(root) / 'imagens'
    path.mkdir(parents=True, exist_ok=True)
    return path


def _index(root):
    file = folder(root) / 'index.json'
    try:
        value = json.loads(file.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(root, index):
    file = folder(root) / 'index.json'
    temp = file.with_suffix('.tmp')
    temp.write_text(json.dumps(index, ensure_ascii=False), encoding='utf-8')
    temp.replace(file)


def kind_of(head):
    for extension, signature in SIGNATURES:
        if head.startswith(signature):
            if extension == '.webp' and head[8:12] != b'WEBP':
                continue
            return extension
    return ''


def public(item):
    return {k: v for k, v in item.items() if k != 'file'}


def library(root):
    return sorted([public(i) for i in _index(root).values() if (folder(root) / i['file']).is_file()],
                  key=lambda i: -i.get('added', 0))


def get(root, image_id):
    if not ID_RE.match(str(image_id or '')):
        raise AssetError('Imagem inválida.')
    item = _index(root).get(image_id)
    if not item or not (folder(root) / item['file']).is_file():
        raise AssetError('Essa imagem não está mais na biblioteca.')
    return item


def path_of(root, image_id):
    return folder(root) / get(root, image_id)['file']


def import_image(root, source, name=''):
    source = Path(source)
    if not source.is_file():
        raise AssetError('Arquivo de imagem não encontrado.')
    if source.stat().st_size > MAX_IMAGE:
        raise AssetError('Imagem grande demais (limite de 15 MB).')
    with source.open('rb') as handle:
        extension = kind_of(handle.read(16))
    if not extension:
        raise AssetError('Use uma imagem PNG, JPG ou WEBP.')
    image_id = hashlib.sha256(b'img:' + media.sha_file(source).encode()).hexdigest()[:16]
    index = _index(root)
    if image_id in index and (folder(root) / index[image_id]['file']).is_file():
        return public(index[image_id])
    try:
        data = json.loads(media.run([media.tool('ffprobe'), '-v', 'error', '-select_streams', 'v:0',
                                     '-show_entries', 'stream=width,height', '-of', 'json', str(source)], 60))
        stream = data['streams'][0]
        width, height = int(stream['width']), int(stream['height'])
    except (KeyError, IndexError, ValueError, RuntimeError) as exc:
        raise AssetError('Não consegui ler essa imagem.') from exc
    if not (16 <= width <= 8000 and 16 <= height <= 8000):
        raise AssetError('Tamanho de imagem fora do esperado (16 a 8000 px).')
    target = folder(root) / (image_id + extension)
    target.write_bytes(source.read_bytes())
    item = dict(id=image_id, file=target.name, name=(name or source.stem)[:80], width=width, height=height,
                alpha=extension in ('.png', '.webp'), added=time.time())
    index[image_id] = item
    _write(root, index)
    return public(item)


def remove(root, image_id):
    item = get(root, image_id)
    (folder(root) / item['file']).unlink(missing_ok=True)
    index = _index(root)
    index.pop(image_id, None)
    _write(root, index)
