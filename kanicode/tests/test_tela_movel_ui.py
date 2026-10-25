"""Componente real de transmissão no viewport de celular, rede simulada e sem acessar o KANIVETE."""
import json
from pathlib import Path
import unittest
import test_layout as layout
import test_conexoes_ui as conexoes

RAIZ = Path(__file__).resolve().parents[1]


@unittest.skipUnless(layout.sync_playwright, 'Playwright opcional não instalado')
class TelaMovelUITest(unittest.TestCase):
    setUpClass = classmethod(conexoes.ConexoesUITest.setUpClass.__func__)

    def setUp(self):
        self.contexto = self.browser.new_context(viewport={'width':390,'height':844}, is_mobile=True, has_touch=True)
        self.addCleanup(self.contexto.close)
        self.page = self.contexto.new_page()
        self.page.set_default_timeout(3000)
        self.erros, self.pedidos = [], []
        self.page.on('pageerror', lambda e:self.erros.append(str(e)))
        self.page.route('http://movel.test/', lambda r:r.fulfill(content_type='text/html',body='<html class="movel"><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0;background:#0e1110;color:white;font:14px sans-serif"><div class="topo" style="height:50px">KaniCode <button id="kv-bt">📺</button></div></body></html>'))
        self.page.route('**/tela?*', lambda r:r.fulfill(content_type='image/svg+xml',body='<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080"><rect width="1920" height="1080" fill="#17251d"/><rect x="30" y="30" width="1860" height="70" fill="#314a3b"/><text x="60" y="80" fill="white" font-size="32">KANIVETE — tela de teste</text><path d="M960 0V1080M0 540H1920" stroke="#55765e"/></svg>'))
        self.page.route('**/tela/estado*',lambda r:r.fulfill(json={'aberto':True}))
        self.page.route('**/tela/monitores',lambda r:r.fulfill(json=[{'id':'principal','nome':'Principal · 3840×2160'}, {'id':'segundo','nome':'Monitor 2 · 1920×1080'}, {'id':'terceiro','nome':'Monitor 3 · 1080×1920'}]))
        def mouse(r):
            self.pedidos.append(r.request.post_data_json)
            r.fulfill(json={'ok':True,'largura':1920,'altura':1080})
        self.page.route('**/tela/mouse',mouse)
        self.page.goto('http://movel.test/')
        self.page.add_style_tag(path=str(RAIZ/'ui/movel.css'))
        codigo=(RAIZ/'ui/movel.js').read_text(encoding='utf-8')
        # Usa as funções do componente sem iniciar conversa, notificações ou microfone.
        trecho=codigo[codigo.index('  // ── 📺 KANIVETE ao vivo'):]
        trecho=trecho.rsplit('})();',1)[0] + 'window.TelaMovelTeste={montar:telaMontar,abrir:telaAbrir};})();'
        self.page.add_script_tag(content='(() => { const $$=id=>document.getElementById(id); const post=(u,d)=>fetch(u,{method:"POST",body:JSON.stringify(d||{})}).then(r=>r.json());\n'+trecho)
        self.page.evaluate('() => { TelaMovelTeste.montar(); TelaMovelTeste.abrir(); }')
        self.page.wait_for_function('document.getElementById("kv-img").naturalWidth === 1920')

    def tearDown(self):
        self.assertEqual(self.erros, [])

    def evento(self, tipo, x=100, y=120):
        self.page.locator('#kv-area').dispatch_event(tipo, {'pointerId':1,'pointerType':'touch','button':0,'clientX':x,'clientY':y})

    def toque(self):
        self.evento('pointerdown'); self.evento('pointerup')

    def test_arrastar_so_move_e_toques_clicam_sem_saltar_cursor(self):
        self.evento('pointerdown')
        self.evento('pointermove',160,140)
        self.evento('pointerup',160,140)
        self.page.wait_for_timeout(100)
        self.assertTrue(self.pedidos)
        self.assertTrue(all(d['acao']=='mover' for d in self.pedidos))
        self.assertGreater(self.pedidos[-1]['x'],.5)
        posicao=(self.pedidos[-1]['x'],self.pedidos[-1]['y'])
        self.toque(); self.page.wait_for_timeout(60); self.toque()
        self.page.wait_for_timeout(100)
        cliques=[d for d in self.pedidos if d['acao']=='clicar']
        self.assertEqual([d['cliques'] for d in cliques],[1,1])
        self.assertTrue(all(d['fonte']=='pc' for d in cliques))
        self.assertTrue(all((d['x'],d['y'])==posicao for d in cliques))
        self.assertFalse(self.page.locator('#kv').evaluate('(el)=>el.classList.contains("kv-grande")'))

    def test_fullscreen_negado_ou_ausente_amplia_e_restaura(self):
        p=self.page
        p.evaluate('() => { document.getElementById("kv").requestFullscreen=()=>Promise.reject(Error("negado")); }')
        p.click('#kv-cheia')
        p.wait_for_function('document.getElementById("kv").classList.contains("kv-grande")')
        r=p.locator('#kv').bounding_box()
        self.assertAlmostEqual(r['height'],844,delta=2)
        self.assertAlmostEqual(r['width'],390,delta=2)
        p.set_viewport_size({'width':844,'height':390})
        p.screenshot(path='D:/kanivete_testes/tela_movel_horizontal.png')
        p.click('#kv-cheia')
        self.assertFalse(p.locator('#kv').evaluate('(el)=>el.classList.contains("kv-grande")'))
        p.evaluate('() => { document.getElementById("kv").requestFullscreen=undefined; }')
        p.click('#kv-cheia')
        self.assertEqual(p.locator('#kv-cheia').get_attribute('aria-pressed'),'true')
        p.click('#kv-fechar')
        self.assertTrue(p.locator('#kv').is_hidden())
        self.assertFalse(p.locator('html').evaluate('(el)=>el.classList.contains("kv-ampliada")'))
        self.assertEqual(self.pedidos,[])

    def test_desligar_mouse_e_cancelar_gesto_nao_clicam(self):
        p=self.page
        self.evento('pointerdown'); self.evento('pointercancel'); self.evento('pointerup')
        p.click('#kv-mouse')
        self.toque()
        p.wait_for_timeout(100)
        self.assertEqual(self.pedidos,[])
        self.assertTrue(p.locator('#kv-cursor').is_hidden())
        self.assertEqual(p.locator('#kv-mouse').get_attribute('aria-pressed'),'false')

    def test_movimentos_lentos_na_rede_sao_agrupados_e_clique_mantem_ordem(self):
        pendentes=[]
        self.page.route('**/tela/mouse',lambda r:pendentes.append(r))
        self.evento('pointerdown'); self.evento('pointermove',120,120)
        self.page.wait_for_timeout(80)
        self.assertEqual(len(pendentes),1)
        for x in range(130,240,10):
            self.evento('pointermove',x,120)
        self.evento('pointerup',230,120)
        self.toque()
        self.assertEqual(len(pendentes),1)
        for i in range(2):
            self.page.wait_for_timeout(80)
            self.assertGreater(len(pendentes),i)
            pendentes[i].fulfill(json={'ok':True,'largura':1920,'altura':1080})
        self.page.wait_for_timeout(80)
        acoes=[r.request.post_data_json['acao'] for r in pendentes]
        self.assertEqual(acoes,['mover','clicar'])

    def test_trocar_monitor_e_kanivete(self):
        p=self.page
        p.wait_for_function("document.querySelector('#kv-fonte').options.length===4")
        p.select_option('#kv-fonte','pc:terceiro')
        p.wait_for_function("document.querySelector('#kv-img').src.includes('monitor=terceiro')")
        self.toque();p.wait_for_timeout(100)
        self.assertEqual(self.pedidos[-1]['monitor'],'terceiro')
        p.select_option('#kv-fonte','kanivete')
        p.wait_for_function("document.querySelector('#kv-img').naturalWidth===1920")
        self.toque();p.wait_for_timeout(60);self.toque();p.wait_for_timeout(100)
        self.assertEqual(self.pedidos[-1]['fonte'],'kanivete')
        self.assertEqual(self.pedidos[-1]['cliques'],2)

    def test_zoom_botoes_e_pinca_nao_clicam(self):
        p=self.page
        p.click('#kv-mais')
        self.assertIn('scale(1.5)',p.locator('#kv-img').get_attribute('style'))
        self.evento('pointerdown',100,130)
        p.locator('#kv-area').dispatch_event('pointerdown',{'pointerId':2,'pointerType':'touch','button':0,'clientX':200,'clientY':130})
        p.locator('#kv-area').dispatch_event('pointermove',{'pointerId':2,'pointerType':'touch','button':0,'clientX':280,'clientY':140})
        p.locator('#kv-area').dispatch_event('pointerup',{'pointerId':2,'pointerType':'touch','button':0,'clientX':280,'clientY':140})
        self.evento('pointerup',100,130)
        p.wait_for_timeout(100)
        self.assertEqual(self.pedidos,[])
        self.assertIn('scale(2.',p.locator('#kv-img').get_attribute('style'))
        for _ in range(5):p.click('#kv-menos')
        self.assertIn('scale(1)',p.locator('#kv-img').get_attribute('style'))
        p.screenshot(path='D:/kanivete_testes/tela_pc_mobile.png')

    def test_falha_nao_repete_clique_e_fechar_descarta_fila(self):
        p=self.page
        p.route('**/tela/mouse',lambda r:r.fulfill(status=503,json={'erro':'indisponível'}))
        self.toque()
        p.wait_for_function('document.getElementById("kv-mouse-status").textContent.includes("indisponível")')
        pendentes=[]
        p.route('**/tela/mouse',lambda r:pendentes.append(r))
        self.toque(); p.wait_for_timeout(80); self.toque()
        self.assertEqual(len(pendentes),1)
        p.click('#kv-fechar')
        p.wait_for_timeout(80)
        self.assertEqual(len(pendentes),1)


if __name__ == '__main__':
    unittest.main()
