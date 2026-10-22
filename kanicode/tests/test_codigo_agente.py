"""Origem e cópia reais em D, sem app nem modelo."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import codigo_agente as codigo


class CodigoAgenteTest(unittest.TestCase):
    def setUp(self):
        self.pasta = Path(tempfile.mkdtemp(prefix="codigo_teste_", dir=r"D:\kanivete_testes"))
        self.origem = self.pasta / "origem"
        self.origem.mkdir()
        self.patch = patch.object(codigo, "BASE", self.pasta / "sessoes")
        self.patch.start()
        self.addCleanup(self.patch.stop)
        (self.origem / "soma.py").write_bytes(b"def soma(a, b):\r\n    return a - b\r\n")
        (self.origem / "test_soma.py").write_text(
            "import unittest\nfrom soma import soma\nclass TestSoma(unittest.TestCase):\n"
            "    def test_soma(self): self.assertEqual(soma(2, 3), 5)\n", encoding="utf-8")
        self.ctx = codigo.Contexto(self.origem, "pickle")
        self.ctx.preparar("soma.py;test_soma.py", "Corrigir soma")

    def corrigir(self):
        self.ctx.escrever("soma.py", "return a + b", "return a - b")

    def test_copia_testes_diff_e_aplicacao_explicita(self):
        self.assertFalse(self.ctx.testar("test_soma.py")["ok"])
        self.corrigir()
        self.assertIn(b"a - b", (self.origem / "soma.py").read_bytes())
        self.assertTrue(self.ctx.testar("test_soma.py")["ok"])
        revisao = self.ctx.revisar()
        self.assertIn("+    return a + b", revisao["diff"])
        self.ctx.aplicar(revisao["revisao"])
        self.assertEqual((self.origem / "soma.py").read_bytes(), b"def soma(a, b):\r\n    return a + b\r\n")
        with self.assertRaises(ValueError):
            self.ctx.escrever("soma.py", "x", "return a + b")

    def test_conflito_na_origem_nao_sobrescreve(self):
        self.corrigir()
        r = self.ctx.revisar()
        (self.origem / "soma.py").write_text("alterado pelo usuário", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "origem mudou"):
            self.ctx.aplicar(r["revisao"])
        self.assertEqual((self.origem / "soma.py").read_text(encoding="utf-8"), "alterado pelo usuário")

    def test_revisao_antiga_sintaxe_e_ancora_ambigua(self):
        r = self.ctx.revisar()
        self.corrigir()
        with self.assertRaisesRegex(ValueError, "cópia mudou"):
            self.ctx.aplicar(r["revisao"])
        with self.assertRaisesRegex(ValueError, "exatamente uma vez"):
            self.ctx.escrever("soma.py", "x", " ")
        self.ctx.escrever("soma.py", "return (", "return a + b")
        self.assertFalse(self.ctx.verificar()["ok"])
        with self.assertRaisesRegex(ValueError, "sintaxe"):
            self.ctx.aplicar(self.ctx.revisar()["revisao"])

    def test_falha_de_teste_bloqueia_aplicar(self):
        self.ctx.escrever("soma.py", "return a * b", "return a - b")
        self.assertFalse(self.ctx.testar("test_soma.py")["ok"])
        with self.assertRaisesRegex(ValueError, "testes falhando"):
            self.ctx.aplicar(self.ctx.revisar()["revisao"])

    def test_recusa_caminhos_dependencias_e_arquivo_fora_contrato(self):
        for nome in ("../x.py", "D:/x.py", ".git/config.py", "requirements.txt", "CLAUDE.md", "package.json"):
            with self.subTest(nome=nome), self.assertRaises(ValueError):
                codigo.relativo(nome)
        with self.assertRaisesRegex(ValueError, "não liberado"):
            self.ctx.escrever("fora.py", "x = 1")
        self.assertNotIn("codigo_aplicar", codigo.FERRAMENTAS)

    def test_agentes_nao_compartilham_sessao(self):
        with self.assertRaises(ValueError):
            codigo.Contexto(self.origem, "kani").carregar()

    def test_kani_e_pickle_usam_mesma_ponte_sem_editar_origem(self):
        import json
        import bigpickle_modo as bp
        import kani_modo as kani
        passos = [
            {"acao":"codigo_preparar","args":{"arquivos":"soma.py;test_soma.py","objetivo":"Corrigir soma"}},
            {"acao":"codigo_substituir","args":{"caminho":"soma.py","antes":"return a - b","depois":"return a + b"}},
            {"acao":"codigo_testar","args":{"caminho":"test_soma.py"}},
            {"acao":"codigo_revisar","args":{}},
            {"acao":"responder","args":{"mensagem":"Cópia corrigida; testes passaram. Revise as alterações."}},
        ]
        for agente in ("kani", "pickle"):
            eventos = []
            with self.subTest(agente=agente), patch.object(kani, "notas", return_value=""), \
                    patch.object(kani.ajudantes, "_kani_subir", return_value=12345), \
                    patch.object(kani, "_chamar", side_effect=[(p, 3) for p in passos]), \
                    patch.object(bp.opencode_mvp, "conversar", side_effect=[(json.dumps(p), 3) for p in passos]):
                rodar = kani.rodar if agente == "kani" else bp.rodar
                r = rodar("Corrija a soma na cópia e rode o teste.", str(self.origem), eventos.append)
                self.assertTrue(r["ok"], r["texto"])
                ctx = codigo.Contexto(self.origem, agente).carregar()
                self.assertEqual(ctx.revisar()["arquivos"], ["soma.py"])
                self.assertTrue(ctx.meta["testes"]["ok"])
                self.assertIn(b"a - b", (self.origem / "soma.py").read_bytes())
                self.assertEqual([e["tokens"] for e in eventos if e["t"] == "agente_uso"], [3,6,9,12,15])

    def test_planejar_nao_libera_ferramentas_de_escrita(self):
        import bigpickle_modo as bp
        import json
        respostas = [
            (json.dumps({"acao":"codigo_preparar","args":{"arquivos":"novo.py"}}),3),
            (json.dumps({"acao":"responder","args":{"mensagem":"Modo de leitura: alteração não executada."}}),3)
        ]
        with patch.object(bp.opencode_mvp, "conversar", side_effect=respostas), patch.object(codigo, "executar") as executar:
            bp.rodar("Analise sem editar", str(self.origem), lambda ev: None, editar=False)
        executar.assert_not_called()
