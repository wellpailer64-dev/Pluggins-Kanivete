import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import passagem


class PassagemTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir="D:/kanivete_testes" if os.path.isdir("D:/kanivete_testes") else None)
        self.d, self.k = self.tmp.name, "C:/proj#aba2"

    def tearDown(self):
        self.tmp.cleanup()

    def test_novo_agente_recebe_o_que_o_outro_fez(self):
        passagem.registrar(self.d, self.k, "claude", "corrige o login", "Corrigi o login em auth.py.")
        b = passagem.pendente(self.d, self.k, "codex")
        self.assertIn("corrige o login", b)
        self.assertIn("Claude: Corrigi o login", b)
        self.assertEqual(passagem.pendente(self.d, self.k, "codex"), "", "não repete o que já passou")

    def test_proprio_turno_nao_volta(self):
        passagem.registrar(self.d, self.k, "claude", "a", "b")
        self.assertEqual(passagem.pendente(self.d, self.k, "claude"), "")

    def test_ida_e_volta(self):
        passagem.registrar(self.d, self.k, "claude", "p1", "r1")
        passagem.pendente(self.d, self.k, "codex")
        passagem.registrar(self.d, self.k, "codex", "p2", "r2")
        b = passagem.pendente(self.d, self.k, "claude")
        self.assertIn("Codex: r2", b)
        self.assertNotIn("r1", b)

    def test_kani_para_claude_fica_com_o_caminho_antigo(self):
        passagem.registrar(self.d, self.k, "kani", "oi", "olá")
        self.assertEqual(passagem.pendente(self.d, self.k, "claude"), "")
        self.assertIn("Kani: olá", passagem.pendente(self.d, self.k, "codex"))

    def test_bloco_da_kani_e_curto(self):
        for i in range(10):
            passagem.registrar(self.d, self.k, "claude", f"pedido {i}", "x" * 3000)
        self.assertLess(len(passagem.pendente(self.d, self.k, "kani")), 2200)
        self.assertLess(len(passagem.pendente(self.d, self.k, "codex")), 10000)

    def test_sem_marcar_repete_ate_o_agente_responder(self):
        passagem.registrar(self.d, self.k, "claude", "p1", "r1")
        self.assertIn("r1", passagem.pendente(self.d, self.k, "codex", marcar=False))
        self.assertIn("r1", passagem.pendente(self.d, self.k, "codex", marcar=False))
        passagem.registrar(self.d, self.k, "codex", "p2", "r2")
        self.assertEqual(passagem.pendente(self.d, self.k, "codex", marcar=False), "")

    def test_abas_separadas(self):
        passagem.registrar(self.d, self.k, "claude", "a", "b")
        self.assertEqual(passagem.pendente(self.d, "C:/proj", "codex"), "")


if __name__ == "__main__":
    unittest.main()
