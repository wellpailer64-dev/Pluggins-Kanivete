"""Prévia e entrega de anexos com ponte simulada e navegador isolado."""
from pathlib import Path
import unittest
import test_layout as layout

@unittest.skipUnless(layout.sync_playwright,'Playwright não instalado')
class AnexosUITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright=layout.sync_playwright().start();cls.addClassCleanup(cls.playwright.stop)
        cls.browser=cls.playwright.chromium.launch(headless=True) if Path(cls.playwright.chromium.executable_path).exists() else cls.playwright.chromium.launch(channel='msedge',headless=True)
        cls.addClassCleanup(cls.browser.close)
    def setUp(self):
        layout.LayoutTest.setUp(self)
    def tearDown(self):
        self.assertEqual(self.erros,[])
    def anexar(self,nome='planilha.xlsx'):
        self.page.evaluate('''nome=>window.kaniAnexosLocais({arquivos:[{nome,caminho:'D:/Pasta com espaços/'+nome}],erros:[]})''',nome)
    def test_preview_remocao_limite_e_nome_sem_html(self):
        self.anexar('<img src=x>.pdf')
        p=self.page
        self.assertEqual(p.locator('.anexo-arquivo img').count(),0)
        self.assertEqual(p.locator('.anexo-nome').inner_text(),'<img src=x>.pdf')
        self.anexar('<img src=x>.pdf')
        self.assertEqual(p.locator('.anexo-arquivo').count(),1)
        p.click('.anexo button'); self.assertTrue(p.locator('#anexos').is_hidden())
        for n in range(10): self.anexar(f'arquivo{n}.zip')
        self.assertEqual(p.locator('.anexo-arquivo').count(),8)
    def test_caminho_entregue_ao_codex_sem_forcar_claude(self):
        p=self.page;p.evaluate("quemDefinir('codex',false)")
        self.anexar();p.fill('#texto','Confira esta planilha');p.click('#enviar')
        p.wait_for_function("chamadas.some(c=>c.nome==='ajudante' && c.args[0]==='codex')")
        pedido=p.evaluate("chamadas.find(c=>c.nome==='ajudante').args[1]")
        self.assertIn('D:/Pasta com espaços/planilha.xlsx',pedido)
        self.assertIn('Confira esta planilha',pedido)
        self.assertTrue(p.locator('#anexos').is_hidden())
    def test_somente_arquivo_claude_e_big_pickle(self):
        p=self.page
        for agente in ['claude','pickle']:
            p.evaluate("q=>{ocupada(false);quemDefinir(q,false);chamadas.length=0}",agente)
            self.anexar('documento.pdf');p.click('#enviar')
            metodo='enviar' if agente=='claude' else 'ajudante'
            p.wait_for_function('nome=>chamadas.some(c=>c.nome===nome)',arg=metodo)
            r=p.evaluate('nome=>chamadas.find(c=>c.nome===nome).args',metodo)
            self.assertIn('documento.pdf',r[0] if agente=='claude' else r[1])
            if agente=='claude': self.assertEqual(r[1],[])
    def test_fila_recebe_caminhos_sem_falsas_imagens(self):
        p=self.page;p.evaluate("quemDefinir('codex',false);ocupada(true)")
        self.anexar('video.mp4');p.click('#enviar')
        p.wait_for_function("chamadas.some(c=>c.nome==='mensagem_enviar')")
        r=p.evaluate("chamadas.find(c=>c.nome==='mensagem_enviar').args")
        self.assertIn('video.mp4',r[1]);self.assertEqual(r[2],[]);self.assertEqual(r[3],'codex')
    def test_drop_de_imagem_preserva_miniatura(self):
        p=self.page
        p.evaluate('''() => {
          window.KC_DROP_LOCAL=true;
          const cv=document.createElement('canvas');cv.width=20;cv.height=20;
          const dados=atob(cv.toDataURL('image/png').split(',')[1]);
          const file=new File([Uint8Array.from(dados,c=>c.charCodeAt(0))],'foto.png',{type:'image/png'});
          const dt=new DataTransfer();dt.items.add(file);
          document.dispatchEvent(new DragEvent('drop',{dataTransfer:dt,bubbles:true,cancelable:true}));
        }''')
        p.wait_for_function("document.querySelectorAll('#anexos .anexo img').length===1")
        self.assertEqual(p.locator('.anexo-arquivo').count(),0)
