"""Ponte OpenCode simulada: não executa cliente nem faz chamada de rede."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import opencode_mvp as oc


class OpenCodeMvpTest(unittest.TestCase):
    def test_cliente_ausente_nao_executa(self):
        with patch.object(oc, 'executavel', return_value=None), patch.object(oc.subprocess, 'run') as rodar:
            self.assertFalse(oc.info()['disponivel'])
            self.assertFalse(oc.testar('Olá')['ok'])
            rodar.assert_not_called()

    def test_argumentos_invalidos_nao_executam(self):
        with patch.object(oc.subprocess, 'run') as rodar:
            for texto in ('', ' ' * 4, 'x' * 4001, None, {}):
                self.assertFalse(oc.testar(texto)['ok'])
            rodar.assert_not_called()

    def test_texto_e_tokens(self):
        saida = '\n'.join(json.dumps(ev) for ev in [
            {'type': 'text', 'part': {'text': 'Olá!'}},
            {'type': 'step_finish', 'part': {'tokens': {'input': 10, 'output': 3, 'reasoning': 2}}}])
        self.assertEqual(oc.interpretar(saida, 0), {'ok': True, 'texto': 'Olá!', 'tokens': 15})

    def test_erro_ou_saida_incompleta_nao_confirma(self):
        for saida, codigo in [('{}', 0), ('não é JSON', 0), ('[]', 0),
                               ('{"type":"error"}', 0), ('{"type":"text","part":{"text":"parcial"}}', 1)]:
            self.assertFalse(oc.interpretar(saida, codigo)['ok'])

    def test_comando_isolado_e_modelo_fixo(self):
        with tempfile.TemporaryDirectory(dir=r'D:\kanivete_testes') as pasta:
            with patch.object(oc, 'BASE', Path(pasta)), patch.object(oc, 'executavel', return_value=r'D:\cliente\opencode.exe'), \
                 patch.object(oc.subprocess, 'run', return_value=Mock(stdout='{"type":"text","part":{"text":"OK"}}', returncode=0)) as rodar:
                self.assertTrue(oc.testar('Olá & echo teste')['ok'])
                args, kwargs = rodar.call_args
                self.assertEqual(args[0][-2:], ['--', 'Olá & echo teste'])
                self.assertEqual(args[0][args[0].index('--model') + 1], 'opencode/big-pickle')
                self.assertFalse(kwargs['shell'])
                self.assertTrue(Path(kwargs['cwd']).is_relative_to(Path(pasta)))
                config = json.loads(kwargs['env']['OPENCODE_CONFIG_CONTENT'])
                self.assertEqual(config['permission'], {'*': 'ask'})
                self.assertEqual(config['agent']['kanicode-mvp']['permission'], {'*': 'ask'})
                self.assertIn('--no-auto', args[0])
                self.assertIn('--pure', args[0])
                self.assertEqual(kwargs['stdin'], subprocess.DEVNULL)
                self.assertEqual(config['share'], 'disabled')
                self.assertFalse(config['autoupdate'])

    def test_timeout_libera_trava(self):
        with tempfile.TemporaryDirectory(dir=r'D:\kanivete_testes') as pasta:
            with patch.object(oc, 'BASE', Path(pasta)), patch.object(oc, 'executavel', return_value='opencode.exe'), \
                 patch.object(oc.subprocess, 'run', side_effect=subprocess.TimeoutExpired('opencode', 60)):
                self.assertIn('60 segundos', oc.testar('Olá')['texto'])
                self.assertFalse(oc._TRAVA.locked())

    def test_concorrencia_nao_inicia_segundo_cliente(self):
        oc._TRAVA.acquire()
        try:
            with patch.object(oc, 'executavel', return_value='opencode.exe'), patch.object(oc.subprocess, 'run') as rodar:
                self.assertIn('andamento', oc.testar('Olá')['texto'])
                rodar.assert_not_called()
        finally:
            oc._TRAVA.release()


if __name__ == '__main__':
    unittest.main()
