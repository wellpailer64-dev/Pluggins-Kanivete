"""Canal local isolado: interface lenta não bloqueia controle; prévia não executa Git."""
import socket
import threading
import unittest
from unittest.mock import Mock, patch

import kanicode


class CanalPreviaTest(unittest.TestCase):
    def setUp(self):
        self.app = kanicode.App.__new__(kanicode.App)
        self.app._saindo = False
        self.entrou = threading.Event()
        self.liberar = threading.Event()
        self.addCleanup(self.liberar.set)
        self.srv = socket.socket()
        self.srv.bind(('127.0.0.1', 0))
        self.srv.listen(8)
        self.endereco = self.srv.getsockname()
        self.thread = threading.Thread(target=self.app._servir, args=(self.srv,), daemon=True)
        self.thread.start()
        self.addCleanup(self.encerrar)

    def encerrar(self):
        self.liberar.set()
        self.app._saindo = True
        try:
            self.srv.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.srv.close()
        self.thread.join(2)

    def chamar(self, cmd):
        with socket.create_connection(self.endereco, timeout=2) as c:
            c.sendall((cmd + '\n').encode())
            return c.recv(64).decode().strip()

    def bloquear(self, *args):
        self.entrou.set()
        self.liberar.wait(3)

    def test_mostrar_lento_nao_prende_ping_reinicio_ou_previa(self):
        self.app.mostrar = self.bloquear
        self.app.previa_git = Mock()
        self.app._pedir = Mock(return_value='depois:reiniciar')
        self.assertEqual(self.chamar('mostrar'), 'ok')
        self.assertTrue(self.entrou.wait(2))
        self.assertEqual(self.chamar('ping'), 'ok')
        self.assertEqual(self.chamar('reiniciar'), 'depois:reiniciar')
        self.assertEqual(self.chamar('previa_git'), 'ok')
        self.app._pedir.assert_called_once_with('reiniciar')

    def test_evento_lento_nao_prende_ping(self):
        self.app._evento = self.bloquear
        self.assertEqual(self.chamar('evento {"t":"teste"}'), 'ok')
        self.assertTrue(self.entrou.wait(2))
        self.assertEqual(self.chamar('ping'), 'ok')

    def test_previa_chama_so_animacao_da_janela(self):
        self.app._aberta = True
        self.app._janela = Mock()
        self.app.mostrar = Mock()
        with patch('subprocess.Popen') as processo:
            self.app.previa_git()
        self.app.mostrar.assert_not_called()
        processo.assert_not_called()
        js = self.app._janela.evaluate_js.call_args.args[0]
        self.assertIn("kbGitAnimar('push')", js)
        self.assertNotIn('kcEv', js)

    def test_previa_abre_janela_se_recolhida(self):
        self.app._aberta = False
        self.app._janela = Mock()
        self.app.mostrar = Mock()
        self.app.previa_git()
        self.app.mostrar.assert_called_once()


if __name__ == '__main__':
    unittest.main()
