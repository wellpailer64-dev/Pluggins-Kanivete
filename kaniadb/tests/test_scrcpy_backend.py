"""Protocolo scrcpy 4.x sem sockets, subprocessos ou aparelho real."""
import io
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scrcpy_backend import Scrcpy, receber


class Fragmentado:
    def __init__(self, dados):
        self.dados = dados

    def recv(self, n):
        n = min(n, 3)
        parte, self.dados = self.dados[:n], self.dados[n:]
        return parte


class ScrcpyTest(unittest.TestCase):
    def criar(self):
        b = Scrcpy('adb.exe', 'serial', 'D:/kanivete_testes', 720, 1600)
        b.controle = Mock()
        return b

    def test_toque_preserva_escala_e_envia_down_up_sem_adb(self):
        b = self.criar()
        b.comando('tocar', {'largura': 1080, 'altura': 2400}, x=540, y=1200)
        pacotes = [c.args[0] for c in b.controle.sendall.call_args_list]
        self.assertEqual([len(p) for p in pacotes], [32, 32])
        down = struct.unpack('>BBQIIHHHII', pacotes[0])
        up = struct.unpack('>BBQIIHHHII', pacotes[1])
        self.assertEqual(down, (2, 0, 0, 360, 800, 720, 1600, 65535, 0, 0))
        self.assertEqual(up[1], 1)
        self.assertEqual(up[7], 0)

    def test_tecla_usa_socket_persistente(self):
        b = self.criar()
        b.comando('tecla', {}, codigo='KEYCODE_BACK')
        dados = b.controle.sendall.call_args.args[0]
        self.assertEqual(len(dados), 28)
        self.assertEqual(struct.unpack('>BBIII', dados[:14]), (0, 0, 4, 0, 0))
        self.assertEqual(struct.unpack('>BBIII', dados[14:]), (0, 1, 4, 0, 0))

    def test_movimento_e_cancelamento(self):
        b = self.criar()
        b.comando('ponteiro', {'largura': 720, 'altura': 1600}, tipo='move', x=10, y=20)
        b.comando('ponteiro', {'largura': 720, 'altura': 1600}, tipo='cancel', x=10, y=20)
        self.assertEqual([c.args[0][1] for c in b.controle.sendall.call_args_list], [2, 3])
        with self.assertRaises(ValueError):
            b.comando('ponteiro', {'largura': 720, 'altura': 1600}, tipo='invalido', x=0, y=0)

    def test_pacotes_fragmentados_e_mudanca_de_sessao(self):
        class Destino(io.BytesIO):
            def close(self):
                pass
        b = self.criar()
        payload = b'\x00\x00\x00\x01h264'
        dados = struct.pack('>III', 0x80000000, 1600, 720)
        dados += struct.pack('>QI', 1 << 62, len(payload)) + payload
        b.video = Fragmentado(dados)
        destino = Destino()
        b.bombear(destino)
        self.assertEqual(destino.getvalue(), payload)
        self.assertEqual((b.largura, b.altura), (1600, 720))
        with self.assertRaises(OSError):
            receber(Fragmentado(b''), 4)

    def test_limpeza_so_remove_o_encaminhamento_e_auxiliar_proprios(self):
        b = self.criar()
        b.controle = None
        b.porta = 47123
        b._adb = Mock()
        b.fechar()
        b.fechar()
        self.assertEqual(b._adb.call_count, 2)
        b._adb.assert_any_call('forward', '--remove', 'tcp:47123')
        b._adb.assert_any_call('shell', 'rm', '-f', b.remoto)
        self.assertRegex(b.remoto, r'^/data/local/tmp/kaniadb-[0-9a-f]{6}\.jar$')


if __name__ == '__main__':
    unittest.main()
