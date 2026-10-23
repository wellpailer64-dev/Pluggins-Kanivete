"""Espaço inicial da janela com API nativa simulada; não controla programas."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import kanicode


class JanelaPainelTest(unittest.TestCase):
    def setUp(self):
        self.app = kanicode.App.__new__(kanicode.App)
        self.app._bola = None
        self.app.maximizada = Mock(return_value=False)
        self.app.tam_inicio = Mock(return_value=[100, 80, 550, 660])
        self.app._area = Mock(return_value=[0, 1920])
        self.app.tam_mudar = Mock()

    def test_abre_espaco_preservando_altura(self):
        self.assertTrue(self.app.painel_espaco())
        self.app.tam_mudar.assert_called_once_with(100, 80, kanicode.JW+270, 660)

    def test_nao_diminui_janela_ja_grande(self):
        self.app.tam_inicio.return_value = [100, 80, 1200, 800]
        self.assertFalse(self.app.painel_espaco())
        self.app.tam_mudar.assert_not_called()

    def test_maximizada_e_tela_cheia_ficam_com_o_usuario(self):
        self.app.maximizada.return_value = True
        self.assertFalse(self.app.painel_espaco())
        self.app.maximizada.return_value = False
        self.app._imagem_tela_cheia = True
        self.assertFalse(self.app.painel_espaco())
        self.app.tam_mudar.assert_not_called()

    def test_limite_do_monitor_e_respeitado(self):
        self.app._area.return_value = [-800, 0]
        self.app.tam_inicio.return_value = [-550, 80, 550, 660]
        self.app.painel_espaco(500)
        self.app.tam_mudar.assert_called_once_with(-800, 80, 800, 660)

    def test_escala_do_windows_e_considerada(self):
        self.app._bola = SimpleNamespace(escala=1.5)
        self.app.painel_espaco(400)
        self.app.tam_mudar.assert_called_once_with(100, 80, round((kanicode.JW+400)*1.5), 660)


if __name__ == '__main__':
    unittest.main()

