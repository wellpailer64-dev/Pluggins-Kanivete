"""Fluxo fragmentado, último quadro, timeout e limpeza; sem adb ou FFmpeg reais."""
import io
from pathlib import Path
import queue
import sys
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from video_continuo import VideoContinuo, _SeparadorJPEG


class Canal:
    def __init__(self, dados=()):
        self.fila = queue.Queue()
        self.closed = False
        for pedaco in dados:
            self.fila.put(pedaco)

    def read1(self, tamanho):
        return self.fila.get()

    def close(self):
        self.closed = True
        self.fila.put(b'')


class Processo:
    def __init__(self, dados=()):
        self.stdin, self.stdout, self.stderr = None, Canal(dados), io.BytesIO()
        self.morto, self.encerramentos = False, 0

    def poll(self):
        return 0 if self.morto else None

    def kill(self):
        self.morto = True
        self.encerramentos += 1
        self.stdout.close()

    def wait(self, timeout):
        return 0


class VideoTest(unittest.TestCase):
    def setUp(self):
        p = patch('video_continuo.localizar_scrcpy', return_value=None)
        p.start()
        self.addCleanup(p.stop)

    def test_fragmentos_e_descarte_dos_quadros_antigos(self):
        s = _SeparadorJPEG()
        self.assertEqual(s.receber(b'ruido\xff'), (None, 0))
        self.assertEqual(s.receber(b'\xd8a\xff'), (None, 0))
        self.assertEqual(s.receber(b'\xd9\xff\xd8b\xff\xd9'), (b'\xff\xd8b\xff\xd9', 2))
        self.assertEqual(len(s.dados), 0)

    def test_fluxo_so_entrega_ultimo_jpeg_e_fecha_somente_processos_proprios(self):
        processos = [Processo(), Processo([b'\xff\xd8a\xff\xd9\xff\xd8b\xff\xd9'])]
        with patch('video_continuo.subprocess.Popen', side_effect=processos) as iniciar:
            v = VideoContinuo('adb.exe', 'serial-teste', ffmpeg='ffmpeg.exe')
            self.assertEqual(v.pegar(timeout=1), b'\xff\xd8b\xff\xd9')
            self.assertEqual(v.estado()['quadros'], 2)
            self.assertTrue(v.estado()['pronto'])
            v.carimbo -= 5
            self.assertEqual(v.ultimo(), b'\xff\xd8b\xff\xd9')
            self.assertGreater(v.estado()['idade_ms'], 4000)
            self.assertIn('--output-format=h264', iniciar.call_args_list[0].args[0])
            self.assertNotIn('screencap', iniciar.call_args_list[0].args[0])
            v.fechar()
            v.fechar()
            self.assertEqual([p.encerramentos for p in processos], [1, 1])
            self.assertFalse(v.estado()['pronto'])

    def test_timeout_encerra_pipeline_e_permite_nova_tentativa(self):
        processos = [Processo(), Processo(), Processo(), Processo([b'\xff\xd8novo\xff\xd9'])]
        with patch('video_continuo.subprocess.Popen', side_effect=processos):
            v = VideoContinuo('adb.exe', 's', ffmpeg='ffmpeg.exe')
            with self.assertRaises(TimeoutError):
                v.pegar(timeout=0.03)
            self.assertEqual([p.encerramentos for p in processos[:2]], [1, 1])
            self.assertEqual(v.pegar(timeout=1), b'\xff\xd8novo\xff\xd9')
            v.fechar()

    def test_eof_nao_reapresenta_quadro_anterior(self):
        processos = [Processo(), Processo([b''])]
        with patch('video_continuo.subprocess.Popen', side_effect=processos):
            v = VideoContinuo('adb.exe', 's', ffmpeg='ffmpeg.exe')
            with self.assertRaisesRegex(RuntimeError, 'encerrou'):
                v.pegar(timeout=1)
            self.assertFalse(v.estado()['pronto'])
            v.fechar()


if __name__ == '__main__':
    unittest.main()
