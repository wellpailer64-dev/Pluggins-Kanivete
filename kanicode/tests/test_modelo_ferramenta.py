"""Modelo de teste: nunca toca no app real; estado e ação são simulados."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from modelo_ferramenta import executar, para_kani


class ModeloFerramentaTest(unittest.TestCase):
    def test_confirma_somente_estado_observado(self):
        observar = Mock(side_effect=["home", "photo"])
        agir = Mock()
        r = executar({"nome": "photo"}, {"nome": str}, observar, agir,
                     lambda antes, depois, args: depois == args["nome"])
        self.assertTrue(r["ok"])
        self.assertEqual(r["antes"], "home")
        self.assertEqual(r["depois"], "photo")
        agir.assert_called_once_with({"nome": "photo"})

    def test_acao_sem_efeito_nao_vira_sucesso(self):
        r = executar({}, {}, lambda args: "home", lambda args: "pronto",
                     lambda antes, depois, args: depois == "photo")
        self.assertFalse(r["ok"])
        self.assertTrue(para_kani(r).startswith("NÃO FEITO"))

    def test_argumentos_invalidos_nao_executam(self):
        for args in ({}, {"nome": ""}, {"nome": 1}, {"nome": "photo", "extra": True}):
            agir, observar = Mock(), Mock()
            r = executar(args, {"nome": str}, observar, agir, Mock())
            self.assertFalse(r["ok"])
            agir.assert_not_called()
            observar.assert_not_called()

    def test_excecao_nao_repete_acao(self):
        agir = Mock(side_effect=RuntimeError("interrompida"))
        r = executar({}, {}, lambda args: "home", agir, Mock())
        self.assertFalse(r["ok"])
        self.assertEqual(r["etapa"], "agir")
        agir.assert_called_once()


if __name__ == "__main__":
    unittest.main()
