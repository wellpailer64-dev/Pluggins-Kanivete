from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import verificar


class VerificarTest(unittest.TestCase):
    def test_selecao_existe_e_recusa_caminho_externo(self):
        for area in verificar.AREAS:
            self.assertTrue(verificar.selecionar(area, []))
        with self.assertRaises(ValueError):
            verificar.selecionar("infra", ["../fora.py"])

    def test_html_separa_js_modulo_e_dados(self):
        p = verificar.Scripts()
        p.feed('<script>let a = 1;</script><script type="application/json">{}</script>'
               '<script src="x.js"></script><script type="module">export {};</script>')
        self.assertEqual(p.scripts, [("let a = 1;", False), ("export {};", True)])

    def test_erro_sintaxe_interrompe_testes_e_retorna_falha(self):
        with tempfile.TemporaryDirectory(dir=r"D:\kanivete_testes") as pasta:
            raiz = Path(pasta)
            (raiz / "tests").mkdir()
            (raiz / "ruim.py").write_text("def (", encoding="utf-8")
            teste = raiz / "tests" / "test_exemplo.py"
            teste.write_text("", encoding="utf-8")
            with patch.object(verificar, "RAIZ", raiz), patch.object(verificar.subprocess, "run") as rodar:
                self.assertEqual(verificar.verificar([raiz / "ruim.py", teste], raiz), 1)
            rodar.assert_not_called()
            self.assertIn("SyntaxError", (raiz / "resultado.txt").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
