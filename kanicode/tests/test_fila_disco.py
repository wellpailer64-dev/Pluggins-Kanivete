import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mensagens import Fila


class FilaDiscoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir="D:/kanivete_testes" if os.path.isdir("D:/kanivete_testes") else None)
        self.arq = os.path.join(self.tmp.name, "fila", "aba1.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_pendentes_voltam_pausadas_e_sem_imagens(self):
        f = Fila(self.arq)
        f.adicionar({"id": "a", "texto": "um", "imagens": [{"mini": "x"}], "quem": "claude"})
        f.adicionar({"id": "b", "texto": "dois", "quem": "codex"})
        g = Fila(self.arq, restaurar=True)
        self.assertEqual([i["id"] for i in g.itens], ["a", "b"])
        self.assertTrue(g.pausada, "não entrega sozinho depois de reiniciar")
        self.assertEqual(g.itens[0]["imagens"], [])

    def test_a_que_estava_entregando_volta_como_falha(self):
        f = Fila(self.arq)
        f.adicionar({"id": "a", "texto": "um", "quem": "claude"})
        f.proxima()
        g = Fila(self.arq, restaurar=True)
        self.assertEqual(g.itens[0]["estado"], "falha")
        self.assertIn("confira", g.itens[0]["erro"])

    def test_entregue_some_do_disco(self):
        f = Fila(self.arq)
        f.adicionar({"id": "a", "texto": "um", "quem": "claude"})
        f.concluir(f.proxima(), True)
        self.assertFalse(os.path.exists(self.arq))

    def test_aba_nova_nao_herda(self):
        Fila(self.arq).adicionar({"id": "a", "texto": "um", "quem": "claude"})
        self.assertEqual(Fila(self.arq).itens, [])
        self.assertFalse(os.path.exists(self.arq))


if __name__ == "__main__":
    unittest.main()
