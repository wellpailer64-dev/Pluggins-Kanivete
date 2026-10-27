"""Abas (2026-10-21): duas tarefas ao mesmo tempo, cada evento marcado com a aba, conversas separadas por aba."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ajudantes
import kanicode

SESSAO1 = "00000000-0000-0000-0000-00000000000a"
SESSAO2 = "00000000-0000-0000-0000-00000000000b"


class AbasTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir="D:/kanivete_testes")
        self.addCleanup(self.temp.cleanup)
        self.pasta = self.temp.name
        for nome, valor in (("DADOS", self.pasta), ("ESTADO", str(Path(self.pasta) / "estado.json"))):
            p = patch.object(kanicode, nome, valor)
            p.start()
            self.addCleanup(p.stop)
        kanicode._gravar_estado(quem="codex", projeto=self.pasta, movel=False)
        self.app = kanicode.App()
        self.app._fala = Mock()
        self.app._bola_estado = Mock()
        self.app._bola_atividade = Mock()
        self.app._na_ui = Mock()
        self.eventos = []
        self.app._janela = Mock()
        self.app._janela.evaluate_js = lambda js: self.eventos.append(json.loads(js[js.index("(") + 1:-1]))
        self.soltar = {}

    def motor(self, texto, pasta, ao_evento=None, parar=None, **kw):
        ao_evento({"t": "ajudante", "quem": "codex", "fase": "passo", "texto": "fazendo " + texto})
        self.soltar[texto].wait(5)
        return {"ok": True, "texto": "feito " + texto, "sessao": SESSAO1 if texto == "um" else SESSAO2, "tokens": 1,
                "uso": {}, "ms": 1, "comandos": []}

    def esperar(self, cond):
        for _ in range(200):
            if cond():
                return True
            threading.Event().wait(.02)
        return False

    def test_duas_tarefas_juntas_e_conversas_separadas(self):
        self.soltar = {"um": threading.Event(), "dois": threading.Event()}
        with patch.object(ajudantes, "codex", side_effect=self.motor):
            self.app.ajudante("codex", "um")
            self.assertTrue(self.app._ocupada())
            r = self.app.aba_nova()
            self.assertEqual(r["ativa"], "2")
            self.assertFalse(self.app._ocupada())          # a aba nova está livre
            self.assertTrue(self.app._alguma_ocupada())
            self.assertEqual(self.app.info()["quem"], "codex")
            self.app.ajudante("codex", "dois")              # antes: "Espere a resposta terminar"
            self.assertEqual([a["ocupada"] for a in self.app.abas()["lista"]], [True, True])
            self.soltar["dois"].set()
            self.assertTrue(self.esperar(lambda: not self.app._abas["2"].ocupada()))
            self.assertTrue(self.app._abas["1"].ocupada())
            self.soltar["um"].set()
            self.assertTrue(self.esperar(lambda: not self.app._alguma_ocupada()))
        por_aba = {}
        for ev in self.eventos:
            if ev["t"] in ("ajudante", "ajudante_resposta", "eco_eu"):
                por_aba.setdefault(ev["aba"], []).append(ev.get("texto"))
        self.assertIn("feito um", por_aba["1"]); self.assertNotIn("feito um", por_aba["2"])
        self.assertIn("feito dois", por_aba["2"]); self.assertIn("fazendo dois", por_aba["2"])
        # cada aba lembra a sua conversa; a aba 1 usa a chave antiga (conversas de antes das abas)
        self.assertEqual(self.app._codex_id(self.pasta), SESSAO2)
        self.app.aba_ativar("1")
        self.assertEqual(self.app._codex_id(self.pasta), SESSAO1)
        self.assertEqual(kanicode._ler_estado()["aba_ativa"], "1")

    def test_abas_voltam_ao_reabrir_e_fechar(self):
        self.app.aba_nova()
        self.app.quem("kani")
        self.app.aba_renomear("2", "Flyer")
        outra = kanicode.App()
        self.assertEqual([(a["id"], a["quem"], a["nome"]) for a in outra.abas()["lista"]],
                         [("1", "codex", ""), ("2", "kani", "Flyer")])
        self.assertEqual(outra.abas()["ativa"], "2")
        r = outra.aba_fechar("2")
        self.assertEqual((r["ativa"], len(r["lista"])), ("1", 1))
        self.assertEqual(len(outra.aba_fechar("1")["lista"]), 1)   # a última não fecha
        self.assertEqual(outra.aba_nova()["ativa"], "3")             # o 2 fechado não volta (nem a conversa dele)

    def test_fechar_aba_trabalhando_para_a_tarefa(self):
        self.soltar = {"um": threading.Event()}
        parou = []
        def motor(texto, pasta, ao_evento=None, parar=None, **kw):
            parar.wait(5)
            parou.append(parar.is_set())
            return {"ok": False, "texto": "parado", "tokens": 0, "uso": {}, "ms": 1, "comandos": []}
        with patch.object(ajudantes, "codex", side_effect=motor):
            self.app.aba_nova()
            self.app.ajudante("codex", "um")
            self.app.aba_fechar("2")
            self.assertTrue(self.esperar(lambda: parou))
        self.assertEqual(parou, [True])
        self.assertEqual(list(self.app._abas), ["1"])


if __name__ == "__main__":
    unittest.main()
