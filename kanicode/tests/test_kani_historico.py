"""Conversa com a Kani continua na janela ao trocar para o Claude, e o Claude recebe as trocas que não viu."""
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import kani_modo
import kanicode


class KaniHistoricoTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir="D:/kanivete_testes")
        self.addCleanup(self.temp.cleanup)
        self.pasta = self.temp.name
        for nome, valor in (("DADOS", self.pasta), ("ESTADO", str(Path(self.pasta)/"estado.json"))):
            p = patch.object(kanicode, nome, valor)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(kani_modo, "DADOS", self.pasta)   # o registro kani_modo.jsonl vai para o temporário
        p.start()
        self.addCleanup(p.stop)
        kanicode._gravar_estado(quem="kani", projeto=self.pasta)
        self.app = kanicode.App()
        self.fim = threading.Event()
        self.app._bola_estado = lambda estado: self.fim.set() if estado != "trabalhando" else None
        self.app._bola_atividade = Mock()
        self.app._na_ui = Mock()
        self.app._evento = Mock()
        self.janela = []
        self.app._para_janela = self.janela.append

    def pedir(self, texto, de="pc"):
        def rodar(pedido, pasta, ev, hist, voz, parar, editar=True):
            ev({"t": "ferr", "id": "k1", "nome": "kani_ver_kanivete", "entrada": {}})
            ev({"t": "ferr_fim", "id": "k1", "ok": True, "saida": "home"})
            return {"ok": True, "texto": "Resposta da Kani", "claude": False, "tokens": 5, "ms": 10}
        self.fim.clear()
        with patch.object(kani_modo, "rodar", side_effect=rodar):
            self.app.ajudante("kani", texto, _de=de)
            self.assertTrue(self.fim.wait(5))

    def test_casa_reconhece_comando_sem_confundir_codigo(self):
        for texto in ("Acenda a luz da cozinha", "Diminua o brilho das lâmpadas",
                      "Qual o estado das tomadas?", "Alimenta os gatos"):
            with self.subTest(texto=texto):
                self.assertTrue(self.app._pedido_casa(texto))
        for texto in ("Implemente ligar luzes em Python", "Corrija o código do alimentador",
                      "Como funciona a automação da Casa?", "/listar luzes", "Oi Kani"):
            with self.subTest(texto=texto):
                self.assertFalse(self.app._pedido_casa(texto))

    def test_casa_na_conversa_claude_encaminha_sem_trocar_modelo(self):
        with patch.object(self.app, "_ajudante_iniciar", return_value=True) as iniciar:
            self.assertTrue(self.app.enviar("Acenda a luz da cozinha", _de="movel-x"))
        iniciar.assert_called_once_with("kani", "Acenda a luz da cozinha", "movel-x")

    def test_casa_no_codex_roda_na_kani(self):
        with patch.object(kani_modo, "rodar", return_value={
                "ok": True, "texto": "Conferido", "claude": False, "tokens": 0, "ms": 1}) as rodar, \
                patch.object(self.app, "_casa_rapido", side_effect=AssertionError("atalho indevido")):
            self.app.ajudante("codex", "Diminua o brilho das lâmpadas")
            self.assertTrue(self.fim.wait(5))
        rodar.assert_called_once()
        self.assertTrue(any(e.get("quem") == "kani" for e in self.janela))

    def test_trocar_para_o_claude_mantem_a_conversa(self):
        self.pedir("Oi Kani", de="movel-x")
        self.assertIn({"t": "eco_eu", "texto": "Oi Kani", "de": "movel-x", "minis": []}, self.janela)
        kanicode._gravar_estado(quem="claude")
        h = self.app.historico()
        self.assertEqual([e["t"] for e in h], ["eu", "ferr", "ferr_fim", "ajudante_resposta"])
        self.assertEqual(h[-1]["texto"], "Resposta da Kani")
        ctx = self.app._kani_para_claude(self.pasta)
        self.assertIn("Pailer: Oi Kani", ctx)
        self.assertIn("Kani: Resposta da Kani", ctx)
        self.assertEqual(self.app._kani_para_claude(self.pasta), "")   # só uma vez

    def test_com_conversa_do_claude_grava_nela_e_nova_limpa(self):
        sid = "00000000-0000-0000-0000-0000000000aa"
        kanicode._gravar_estado(sessoes={self.pasta: sid})
        self.pedir("Fecha o KANIVETE")
        self.assertTrue((Path(self.pasta)/"conversas"/(sid + ".jsonl")).is_file())
        self.app.nova()
        self.assertEqual(self.app.historico(), [])
        self.assertEqual(self.app._kani_para_claude(self.pasta), "")


class KaniFecharTest(unittest.TestCase):
    def test_fechar_aba_kanivete_vira_fechar_o_app(self):
        kani_modo.pedido_atual[0] = "Pode fechar o KANIVETE pra mim?"
        with patch.object(kani_modo, "_reiniciar_kanivete", return_value="fechei o KANIVETE") as r:
            self.assertEqual(kani_modo._executar("fechar_aba", {"nome": "KANIVETE"}, "."), "fechei o KANIVETE")
        r.assert_called_once_with(reabrir=False)

    def test_sem_pedido_nao_fecha(self):
        kani_modo.pedido_atual[0] = "Deixa o KANIVETE"
        with patch.object(kani_modo, "_reiniciar_kanivete") as r:
            self.assertTrue(kani_modo._executar("fechar_aba", {"nome": "o kanivete"}, ".").startswith("NÃO FEITO"))
        r.assert_not_called()


if __name__ == "__main__":
    unittest.main()
