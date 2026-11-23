"""Gravação de arquivos de estado sem deixar metade escrita: grava ao lado, força ao disco e troca de uma vez."""
import json
import os
import tempfile
from pathlib import Path


def write_bytes(path, data, private=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=str(path.parent))
    try:
        with os.fdopen(handle, 'wb') as out:
            out.write(data)
            out.flush()
            try:
                os.fsync(out.fileno())
            except OSError:
                pass
        if private:
            try:
                os.chmod(name, 0o600)
            except OSError:
                pass
        os.replace(name, path)
    except BaseException:
        try:
            os.unlink(name)
        except OSError:
            pass
        raise
    return path


def write_text(path, text, encoding='utf-8', private=False):
    return write_bytes(path, str(text).encode(encoding), private)


def write_json(path, value, **options):
    private = options.pop('private', False)
    options.setdefault('ensure_ascii', False)
    return write_text(path, json.dumps(value, **options), private=private)
