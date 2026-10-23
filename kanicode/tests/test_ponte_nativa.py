"""Integração real pywebview/WebView2 via pythonw, sem agentes ou dados de produção."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


@unittest.skipUnless(os.name == 'nt', 'integração WebView2 exige Windows')
class PonteNativaTest(unittest.TestCase):
    def test_envio_historico_e_erro_pela_ponte_real(self):
        base = Path(tempfile.mkdtemp(prefix='ponte_nativa_', dir='D:/kanivete_testes'))
        script = Path(__file__).with_name('apoio_ponte_nativa.py')
        exe = Path(sys.executable).with_name('pythonw.exe')
        r = subprocess.run([str(exe),str(script),str(base)], timeout=40, creationflags=0x08000000)
        self.assertEqual(r.returncode,0)
        resultado = json.loads((base/'resultado.json').read_text(encoding='utf-8'))
        self.assertNotIn('erro',resultado,resultado)
        for campo in ('historico_recuperado','motor_chamado','pedido_preservado','sem_reenvio_automatico','diagnostico_gravado'):
            self.assertTrue(resultado.get(campo),campo)


if __name__ == '__main__':
    unittest.main()

