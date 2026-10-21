"""Valida falhas do driver e leituras parciais sem exigir uma GPU no computador."""
import ctypes
import unittest
from unittest.mock import Mock, patch

import gpu


class GpuTest(unittest.TestCase):
    def dll(self):
        dll = Mock()
        dll.nvmlInit_v2.return_value = 0
        dll.nvmlDeviceGetHandleByIndex_v2.return_value = 0

        def nome(_, buf, tamanho):
            buf.value = b'GPU de teste'
            return 0

        def utilizacao(_, ptr):
            ctypes.cast(ptr, ctypes.POINTER(gpu._Utilizacao)).contents.gpu = 0
            return 0

        def memoria(_, ptr):
            m = ctypes.cast(ptr, ctypes.POINTER(gpu._Memoria)).contents
            m.used, m.total = 2 * 1024 ** 3, 8 * 1024 ** 3
            return 0

        dll.nvmlDeviceGetName.side_effect = nome
        dll.nvmlDeviceGetUtilizationRates.side_effect = utilizacao
        dll.nvmlDeviceGetMemoryInfo.side_effect = memoria
        dll.nvmlDeviceGetTemperature.return_value = 3  # não suportado
        return dll

    def test_driver_inicializa_uma_vez_zero_e_memoria_64_bits(self):
        dll = self.dll()
        with patch.object(gpu.C, 'CDLL', return_value=dll), patch.object(gpu.atexit, 'register'):
            monitor = gpu._Monitor()
            d = monitor.ler()
            self.assertTrue(d['disponivel'])
            self.assertEqual(d['uso'],0)
            self.assertEqual(d['memoria_total'],8589934592)
            self.assertIsNone(d['temperatura'])
            self.assertEqual(monitor.ler(),d)
            dll.nvmlInit_v2.assert_called_once()
            monitor.fechar(); monitor.fechar()
            dll.nvmlShutdown.assert_called_once()

    def test_sem_driver_nao_repete_carga_a_cada_amostra(self):
        with patch.object(gpu.C, 'CDLL', side_effect=OSError('sem driver')) as carregar:
            monitor = gpu._Monitor()
            self.assertEqual(monitor.ler(),{'disponivel':False})
            tentativas = carregar.call_count
            self.assertEqual(monitor.ler(),{'disponivel':False})
            self.assertEqual(carregar.call_count,tentativas)

    def test_perda_de_gpu_nao_mostra_valores_antigos(self):
        dll = self.dll()
        with patch.object(gpu.C, 'CDLL', return_value=dll), patch.object(gpu.atexit, 'register'):
            monitor = gpu._Monitor()
            self.assertTrue(monitor.ler()['disponivel'])
            dll.nvmlDeviceGetUtilizationRates.side_effect = None
            dll.nvmlDeviceGetUtilizationRates.return_value = 15
            dll.nvmlDeviceGetMemoryInfo.side_effect = None
            dll.nvmlDeviceGetMemoryInfo.return_value = 15
            d = monitor.ler()
            self.assertFalse(d['disponivel'])
            self.assertIsNone(d['uso'])
            self.assertIsNone(d['memoria_usada'])
            monitor.fechar()
