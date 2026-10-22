"""Voz do Codex com janela recolhida, sem modelo de voz nem dispositivo de audio."""
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import Mock, call, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ajudantes
import kanicode


class CodexVozTest(unittest.TestCase):
    def setUp(self):
        estado = patch.object(kanicode, "_ler_estado", return_value={})
        estado.start()
        self.addCleanup(estado.stop)
        self.app = kanicode.App()
        self.app._fala = Mock()
        self.app._para_janela = Mock()
        self.app._na_ui = Mock()
        self.app._bola_estado = Mock()
        self.app._bola_atividade = Mock()
        self.app._ajudante_ativo = "codex"
        self.app._codex_parar = threading.Event()
        self.app._evento({"t": "ajudante", "quem": "codex", "fase": "inicio"})

    def comentario(self, texto="Conferi a causa.", concluido=True):
        self.app._evento({"t": "codex_progresso", "id": "m1", "texto": texto, "concluido": concluido})

    def test_recolhido_le_comentarios_concluidos_e_nao_le_operacoes(self):
        self.comentario("Conferindo", concluido=False)
        self.app._evento({"t": "ajudante", "quem": "codex", "fase": "passo", "texto": "executando teste"})
        self.app._fala.dizer.assert_not_called()
        self.comentario()
        self.comentario()
        self.comentario("Testes passaram.")
        self.assertEqual(self.app._fala.dizer.call_args_list, [call("Conferi a causa."), call("Testes passaram.")])
        self.app._fala.novo.assert_called_once()
        self.app._fala.terminar.assert_not_called()

    def test_aberto_so_le_ao_recolher_sem_repetir(self):
        self.app._aberta = True
        self.comentario()
        self.app._fala.dizer.assert_not_called()
        self.app.esconder()
        self.app.esconder()
        self.app._fala.dizer.assert_called_once_with("Conferi a causa.")
        self.comentario("Agora corrigi.")
        self.assertEqual(self.app._fala.dizer.call_count, 2)

    def test_reabrir_interrompe_leitura_de_novos_comentarios(self):
        self.comentario()
        self.app._aberta = True
        self.comentario("Chat aberto.")
        self.app._fala.dizer.assert_called_once_with("Conferi a causa.")

    def test_final_nao_repete_comentario_e_termina_fila(self):
        self.comentario("Pronto.")
        self.app._codex_voz({"t": "ajudante_resposta", "quem": "codex", "texto": "Pronto."})
        self.app._fala.dizer.assert_called_once_with("Pronto.")
        self.app._fala.terminar.assert_called_once()
        self.assertFalse(self.app._por_voz)

    def test_final_sem_progresso_tambem_e_lido(self):
        self.app._codex_voz({"t": "ajudante_resposta", "quem": "codex", "texto": "Falha de conexao."})
        self.app._fala.dizer.assert_called_once_with("Falha de conexao.")
        self.app._fala.terminar.assert_called_once()

    def test_parar_corta_audio_e_nao_le_novos_eventos(self):
        self.comentario()
        self.app.parar()
        self.app._fala.parar.assert_called_once()
        self.comentario("Nao deve tocar.")
        self.app._codex_voz({"t": "ajudante_resposta", "quem": "codex", "texto": "Interrompido.", "cancelado": True})
        self.app._fala.dizer.assert_called_once_with("Conferi a causa.")
        self.app._fala.terminar.assert_not_called()

    def test_nova_tarefa_pode_repetir_a_mesma_frase(self):
        self.comentario()
        self.app._evento({"t": "ajudante", "quem": "codex", "fase": "inicio"})
        self.comentario()
        self.assertEqual(self.app._fala.dizer.call_count, 2)

    def test_fim_de_audio_nao_abre_microfone_durante_execucao(self):
        self.app._voz = Mock()
        self.app._fala_estado("fim")
        self.app._voz.escutar.assert_not_called()
        self.app._ajudante_ativo = None
        self.app._fala_estado("fim")
        self.app._voz.escutar.assert_called_once()

    def test_voz_do_claude_continua_recebendo_texto(self):
        self.app._ajudante_ativo = None
        self.app._por_voz = True
        self.app._evento({"t": "inicio"})
        self.app._evento({"t": "texto_novo"})
        self.app._evento({"t": "texto", "d": "Resposta do Claude."})
        self.app._evento({"t": "fim"})
        self.app._fala.novo.assert_called_once()
        self.app._fala.pedaco.assert_called_once_with("Resposta do Claude.")
        self.app._fala.terminar.assert_called_once()
        self.assertFalse(self.app._por_voz)

    def test_falha_de_voz_nao_aborta_execucao(self):
        self.app._fala.dizer.side_effect = RuntimeError("audio indisponivel")
        self.comentario()
        self.assertTrue(any(c.args[0].get("fase") == "erro:audio indisponivel" for c in self.app._para_janela.call_args_list))

    def test_fluxo_real_da_ponte_le_andamento_e_final_uma_vez(self):
        self.app._ajudante_ativo = None
        self.app._codex_id = Mock(return_value=None)
        self.app._codex_registrar = Mock()
        self.app._pasta = Mock(return_value="D:/kanivete_testes")
        fim = threading.Event()
        eventos = []
        def publicar(ev):
            eventos.append(ev)
            if ev.get("t") == "ajudante_resposta":
                fim.set()
        self.app._para_janela = publicar
        def rodar(*args, ao_evento, **kwargs):
            ao_evento({"t": "ajudante", "quem": "codex", "fase": "inicio"})
            ao_evento({"t": "codex_progresso", "texto": "Conferi.", "concluido": True})
            ao_evento({"t": "codex_progresso", "texto": "Pronto.", "concluido": True})
            ao_evento({"t": "ajudante", "quem": "codex", "fase": "fim"})
            return {"texto": "Pronto.", "ok": True, "tokens": 1}
        with patch.object(ajudantes, "codex", side_effect=rodar):
            self.app.ajudante("codex", "Conferir")
            self.assertTrue(fim.wait(5))
        self.assertEqual(self.app._fala.dizer.call_args_list, [call("Conferi."), call("Pronto.")])
        self.app._fala.terminar.assert_called_once()
        self.assertFalse(self.app._ocupada())
        self.assertEqual(eventos[-1]["t"], "ajudante_resposta")


if __name__ == "__main__":
    unittest.main()

