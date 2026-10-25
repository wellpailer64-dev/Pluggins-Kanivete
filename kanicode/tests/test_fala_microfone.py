"""Prioridade do microfone com amostras conhecidas, sem modelos nem dispositivos de áudio."""
from pathlib import Path
import sys
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call, patch
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fala
import kanicode


class PararCallback(Exception):
    pass


class FalaMicrofoneTest(unittest.TestCase):
    def setUp(self):
        with patch.object(fala.threading, 'Thread'):
            self.f = fala.Fala()
        self.abriu = threading.Event()
        self.fluxo = None
        teste = self

        class Fluxo:
            def __init__(self, callback, finished_callback, **_):
                self.callback, self.fim = callback, finished_callback

            def __enter__(self):
                teste.fluxo = self
                teste.abriu.set()
                return self

            def __exit__(self, *_):
                pass

            def abort(self):
                self.fim()

        self.dispositivo = SimpleNamespace(OutputStream=Fluxo, CallbackStop=PararCallback)
        self.patch = patch.dict(sys.modules, {'sounddevice': self.dispositivo})
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.erros = []

    def iniciar(self, valido=None):
        def tocar():
            try:
                self.f._reproduzir(self.f._ger, np.arange(1, 13, dtype=np.float32), 24000, valido)
            except Exception as e:
                self.erros.append(e)
        self.th = threading.Thread(target=tocar, daemon=True)
        self.th.start()
        self.addCleanup(self.encerrar)

    def encerrar(self):
        self.f.parar()
        self.th.join(2)
        self.assertFalse(self.th.is_alive())
        self.assertEqual(self.erros, [])

    def bloco(self):
        saida = np.full((4, 1), -99, np.float32)
        try:
            self.fluxo.callback(saida, 4, None, None)
        except PararCallback:
            self.fluxo.fim()
        return saida[:, 0]

    def test_pausa_silencia_e_retomada_nao_perde_nem_repete_amostras(self):
        self.iniciar()
        self.assertTrue(self.abriu.wait(2))
        np.testing.assert_array_equal(self.bloco(), [1, 2, 3, 4])
        self.f.pausar()
        np.testing.assert_array_equal(self.bloco(), [0, 0, 0, 0])
        np.testing.assert_array_equal(self.bloco(), [0, 0, 0, 0])
        self.f.pausar(False)
        np.testing.assert_array_equal(self.bloco(), [5, 6, 7, 8])
        np.testing.assert_array_equal(self.bloco(), [9, 10, 11, 12])

    def test_fala_nova_aguarda_microfone_e_cancelamento_invalida(self):
        self.f.pausar()
        self.iniciar()
        self.assertFalse(self.abriu.wait(.12))
        self.f.pausar(False)
        self.assertTrue(self.abriu.wait(2))
        self.f.pausar()
        ger = self.f._ger
        self.f.parar()
        self.assertNotEqual(ger, self.f._ger)
        np.testing.assert_array_equal(self.bloco(), [0, 0, 0, 0])

    def test_prontidao_vencida_na_pausa_nao_volta_a_tocar(self):
        valido = threading.Event(); valido.set()
        self.iniciar(valido.is_set)
        self.assertTrue(self.abriu.wait(2))
        np.testing.assert_array_equal(self.bloco(), [1, 2, 3, 4])
        self.f.pausar()
        valido.clear()
        self.f.pausar(False)
        np.testing.assert_array_equal(self.bloco(), [0, 0, 0, 0])


class AppMicrofoneTest(unittest.TestCase):
    def setUp(self):
        with patch.object(kanicode, '_ler_estado', return_value={}):
            self.app = kanicode.App()
        self.app._fala = Mock()
        self.app._voz = SimpleNamespace(_seguir=0, escutar=Mock(return_value=True))
        self.app._na_ui = Mock()
        self.app._para_janela = Mock()

    def test_microfone_pausa_antes_de_abrir_e_nao_cancela_fala(self):
        ordem = Mock()
        ordem.attach_mock(self.app._fala.pausar, 'pausar')
        ordem.attach_mock(self.app._voz.escutar, 'escutar')
        self.assertTrue(self.app.ouvir()['ok'])
        self.assertEqual(ordem.mock_calls[:2], [call.pausar(True), call.escutar(manual=True)])
        self.app._voz_acordou()
        self.app._fala.parar.assert_not_called()
        self.assertTrue(self.app._microfone_prioritario)

    def test_retoma_no_fim_cancelamento_erro_e_sem_liberar_antes_da_captura(self):
        for fim in ('escutando', 'cancelado', 'desligada', 'erro:microfone'):
            with self.subTest(fim=fim):
                self.app._voz_estado('ouvindo')
                self.app._voz_estado('transcrevendo')
                self.assertTrue(self.app._microfone_prioritario)
                self.app._voz_estado(fim)
                self.assertFalse(self.app._microfone_prioritario)
                self.app._fala.pausar.assert_called_with(False)
        self.app._voz._seguir = 5
        self.app._microfone_fala(True)
        self.app._voz_estado('escutando')
        self.assertTrue(self.app._microfone_prioritario)

    def test_falha_de_abertura_libera_fila_e_fala_criada_durante_gravacao_espera(self):
        self.app._voz.escutar.side_effect = RuntimeError('microfone indisponível')
        self.assertFalse(self.app.ouvir()['ok'])
        self.assertFalse(self.app._microfone_prioritario)
        self.app._fala = None
        self.app._microfone_prioritario = True
        with patch.object(fala, 'Fala') as motor:
            self.app._fala_obj()
            motor.return_value.pausar.assert_called_once_with(True)


if __name__ == '__main__':
    unittest.main()
