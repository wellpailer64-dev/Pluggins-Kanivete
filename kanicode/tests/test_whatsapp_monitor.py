"""Monitor isolado: referências, filtros, deduplicação, áudio e desligamento."""
import copy
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from whatsapp_monitor import Monitor, observar


def mensagem(id_, conversa="Ana", **campos):
    return dict(id=id_, conversa=conversa, pessoa=conversa, texto="Olá", audio=False, **campos)


def foto(*mensagens, conversa="Ana", previas=None):
    return dict(aba="teste", pronto=True, conversa=conversa, mensagens=list(mensagens), previas=previas or [])


class MonitorTest(unittest.TestCase):
    def setUp(self):
        pasta = Path("D:/kanivete_testes/whatsapp")
        pasta.mkdir(parents=True, exist_ok=True)
        tmp = tempfile.TemporaryDirectory(dir=pasta)
        self.addCleanup(tmp.cleanup)
        self.arquivo = Path(tmp.name) / "config.json"
        self.m = Monitor(lambda texto: True, arquivo=self.arquivo)

    def test_referencia_novas_duplicadas_e_historico_ao_rolar(self):
        a, b, velho = mensagem("a"), mensagem("b"), mensagem("velho")
        self.m.receber([foto(a)])
        self.assertTrue(self.m.fila.empty())
        self.m.receber([foto(velho, a, b)])
        self.assertEqual(self.m.fila.get_nowait()["id"], "b")
        self.m.receber([foto(a, b)])
        self.assertTrue(self.m.fila.empty())
        self.m.receber([foto(mensagem("c", "Bia"), conversa="Bia")])
        self.assertTrue(self.m.fila.empty())
        self.m.receber([foto(mensagem("d", "Bia"), conversa="Bia")])
        self.assertTrue(self.m.fila.empty())  # sem âncora visível: só atualiza referência

    def test_conversa_carregando_primeiro_lote_so_estabelece_referencia(self):
        self.m.receber([foto()])
        self.m.receber([foto(mensagem("primeira"))])
        self.assertTrue(self.m.fila.empty())
        self.m.receber([foto(mensagem("primeira"), mensagem("nova"))])
        self.assertEqual(self.m.fila.get_nowait()["id"], "nova")

    def test_previas_e_filtros_sem_reler_as_iniciais(self):
        p = dict(mensagem("p1", "Grupo"), previa=True, nao_lidas="1 mensagem não lida")
        self.m.receber([foto(previas=[p])])
        self.m.receber([foto(previas=[dict(p, id="p2", texto="Novo", nao_lidas="2 mensagens não lidas")])])
        self.assertEqual(self.m.fila.get_nowait()["conversa"], "Grupo")
        self.m.configurar(dict(ignorados=["GRUPO"], palavras=["propaganda"]))
        self.m.receber([foto(previas=[dict(p, id="p3", texto="Mais", nao_lidas="3 mensagens não lidas")])])
        self.assertTrue(self.m.fila.empty())
        self.assertTrue(self.m.ignorar(dict(mensagem("x"), texto="Uma PROPAGANDA")))
        self.assertTrue(self.m.ignorar(dict(mensagem("x"), pessoa="Grupo")))

    def test_persistencia_so_de_preferencias_e_copias(self):
        self.m.configurar(dict(ignorados=[" Ana ", "Ana"], palavras=["anúncio"], audios=False))
        self.m.historico.append(mensagem("privado"))
        outro = Monitor(lambda t: True, arquivo=self.arquivo)
        self.assertEqual(outro.ignorados, ["Ana"])
        self.assertFalse(outro.audios)
        self.assertNotIn("privado", self.arquivo.read_text(encoding="utf-8"))
        est = self.m.estado(); est["ignorados"].clear(); est["historico"][0]["texto"] = "Mudou"
        self.assertEqual(self.m.ignorados, ["Ana"])
        self.assertEqual(self.m.historico[0]["texto"], "Olá")
        with self.assertRaises(ValueError):
            self.m.configurar(dict(ignorados="não é lista"))

    def test_audio_resumo_filtro_e_falha_local(self):
        self.m.fim.clear()
        self.m.transcrever = lambda m: "Reunião amanhã às dez"
        self.m.resumir = lambda t: "Reunião amanhã, 10h."
        audio = dict(mensagem("audio"), audio=True)
        self.assertEqual(self.m.preparar(audio)["resumo"], "Reunião amanhã, 10h.")
        self.m.palavras = ["reunião"]
        self.assertIsNone(self.m.preparar(audio))
        self.m.palavras = []
        self.m.resumir = lambda t: (_ for _ in ()).throw(RuntimeError("sem modelo"))
        self.assertIn("Transcrição:", self.m.preparar(audio)["resumo"])
        self.m.transcrever = lambda m: (_ for _ in ()).throw(RuntimeError("indisponível"))
        self.assertIn("não consegui transcrever", self.m.preparar(audio)["texto"])
        self.m.transcrever = lambda m: self.fail("prévia não deve carregar áudio")
        self.assertIn("Abra a conversa", self.m.preparar(dict(audio, previa=True))["texto"])

    def test_desligar_durante_transcricao_nao_fala_nem_resuma(self):
        entrou, soltar = threading.Event(), threading.Event()
        self.m.fim.clear()
        def transcrever(m):
            entrou.set(); soltar.wait(3); return "texto privado"
        self.m.transcrever = transcrever
        self.m.resumir = lambda t: self.fail("não resumir após desligar")
        self.m.falar = lambda t: self.fail("não falar após desligar")
        self.m.fila.put(dict(mensagem("audio"), audio=True))
        t = threading.Thread(target=self.m._ler)
        t.start()
        self.assertTrue(entrou.wait(2))
        self.m.ligar(False); soltar.set(); t.join(3)
        self.assertFalse(t.is_alive())
        self.assertEqual(len(self.m.historico), 0)

    def test_ligar_desligar_sem_reanunciar(self):
        base = foto(mensagem("a"))
        self.m.observar = lambda: [copy.deepcopy(base)]
        self.assertTrue(self.m.ligar(True)["ligado"])
        threads = list(self.m.threads)
        self.m.ligar(True)
        self.assertEqual(threads, self.m.threads)
        self.assertFalse(self.m.ligar(False)["ligado"])
        for t in threads:
            t.join(3)
            self.assertFalse(t.is_alive())

    def test_fala_curta_sem_repetir_remetente_em_mensagens_seguidas(self):
        mensagens = [
            dict(mensagem("1", "Vini"), texto="Oi", previa=True),
            dict(mensagem("2", "Vini"), texto="Tudo bem?", previa=True),
            dict(mensagem("3", "Ana"), texto="Bom dia"),
            dict(mensagem("4", "Vini"), texto="Voltei"),
            dict(mensagem("5", "Grupo"), pessoa="Vini", texto="Reunião às dez"),
            dict(mensagem("6", "Grupo"), pessoa="Vini", texto="Confirmado"),
            dict(mensagem("7", "Grupo"), pessoa="Ana", texto="Estarei lá"),
        ]
        falas = []
        def falar(texto):
            falas.append(texto)
            if len(falas) == len(mensagens):
                self.m.fim.set()
            return True
        self.m.falar = falar
        self.m.fim.clear()
        for m in mensagens:
            self.m.fila.put(m)
        self.m._ler()
        self.assertEqual(falas, ["Mensagem de Vini. Oi", "Tudo bem?", "Mensagem de Ana. Bom dia",
                                 "Mensagem de Vini. Voltei", "Mensagem de Vini, em Grupo. Reunião às dez",
                                 "Confirmado", "Mensagem de Ana, em Grupo. Estarei lá"])
        # Nova sessão reapresenta o remetente, mesmo se foi o último a falar.
        self.m.falar = lambda texto: (falas.append(texto), self.m.fim.set(), True)[-1]
        self.m.fim.clear()
        self.m.fila.put(mensagens[-1])
        self.m._ler()
        self.assertEqual(falas[-1], "Mensagem de Ana, em Grupo. Estarei lá")

    def test_observacao_so_abas_whatsapp_do_processo_sem_portas(self):
        class KB:
            ativo = staticmethod(lambda: True)
            abas = staticmethod(lambda: [dict(id="ok", url="https://web.whatsapp.com/"),
                                          dict(id="falsa", url="https://web.whatsapp.com.falso/"),
                                          dict(id="local", url="http://127.0.0.1:9333/")])
            chamadas = []
            @classmethod
            def js(cls, codigo, aba):
                cls.chamadas.append(aba); return dict(pronto=True)
        with patch.dict("sys.modules", kanibrowser=KB):
            self.assertEqual(observar()[0]["aba"], "ok")
        self.assertEqual(KB.chamadas, ["ok"])


if __name__ == "__main__":
    unittest.main()
