"""Monitor físico, captura e entrada simulados; nunca move o mouse do usuário."""
import contextlib
import ctypes
import http.client
import io
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import Mock, patch
from PIL import Image
import tela_pc as pc
import movel

MONITORES = [{'id':'principal','principal':True,'nome':'Principal · 3840×2160','x':0,'y':0,'largura':3840,'altura':2160},
             {'id':'esquerdo','principal':False,'nome':'Monitor 2','x':-1920,'y':-300,'largura':1920,'altura':1080}]


class TelaPCTest(unittest.TestCase):
    def test_captura_libera_gdi_mesmo_com_falha(self):
        u=Mock();u.GetDC.return_value=1
        g=Mock();g.CreateCompatibleDC.return_value=2;g.SelectObject.return_value=4;g.StretchBlt.return_value=0
        memoria=ctypes.create_string_buffer(4*1280*720)
        def criar(tela,info,uso,pixels,secao,offset):
            pixels._obj.value=ctypes.addressof(memoria);return 3
        g.CreateDIBSection.side_effect=criar
        with patch.object(pc,'_pixels',return_value=contextlib.nullcontext(u)),patch.object(pc.ctypes,'WinDLL',return_value=g):
            with self.assertRaises(OSError):pc._capturar(MONITORES[0],1280)
        g.SelectObject.assert_any_call(2,4);g.DeleteObject.assert_called_once_with(3)
        g.DeleteDC.assert_called_once_with(2);u.ReleaseDC.assert_called_once_with(None,1)

    def test_coordenadas_negativas_e_extremos(self):
        with patch.object(pc,'monitores',return_value=MONITORES),patch.object(pc,'_entrada') as entrada:
            r=pc.mouse({'acao':'clicar','monitor':'esquerdo','x':0,'y':1,'cliques':2})
            entrada.assert_called_once_with(-1920,779,2)
            self.assertEqual(r['largura'],1920)
            pc.mouse({'acao':'mover','x':1,'y':0})
            entrada.assert_called_with(3839,0,0)

    def test_recusa_coordenadas_e_monitor_desconectado(self):
        with patch.object(pc,'monitores',return_value=MONITORES),patch.object(pc,'_entrada') as entrada:
            for d in ({'acao':'mover','x':float('nan'),'y':0},{'acao':'clicar','x':0,'y':0,'cliques':3}):
                with self.assertRaises(ValueError):pc.mouse(d)
            with self.assertRaises(LookupError):pc.mouse({'acao':'clicar','x':0,'y':0,'monitor':'inexistente'})
            entrada.assert_not_called()

    def test_jpeg_limitado_e_recorte_do_monitor(self):
        with patch.object(pc,'_capturar',return_value=Image.new('RGB',(1280,720))) as captura:
            jpg=pc.quadro(MONITORES[1])
            captura.assert_called_once_with(MONITORES[1],1280)
            with Image.open(io.BytesIO(jpg)) as im:
                self.assertEqual(im.size,(1280,720))
                self.assertEqual(im.format,'JPEG')

    def test_stream_para_ao_fechar_sem_fila_de_quadros(self):
        class Saida(io.BytesIO):
            def flush(self):raise BrokenPipeError()
        saida=Saida()
        with patch.object(pc,'monitor',return_value=MONITORES[0]),patch.object(pc,'quadro',return_value=b'JPEG') as quadro:
            with self.assertRaises(BrokenPipeError):pc.transmitir(saida)
            quadro.assert_called_once()
            self.assertIn(b'Content-Length: 4\r\n\r\nJPEG',saida.getvalue())

    def test_stream_nao_reenvia_quadros_iguais(self):
        class Saida(io.BytesIO):
            n=0
            def flush(self):
                self.n+=1
                if self.n==2:raise BrokenPipeError()
        saida=Saida()
        with patch.object(pc,'monitor',return_value=MONITORES[0]),patch.object(pc,'quadro',side_effect=[b'A',b'A',b'B']) as quadro,patch.object(pc.time,'sleep'):
            with self.assertRaises(BrokenPipeError):pc.transmitir(saida)
            self.assertEqual(quadro.call_count,3)
            self.assertEqual(saida.getvalue().count(b'Content-Type: image/jpeg'),2)

    def test_http_pareamento_rota_pc_e_lista_monitores(self):
        servidor=ThreadingHTTPServer(('127.0.0.1',0),movel._H)
        th=threading.Thread(target=servidor.serve_forever,daemon=True);th.start()
        def pedir(path,cookie=False,dados=None):
            con=http.client.HTTPConnection('127.0.0.1',servidor.server_port,timeout=3)
            cab={'Content-Type':'application/json','Sec-Fetch-Site':'same-origin'}
            if cookie:cab['Cookie']='kc_chave=teste-pc'
            con.request('POST' if dados is not None else 'GET',path,json.dumps(dados) if dados else None,cab)
            r=con.getresponse();res=(r.status,r.read());con.close();return res
        try:
            with patch.object(movel,'_chave','teste-pc'),patch.object(pc,'monitores',return_value=MONITORES),patch.object(pc,'mouse',return_value={'ok':True}) as mouse:
                self.assertEqual(pedir('/tela/monitores')[0],403)
                self.assertEqual(len(json.loads(pedir('/tela/monitores',True)[1])),2)
                self.assertTrue(json.loads(pedir('/tela/estado?fonte=pc',True)[1])['aberto'])
                dados={'fonte':'pc','monitor':'esquerdo','acao':'clicar','x':.5,'y':.4}
                self.assertEqual(pedir('/tela/mouse',True,dados)[0],200)
                mouse.assert_called_once_with(dados)
                import tela_movel
                with patch.object(tela_movel,'alvo') as alvo,patch.object(pc,'transmitir') as transmitir:
                    self.assertEqual(pedir('/tela?fonte=pc&monitor=esquerdo&largura=2560',True)[0],200)
                    self.assertEqual(transmitir.call_args.args[1:],('esquerdo',2560))
                    alvo.assert_not_called()
        finally:servidor.shutdown();servidor.server_close();th.join(2)
