"""Proteção de dados e navegador configurados antes de importar o app."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dados_app
import verificar
from teste_isolado import proteger


class AmbienteIsoladoTest(unittest.TestCase):
    def test_verificador_prepara_dados_e_chromium_sem_configuracao_manual(self):
        with patch.dict(os.environ):
            os.environ.pop('PLAYWRIGHT_BROWSERS_PATH', None)
            saida = verificar.ambiente()
            self.assertEqual(Path(os.environ['PLAYWRIGHT_BROWSERS_PATH']), Path('D:/kanivete_testes/playwright'))
            self.assertEqual(dados_app.pasta_dados(), saida / 'dados')
            self.assertEqual(os.environ['KANICODE_TESTE'], '1')
            self.assertTrue(Path(os.environ['CODEX_HOME']).is_relative_to(saida))

    def test_dados_de_teste_fora_da_area_sao_recusados(self):
        with patch.dict(os.environ, KANICODE_TESTE='1', KANICODE_DADOS_TESTE='D:/Kanivete/KaniCode'):
            with self.assertRaises(ValueError):
                dados_app.pasta_dados()

    def test_protecao_recusa_escrita_antes_de_criar_arquivo(self):
        with tempfile.TemporaryDirectory(dir='D:/kanivete_testes') as pasta:
            alvo = Path(pasta) / 'nao_gravar.json'
            proteger([alvo])
            with self.assertRaises(PermissionError):
                alvo.write_text('não deve existir', encoding='utf-8')
            self.assertFalse(alvo.exists())

    def test_eventos_e_uso_ficam_na_pasta_isolada(self):
        import kanicode
        base = dados_app.pasta_dados()
        self.assertEqual(Path(kanicode.DADOS), base)
        app = kanicode.App()
        app._para_janela = Mock()
        app._codex_voz = Mock()
        app._evento({'t':'codex_progresso', 'texto':'marcador isolado'})
        app._codex_registrar(str(base), 'pedido simulado', {'ok':True,'texto':'resposta simulada','tokens':0,'ms':0})
        self.assertTrue((base / 'ao_vivo.jsonl').exists())
        self.assertTrue((base / 'codex_uso.jsonl').exists())
        self.assertIn('marcador isolado', (base / 'ao_vivo.jsonl').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()

