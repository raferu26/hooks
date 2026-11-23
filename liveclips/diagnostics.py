"""Diagnóstico simples das dependências externas do LiveClips."""
from . import media


def main():
    paths=media.tool_status();missing=[]
    print('LIVECLIPS - VERIFICACAO DAS FERRAMENTAS')
    for name,path in paths.items():
        if path:print('[OK]',name,':',path)
        else:print('[FALTA]',name);missing.append(name)
    if missing:
        print('Faltando:',', '.join(missing))
        raise SystemExit(1)
    print('Todas as ferramentas principais foram encontradas.')


if __name__=='__main__':main()
