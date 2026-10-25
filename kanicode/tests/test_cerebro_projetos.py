"""Fichas de trabalho: mescla, certeza, identidade e grupos, sempre com dados isolados no D."""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import perfil_cerebro as cerebro


class ProjetosTest(unittest.TestCase):
    def setUp(self):
        os.makedirs("D:/kanivete_testes", exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir="D:/kanivete_testes")
        self.patches = []
        for nome in ("DADOS", "PASTA", "ARQ_PROPRIOS", "ARQ_VIDA", "ARQ_ARQUIVO", "ARQ_HIST"):
            valor = self.tmp.name if nome in ("DADOS", "PASTA") else os.path.join(self.tmp.name, nome + ".json")
            p = patch.object(cerebro, nome, valor)
            p.start()
            self.patches.append(p)
        p = patch.object(cerebro, "_fonte_ferramentas_kani", return_value=())
        p.start()
        self.patches.append(p)
        p = patch.object(cerebro, "_fonte_pc", return_value=())
        p.start()
        self.patches.append(p)
        cerebro._MEM.update(chave=None, dados=None, vets=[], idf={})

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        cerebro._MEM.update(chave=None, dados=None, vets=[], idf={})
        self.tmp.cleanup()

    def registrar(self, nome="Cliente — reels outubro", **ficha):
        return cerebro.acao({"acao": "projeto", "projeto": nome, "ficha": ficha or {"formato": "vídeo"},
                             "origem": "conversa confirmada", "certeza": "pailer", "area": "video"})

    def test_mescla_sem_duplicar_e_sem_regravar_igual(self):
        r = self.registrar(cliente="Cliente", resumo="Campanha outubro", ferramentas="Kanivete")
        self.registrar(etapa="legendas")
        nos = cerebro.ler()["nos"]
        self.assertEqual(len(nos), 1)
        self.assertEqual(nos[0]["chave"], r["chave"])
        self.assertEqual(nos[0]["ficha"]["cliente"], "Cliente")
        self.assertEqual(nos[0]["ficha"]["etapa"], "legendas")
        with patch.object(cerebro, "_jgravar") as gravar:
            self.assertFalse(self.registrar(etapa="legendas")["alterado"])
            gravar.assert_not_called()
        self.assertFalse(cerebro.atualizar(r["chave"], texto="sobrescrever")["ok"])

    def test_status_muda_grupo_sem_apagar(self):
        self.registrar()
        self.assertEqual(cerebro.ler()["nos"][0]["grupo"], "andamento")
        self.registrar(status="pausado")
        self.assertEqual(cerebro.ler()["nos"][0]["grupo"], "andamento")
        self.registrar(status="concluído")
        self.assertEqual(cerebro.ler()["nos"][0]["grupo"], "projetos")
        self.assertIn("Projetos", str(cerebro.mapa()))

    def test_certeza_campos_e_projetos_distintos(self):
        r = cerebro.acao({"acao": "projeto", "projeto": "Palpite", "ficha": {"cliente": "X"}})
        self.assertFalse(r["guardado"])
        self.assertFalse(os.path.exists(cerebro.ARQ_PROPRIOS))
        with self.assertRaises(ValueError):
            self.registrar(status="acho que terminou")
        with self.assertRaises(ValueError):
            self.registrar(resumo="x" * 701)
        self.registrar()
        self.registrar("Cliente — flyer outubro", formato="flyer")
        self.assertEqual(len(cerebro.ler()["nos"]), 2)
        self.registrar(cliente="")
        p = cerebro._jler(cerebro.ARQ_PROPRIOS, [])[0]
        self.assertEqual(p["fontes_campos"]["cliente"]["certeza"], "pailer")
        self.assertNotIn("Cliente:", p["texto"])

    def test_ligacao_e_arquivado_nao_ressuscita(self):
        r = self.registrar()
        o = cerebro.guardar("Referência visual", "Referência confirmada da campanha", origem="conversa",
                            certeza="pailer", forcar=True)
        cerebro.acao({"acao": "projeto", "projeto": "Cliente — reels outubro", "ficha": {"etapa": "montagem"},
                      "ligar": [o["chave"]], "certeza": "verificado", "origem": "projeto aberto"})
        self.assertTrue(any(l[2] == 1 for l in cerebro.ler()["ligas"]))
        cerebro.descartar(r["chave"], "teste")
        self.assertFalse(self.registrar(etapa="revisão")["guardado"])


if __name__ == "__main__":
    unittest.main()
