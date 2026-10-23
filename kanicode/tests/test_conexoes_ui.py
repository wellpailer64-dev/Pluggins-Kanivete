"""Tela real em navegador headless isolado. Ponte simulada, sem Google ou app do usuário."""
from pathlib import Path
import unittest
import test_layout as layout
sync_playwright = layout.sync_playwright


@unittest.skipUnless(sync_playwright, 'Playwright opcional não instalado')
class ConexoesUITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.addClassCleanup(cls.playwright.stop)
        if Path(cls.playwright.chromium.executable_path).exists():
            cls.browser = cls.playwright.chromium.launch(headless=True)
        elif Path(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe').exists():
            cls.browser = cls.playwright.chromium.launch(channel='msedge', headless=True)
        else:
            raise unittest.SkipTest('Nenhum navegador headless instalado')
        cls.addClassCleanup(cls.browser.close)

    def setUp(self):
        layout.LayoutTest.setUp(self)
        self.page.evaluate('''() => {
          window.googleTeste = {configurado:false,conectado:false,conectando:false,mensagem:'',
            conta:'',ultima_sync:null,calendarios:[],selecionados:[],eventos:[],antes:10,avisos:{}};
          window.driveTeste = {configurado:false,conectado:false,conectando:false,mensagem:'',conta:'',ultima_sync:null,reutilizavel:true,arquivos:[],proxima:''};
          const anterior=window.pywebview.api;
          window.pywebview.api = new Proxy({}, {get:(_,nome)=> {
            if(nome.startsWith('drive_')) return async (...args) => {
              chamadas.push({nome,args});
              if(nome==='drive_usar_calendar' || nome==='drive_importar') driveTeste.configurado=true;
              if(nome==='drive_conectar') Object.assign(driveTeste,{conectando:true});
              if(nome==='drive_desconectar') Object.assign(driveTeste,{conectado:false,conectando:false,arquivos:[],conta:''});
              if(nome==='drive_buscar') return {arquivos:[{id:args[1]?'b':'a',nome:args[1]?'Segunda página':'<img src=x onerror=alert(1)>',pasta:false,url:'https://drive.google.com/file/d/a'}],proxima:args[1]?'':'pagina-2'};
              return {...driveTeste};
            };
            if(nome.startsWith('gmail_')) return async (...args) => {
              chamadas.push({nome,args});
              if(nome==='gmail_buscar') return {mensagens:[{id:'m1',assunto:'<img src=x onerror=alert(1)>',de:'cliente',data:'hoje'}],proxima:''};
              if(nome==='gmail_ler') return {assunto:'Cliente',de:'cliente',para:'eu',data:'hoje',texto:'<script>alert(1)</script>'};
              if(nome==='gmail_rascunho') return {id:'r1',mensagem:'Rascunho criado. Nenhum e-mail foi enviado.'};
              return {configurado:true,conectado:!!window.gmailConectado,conectando:false,mensagem:'',reutilizavel:true};
            };
            if(!nome.startsWith('google_')) return anterior[nome];
            return async (...args) => {
              chamadas.push({nome,args});
              if(nome==='google_importar') googleTeste.configurado=true;
              if(nome==='google_selecionar') {googleTeste.selecionados=args[0];googleTeste.antes=args[1];}
              if(nome==='google_desconectar') {googleTeste.conectado=false;googleTeste.eventos=[];}
              return {...googleTeste};
            };
          }});
        }''')

    def tearDown(self):
        self.assertEqual(self.erros, [])

    def abrir(self, conectado=False, catalogo=False):
        if conectado:
            self.page.evaluate('''() => Object.assign(googleTeste, {configurado:true,conectado:true,
              conta:'teste@example.com',ultima_sync:'2026-10-22T15:00:00Z',
              calendarios:[{id:'a',nome:'Pessoal',principal:true},{id:'b',nome:'Trabalho'}],selecionados:['a'],
              eventos:[{titulo:'<img src=x onerror=alert(1)>',inicio:'2026-10-23T13:00:00-03:00',calendario:'Pessoal',dia_inteiro:false}]})''')
        self.page.click('#ferramentas-bt')
        self.page.click('#config-conexoes')
        self.page.wait_for_function("document.querySelector('#configuracoes').open && !document.querySelector('#google-status').textContent.includes('Carregando')")
        if not catalogo:
            self.page.click('[data-conexao="calendar"]')

    def test_configuracao_inicial_importacao_e_contas_separadas(self):
        self.abrir()
        self.assertTrue(self.page.locator('#google-conectar').is_disabled())
        self.assertTrue(self.page.locator('#google-ajuda').get_attribute('open') is not None)
        self.page.click('#google-importar')
        self.page.wait_for_function("!document.querySelector('#google-conectar').disabled")
        self.page.click('#config-fechar')
        self.page.click('#lado-aj')
        self.assertFalse(self.page.locator('#configuracoes').is_visible())
        self.page.wait_for_selector('#contas', state='visible')

    def test_calendarios_preferencias_xss_e_desconectar(self):
        self.abrir(True)
        self.assertIn('<img src=x', self.page.locator('#google-eventos').inner_text())
        self.assertEqual(self.page.locator('#google-eventos img').count(), 0)
        self.page.locator('#google-calendarios input[value="a"]').uncheck()
        self.page.locator('#google-calendarios input[value="b"]').check()
        self.page.fill('#google-antes', '25')
        self.page.get_by_role('button', name='Salvar preferências').click()
        self.page.wait_for_function("chamadas.some(c=>c.nome==='google_selecionar')")
        self.assertEqual(self.page.evaluate("chamadas.find(c=>c.nome==='google_selecionar').args"), [['b'], 25])
        self.page.click('#google-desconectar')
        self.page.wait_for_function("document.querySelector('#google-preferencias').hidden")
        self.page.click('#conexoes-voltar')
        self.assertNotIn('conectado', self.page.locator('[data-conexao="calendar"]').get_attribute('class'))
        self.assertEqual(self.page.locator('#conexoes-resumo').inner_text(), 'Nenhuma conexão ativa')

    def test_gmail_busca_leitura_rascunho(self):
        self.page.evaluate("window.gmailConectado = true")
        self.abrir(catalogo=True)
        p = self.page
        p.click('[data-conexao="gmail"]')
        p.fill('#gmail-termo', 'from:cliente')
        p.click('#gmail-busca button')
        p.click('#gmail-lista button')
        self.assertEqual(p.locator('#gmail-corpo').inner_text(), '<script>alert(1)</script>')
        self.assertEqual(p.locator('#gmail-leitura script').count(), 0)
        p.fill('#gmail-para', 'cliente@example.com')
        p.fill('#gmail-novo-assunto', 'Teste')
        p.fill('#gmail-texto', 'Olá')
        p.click('#gmail-rascunho button')
        p.wait_for_function("document.querySelector('#gmail-status').textContent.includes('Nenhum e-mail')")
        self.assertTrue(p.evaluate("chamadas.some(c=>c.nome==='gmail_rascunho' && c.args[2]==='Olá')"))

    def test_cards_estado_navegacao_e_sugestoes(self):
        self.abrir(True, catalogo=True)
        p = self.page
        self.assertEqual(p.locator('.conexao-card').count(), 4)
        self.assertEqual(p.locator('.conexao-card.conectado').count(), 1)
        self.assertTrue(p.locator('#conexao-google').is_hidden())
        self.assertIn('1 conexão ativa', p.locator('#conexoes-resumo').inner_text())
        p.screenshot(path=r'D:\kanivete_testes\conexoes_cards.png')
        for app, nome in [('github', 'GitHub')]:
            p.click(f'[data-conexao="{app}"]')
            self.assertEqual(p.locator('#sugestao-titulo').inner_text(), nome)
            self.assertTrue(p.get_by_text('Ainda não disponível', exact=True).is_visible())
            self.assertEqual(p.locator('#conexao-sugestao button').count(), 0)
            p.click('#conexoes-voltar')
            self.assertEqual(p.evaluate('document.activeElement.dataset.conexao'), app)
        p.click('[data-conexao="calendar"]')
        self.assertTrue(p.locator('#google-sync').is_visible())
        p.click('#config-fechar')
        p.click('#ferramentas-bt'); p.click('#config-conexoes')
        self.assertTrue(p.locator('#conexoes-catalogo').is_visible())

    def test_card_desconectado_e_falha_de_verificacao(self):
        self.abrir(catalogo=True)
        p = self.page
        self.assertEqual(p.locator('.conexao-card.conectado').count(), 0)
        self.assertIn('Não conectado', p.locator('[data-conexao="calendar"]').inner_text())
        p.click('[data-conexao="calendar"]')
        self.assertTrue(p.locator('#google-importar').is_visible())
        p.click('#config-fechar')
        p.evaluate('''() => {
          window.googleFalhar = true;
          const anterior = window.pywebview.api;
          window.pywebview.api = new Proxy(anterior, {get:(alvo,nome) => {
            if (nome === 'google_status' && googleFalhar) return async () => { throw new Error('Falha de teste'); };
            return alvo[nome];
          }});
        }''')
        p.click('#ferramentas-bt'); p.click('#config-conexoes')
        p.wait_for_selector('#conexoes-erro', state='visible')
        self.assertIn('Falha de teste', p.locator('#conexoes-erro').inner_text())
        self.assertTrue(p.locator('#conexoes-repetir').is_visible())
        p.evaluate('window.googleFalhar = false')
        p.click('#conexoes-repetir')
        p.wait_for_selector('#conexoes-erro', state='hidden')
        self.assertIn('Não conectado', p.locator('[data-conexao="calendar"]').inner_text())

    def test_drive_configura_autoriza_busca_pagina_e_desconecta(self):
        self.abrir(True, catalogo=True)
        p = self.page
        p.click('[data-conexao="drive"]')
        self.assertTrue(p.locator('#drive-conectar').is_disabled())
        p.click('#drive-reutilizar')
        p.wait_for_function("!document.querySelector('#drive-conectar').disabled")
        p.click('#drive-conectar')
        self.assertTrue(p.locator('#drive-desconectar').is_visible())
        p.evaluate('''() => Object.assign(driveTeste,{conectado:true,conectando:false,conta:'teste@example.com',ultima_sync:'2026-10-22T15:00:00Z'})''')
        p.wait_for_selector('#drive-consulta', state='visible')
        p.click('#conexoes-voltar')
        self.assertEqual(p.locator('.conexao-card.conectado').count(), 2)
        self.assertEqual(p.locator('#conexoes-resumo').inner_text(), '2 conexões ativas')
        p.click('[data-conexao="drive"]')
        p.fill('#drive-termo', 'cliente')
        p.locator('#drive-busca button').click()
        p.wait_for_selector('#drive-arquivos article')
        self.assertIn('<img', p.locator('#drive-arquivos').inner_text())
        self.assertEqual(p.locator('#drive-arquivos img').count(), 0)
        p.click('#drive-mais')
        p.wait_for_function("document.querySelector('#drive-arquivos').children.length === 2")
        self.assertEqual(p.evaluate("chamadas.filter(c=>c.nome==='drive_buscar').map(c=>c.args)"), [['cliente', '', '', False], ['cliente', 'pagina-2', '', False]])
        p.locator('#drive-arquivos button').first.click()
        p.wait_for_function("chamadas.some(c=>c.nome==='resposta_abrir_link')")
        p.screenshot(path=r'D:\kanivete_testes\conexoes_drive.png')
        p.click('#drive-desconectar')
        p.wait_for_selector('#drive-consulta', state='hidden')
        p.click('#conexoes-voltar')
        self.assertEqual(p.locator('.conexao-card.conectado').count(), 1)
        self.assertNotIn('conectado', p.locator('[data-conexao="drive"]').get_attribute('class'))

    def test_drive_somente_leitura_oferece_ampliacao_sem_escrita(self):
        self.page.evaluate("Object.assign(driveTeste,{configurado:true,conectado:true,controle_total:false})")
        self.abrir(catalogo=True)
        p = self.page; p.click('[data-conexao="drive"]')
        self.assertEqual(p.locator('#drive-conectar').inner_text(), 'Autorizar controle total')
        self.assertTrue(p.locator('#drive-enviar').is_disabled())
        self.assertTrue(p.locator('#drive-criar').is_disabled())
        self.assertIn('Somente leitura', p.locator('#drive-status').inner_text())

    def test_drive_gerencia_itens_pastas_e_lixeira(self):
        p = self.page
        p.evaluate('''() => {
          Object.assign(driveTeste,{configurado:true,conectado:true,controle_total:true,conta:'teste@example.com'});
          const itens = [
            {id:'destino',nome:'Cliente',pasta:true,pais:['root'],url:'https://drive.google.com/drive/folders/destino'},
            {id:'arquivo',nome:'Contrato.txt',pasta:false,pais:['root'],url:'https://drive.google.com/file/d/arquivo'}];
          const anterior=pywebview.api;
          pywebview.api=new Proxy(anterior,{get:(alvo,nome)=>{
            const opcoes=['drive_buscar','drive_criar_pasta','drive_renomear','drive_mover','drive_lixeira','drive_enviar','drive_baixar'];
            if(!opcoes.includes(nome)) return alvo[nome];
            return async(...args)=>{
              chamadas.push({nome,args});
              if(nome==='drive_buscar') return {arquivos:itens.filter(i=>!!i.lixeira===!!args[3] && (!args[2] || i.pais.includes(args[2]))),proxima:''};
              if(nome==='drive_criar_pasta') { const item={id:'nova',nome:args[0],pasta:true,pais:[args[1]],url:'https://drive.google.com/drive/folders/nova'};itens.push(item);return item; }
              if(nome==='drive_enviar') return {id:'enviado',name:'Arquivo enviado.txt'};
              if(nome==='drive_baixar') return {id:args[0],caminho:'D:/kanivete_testes/Contrato.txt'};
              const item=itens.find(i=>i.id===args[0]);
              if(nome==='drive_renomear') item.nome=args[1];
              if(nome==='drive_mover') item.pais=[args[1]];
              if(nome==='drive_lixeira') item.lixeira=!args[1];
              return item;
            };
          }});
        }''')
        self.abrir(catalogo=True); p.click('[data-conexao="drive"]')
        p.locator('#drive-busca button').click()
        p.wait_for_selector('#drive-arquivos article')
        p.get_by_role('button', name='Ações de Contrato.txt', exact=True).click()
        p.select_option('#drive-op-acao', 'renomear'); p.fill('#drive-op-valor','Contrato final.txt')
        self.assertFalse(p.evaluate("chamadas.some(c=>c.nome==='drive_renomear')"))
        p.click('#drive-op-confirmar')
        p.wait_for_function("chamadas.some(c=>c.nome==='drive_renomear') && document.querySelector('#drive-operacao').hidden")
        p.get_by_role('button', name='Ações de Contrato final.txt', exact=True).click()
        p.select_option('#drive-op-acao','mover');p.fill('#drive-op-valor','https://drive.google.com/drive/folders/destino')
        p.click('#drive-op-confirmar');p.wait_for_function("chamadas.some(c=>c.nome==='drive_mover') && document.querySelector('#drive-operacao').hidden")
        self.assertEqual(p.evaluate("chamadas.find(c=>c.nome==='drive_mover').args"),['arquivo','destino'])
        p.get_by_role('button', name='Entrar na pasta Cliente', exact=True).click()
        p.wait_for_function("document.querySelector('#drive-local').textContent==='Cliente'")
        p.click('#drive-criar');p.fill('#drive-op-valor','Referências');p.click('#drive-op-confirmar')
        p.wait_for_function("chamadas.some(c=>c.nome==='drive_criar_pasta') && document.querySelector('#drive-operacao').hidden")
        self.assertEqual(p.evaluate("chamadas.find(c=>c.nome==='drive_criar_pasta').args"),['Referências','destino'])
        p.click('#drive-enviar');p.wait_for_function("chamadas.some(c=>c.nome==='drive_enviar') && !document.querySelector('#drive-enviar').disabled")
        self.assertEqual(p.evaluate("chamadas.find(c=>c.nome==='drive_enviar').args"),[None,'destino'])
        p.get_by_role('button', name='Ações de Contrato final.txt', exact=True).click()
        p.select_option('#drive-op-acao','baixar');p.click('#drive-op-confirmar')
        p.wait_for_function("document.querySelector('#drive-status').textContent.includes('Arquivo salvo em:')")
        self.assertEqual(p.evaluate("chamadas.find(c=>c.nome==='drive_baixar').args"),['arquivo',None,''])
        p.get_by_role('button', name='Ações de Contrato final.txt', exact=True).click()
        p.select_option('#drive-op-acao','lixeira');p.click('#drive-op-confirmar')
        p.wait_for_function("chamadas.some(c=>c.nome==='drive_lixeira') && document.querySelector('#drive-operacao').hidden")
        p.select_option('#drive-visao','lixeira');p.wait_for_function("document.querySelector('#drive-local').textContent==='Lixeira'")
        p.get_by_role('button', name='Ações de Contrato final.txt', exact=True).click()
        p.select_option('#drive-op-acao','restaurar');p.click('#drive-op-confirmar')
        p.wait_for_function("chamadas.filter(c=>c.nome==='drive_lixeira').length===2 && document.querySelector('#drive-operacao').hidden")
        self.assertEqual(p.evaluate("chamadas.filter(c=>c.nome==='drive_lixeira').map(c=>c.args)"),[['arquivo',False],['arquivo',True]])
        p.select_option('#drive-visao','root');p.wait_for_function("document.querySelector('#drive-local').textContent==='Meu Drive'")
        p.screenshot(path=r'D:\kanivete_testes\drive_controle_total.png')

    def test_modal_pequeno_com_scroll_e_escape(self):
        self.page.set_viewport_size({'width': 360, 'height': 540})
        self.abrir(True, catalogo=True)
        self.assertEqual(self.page.locator('#configuracoes').evaluate('(e) => e.scrollWidth <= e.clientWidth'), True)
        caixa = self.page.locator('#configuracoes').bounding_box()
        self.assertGreaterEqual(caixa['x'], 0)
        self.assertLessEqual(caixa['x'] + caixa['width'], 360)
        self.assertLessEqual(caixa['height'], 540)
        self.page.screenshot(path=r'D:\kanivete_testes\conexoes_360.png')
        self.page.keyboard.press('Escape')
        self.assertFalse(self.page.locator('#configuracoes').is_visible())


if __name__ == '__main__':
    unittest.main()
