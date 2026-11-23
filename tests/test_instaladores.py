"""Arquivos .bat que o usuário executa no Windows: regras que só dá para checar estaticamente aqui.
Execução real no Windows NÃO é validada por este teste."""
import re,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
BATS=sorted(ROOT.glob('*.bat'))


class Bats(unittest.TestCase):
    def test_crlf(self):
        # cmd.exe pode errar ao localizar rótulos (goto) em arquivos só com LF.
        self.assertTrue(BATS)
        for bat in BATS:
            data=bat.read_bytes()
            self.assertNotIn(b'\n',data.replace(b'\r\n',b''),bat.name)

    def test_ascii(self):
        for bat in BATS:
            bat.read_bytes().decode('ascii')

    def test_goto_labels_exist(self):
        for bat in BATS:
            text=bat.read_text()
            labels={m.group(1).lower() for m in re.finditer(r'^:(\w+)',text,re.M)}
            for target in re.findall(r'goto (\w+)',text,re.I):
                if target.lower()!='eof':self.assertIn(target.lower(),labels,f'{bat.name}: goto {target}')

    def test_no_close_paren_in_block_echo(self):
        # um ")" solto em echo dentro de bloco ( ... ) fecha o bloco antes da hora
        for bat in BATS:
            depth=0
            for n,line in enumerate(bat.read_text().splitlines(),1):
                stripped=line.strip()
                if depth and stripped.lower().startswith('echo ') and ')' in stripped:
                    self.fail(f'{bat.name}:{n}: ")" dentro de echo em bloco')
                if stripped.startswith(')'):depth=max(0,depth-1)
                if stripped.endswith('('):depth+=1

    def test_update_handles_quotes_and_apostrophes(self):
        text=(ROOT/'ATUALIZAR.bat').read_text()
        self.assertIn('NOVO_ZIP:"=',text)
        self.assertIn("NOVO_ZIP:'=''",text)

    def test_install_does_not_abort_without_facial_model(self):
        text=(ROOT/'INSTALAR.bat').read_text()
        self.assertNotIn('goto modelo',text)


if __name__=='__main__':unittest.main()
