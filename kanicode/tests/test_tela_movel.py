"""Mouse remoto: protocolo isolado, autenticação HTTP e cliques em página de teste; nunca acessa a porta 9222."""
import http.client
import json
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tela_movel as tela
import movel
import test_layout as layout
import test_conexoes_ui as conexoes


class ProtocoloTest(unittest.TestCase):
    def setUp(self):
        self.chamadas = []
        teste = self

        class Canal:
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def send(self, texto):
                teste.chamadas.append(json.loads(texto))
            def recv(self, **_):
                cmd = teste.chamadas[-1]
                r = {'cssVisualViewport': {'clientWidth': 1920, 'clientHeight': 1080}}
                return json.dumps({'id':cmd['id'], 'result':r if cmd['method']=='Page.getLayoutMetrics' else {}})
        self.canal = Canal()
        self.patches = [patch.object(tela, 'alvo', return_value=(9333, 'ws://127.0.0.1:9333/teste')),
                        patch('websockets.sync.client.connect', return_value=self.canal)]
        for p in self.patches:
            p.start(); self.addCleanup(p.stop)

    def test_coordenadas_css_independem_do_tamanho_do_jpeg(self):
        r = tela.mouse({'acao':'mover','x':.5,'y':.25})
        self.assertEqual(r['largura'], 1920)
        params = self.chamadas[-1]['params']
        self.assertEqual((params['x'],params['y']), (960,270))
        self.assertEqual(params['type'], 'mouseMoved')
        self.assertEqual(len(self.chamadas), 2)

    def test_duplo_clique_solto_e_limites(self):
        tela.mouse({'acao':'clicar','x':1,'y':1,'cliques':2})
        eventos = [c['params'] for c in self.chamadas[1:]]
        self.assertEqual([e['type'] for e in eventos], ['mouseMoved','mousePressed','mouseReleased'])
        self.assertEqual(eventos[-1]['clickCount'], 2)
        self.assertEqual(eventos[-1]['buttons'], 0)
        self.assertEqual((eventos[-1]['x'],eventos[-1]['y']), (1919,1079))

    def test_rejeita_entrada_invalida_antes_de_conectar(self):
        for d in [None, {}, {'acao':'teclado','x':0,'y':0}, {'acao':'mover','x':float('nan'),'y':0},
                  {'acao':'mover','x':-.1,'y':0}, {'acao':'clicar','x':0,'y':0,'cliques':True}]:
            with self.subTest(d=d), self.assertRaises(ValueError):
                tela.mouse(d)
        self.assertEqual(self.chamadas, [])


class AutorizacaoTest(unittest.TestCase):
    def test_so_celular_pareado_mesma_origem_pode_enviar_mouse(self):
        servidor = ThreadingHTTPServer(('127.0.0.1',0), movel._H)
        th = threading.Thread(target=servidor.serve_forever, daemon=True); th.start()
        try:
            host = '127.0.0.1:' + str(servidor.server_port)
            def pedir(cookie=False, origem=None, dados=None, site=None):
                con = http.client.HTTPConnection('127.0.0.1',servidor.server_port,timeout=3)
                cab = {'Content-Type':'application/json'}
                if cookie: cab['Cookie']='kc_chave=teste-local'
                if origem: cab['Origin']=origem
                if site: cab['Sec-Fetch-Site']=site
                con.request('POST','/tela/mouse',json.dumps(dados or {'acao':'mover','x':.5,'y':.5}),cab)
                r = con.getresponse(); codigo=r.status; r.read(); con.close(); return codigo
            with patch.object(movel,'_chave','teste-local'), patch.object(tela,'mouse',return_value={'ok':True}) as mouse:
                self.assertEqual(pedir(),403)
                self.assertEqual(pedir(True,'https://outra-origem.test'),403)
                mouse.assert_not_called()
                self.assertEqual(pedir(True,'http://'+host),200)
                mouse.assert_called_once()
                # O proxy HTTPS pode reescrever Host; o navegador continua na mesma origem.
                self.assertEqual(pedir(True,'https://pc.ts.net',site='same-origin'),200)
                self.assertEqual(pedir(True,'http://'+host,site='cross-site'),403)
        finally:
            servidor.shutdown(); servidor.server_close(); th.join(2)


@unittest.skipUnless(layout.sync_playwright, 'Playwright opcional não instalado')
class MousePaginaTest(unittest.TestCase):
    setUpClass = classmethod(conexoes.ConexoesUITest.setUpClass.__func__)

    def test_hover_clique_e_duplo_clique_reais_na_pagina_isolada(self):
        p = self.browser.new_page(viewport={'width':1000,'height':600})
        self.addCleanup(p.close)
        p.set_content('<button style="position:absolute;left:400px;top:250px;width:200px;height:100px" id="alvo">Teste</button><script>window.eventos=[];for(const t of ["mouseenter","click","dblclick"])alvo.addEventListener(t,e=>eventos.push([t,e.detail,e.isTrusted]));</script>')
        sessao = p.context.new_cdp_session(p)
        class Canal:
            def __enter__(self): return self
            def __exit__(self,*_): pass
            def send(self, texto):
                d=json.loads(texto); self.resposta=json.dumps({'id':d['id'],'result':sessao.send(d['method'],d['params'])})
            def recv(self,**_): return self.resposta
        with patch.object(tela,'alvo',return_value=(9333,'ws://teste-isolado')), patch('websockets.sync.client.connect',return_value=Canal()):
            tela.mouse({'acao':'mover','x':.5,'y':.5})
            tela.mouse({'acao':'clicar','x':.5,'y':.5,'cliques':1})
            tela.mouse({'acao':'clicar','x':.5,'y':.5,'cliques':2})
        eventos=p.evaluate('eventos')
        self.assertEqual([e[0] for e in eventos], ['mouseenter','click','click','dblclick'])
        self.assertEqual([e[1] for e in eventos], [0,1,2,2])
        self.assertTrue(all(e[2] for e in eventos))


if __name__ == '__main__':
    unittest.main()
