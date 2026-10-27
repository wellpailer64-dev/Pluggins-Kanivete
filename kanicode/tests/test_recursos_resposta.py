"""Ações nativas com Explorer/navegador/clipboard simulados e imagens temporárias."""
import base64
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image
import recursos_resposta as r
import kanicode


class RecursosRespostaTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir="D:/kanivete_testes")
        self.addCleanup(self.temp.cleanup)
        self.pasta = Path(self.temp.name)
        self.arquivo = self.pasta/'print com espaços.png'
        Image.new('RGBA',(96,64),(90,160,120,128)).save(self.arquivo)

    def test_explorer_abre_pasta_e_seleciona_arquivo_sem_executar(self):
        with patch.object(r.subprocess,'Popen') as popen:
            r.abrir_caminho(str(self.pasta),str(self.pasta))
            self.assertEqual(popen.call_args.args[0][1:],[str(self.pasta)])
            r.abrir_caminho(self.arquivo.name+':12:4',str(self.pasta))
            self.assertEqual(popen.call_args.args[0][1:],['/select,',str(self.arquivo)])
            exe = self.pasta/'teste.exe'; exe.write_bytes(b'nao executar')
            r.abrir_caminho(str(exe),str(self.pasta))
            self.assertEqual(popen.call_args.args[0][1:],['/select,',str(exe)])
            with self.assertRaises(ValueError): r.abrir_caminho('inexistente',str(self.pasta))
            self.assertEqual(popen.call_count,3)

    def test_links_so_http_https_chrome_e_padrao(self):
        with patch.object(r,'_chrome',return_value='C:/Chrome/chrome.exe'), patch.object(r.subprocess,'Popen') as popen, patch.object(r.os,'startfile') as abrir:
            url='https://example.com/a?q=1&b=(x)'
            r.abrir_link(url)
            popen.assert_called_once_with(['C:/Chrome/chrome.exe',url])
            r.abrir_link(url,'padrao'); abrir.assert_called_once_with(url)
            for alvo in ('javascript:alert(1)','file:///C:/Windows/notepad.exe','https://user:senha@example.com','https://example.com/\n--flag'):
                with self.assertRaises(ValueError): r.abrir_link(alvo)
            self.assertEqual(popen.call_count,1)

    def test_preferencia_do_navegador_persiste(self):
        with patch.object(kanicode,'ESTADO',str(self.pasta/'estado.json')), patch.object(kanicode,'DADOS',str(self.pasta)):
            app=kanicode.App()
            self.assertEqual(app.resposta_navegador()['navegador'],'chrome')
            app.resposta_navegador('padrao')
            self.assertEqual(kanicode.App().resposta_navegador()['navegador'],'padrao')
            with self.assertRaises(ValueError): app.resposta_navegador('powershell')

    def test_imagem_completa_salva_original_e_converte_extensao(self):
        d=r.imagem_dados(str(self.arquivo),str(self.pasta))
        dados,info=r.imagem(d['url'],str(self.pasta))
        self.assertEqual((d['largura'],d['altura']),(96,64))
        self.assertEqual(dados,self.arquivo.read_bytes())
        destino=self.pasta/'copia.png'; r.salvar_imagem(dados,info,str(destino))
        self.assertEqual(destino.read_bytes(),dados)
        jpg=self.pasta/'convertida.jpg'; r.salvar_imagem(dados,info,str(jpg))
        with Image.open(jpg) as im: self.assertEqual((im.format,im.size),('JPEG',(96,64)))

    def test_clipboard_codigo_e_bitmap_sem_efeito_na_area_real(self):
        texto='SELECT "ação", 1 < 2;\n  -- fim'
        with patch.object(r,'_clipboard',return_value=True) as clipboard:
            r.copiar_texto(texto)
            self.assertEqual(clipboard.call_args.args,(13,(texto+'\0').encode('utf-16-le')))
            r.copiar_imagem(str(self.arquivo),str(self.pasta))
            formato,dib=clipboard.call_args.args
            self.assertEqual(formato,8)
            self.assertNotEqual(dib[:2],b'BM')
            with Image.open(io.BytesIO(b'BM'+(len(dib)+14).to_bytes(4,'little')+b'\0'*4+(54).to_bytes(4,'little')+dib)) as im:
                self.assertEqual(im.size,(96,64))

    def test_recusa_imagem_invalida_e_limite_de_tamanho(self):
        for dado in ('data:image/svg+xml;base64,PHN2Zy8+','data:image/png;base64,'+base64.b64encode(b'nao e imagem').decode()):
            with self.assertRaises((ValueError,OSError)): r.imagem(dado,str(self.pasta))
        with patch.object(r,'MAX_IMAGEM',8):
            with self.assertRaisesRegex(ValueError,'32 MB'): r.imagem(str(self.arquivo),str(self.pasta))

    def test_cancelar_dialogo_nao_grava_arquivo(self):
        app=kanicode.App();app._pasta=lambda:str(self.pasta)
        app._janela=Mock();app._janela.create_file_dialog.return_value=None
        with patch.object(r,'salvar_imagem') as salvar:
            self.assertFalse(app.resposta_salvar_imagem(str(self.arquivo)))
            salvar.assert_not_called()

    def test_tela_cheia_nativa_restaura_e_nao_alterna_duas_vezes(self):
        app=kanicode.App();app._janela=Mock()
        self.assertTrue(app.resposta_tela_cheia(True))
        self.assertTrue(app.resposta_tela_cheia(True))
        self.assertEqual(app._janela.toggle_fullscreen.call_count,1)
        self.assertFalse(app.resposta_tela_cheia(False))
        self.assertFalse(app.resposta_tela_cheia(False))
        self.assertEqual(app._janela.toggle_fullscreen.call_count,2)
