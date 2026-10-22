"""Reinício simulado: não encerra nem abre aplicativos reais."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import kanicode


class ReiniciarTest(unittest.TestCase):
    def setUp(self):
        self.app = kanicode.App.__new__(kanicode.App)
        self.app._pendente = None
        self.app._alguma_ocupada = Mock(return_value=False)

    def test_botao_usa_fluxo_existente(self):
        self.app._pedir = Mock(return_value='depois:reiniciar')
        self.assertEqual(self.app.reiniciar(), 'depois:reiniciar')
        self.app._pedir.assert_called_once_with('reiniciar')

    def test_ocupada_aguarda_sem_encerrar(self):
        self.app._alguma_ocupada.return_value = True
        self.app._atualizar = Mock()
        self.assertEqual(self.app.reiniciar(), 'depois:reiniciar')
        self.assertEqual(self.app._pendente, 'reiniciar')
        self.app._pendente_rodar()
        self.app._atualizar.assert_not_called()
        self.app._alguma_ocupada.return_value = False
        self.app._pendente_rodar()
        self.app._pendente_rodar()
        self.app._atualizar.assert_called_once_with('reiniciar')

    def test_livre_agenda_em_thread(self):
        with patch.object(kanicode.threading, 'Thread') as thread:
            self.assertEqual(self.app.reiniciar(), 'reiniciar')
        self.assertEqual(thread.call_args.kwargs['args'], ('reiniciar',))
        thread.return_value.start.assert_called_once()

    def test_reabre_com_mesmos_argumentos_antes_de_sair(self):
        self.app._aberta = True
        self.app.sair = Mock()
        with patch('subprocess.Popen') as abrir, patch.object(sys, 'argv', ['kanicode.py', '--console', '--reaberto', '--abrir']):
            abrir.side_effect = lambda *a, **k: self.app.sair.assert_not_called()
            self.app._atualizar('reiniciar')
        comando = abrir.call_args.args[0]
        self.assertEqual(comando.count('--abrir'), 1)
        self.assertEqual(comando.count('--reaberto'), 1)
        self.assertIn('--console', comando)
        self.app.sair.assert_called_once()

    def test_falha_ao_abrir_nao_fecha_instancia_atual(self):
        self.app._aberta = True
        self.app.sair = Mock()
        with patch('subprocess.Popen', side_effect=OSError('falha simulada')):
            with self.assertRaises(OSError):
                self.app._atualizar('reiniciar')
        self.app.sair.assert_not_called()


if __name__ == '__main__':
    unittest.main()
