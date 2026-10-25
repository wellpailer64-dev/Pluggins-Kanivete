"""Sinais reais, canal local e faixa responsiva, com operações simuladas."""
from pathlib import Path
import json
import socket
import threading
import unittest
from unittest.mock import patch
import progresso
import test_layout as layout


class ProgressoTest(unittest.TestCase):
    def setUp(self):
        with progresso._trava:
            progresso._itens.clear()

    def test_sem_inventar_percentual_e_sem_falso_fim(self):
        with patch.object(progresso.time, 'monotonic', return_value=100):
            progresso.registrar({'id':'d','tipo':'download'})
        with patch.object(progresso.time, 'monotonic', return_value=130):
            item = progresso.listar()[0]
            self.assertIsNone(item['pct']); self.assertTrue(item['sem_sinal'])
            self.assertEqual(item['estado'], 'ativo')
            progresso.registrar({'id':'d','tipo':'download','estado':'erro','pct':45})
            self.assertEqual(progresso.listar()[0]['pct'],45)
        with patch.object(progresso.time, 'monotonic', return_value=141):
            self.assertEqual(progresso.listar(),[])

    def test_canal_recebe_sem_conversa(self):
        from kanicode import App
        app = App.__new__(App)
        a,b = socket.socketpair()
        t = threading.Thread(target=app._canal_atender,args=(a,));t.start()
        with b:
            b.sendall(('progresso '+json.dumps([{'id':'r','tipo':'render','pct':32}])+'\n').encode())
            self.assertEqual(b.recv(32),b'ok\n')
        t.join(3)
        self.assertEqual(app.progresso_listar()[0]['pct'],32)

    def test_limites_e_validacao(self):
        for i in range(100):
            progresso.registrar({'id':str(i),'tipo':'render','pct':101})
        self.assertEqual(len(progresso.listar()),64)
        self.assertEqual(progresso.listar()[0]['pct'],100)
        with self.assertRaises(ValueError):
            progresso.registrar({'id':'x','tipo':'render','pct':float('nan')})


@unittest.skipUnless(layout.sync_playwright,'Playwright não instalado')
class ProgressoUITest(unittest.TestCase):
    setUpClass = layout.LayoutTest.__dict__['setUpClass']
    setUp = layout.LayoutTest.setUp

    def test_pc_e_mobile_com_erro_e_sem_percentual(self):
        p=self.page
        for largura in (1000,390):
            if largura == 390:
                p.add_style_tag(path=str(Path(__file__).resolve().parents[1]/'ui/movel.css'))
                p.evaluate("document.documentElement.classList.add('movel')")
            p.set_viewport_size({'width':largura,'height':740})
            p.evaluate('''()=>KCProgresso.mostrar([
              {id:'r',tipo:'render',titulo:'Render <img src=x>',pct:42,estado:'ativo'},
              {id:'d',tipo:'download',titulo:'Download de vídeo',pct:null,estado:'ativo'},
              {id:'e',tipo:'render',titulo:'Exportação',pct:10,estado:'erro'}])''')
            self.assertEqual(p.locator('#kc-progresso img').count(),0)
            self.assertIn('42%',p.locator('#kc-progresso').inner_text())
            self.assertIn('Falhou',p.locator('#kc-progresso').inner_text())
            self.assertEqual(p.locator('#kc-progresso progress:not([value])').count(),1)
            caixa=p.locator('#kc-progresso').bounding_box()
            self.assertGreater(caixa['width'],200)
            self.assertLessEqual(caixa['x']+caixa['width'],largura+1)
        p.screenshot(path='D:/kanivete_testes/progresso_mobile.png')
        p.evaluate('KCProgresso.mostrar([])')
        self.assertTrue(p.locator('#kc-progresso').is_hidden())

    def test_consulta_api_compartilhada(self):
        p=self.page
        p.evaluate('''()=>{const api=pywebview.api;pywebview.api=new Proxy(api,{get:(a,n)=>
          n==='progresso_listar'?async()=>[{id:'r',tipo:'render',titulo:'Render compartilhado',pct:67,estado:'ativo'}]:a[n]});}''')
        p.wait_for_function("document.querySelector('#kc-progresso').textContent.includes('67%')")

    def test_observador_preserva_callbacks_e_repassa_fim(self):
        p=self.page
        p.evaluate('''()=>{window.lotes=[];window.origem=[];
          window.KPLUG={chamar:async(p,f,d)=>lotes.push(d.itens)};window.PLUGIN_ID='teste';
          window.veOnExport=d=>{origem.push(d);return 17};
          window.veOnRender=d=>origem.push(d);window.veOnComp=d=>origem.push(d);
          window.updateVideoDownloaderProgress=d=>origem.push(d);
        }''')
        p.add_script_tag(path=str(Path(__file__).resolve().parents[1]/'progresso_kanivete.js'))
        self.assertEqual(p.evaluate("veOnExport({pct:23})"),17)
        p.evaluate("updateVideoDownloaderProgress({percent:60});veOnRender({hash:'a',pct:40});veOnRender({hash:'b',pct:20})")
        p.wait_for_function('lotes.flat().length===4')
        p.evaluate("veOnExport({done:true,success:false,error:'Teste de erro'})")
        p.wait_for_function("lotes.flat().some(i=>i.estado==='erro')")
        self.assertEqual(p.evaluate('origem.length'),5)
