"""API real com estado temporário e motor simulado; não abre nem controla a janela."""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ajudantes
import kanicode

SESSAO = "00000000-0000-0000-0000-000000000001"
OUTRA = "00000000-0000-0000-0000-000000000002"


class AppCodexTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir="D:/kanivete_testes")
        self.addCleanup(self.temp.cleanup)
        self.pasta = self.temp.name
        for nome, valor in (("DADOS", self.pasta), ("ESTADO", str(Path(self.pasta)/"estado.json"))):
            p = patch.object(kanicode, nome, valor)
            p.start()
            self.addCleanup(p.stop)
        kanicode._gravar_estado(quem="codex", projeto=self.pasta)
        self.app = kanicode.App()
        self.app._fala = Mock()
        self.fim = threading.Event()
        self.app._bola_estado = lambda estado: self.fim.set() if estado != "trabalhando" else None
        self.app._bola_atividade = Mock()
        self.app._na_ui = Mock()
        self.app._evento = Mock()
        self.app._para_janela = Mock()

    def resultado(self):
        return {"ok": True, "texto": "Pronto", "sessao": SESSAO, "tokens": 30,
                "uso": {"entrada": 100, "cache": 80, "saida": 10}, "ms": 200,
                "primeiro_evento_ms": 50, "esforco": "low", "comandos": [],
                "estourou": False, "cancelado": False}

    def aguardar(self):
        self.assertTrue(self.fim.wait(3), "a API não liberou a tarefa")
        self.assertFalse(self.app._ocupada())

    def test_sessao_e_historico_sobrevivem_a_nova_instancia(self):
        with patch.object(ajudantes, "codex", return_value=self.resultado()) as motor:
            self.app.ajudante("codex", "Pedido simples")
            self.aguardar()
        self.assertIsNone(motor.call_args.kwargs["retomar"])
        outra = kanicode.App()
        self.assertEqual(outra._codex_id(self.pasta), SESSAO)
        self.assertEqual([e["texto"] for e in outra.historico()], ["Pedido simples", "Pronto"])
        self.fim.clear()
        with patch.object(ajudantes, "codex", return_value=self.resultado()) as motor:
            self.app.ajudante("codex", "Continue")
            self.aguardar()
        self.assertEqual(motor.call_args.kwargs["retomar"], SESSAO)
        linhas = (Path(self.pasta)/"codex_uso.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(linhas), 2)
        self.assertNotIn("Pedido simples", "\n".join(linhas))

    def test_ids_por_pasta_e_nova_nao_apaga_conversa_do_claude(self):
        self.app._codex_guardar(self.pasta, SESSAO)
        self.app._codex_guardar(str(Path(self.pasta)/"outro"), OUTRA)
        kanicode._gravar_estado(sessoes={self.pasta: "claude-preservado"})
        self.app.nova()
        self.assertIsNone(self.app._codex_id(self.pasta))
        self.assertEqual(self.app._codex_id(str(Path(self.pasta)/"outro")), OUTRA)
        self.assertEqual(kanicode._ler_estado()["sessoes"][self.pasta], "claude-preservado")

    def test_planejar_passa_somente_leitura(self):
        self.app.modo("plan")
        with patch.object(ajudantes, "codex", return_value=self.resultado()) as motor:
            self.app.ajudante("codex", "Planeje uma mudança")
            self.aguardar()
        self.assertFalse(motor.call_args.kwargs["editar"])

    def test_motor_esta_livre_quando_a_janela_recebe_resposta(self):
        estados = []
        self.app._para_janela = lambda ev: ev.get("t") == "eco_eu" or estados.append(self.app._ocupada())
        with patch.object(ajudantes, "codex", return_value=self.resultado()):
            self.app.ajudante("codex", "Pedido")
            self.aguardar()
        self.assertEqual(estados, [False])

    def test_parar_e_concorrencia(self):
        iniciou = threading.Event()
        def motor(*args, **kw):
            iniciou.set()
            self.assertTrue(kw["parar"].wait(2))
            return self.resultado()
        with patch.object(ajudantes, "codex", side_effect=motor):
            self.app.ajudante("codex", "Primeira")
            self.assertTrue(iniciou.wait(2))
            self.assertTrue(self.app.info()["ocupada"])
            with self.assertRaises(RuntimeError):
                self.app.ajudante("codex", "Segunda simultânea")
            with self.assertRaises(RuntimeError):
                self.app.nova()
            self.app.parar()
            self.aguardar()

    def test_falha_do_motor_libera_proxima_demanda(self):
        with patch.object(ajudantes, "codex", side_effect=OSError("falha ao abrir")):
            self.app.ajudante("codex", "Pedido")
            self.aguardar()
        resposta = self.app._para_janela.call_args.args[0]
        self.assertFalse(resposta["ok"])
        self.assertIn("falha ao abrir", resposta["texto"])
        self.assertFalse(self.app._ajudante_trava.locked())

    def test_sessao_e_guardada_antes_da_resposta(self):
        def motor(*args, **kw):
            kw["ao_evento"]({"t": "ajudante", "fase": "passo", "sessao": SESSAO})
            self.assertEqual(kanicode.App()._codex_id(self.pasta), SESSAO)
            return self.resultado()
        with patch.object(ajudantes, "codex", side_effect=motor):
            self.app.ajudante("codex", "Pedido")
            self.aguardar()


if __name__ == "__main__":
    unittest.main()
