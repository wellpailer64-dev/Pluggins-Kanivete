"""Efeitos do Pailer na doca, sem reproduzir áudio nem abrir o app."""
import unittest
from unittest.mock import patch

import sons_bolinha as sons


class SonsChatTest(unittest.TestCase):
    def test_arquivos_reais_e_troca_rapida(self):
        with patch.object(sons, "_mci", return_value=0) as mci, patch.object(sons, "_abertos", []), patch.object(sons, "_ultimo", 100), patch.object(sons.time, "monotonic", return_value=100.1):
            self.assertTrue(sons.tocar("entrada_chat"))
            self.assertTrue(sons.tocar("saida_chat"))
            comandos = [c.args[0] for c in mci.call_args_list]
            self.assertTrue(any('inter chat.wav" type mpegvideo' in c for c in comandos))
            self.assertTrue(any('out chat.wav" type mpegvideo' in c for c in comandos))
            self.assertEqual(sum(c.startswith('play ') for c in comandos), 2)
            self.assertIn('close kcbola0', comandos)
            self.assertFalse(sons.tocar("erro"))

    def test_arquivo_ausente_nao_toca(self):
        with patch.object(sons.os.path, "isfile", return_value=False), patch.object(sons, "_mci") as mci:
            self.assertFalse(sons.tocar("entrada_chat"))
            self.assertFalse(sons.tocar("saida_chat"))
            mci.assert_not_called()


if __name__ == "__main__":
    unittest.main()
