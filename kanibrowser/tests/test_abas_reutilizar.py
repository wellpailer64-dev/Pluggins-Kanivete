"""Reutilização de abas sem abrir navegador, navegar em conta real ou fechar páginas."""
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import kanibrowser as kb


class AbasReutilizar(unittest.TestCase):
    def test_trabalho_silencioso_nao_acende_status(self):
        with patch.dict(kb._k, {"fazendo": [], "log": []}), patch.object(kb, "aba_kani", return_value="kani"):
            with kb.trabalho("monitor WhatsApp", registrar=False) as aba:
                self.assertEqual(aba, "kani")
                self.assertEqual(kb._k["fazendo"], [])
                self.assertEqual(kb._k["log"], [])

    def setUp(self):
        self.abas = [{"id": "wa", "url": "https://web.whatsapp.com/", "titulo": "WhatsApp", "kani": False}]
        self.patches = [
            patch.object(kb, "abas", side_effect=lambda: list(self.abas)),
            patch.object(kb, "frente"),
            patch.object(kb, "_cdp"),
            patch.dict(kb._k, {"aba": "agente"}),
        ]
        self.mocks = [p.start() for p in self.patches]
        for p in self.patches:
            self.addCleanup(p.stop)

    def test_nova_reutiliza_whatsapp_sem_criar(self):
        with patch.object(kb, "_nova") as criar:
            r = kb.nova("https://WEB.whatsapp.com:443")
        self.assertEqual(r["id"], "wa")
        self.assertTrue(r["reutilizada"])
        criar.assert_not_called()
        self.mocks[1].assert_called_once_with("wa")

    def test_ir_reutiliza_sem_navegar_e_proximas_operacoes_usam_a_mesma_aba(self):
        kb.ir("https://web.whatsapp.com")
        self.assertEqual(kb._k["aba"], "wa")
        self.mocks[2].assert_not_called()
        with patch.object(kb, "ativo", return_value=True):
            self.assertEqual(kb._aba(), "wa")

    def test_aba_explicita_navega_sem_trocar_alvo_do_agente(self):
        kb.ir("https://web.whatsapp.com", "outra")
        self.mocks[2].assert_called_once_with("outra", "Page.navigate", {"url": "https://web.whatsapp.com"})
        self.assertEqual(kb._k["aba"], "agente")

    def test_paginas_buscas_e_rotas_diferentes_nao_sao_duplicatas(self):
        self.abas[:] = [{"id": "doc", "url": "https://exemplo.com/doc/1?q=a#parte1"}]
        for url in ["https://exemplo.com/doc/2?q=a#parte1", "https://exemplo.com/doc/1?q=b#parte1",
                    "https://exemplo.com/doc/1?q=a#parte2", "http://exemplo.com/doc/1?q=a#parte1"]:
            with self.subTest(url=url), patch.object(kb, "_nova", return_value={"id": "nova"}) as criar:
                self.assertEqual(kb.nova(url)["id"], "nova")
                criar.assert_called_once_with(url)

    def test_sem_correspondencia_ir_navega_normalmente(self):
        kb.ir("https://outro.com/")
        self.mocks[2].assert_called_once_with(None, "Page.navigate", {"url": "https://outro.com/"})
        self.assertEqual(kb._k["aba"], "agente")

    def test_prefere_aba_do_agente_se_ja_houver_duas_iguais(self):
        self.abas.append({"id": "agente", "url": "https://web.whatsapp.com/"})
        self.assertEqual(kb.nova("https://web.whatsapp.com")["id"], "agente")
        self.assertEqual(len(self.abas), 2)  # não fecha abas nem decide que uma tarefa alheia terminou

    def test_pedidos_simultaneos_nao_criam_duas_abas(self):
        resultados = []
        def criar(url):
            aba = {"id": "nova", "url": url}
            self.abas.append(aba)
            return aba
        with patch.object(kb, "_nova", side_effect=criar) as nova:
            threads = [threading.Thread(target=lambda: resultados.append(kb.nova("https://outro.com/"))) for _ in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            nova.assert_called_once()
        self.assertEqual([r["id"] for r in resultados], ["nova"] * 4)


if __name__ == "__main__":
    unittest.main()
