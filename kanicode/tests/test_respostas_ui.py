"""Interações nas respostas reais, sem abrir Explorer/navegador nem tocar no clipboard do PC."""
import base64
import io
import unittest
from PIL import Image
import test_layout as layout


@unittest.skipUnless(layout.sync_playwright,'Playwright opcional não instalado')
class RespostasUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        layout.LayoutTest.setUpClass()
        cls.addClassCleanup(layout.LayoutTest.doClassCleanups)

    def setUp(self):
        self.fixture=layout.LayoutTest('test_controles_nas_posicoes_pedidas_e_fotos')
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.p=self.fixture.page
        buf=io.BytesIO();Image.new('RGB',(1600,900),'#466756').save(buf,'PNG')
        self.url='data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode()
        self.p.evaluate('''url => {
          window.imagemTeste=url;window.acoesResposta=[];window.navegadorTeste='chrome';window.cancelarSalvar=false;
          const anterior=pywebview.api;
          pywebview.api=new Proxy(anterior,{get:(alvo,nome) => {
            if(nome==='miniatura') return async () => imagemTeste;
            if(nome.startsWith('resposta_')) return async (...args) => {
              acoesResposta.push({nome,args});
              if(nome==='resposta_imagem') return {url:imagemTeste,nome:'print completo.png'};
              if(nome==='resposta_navegador') {if(args[0]) navegadorTeste=args[0];return {navegador:navegadorTeste};}
              if(nome==='resposta_salvar_imagem') return !cancelarSalvar;
              if(nome==='resposta_tela_cheia') return args[0];
              return true;
            };
            return alvo[nome];
          }});
        }''',self.url)

    def tearDown(self):
        self.assertEqual(self.fixture.erros,[])

    def resposta(self,texto,quem='codex'):
        self.p.evaluate('d => {conversa.innerHTML="";bolhaAjudante(d.quem,d.texto,true)}',{'quem':quem,'texto':texto})

    def test_copia_codigo_limpo_de_todos_os_modelos_e_streaming(self):
        sql='SELECT "ação", 1 < 2;\n  -- preserva espaços & símbolos'
        for quem in ('claude','codex','kani'):
            if quem=='claude':
                self.p.evaluate('conversa.innerHTML="";K.bolha=null;K.bruto=""')
                for pedaco in ('```sql\n'+sql[:20],sql[20:]+'\n```'):
                    self.fixture.evento({'t':'texto','d':pedaco})
            else:self.resposta('```sql\n'+sql+'\n```',quem)
            self.p.click('[data-copiar-codigo]')
            self.p.wait_for_function("acoesResposta.at(-1)?.nome === 'resposta_copiar_texto'")
            self.assertEqual(self.p.evaluate('acoesResposta.at(-1).args[0]'),sql)
            self.assertEqual(self.p.locator('.codigo code').inner_text(),sql)
        self.resposta('Execute `py -3.13 app.py --teste` e aguarde.')
        self.p.click('[data-copiar-inline]')
        self.assertEqual(self.p.evaluate('acoesResposta.at(-1).args[0]'),'py -3.13 app.py --teste')
        self.resposta('    SELECT 1;\n      -- recuo interno')
        self.p.click('[data-copiar-codigo]')
        self.assertEqual(self.p.evaluate('acoesResposta.at(-1).args[0]'),'SELECT 1;\n  -- recuo interno')

    def test_pastas_links_externos_e_preferencia_sem_navegar_na_janela(self):
        self.resposta('Pasta: `D:\\Meus Projetos\\Saídas`\n\n[Arquivo](<D:/Meus Projetos/app.py:12>)\n\n[Site](https://example.com/busca?a=1&b=(dois)) e https://example.com/docs.')
        self.p.locator('[data-abrir-caminho]').first.click()
        self.assertEqual(self.p.evaluate('acoesResposta.at(-1).args[0]'),'D:\\Meus Projetos\\Saídas')
        self.p.locator('[data-abrir-caminho]').nth(1).click()
        self.assertEqual(self.p.evaluate('acoesResposta.at(-1).args[0]'),'D:/Meus Projetos/app.py:12')
        antes=self.p.url
        self.p.locator('a[data-link-externo]').first.click()
        self.assertEqual(self.p.evaluate('acoesResposta.at(-1).args[0]'),'https://example.com/busca?a=1&b=(dois)')
        self.assertEqual(self.p.url,antes)
        self.assertEqual(self.p.locator('a[data-link-externo]').nth(1).get_attribute('href'),'https://example.com/docs')
        self.p.click('#ferramentas-bt');self.p.select_option('#navegador-links','padrao')
        self.assertEqual(self.p.evaluate('navegadorTeste'),'padrao')

    def test_imagem_zoom_tela_cheia_copia_salva_e_escape(self):
        self.resposta('[Resultado](<D:/Meus Projetos/print completo.png>)')
        self.p.wait_for_function("document.querySelector('.imagem-abrir img').naturalWidth > 0")
        self.p.click('.imagem-abrir')
        self.p.wait_for_function("!document.querySelector('[data-visor=copiar]').disabled")
        self.assertIn('1600 × 900',self.p.locator('.visor-estado').inner_text())
        antes=self.p.locator('.visor-zoom').inner_text()
        self.p.click('[data-visor=mais]')
        self.assertNotEqual(self.p.locator('.visor-zoom').inner_text(),antes)
        self.p.click('[data-visor=menos]')
        self.assertEqual(self.p.locator('.visor-zoom').inner_text(),antes)
        self.assertTrue(self.p.evaluate("acoesResposta.some(c=>c.nome==='resposta_tela_cheia' && c.args[0]===true)"))
        self.p.click('[data-visor=tela]')
        self.assertFalse(self.p.evaluate('acoesResposta.at(-1).args[0]'))
        self.p.click('[data-visor=copiar]')
        self.assertIn('copiada',self.p.locator('.visor-estado').inner_text())
        self.assertEqual(self.p.evaluate('acoesResposta.at(-1).args[0]'),self.url)
        self.p.click('[data-visor=salvar]')
        self.assertIn('salva',self.p.locator('.visor-estado').inner_text())
        self.p.evaluate('cancelarSalvar=true');self.p.click('[data-visor=salvar]')
        self.assertIn('cancelado',self.p.locator('.visor-estado').inner_text())
        self.p.keyboard.press('Escape')
        self.assertFalse(self.p.locator('.imagem-visor').is_visible())
        self.assertFalse(self.p.evaluate("chamadas.some(c=>c.nome==='esconder')"))

    def test_markdown_nao_executa_html_nem_links_ativos_perigosos(self):
        self.resposta('<img src=x onerror="window.injetado=1">\n\n[ruim](javascript:alert(1))\n\n![ruim](data:image/svg+xml,xxx)\n\n```html\n<script>window.injetado=2</script>\n```')
        self.assertFalse(self.p.evaluate('!!window.injetado'))
        self.assertEqual(self.p.locator('#conversa script, #conversa .resposta-imagem img, #conversa a').count(),0)
        self.p.click('[data-copiar-codigo]')
        self.assertEqual(self.p.evaluate('acoesResposta.at(-1).args[0]'),'<script>window.injetado=2</script>')

    def test_mobile_copia_e_baixa_no_dispositivo(self):
        self.p.evaluate('''() => {window.KC_MOVEL=true;window.clipboardLocal=[];
          Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async t=>clipboardLocal.push(t)}});
        }''')
        self.resposta('~~~powershell\nGet-ChildItem "D:/Meus Projetos"\n~~~')
        self.p.click('[data-copiar-codigo]')
        self.assertEqual(self.p.evaluate('clipboardLocal'),['Get-ChildItem "D:/Meus Projetos"'])
        self.resposta('![Print]('+self.url+')')
        self.p.click('.imagem-abrir')
        self.p.wait_for_function("!document.querySelector('[data-visor=salvar]').disabled")
        self.p.click('[data-visor=tela]')
        self.p.wait_for_function('!!document.fullscreenElement')
        with self.p.expect_download() as download:self.p.click('[data-visor=salvar]')
        self.assertEqual(download.value.suggested_filename,'imagem.png')
        self.assertFalse(self.p.evaluate("acoesResposta.some(c=>/resposta_(copiar|salvar)/.test(c.nome))"))

    def test_imagem_de_ferramenta_e_layout_estreito(self):
        self.fixture.evento({'t':'ferr','id':'print','nome':'Read','entrada':{'file_path':'D:/Meu Projeto/print.png'}})
        self.fixture.evento({'t':'ferr_fim','id':'print','ok':True,'saida':''})
        self.p.wait_for_selector('.print[data-imagem]')
        self.p.click('.print')
        self.p.wait_for_function("!document.querySelector('[data-visor=salvar]').disabled")
        self.p.click('[data-visor=fechar]')
        self.resposta('```sql\nSELECT '+('abc '*180)+';\n```\n\nPasta: `D:\\Projetos\\Uma pasta comprida com espaços`')
        self.p.set_viewport_size({'width':340,'height':600})
        self.assertLessEqual(self.p.evaluate('document.body.scrollWidth'),340)
        self.assertGreater(self.p.locator('[data-copiar-codigo]').bounding_box()['width'],40)
