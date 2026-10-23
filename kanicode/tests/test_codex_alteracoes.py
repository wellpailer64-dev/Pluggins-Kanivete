"""Diff do turno com arquivos reais; sem Git, conta ou app."""
from pathlib import Path
import tempfile
import unittest

from codex_alteracoes import Captura


class AlteracoesCodexTest(unittest.TestCase):
    def setUp(self):
        self.pasta = Path(tempfile.mkdtemp(prefix="diff_teste_", dir=r"D:\kanivete_testes"))

    def test_compara_com_arquivo_do_usuario_sem_incluir_edicoes_anteriores(self):
        p = self.pasta / "codigo.py"
        p.write_bytes(b"# edicao anterior do usuario\r\nx = 1\r\n")
        captura = Captura(self.pasta)
        p.write_bytes(b"# edicao anterior do usuario\r\nx = 2\r\n")
        r = captura.registrar({"path":"codigo.py"})
        self.assertEqual(r['conteudo'], '# edicao anterior do usuario\nx = 2\n')
        self.assertEqual((r['adicionadas'], r['removidas']), (1, 1))
        self.assertIn('-x = 1', r['diff'])
        self.assertIn('+x = 2', r['diff'])
        self.assertNotIn('+# edicao anterior', r['diff'])
        self.assertIn('início desta tarefa', r['rotulo'])
        self.assertIsNone(captura.registrar({'path':'../fora.py'}))

    def test_novo_arquivo_e_limite_sem_inventar_base(self):
        captura = Captura(self.pasta)
        p = self.pasta / 'novo.py'
        p.write_text('x = 1\n', encoding='utf-8')
        self.assertIn('+x = 1', captura.registrar({'path':'novo.py'})['diff'])
        captura.completa = False
        atual = captura.registrar({'path':'novo.py'})
        self.assertIn('não um diff', atual['rotulo'])
        self.assertEqual(atual['diff'], 'x = 1\n')

    def test_arquivo_grande_fora_do_diff_e_diretorio_ignorado(self):
        (self.pasta / 'grande.py').write_bytes(b'x' * 600000)
        captura = Captura(self.pasta)
        self.assertIsNone(captura.registrar({'path':'grande.py'}))
        self.assertIsNone(captura.registrar({'path':'.git/config.py'}))
