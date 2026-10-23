"""Painel real em navegador isolado, sem app ou contas reais."""
from pathlib import Path
import unittest
import test_layout as layout

@unittest.skipUnless(layout.sync_playwright, 'Playwright não instalado')
class TarefasUITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright=layout.sync_playwright().start()
        cls.addClassCleanup(cls.playwright.stop)
        cls.browser=cls.playwright.chromium.launch(headless=True) if Path(cls.playwright.chromium.executable_path).exists() else cls.playwright.chromium.launch(channel='msedge',headless=True)
        cls.addClassCleanup(cls.browser.close)
    def setUp(self):
        layout.LayoutTest.setUp(self)
        self.page.evaluate('''() => {
          window.todoTeste=[]; window.todoFalhar=false;
          const anterior=window.pywebview.api;
          window.pywebview.api=new Proxy({}, {get:(_,nome)=> {
            if(!nome.startsWith('todo_')) return anterior[nome];
            return async (...args)=> {
              chamadas.push({nome,args});
              if(todoFalhar) throw new Error('Falha de teste');
              if(nome==='todo_listar') return structuredClone(todoTeste);
              if(nome==='todo_salvar') {
                let i=todoTeste.find(i=>i.id===args[2]);
                if(!i) {i={id:String(todoTeste.length+1),concluida:false,criado:'2026-01-01',origem:'manual'};todoTeste.push(i);}
                Object.assign(i,{titulo:args[0],prazo:args[1]});return i;
              }
              if(nome==='todo_concluir') {todoTeste.find(i=>i.id===args[0]).concluida=args[1];return {};}
              if(nome==='todo_alarmes') return structuredClone(window.alarmesTeste||[]);
              if(nome==='todo_alarme_apagar') {window.alarmesTeste=(window.alarmesTeste||[]).filter(a=>a.id!==args[0]);return {};}
              if(nome==='todo_alarme_salvar') {const a=(window.alarmesTeste||[]).find(a=>a.id===args[0]); if(a) Object.assign(a,{titulo:args[1],hora:args[2].slice(-5),data:args[2].slice(0,10)}); return a||{};}
              if(nome==='todo_agenda') return window.agendaTeste || {itens:[{id:'a',titulo:'Consulta médica',inicio:'2026-12-01T15:00',origem:'kani'},{id:'b',titulo:'Reunião',inicio:'2026-12-02',dia_inteiro:true,origem:'google',calendario:'Trabalho'}],google_conectado:true,ultima_sync:'2026-10-22T10:00:00Z'};
              return {id:'l1'};
            };
          }});
        }''')
    def tearDown(self):
        self.assertEqual(self.erros,[])
    def abrir(self):
        self.page.click('#todo-trilho')
        self.page.wait_for_function("document.querySelector('#todo-trilho').getAttribute('aria-expanded')==='true'")
    def test_criar_editar_concluir_reabrir_e_xss(self):
        p=self.page; self.abrir()
        p.fill('#todo-titulo','<img src=x onerror=alert(1)>')
        p.click('#todo-salvar')
        p.wait_for_function("document.querySelectorAll('#todo-lista .todo-linha').length===1")
        self.assertEqual(p.locator('#todo-lista img').count(),0)
        p.click('#todo-lista .todo-editar'); p.fill('#todo-titulo','Comprar café'); p.click('#todo-salvar')
        p.click('#todo-lista input[type=checkbox]')
        p.wait_for_function("document.querySelector('#todo-concluidas').hidden===false")
        p.click('#todo-concluidas summary'); p.click('#todo-feitas input[type=checkbox]')
        p.wait_for_function("document.querySelectorAll('#todo-lista .todo-linha').length===1")
        self.assertEqual(p.locator('#todo-lista b').inner_text(),'Comprar café')
        p.keyboard.press('Escape')
        p.click('#todo-trilho')
        self.assertEqual(p.locator('#todo-lista b').inner_text(),'Comprar café')
    def test_navegacao_sem_crescimento_duplo_e_agenda(self):
        p=self.page; self.abrir()
        p.click('#atv-trilho'); self.assertFalse(p.locator('#todo-painel').is_visible())
        p.click('#todo-trilho'); p.click('#todo-tab-agenda')
        self.assertIn('Consulta médica',p.locator('#todo-eventos').inner_text())
        self.assertIn('Dia inteiro',p.locator('#todo-eventos').inner_text())
        p.click('#todo-sync')
        self.assertTrue(p.evaluate("chamadas.some(c=>c.nome==='todo_agenda' && c.args[0]===true)"))
        p.click('#todo-fechar')
        # A janela ganha só o espaço necessário; fechar não desfaz o tamanho escolhido.
        self.assertFalse(p.evaluate("chamadas.some(c=>c.nome==='crescer')"))
        self.assertEqual(p.evaluate("chamadas.filter(c=>c.nome==='painel_espaco').length"), 3)
    def test_novas_em_cima(self):
        p=self.page
        p.evaluate("todoTeste=[{id:'1',titulo:'Velha',criado:'2026-10-01T10:00',concluida:false,origem:'manual'},{id:'2',titulo:'Nova',criado:'2026-10-20T10:00',concluida:false,origem:'manual'}]")
        self.abrir()
        p.wait_for_function("document.querySelectorAll('#todo-lista .todo-linha').length===2")
        self.assertEqual(p.locator('#todo-lista b').all_inner_texts(),['Nova','Velha'])
    def test_agenda_semana(self):
        p=self.page
        p.evaluate("""() => { const d=new Date(); d.setDate(d.getDate()+1);
          const k=`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
          window.agendaTeste={itens:[{id:'x',titulo:'Gravação',inicio:k+'T09:30',origem:'kani'},{id:'y',titulo:'Feriado',inicio:k,dia_inteiro:true,origem:'google'}],google_conectado:false}; }""")
        self.abrir(); p.click('#todo-tab-agenda'); p.click('.todo-vista [data-v=semana]')
        p.wait_for_function("document.querySelectorAll('.todo-semana button').length===7")
        self.assertIn('Nada marcado',p.locator('#todo-eventos').inner_text())   # hoje vazio
        self.assertEqual(p.locator('.todo-semana button').nth(1).locator('i span').count(),2)
        p.locator('.todo-semana button').nth(1).click()
        txt=p.locator('#todo-eventos').inner_text()
        self.assertIn('Gravação',txt); self.assertIn('Feriado',txt)
        self.assertEqual(p.evaluate("localStorage.getItem('kc-todo-vista')"),'semana')
        p.click('.todo-vista [data-v=lista]')
        self.assertEqual(p.locator('.todo-semana').count(),0)
        self.assertIn('Gravação',p.locator('#todo-eventos').inner_text())
    def test_lembrete_e_falha_visivel(self):
        p=self.page; self.abrir(); p.click('#todo-tab-alarmes')
        p.click('#todo-lembrete summary'); p.fill('#todo-lembrete-titulo','Consulta'); p.fill('#todo-inicio','2026-12-01T15:00')
        p.click('#todo-lembrete-salvar')
        p.wait_for_function("document.querySelector('#todo-status').textContent.includes('Lembrete salvo')")
        self.assertTrue(p.evaluate("chamadas.some(c=>c.nome==='todo_lembrar' && c.args[2]===10)"))
        p.evaluate('todoFalhar=true'); p.click('#todo-tab-agenda'); p.click('#todo-sync')
        p.wait_for_function("document.querySelector('#todo-status').textContent.includes('Falha de teste')")
    def test_alarmes_editar_excluir(self):
        p=self.page
        p.evaluate("window.alarmesTeste=[{id:'a1',titulo:'Alarme',data:'2026-12-01',hora:'17:17',dias:[],antes:10,passado:false}]")
        self.abrir(); p.click('#todo-tab-alarmes')
        p.wait_for_function("document.querySelectorAll('#todo-alarmes-lista .todo-linha').length===1")
        self.assertIn('17:17',p.locator('#todo-alarmes-lista').inner_text())
        p.click('#todo-alarmes-lista .todo-editar'); self.assertEqual(p.input_value('#todo-inicio'),'2026-12-01T17:17')
        p.fill('#todo-inicio','2026-12-01T14:50'); p.click('#todo-lembrete-salvar')
        p.wait_for_function("document.querySelector('#todo-alarmes-lista').innerText.includes('14:50')")
        p.click('.todo-excluir'); p.click('.todo-excluir.confirmar')
        p.wait_for_function("document.querySelectorAll('#todo-alarmes-lista .todo-linha').length===0")
    def test_visual_desktop_e_celular(self):
        p=self.page; p.set_viewport_size({'width':1000,'height':780}); self.abrir()
        p.fill('#todo-titulo','Preparar proposta do cliente'); p.click('#todo-salvar')
        p.wait_for_function("document.querySelectorAll('#todo-lista .todo-linha').length===1")
        p.screenshot(path=r'D:\kanivete_testes\todo_impl\desktop.png')
        p.add_style_tag(path=str(Path(__file__).resolve().parents[1]/'ui/movel.css'))
        p.evaluate("document.documentElement.classList.add('movel')")
        p.set_viewport_size({'width':390,'height':844})
        p.screenshot(path=r'D:\kanivete_testes\todo_impl\celular.png')
        self.assertTrue(p.evaluate("document.documentElement.scrollWidth<=innerWidth"))
