"""Aba Agente no painel real: origem, conclusão e retomada, sem motores ou dados reais."""
from pathlib import Path
import unittest
import test_layout as layout
import test_tarefas_ui as pessoal


@unittest.skipUnless(layout.sync_playwright,'Playwright não instalado')
class AgenteUITest(unittest.TestCase):
    setUpClass=pessoal.TarefasUITest.__dict__['setUpClass']
    setUpBase=pessoal.TarefasUITest.setUp
    tearDown=pessoal.TarefasUITest.tearDown

    def setUp(self):
        self.setUpBase()
        self.page.set_viewport_size({'width':1000,'height':740})
        self.page.evaluate('''()=>{
          window.agenteTeste=[{id:'ag1',titulo:'Conferir o streaming <img src=x>',estado:'adiada',concluida:false,agente:'codex',aba:'1',mensagem_id:'origem-1',texto:'Corrija a tela cheia e depois confira no celular.',motivo:'Falta conferir no aparelho.'}];
          window.agenteFalhar=false;
          const anterior=pywebview.api;
          pywebview.api=new Proxy(anterior,{get:(alvo,nome)=>{
            if(nome==='todo_agente_listar')return async()=>structuredClone(agenteTeste);
            if(nome==='todo_agente_contexto')return async id=>{if(agenteFalhar)throw Error('Falha de teste');return structuredClone(agenteTeste.find(i=>i.id===id));};
            if(nome==='todo_agente_concluir')return async(id,on)=>{const i=agenteTeste.find(i=>i.id===id);i.concluida=on;i.estado=on?'concluida':'pendente';return structuredClone(i);};
            return alvo[nome];
          }});
          const b=bolha('eu',agenteTeste[0].texto);b.dataset.mensagemId='origem-1';
        }''')

    def abrir(self):
        self.page.click('#todo-trilho');self.page.click('#todo-tab-agente')
        self.page.wait_for_selector('#todo-agente-lista .todo-linha')

    def test_espelho_fechado_atualiza_e_abre_pedido(self):
        p=self.page
        p.evaluate("kcEv({t:'todo_agente',aba:'outra'})")
        p.wait_for_selector('#todo-agente-espelho .todo-agente-tag')
        self.assertEqual(p.locator('.todo-agente-contagem').inner_text(),'Agente · 1')
        self.assertEqual(p.locator('#todo-agente-espelho img').count(),0)
        self.assertTrue(p.evaluate("document.querySelector('#todo-agente-espelho').nextElementSibling.id==='status'"))
        p.locator('.todo-agente-tag').click()
        p.wait_for_selector('#todo-agente-contexto pre')
        self.assertEqual(p.locator('#todo-tab-agente').get_attribute('aria-selected'),'true')
        p.locator('#todo-agente-lista input').click()
        p.wait_for_function("document.querySelector('.todo-agente-contagem').textContent==='Agente · 0'")
        self.assertEqual(p.locator('.todo-agente-tag').count(),0)

    def test_espelho_mobile_fica_em_uma_linha(self):
        p=self.page
        p.set_viewport_size({'width':390,'height':740})
        p.add_style_tag(path=str(Path(__file__).resolve().parents[1]/'ui/movel.css'))
        p.evaluate('''()=>{document.documentElement.classList.add('movel');
          agenteTeste=Array.from({length:8},(_,n)=>({id:'t'+n,titulo:'Uma tarefa com um título bastante longo para conferir o espelho '+n,estado:'pendente',concluida:false}));
          agenteTeste.push({id:'feita',titulo:'Concluída',concluida:true},{id:'cancelada',titulo:'Cancelada',estado:'cancelada'});
          kcEv({t:'todo_agente'});
        }''')
        p.wait_for_function("document.querySelectorAll('.todo-agente-tag').length===8")
        self.assertEqual(p.locator('.todo-agente-contagem').inner_text(),'Agente · 8')
        caixa=p.locator('#todo-agente-espelho').bounding_box()
        self.assertLess(caixa['height'],32)
        self.assertLessEqual(caixa['x']+caixa['width'],391)
        self.assertTrue(p.evaluate("(()=>{const e=document.querySelector('.todo-agente-tags');return e.scrollWidth>e.clientWidth})()"))
        p.screenshot(path='D:/kanivete_testes/todo_agente_espelho_mobile.png')

    def test_espelho_so_mostra_o_que_pede_acao(self):
        p=self.page
        p.evaluate('''()=>{agenteTeste=[
          {id:'conf',titulo:'Respondido',estado:'a_conferir',concluida:false,aba:'1',criado:'2026-01-01T01'},
          {id:'f1',titulo:'Falha velha',estado:'falha',concluida:false,aba:'2',criado:'2026-01-01T01'},
          {id:'f2',titulo:'Falha nova',estado:'falha',concluida:false,aba:'2',criado:'2026-01-01T02'},
          {id:'f3',titulo:'Falha outra aba',estado:'falha',concluida:false,aba:'3',criado:'2026-01-01T01'},
          {id:'ad',titulo:'Para depois',estado:'adiada',concluida:false,aba:'1',criado:'2026-01-01T01'}];
          kcEv({t:'todo_agente'});}''')
        p.wait_for_function("document.querySelector('.todo-agente-contagem').textContent==='Agente · 3'")
        ids=p.evaluate("[...document.querySelectorAll('.todo-agente-tag')].map(e=>e.dataset.tarefaAgente)")
        self.assertEqual(sorted(ids),['ad','f2','f3'])

    def test_aba_origem_segura_e_localizar_mensagem(self):
        p=self.page;self.abrir()
        self.assertIn('Para depois',p.locator('#todo-agente-lista').inner_text())
        self.assertEqual(p.locator('#todo-agente-lista img').count(),0)
        self.assertTrue(p.locator('#todo-pe').is_hidden())
        p.get_by_role('button',name='Ver pedido',exact=True).click()
        p.wait_for_selector('#todo-agente-contexto pre')
        self.assertEqual(p.locator('#todo-agente-contexto pre').inner_text(),'Corrija a tela cheia e depois confira no celular.')
        p.get_by_role('button',name='Localizar na conversa',exact=True).click()
        self.assertTrue(p.evaluate('mensagemLocalizar(agenteTeste[0])'))
        p.screenshot(path='D:/kanivete_testes/todo_agente.png')

    def test_concluir_sai_da_lista_e_reabrir_volta(self):
        p=self.page;self.abrir()
        p.locator('#todo-agente-lista input[type=checkbox]').click()
        p.wait_for_function("document.querySelectorAll('#todo-agente-lista .todo-linha').length===0")
        p.locator('#todo-agente-concluidas summary').click()
        self.assertTrue(p.locator('#todo-agente-feitas .todo-linha.feita').is_visible())
        p.locator('#todo-agente-feitas input').click()
        p.wait_for_selector('#todo-agente-lista .todo-linha')
        self.assertFalse(p.evaluate('agenteTeste[0].concluida'))
        p.click('#todo-tab-tarefas')
        self.assertEqual(p.locator('#todo-lista .todo-linha').count(),0)

    def test_evento_de_outra_aba_atualiza_sem_apagar_a_origem(self):
        p=self.page;self.abrir()
        p.get_by_role('button',name='Ver pedido',exact=True).click()
        p.wait_for_selector('#todo-agente-contexto pre')
        p.evaluate("() => { agenteTeste[0].concluida=true;agenteTeste[0].estado='concluida';kcEv({t:'todo_agente',aba:'outra'}); }")
        p.wait_for_function("document.querySelectorAll('#todo-agente-lista .todo-linha').length===0")
        self.assertIn('Corrija a tela cheia',p.locator('#todo-agente-contexto').inner_text())
        p.click('#todo-tab-agente');p.keyboard.press('ArrowRight')
        self.assertEqual(p.locator('#todo-tab-agenda').get_attribute('aria-selected'),'true')


if __name__=='__main__':unittest.main()
