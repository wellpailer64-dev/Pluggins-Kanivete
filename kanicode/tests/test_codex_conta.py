"""Protocolo simulado: não consome benefício nem acessa a conta real."""
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch

import codex_conta as conta


def dados(percentual=100, creditos=1):
    return {"rateLimits": {"primary": {"usedPercent": percentual, "resetsAt": 1800000000, "windowDurationMins": 300}},
            "rateLimitResetCredits": {"availableCount": creditos, "credits": [{"id": "beneficio", "status": "available"}]}}


class ContaCodexTest(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="conta_teste_", dir=r"D:\kanivete_testes"))
        self.patch = patch.object(conta, "BASE", self.base)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        conta._CACHE.update(quando=0, valor=None)
        conta._TENTATIVAS.clear()
        self.cliente = type("ClienteFalso", (), {"atualizado_em": 0})()
        self.cliente.pedir = unittest.mock.Mock(return_value=dados())
        self.conexao = patch.object(conta, "conexao")
        con = self.conexao.start()
        con.return_value.__enter__.return_value = self.cliente
        self.addCleanup(self.conexao.stop)

    def test_consulta_cache_e_forcar_nao_consumem(self):
        self.assertTrue(conta.consultar()["cota"]["atingido"])
        conta.consultar()
        self.assertEqual(self.cliente.pedir.call_count, 1)
        self.cliente.pedir.return_value = dados(0, 0)
        self.assertFalse(conta.consultar(True)["cota"]["atingido"])
        self.assertTrue(all(c.args[0] == "account/rateLimits/read" for c in self.cliente.pedir.call_args_list))

    def test_sem_beneficio_nao_consume(self):
        self.cliente.pedir.return_value = dados(100, 0)
        self.assertFalse(conta.redefinir(str(uuid.uuid4()))["ok"])
        self.assertEqual(self.cliente.pedir.call_count, 1)

    def test_redefinicao_tem_chave_idempotente_e_atualiza(self):
        chave = str(uuid.uuid4())
        self.cliente.pedir.side_effect = [dados(), {"outcome": "reset"}, dados(0, 0)]
        r = conta.redefinir(chave, "beneficio")
        self.assertTrue(r["ok"])
        self.assertFalse(r["cota"]["atingido"])
        self.assertEqual(self.cliente.pedir.call_args_list[1].args,
                         ("account/rateLimitResetCredit/consume", {"idempotencyKey": chave, "creditId": "beneficio"}))
        self.assertIsNone(conta.pendente())

    def test_perda_de_resposta_preserva_mesma_tentativa(self):
        chave = str(uuid.uuid4())
        self.cliente.pedir.side_effect = [dados(), TimeoutError("sem resposta")]
        self.assertTrue(conta.redefinir(chave)["pendente"])
        self.assertEqual(conta.pendente()["tentativa"], chave)
        conta._TENTATIVAS.clear()
        self.cliente.pedir.side_effect = [dados(0, 0), {"outcome": "alreadyRedeemed"}, dados(0, 0)]
        self.assertTrue(conta.redefinir(chave)["ok"])
        self.assertIsNone(conta.pendente())

    def test_resultado_desconhecido_mantem_tentativa_pendente(self):
        chave = str(uuid.uuid4())
        self.cliente.pedir.side_effect = [dados(), {"outcome":"novoResultado"}, dados()]
        self.assertTrue(conta.redefinir(chave)["pendente"])
        self.assertEqual(conta.pendente()["tentativa"], chave)

    def test_uuid_invalido_nao_chama_cliente(self):
        self.assertFalse(conta.redefinir("invalido")["ok"])
        self.cliente.pedir.assert_not_called()
