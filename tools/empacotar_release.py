"""Empacota o Hook's para entrega (ZIP versionado) a partir dos arquivos RASTREADOS pelo git — nunca de uma pasta suja.
Uso:  python3 tools/empacotar_release.py [--saida PASTA]      (rode na raiz do repositório, com a árvore limpa)
Gera `Hooks-<versão>.zip` + `Hooks-<versão>.zip.sha256`, com `MANIFESTO.sha256` (hash de cada arquivo) dentro do ZIP, e VERIFICA:
integridade do ZIP, hashes do manifesto, `.bat` com finais de linha CRLF e `chcp 65001`, ausência de segredos/vídeos/banco/venv,
presença dos arquivos que o instalador exige. NÃO prova que funciona no Windows: isso só o teste físico prova (docs/WINDOWS_BETA.md)."""
import argparse, hashlib, json, re, subprocess, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INCLUDE_DIRS = ('liveclips/', 'hooks_cloud/', 'assets/')
INCLUDE_FILES = ('requirements.txt', 'README.md', 'THIRD_PARTY_NOTICES.md', 'cloud_config.exemplo.json', 'DEPLOY_SERVIDOR.md', 'DPA_RASCUNHO.md',
                 'docs/WINDOWS_BETA.md', 'docs/CHANGELOG.md', 'docs/COMPOSICAO_REACAO.md')
REQUIRED = ('INSTALAR.bat', 'ABRIR_LIVECLIPS.bat', 'ATUALIZAR.bat', 'CRIAR_ATALHO.bat', 'CRIAR_ATALHO.ps1', 'GERAR_DIAGNOSTICO.bat', 'RESTAURAR_BACKUP.bat',
            'requirements.txt', 'liveclips/__main__.py', 'liveclips/static/index.html')
FORBIDDEN = re.compile(r'(^|/)(\.git|\.venv|venv|__pycache__|tests|validacao|ui|docs/handoff)(/|$)|\.(mp4|ts|mkv|mov|wav|mp3|sqlite3?|db|pem|key|p12|env)$|(^|/)\.env', re.I)
SECRET = re.compile(rb'(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|sk-[A-Za-z0-9]{20,})')   # com tamanho mínimo: o texto "github_pat_" em documentação não é segredo


def tracked():
    out = subprocess.run(['git', '-C', str(ROOT), 'ls-files'], capture_output=True, text=True, check=True).stdout.splitlines()
    return out


def wanted(path):
    if path in REQUIRED or path in INCLUDE_FILES:
        return True
    if path.endswith(('.bat', '.ps1')) and '/' not in path:
        return True
    return path.startswith(INCLUDE_DIRS)


def version():
    m = re.search(r"__version__\s*=\s*'([^']+)'", (ROOT / 'liveclips' / '__init__.py').read_text(encoding='utf-8'))
    return m.group(1)


def build(out_dir, allow_dirty=False):
    if not allow_dirty and subprocess.run(['git', '-C', str(ROOT), 'status', '--porcelain', '--untracked-files=no'], capture_output=True, text=True).stdout.strip():
        raise SystemExit('A árvore tem alterações não commitadas: commite antes de empacotar (o ZIP sai só do que está no git).')
    files = [f for f in tracked() if wanted(f)]
    bad = [f for f in files if FORBIDDEN.search(f)]
    if bad:
        raise SystemExit('Arquivos proibidos no pacote: %s' % bad[:5])
    missing = [r for r in REQUIRED if r not in files]
    if missing:
        raise SystemExit('Faltam arquivos exigidos: %s' % missing)
    ver = version(); out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    zpath = out_dir / f'Hooks-{ver}.zip'; manifest = []
    with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in sorted(files):
            data = (ROOT / f).read_bytes()
            if SECRET.search(data):
                raise SystemExit('Possível segredo em %s' % f)
            if f.endswith(('.bat', '.ps1')):                     # o Windows exige CRLF nos .bat
                data = data.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
            manifest.append('%s  %s' % (hashlib.sha256(data).hexdigest(), f))
            z.writestr(zipfile.ZipInfo(f'Hooks-{ver}/{f}', date_time=(2026, 1, 1, 0, 0, 0)), data, zipfile.ZIP_DEFLATED)
        z.writestr(f'Hooks-{ver}/MANIFESTO.sha256', '\n'.join(manifest) + '\n')
    digest = hashlib.sha256(zpath.read_bytes()).hexdigest()
    (out_dir / (zpath.name + '.sha256')).write_text(f'{digest}  {zpath.name}\n')
    return zpath, digest, verify(zpath)


def verify(zpath):
    """Confere o ZIP pronto: devolve a lista de verificações [(nome, ok, detalhe)]."""
    checks = []
    with zipfile.ZipFile(zpath) as z:
        checks.append(('zip_integro', z.testzip() is None, ''))
        names = z.namelist(); prefix = names[0].split('/')[0] + '/'
        manifest = dict(line.split('  ', 1)[::-1] for line in z.read(prefix + 'MANIFESTO.sha256').decode().splitlines())
        mism = [n for n, h in manifest.items() if hashlib.sha256(z.read(prefix + n)).hexdigest() != h]
        checks.append(('manifesto_confere', not mism, mism[:3]))
        bats = [n for n in names if n.endswith('.bat')]
        crlf = [n for n in bats if b'\r\n' not in z.read(n) or re.search(rb'(?<!\r)\n', z.read(n))]
        checks.append(('bat_crlf', not crlf, crlf))
        chcp = [n for n in bats if n.endswith('INSTALAR.bat') and b'chcp 65001' not in z.read(n)]
        checks.append(('instalar_chcp_65001', not chcp, chcp))
        checks.append(('sem_proibidos', not [n for n in names if FORBIDDEN.search(n[len(prefix):])], ''))
        checks.append(('sem_segredos', not [n for n in names if SECRET.search(z.read(n))], ''))
        checks.append(('tem_requeridos', all(prefix + r in names for r in REQUIRED), ''))
    return checks


AI_WHEELS = re.compile(r'^(mediapipe|faster[-_]whisper|ctranslate2|onnxruntime|jax|jaxlib|ml[-_]dtypes|matplotlib|scipy|tokenizers|huggingface[-_]hub|hf[-_]xet|sentencepiece|torch|tensorflow|av)-', re.I)
TEST_DOCS = ('LEIA-ME_TESTE_WINDOWS.txt', 'CHECKLIST_W01_W10.md', 'REGISTRO_DE_PROBLEMAS.md', 'LIMITACOES.md', 'ROTEIRO_LAYOUT_REACAO.md')
TEST_REQUIRED = ('INSTALAR_TESTE.bat', 'AUTOTESTE.bat', 'MEDIR_DESEMPENHO.bat', 'COLETAR_RELATORIO.bat', 'VERIFICAR_PACOTE.bat', 'requirements-sem-ia.txt',
                 'LEIA-ME_TESTE_WINDOWS.txt', 'CHECKLIST_W01_W10.md', 'LIMITACOES.md', 'BUILD_INFO.json', 'MANIFESTO.sha256')


def wheel_fits_windows_py311(name):
    """O wheel serve para Windows 64 bits com Python 3.11? (puro Python, abi3 ou cp311 win_amd64)"""
    if name.endswith('-none-any.whl'):
        return True
    return bool(re.search(r'-(cp311-cp311|cp3\d+-abi3|cp311-abi3|py3-none)-win_amd64\.whl$', name))


def head_commit():
    return subprocess.run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()


def build_test(out_dir, wheels, results_md=None, includes=(), allow_dirty=False):
    """Pacote de TESTE para Windows (variante experimental sem IA): código + `wheels/` offline + scripts + roteiro, de um commit identificado.
    Devolve (zip, sha256, verificações)."""
    if not allow_dirty and subprocess.run(['git', '-C', str(ROOT), 'status', '--porcelain', '--untracked-files=no'], capture_output=True, text=True).stdout.strip():
        raise SystemExit('A árvore tem alterações não commitadas: commite antes de empacotar.')
    wheels = Path(wheels)
    whl = sorted(wheels.glob('*.whl'))
    if not whl:
        raise SystemExit('Pasta de wheels vazia.')
    bad = [w.name for w in whl if AI_WHEELS.match(w.name)]
    if bad:
        raise SystemExit('Wheels de IA na variante sem IA: %s' % bad)
    wrong = [w.name for w in whl if not wheel_fits_windows_py311(w.name)]
    if wrong:
        raise SystemExit('Wheels que não servem para Windows 64 bits/Python 3.11: %s' % wrong[:5])
    commit = head_commit(); ver = version(); out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    files = [f for f in tracked() if wanted(f) or f in ('requirements-sem-ia.txt',)]
    files = [f for f in files if not FORBIDDEN.search(f)]
    zpath = out_dir / f'Hooks-{ver}-teste-sem-ia-{commit[:10]}.zip'
    prefix = f'Hooks-{ver}-teste/'
    manifest = []
    build_info = dict(version=ver, commit=commit, variant='sem_ia', built=__import__('datetime').datetime.now().astimezone().isoformat(timespec='seconds'),
                      includes=list(includes), wheels=len(whl), python='3.11 (64 bits)', numpy='1.26.4')
    with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as z:
        def put(name, data):
            if SECRET.search(data):
                raise SystemExit('Possível segredo em %s' % name)
            if name.endswith(('.bat', '.ps1')):
                data = data.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
            manifest.append('%s  %s' % (hashlib.sha256(data).hexdigest(), name))
            z.writestr(zipfile.ZipInfo(prefix + name, date_time=(2026, 1, 1, 0, 0, 0)), data, zipfile.ZIP_DEFLATED)
        for f in sorted(files):
            put(f, (ROOT / f).read_bytes())
        for name in TEST_DOCS:
            put(name, (ROOT / 'docs' / 'WINDOWS_TESTE' / name).read_bytes())
        put('VARIANTE_SEM_IA', 'Variante experimental sem IA: perfis novos nascem com ai_mode=sem_ia.\n'.encode('utf-8'))
        put('BUILD_INFO.json', json.dumps(build_info, ensure_ascii=False, indent=1).encode('utf-8'))
        put('TESTES_REALIZADOS.md', (Path(results_md).read_bytes() if results_md else 'Nenhum resultado informado ao empacotar.\n'.encode('utf-8')))
        for w in whl:
            put('wheels/' + w.name, w.read_bytes())
        z.writestr(prefix + 'MANIFESTO.sha256', '\n'.join(manifest) + '\n')
    digest = hashlib.sha256(zpath.read_bytes()).hexdigest()
    (out_dir / (zpath.name + '.sha256')).write_text(f'{digest}  {zpath.name}\n')
    return zpath, digest, verify_test(zpath)


def verify_test(zpath):
    checks = []
    with zipfile.ZipFile(zpath) as z:
        names = z.namelist(); prefix = names[0].split('/')[0] + '/'
        checks.append(('zip_integro', z.testzip() is None, ''))
        manifest = dict(line.split('  ', 1)[::-1] for line in z.read(prefix + 'MANIFESTO.sha256').decode().splitlines())
        mism = [n for n, h in manifest.items() if hashlib.sha256(z.read(prefix + n)).hexdigest() != h]
        checks.append(('manifesto_confere', not mism, mism[:3]))
        checks.append(('todos_os_arquivos_no_manifesto', set(manifest) == {n[len(prefix):] for n in names if not n.endswith('/') and not n.endswith('MANIFESTO.sha256')}, ''))
        checks.append(('tem_requeridos', all(prefix + r in names for r in TEST_REQUIRED), [r for r in TEST_REQUIRED if prefix + r not in names]))
        bats = [n for n in names if n.endswith('.bat')]
        checks.append(('bat_crlf', not [n for n in bats if re.search(rb'(?<!\r)\n', z.read(n))], ''))
        checks.append(('sem_wheels_de_ia', not [n for n in names if n.startswith(prefix + 'wheels/') and AI_WHEELS.match(n.split('/')[-1])], ''))
        checks.append(('sem_proibidos', not [n for n in names if FORBIDDEN.search(n[len(prefix):]) and not n.endswith('.whl')], ''))
        checks.append(('sem_segredos', not [n for n in names if not n.endswith('.whl') and SECRET.search(z.read(n))], ''))
        info = json.loads(z.read(prefix + 'BUILD_INFO.json'))
        checks.append(('build_info_tem_commit', len(info.get('commit', '')) == 40, info.get('commit', '')[:10]))
        req = z.read(prefix + 'requirements-sem-ia.txt').decode()
        checks.append(('requirements_sem_pilha_de_ia', not re.search(r'(?im)^\s*(mediapipe|faster-whisper|onnxruntime|torch|tensorflow)', req), ''))
    return checks


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--saida', default=str(ROOT.parent / 'release'))
    ap.add_argument('--teste-sem-ia', action='store_true', help='pacote de TESTE para Windows (variante experimental sem IA) com wheels offline')
    ap.add_argument('--wheels', help='pasta com os .whl win_amd64/cp311 (pip download) para a variante de teste'); ap.add_argument('--resultados', help='arquivo .md com os testes realizados')
    ap.add_argument('--inclui', nargs='*', default=[], help='PRs/branches incluídos neste build (texto)')
    a = ap.parse_args()
    z, d, checks = build_test(a.saida, a.wheels, a.resultados, a.inclui) if a.teste_sem_ia else build(a.saida)
    print(z, d)
    for name, ok, detail in checks:
        print(('OK    ' if ok else 'FALHA ') + name, detail or '')
    sys.exit(0 if all(ok for _, ok, _ in checks) else 1)
