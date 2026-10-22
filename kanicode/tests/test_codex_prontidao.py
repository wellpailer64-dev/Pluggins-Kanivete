"""Confirmacao local sem rede, modelo real, espera de temporizador ou dispositivo de audio."""
from pathlib import Path
import queue
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fala
import kanicode


class ProntidaoAppTest(unittest.TestCase):
    def setUp(self):
        with patch.object(kanicode, "_ler_estado", return_value={}):
            self.app = kanicode.App()
        self.app._fala = Mock()
        self.app._para_janela = Mock()
        self.app._ajudante_ativo = "codex"
        self.app._codex_parar = threading.Event()
        self.timer = patch.object(kanicode.threading, "Timer").start()
        self.addCleanup(patch.stopall)

    def agendar(self):
        self.app._prontidao_agendar()
        self.assertEqual(self.timer.call_args.args[0], 1.0)
        return self.timer.call_args.args[1]

    def test_demora_toca_uma_confirmacao_sem_escrever_no_historico(self):
        tocar = self.agendar()
        self.timer.return_value.start.assert_called_once()
        tocar()
        self.app._fala.prontidao.assert_called_once()
        self.app._para_janela.assert_not_called()

    def test_primeiro_texto_cancela_mesmo_antes_de_concluir_mensagem(self):
        tocar = self.agendar()
        self.app._codex_voz({"t": "codex_progresso", "texto": "Conferindo", "concluido": False})
        tocar()
        self.app._fala.prontidao.assert_not_called()
        self.timer.return_value.cancel.assert_called_once()

    def test_confirmacao_enfileirada_fica_invalida_quando_chega_resposta(self):
        tocar = self.agendar()
        tocar()
        valido = self.app._fala.prontidao.call_args.args[0]
        self.assertTrue(valido())
        self.app._codex_voz({"t": "codex_progresso", "texto": "Resposta", "concluido": False})
        self.assertFalse(valido())

    def test_abrir_chat_impede_aviso_pendente(self):
        tocar = self.agendar()
        self.app._aberta = True
        tocar()
        self.app._fala.prontidao.assert_not_called()

    def test_chat_aberto_nao_agenda_confirmacao(self):
        self.app._aberta = True
        self.app._prontidao_agendar()
        self.timer.assert_not_called()

    def test_parar_cancela_aviso_e_audio_ja_iniciado(self):
        tocar = self.agendar()
        self.app.parar()
        tocar()
        self.app._fala.prontidao.assert_not_called()
        self.app._fala.parar.assert_called_once()

    def test_tarefa_nova_invalida_confirmacao_da_anterior(self):
        anterior = self.agendar()
        nova = self.agendar()
        anterior()
        self.app._fala.prontidao.assert_not_called()
        nova()
        self.app._fala.prontidao.assert_called_once()

    def test_fim_antes_do_aviso_cancela_temporizador(self):
        tocar = self.agendar()
        self.app._codex_voz({"t": "ajudante_resposta", "quem": "codex", "texto": "Pronto"})
        tocar()
        self.app._fala.prontidao.assert_not_called()


class ProntidaoModelosTest(unittest.TestCase):
    def setUp(self):
        with patch.object(kanicode, '_ler_estado', return_value={}):
            self.app = kanicode.App()
        self.app._fala = Mock()
        self.app._para_janela = Mock()
        self.app._bola_estado = Mock()
        self.app._bola_atividade = Mock()
        self.app._na_ui = Mock()
        self.timer = patch.object(kanicode.threading, 'Timer').start()
        self.addCleanup(patch.stopall)

    def agendar(self, quem):
        self.app._ajudante_ativo = quem if quem != 'claude' else None
        self.app._respondendo = quem == 'claude'
        self.app._prontidao_agendar()
        return self.timer.call_args.args[1]

    def test_os_quatro_motores_confirmam_demora(self):
        for quem in ('claude', 'codex', 'kani', 'pickle'):
            with self.subTest(quem=quem):
                self.app._fala.reset_mock()
                self.agendar(quem)()
                self.app._fala.prontidao.assert_called_once()
                self.assertTrue(self.app._fala.prontidao.call_args.args[0]())

    def test_primeira_resposta_cancela_em_todos_os_motores(self):
        for quem, evento in [('claude', {'t':'texto','d':'Conferindo'}),
                             ('codex', {'t':'codex_progresso','texto':'Conferindo'}),
                             ('kani', {'t':'ajudante_resposta','quem':'kani','texto':'Pronto'}),
                             ('pickle', {'t':'pickle_progresso','texto':'Conferindo'})]:
            with self.subTest(quem=quem):
                self.app._fala.reset_mock()
                tocar = self.agendar(quem)
                self.app._codex_voz(evento)
                tocar()
                self.app._fala.prontidao.assert_not_called()

    def test_fim_erro_parar_e_permissao_invalidam_aviso_enfileirado(self):
        for quem in ('claude', 'codex', 'kani', 'pickle'):
            for fim in ('fim', 'saiu', 'permissao', 'pergunta', 'parar'):
                with self.subTest(quem=quem, fim=fim):
                    self.agendar(quem)()
                    valido = self.app._fala.prontidao.call_args.args[0]
                    self.assertTrue(valido())
                    if fim == 'parar':
                        self.app.parar()
                    else:
                        self.app._codex_voz({'t':fim})
                    self.assertFalse(valido())

    def test_aba_de_tras_nao_perde_aviso_por_troca_ou_cancelamento_de_outra(self):
        tocar1 = self.agendar('claude')
        self.app._abas['2'] = kanicode._Aba('2', 'kani')
        self.app._aba_ativa = '2'
        tocar2 = self.agendar('kani')
        self.app._prontidao_cancelar()
        tocar2()
        self.app._fala.prontidao.assert_not_called()
        tocar1()
        self.app._fala.prontidao.assert_called_once()
        # O callback é usado depois pela thread de áudio, fora do contexto da aba 1.
        self.assertTrue(self.app._fala.prontidao.call_args.args[0]())
        self.app._na_aba('1', self.app._prontidao_cancelar)()
        self.assertFalse(self.app._fala.prontidao.call_args.args[0]())

    def test_envio_claude_agenda_e_falha_de_envio_cancela(self):
        self.app._sessao = Mock(sessao_id='existente', ocupada=False)
        self.app._kani_para_claude = Mock(return_value='')
        self.assertTrue(self.app.enviar('Analise este vídeo'))
        tocar = self.timer.call_args.args[1]
        tocar()
        self.app._fala.prontidao.assert_called_once()
        self.app._fala.reset_mock()
        self.app._sessao.enviar.side_effect = OSError('falha de envio')
        self.assertFalse(self.app.enviar('Continue'))
        self.timer.call_args.args[1]()
        self.app._fala.prontidao.assert_not_called()

    def test_envio_dos_tres_ajudantes_agenda(self):
        for quem in ('codex', 'kani', 'pickle'):
            with self.subTest(quem=quem):
                self.app._ajudante_ativo = None
                self.app._respondendo = False
                with patch.object(kanicode.threading, 'Thread'):
                    self.app.ajudante(quem, 'Analise este vídeo')
                self.assertIsNotNone(self.app._prontidao_pendente)
                self.app._prontidao_cancelar()
                self.app._ajudante_trava.release()


class ProntidaoAudioTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=r"D:\kanivete_testes")
        self.addCleanup(self.temp.cleanup)
        self.cache = Path(self.temp.name) / "prontidao.npz"
        self.patches = [patch.object(fala, "CACHE_PRONTIDAO", str(self.cache)),
                        patch.object(fala, "MODELOS", self.temp.name),
                        patch.object(fala.threading, "Thread")]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.f = fala.Fala()
        self.f.carregar = Mock(return_value=SimpleNamespace(create=Mock(return_value=(np.ones(2400, dtype=np.float32), 24000))))

    def test_prepara_uma_vez_e_reproduz_cache_sem_sintese(self):
        self.f.preparar_prontidao()
        self.assertTrue(self.cache.is_file())
        self.assertEqual(self.f.carregar.return_value.create.call_count, len(fala.PRONTIDAO))
        outra = fala.Fala()
        outra.carregar = Mock(side_effect=AssertionError("nao sintetizar"))
        for _ in fala.PRONTIDAO:
            self.assertTrue(outra.prontidao(lambda: True))
        self.assertEqual(outra._audios.qsize(), len(fala.PRONTIDAO))
        outra.carregar.assert_not_called()

    def test_fila_cheia_nao_bloqueia_e_nao_altera_pendencias(self):
        self.f.preparar_prontidao()
        for _ in range(3):
            self.assertTrue(self.f.prontidao(lambda: True))
        self.assertFalse(self.f.prontidao(lambda: True))
        self.assertEqual(self.f._pend, 3)

    def test_aviso_cancelado_na_fila_nao_toca_nem_atrapalha_audio_real(self):
        self.f.preparar_prontidao()
        self.f.prontidao(lambda: False)
        self.assertTrue(self.f._audios.empty())
        self.f.prontidao(lambda: True)
        ger, audio, taxa, _ = self.f._audios.get_nowait()
        self.f._audios = Mock()
        self.f._audios.get.side_effect = [(ger, audio, taxa, lambda: False), (ger, audio, taxa, None), StopIteration]
        self.f._audios.empty.return_value = True
        self.f._pend = 2
        self.f._estado = Mock()
        dispositivo = SimpleNamespace(play=Mock(), wait=Mock())
        with patch.dict(sys.modules, {"sounddevice": dispositivo}):
            with self.assertRaises(StopIteration):
                self.f._tocar()
        dispositivo.play.assert_called_once()
        self.assertEqual(self.f._pend, 0)

    def test_primeiro_uso_confirma_apos_preparar_se_pedido_ainda_vale(self):
        valido = threading.Event()
        valido.set()
        self.assertFalse(self.f.prontidao(valido.is_set))
        preparar = fala.threading.Thread.call_args.kwargs['target']
        preparar()
        self.assertEqual(self.f._audios.qsize(), 1)
        self.assertTrue(self.cache.is_file())

    def test_primeiro_uso_cancelado_nao_fala_apos_preparar(self):
        valido = threading.Event()
        valido.set()
        self.f.prontidao(valido.is_set)
        preparar = fala.threading.Thread.call_args.kwargs['target']
        valido.clear()
        preparar()
        self.assertTrue(self.f._audios.empty())

    def test_cache_corrompido_nao_impede_a_resposta(self):
        self.cache.write_bytes(b"nao e um arquivo npz")
        self.assertFalse(self.f.prontidao(lambda: True))
        self.assertTrue(self.f._audios.empty())


if __name__ == "__main__":
    unittest.main()

