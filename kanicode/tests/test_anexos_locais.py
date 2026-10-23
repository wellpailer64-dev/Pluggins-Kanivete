"""Drop nativo simulado; arquivos e saídas apenas no D."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import anexos_locais as a

class AnexosLocaisTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=r'D:\kanivete_testes')
        self.addCleanup(self.tmp.cleanup)
        self.p=Path(self.tmp.name)
    def test_caminho_original_sem_ler_conteudo_e_sem_copiar(self):
        f=self.p/'orçamento final.xlsx'; f.write_bytes(b'dados')
        janela=Mock()
        a.receber(janela, {'dataTransfer':{'files':[{'name':f.name,'type':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','pywebviewFullPath':str(f)}]}})
        script=janela.evaluate_js.call_args.args[0]
        r=json.loads(script[len('window.kaniAnexosLocais('):-1])
        self.assertEqual(r['arquivos'][0]['caminho'],str(f.resolve()))
        self.assertNotIn('dados',r['arquivos'][0])
        self.assertEqual(list(self.p.iterdir()),[f])
    def test_imagem_segue_fluxo_atual_e_psd_vira_arquivo(self):
        f=self.p/'arte.psd';f.write_bytes(b'psd')
        janela=Mock()
        a.receber(janela,{'dataTransfer':{'files':[{'name':'foto.png','type':'image/png'}, {'name':f.name,'type':'image/vnd.adobe.photoshop','pywebviewFullPath':str(f)}]}})
        script=janela.evaluate_js.call_args.args[0]
        self.assertIn('arte.psd',script);self.assertNotIn('foto.png',script)
    def test_caminho_ausente_pasta_e_arquivo_inexistente_informam_erro(self):
        janela=Mock()
        a.receber(janela,{'dataTransfer':{'files':[{'name':'sem.pdf'}, {'name':'pasta','pywebviewFullPath':str(self.p)}, {'name':'sumiu','pywebviewFullPath':str(self.p/'sumiu')} ]}})
        script=janela.evaluate_js.call_args.args[0]
        r=json.loads(script[len('window.kaniAnexosLocais('):-1])
        self.assertEqual(r['arquivos'],[]);self.assertEqual(len(r['erros']),3)
