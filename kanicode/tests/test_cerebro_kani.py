"""Área da Kani: ferramentas e autoria, com dados isolados no D."""
import unittest
from unittest.mock import patch
import test_cerebro_projetos as projetos
import perfil_cerebro as c

FONTE_KANI = c._fonte_ferramentas_kani


class KaniTest(unittest.TestCase):
    setUp = projetos.ProjetosTest.setUp
    tearDown = projetos.ProjetosTest.tearDown

    def test_catalogo_real_sem_importar_motor(self):
        with patch.object(c, "_fonte_ferramentas_kani", FONTE_KANI):
            nos = c.montar()["nos"]
        ferramentas = [n for n in nos if n.get("ferramenta_kani")]
        self.assertIn("responder", {n["titulo"] for n in ferramentas})
        self.assertTrue(any(n["titulo"].startswith("codigo_") for n in ferramentas))
        self.assertEqual(len({n["chave"] for n in ferramentas}), len(ferramentas))
        for n in ferramentas:
            self.assertEqual((n["area"], n["grupo"], n["agente"]), ("kani", "ferramentas", "não registrado"))
            self.assertIn("Cadastro não comprova execução", n["texto"])
            self.assertEqual(n["vida"], 1)
        self.assertFalse(c._candidatos({"nos": ferramentas}, c.time.time()))

    def test_aprendizado_sobre_kani_nao_inventa_autoria(self):
        ref = c.guardar("Kani local: consulta", "Conferir a fonte antes de responder.", tipo="licao",
                        certeza="verificado", origem="teste", forcar=True)["chave"]
        n = c._achar(ref)
        self.assertEqual((n["area"], n["grupo"], n["agente"]), ("kani", "aprendizados", "não registrado"))

    def test_autoria_kani_preserva_assunto(self):
        ref = c.guardar("Exportação no KANIVETE", "Conferir a duração do vídeo.", tipo="licao",
                        certeza="verificado", origem="teste", forcar=True)["chave"]
        c.classificar(ref, ["kanivete"], "aprendizado", "registro da Kani", "verificado", agente="kani")
        n = c._achar(ref)
        self.assertEqual((n["area"], n["grupo"], n["agente"]), ("kani", "aprendizados", "kani"))
        self.assertEqual(n["ambitos"], ["kanivete"])


if __name__ == "__main__":
    unittest.main()
