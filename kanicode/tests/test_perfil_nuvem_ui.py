"""Meu perfil e Drive na interface isolada, com ponte simulada."""
import unittest
import test_layout as layout


@unittest.skipUnless(layout.sync_playwright,'Playwright opcional não instalado')
class PerfilNuvemUITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls): layout.LayoutTest.setUpClass.__func__(cls)
    def setUp(self):
        layout.LayoutTest.setUp(self)
        self.page.evaluate("""() => {
          window.Cerebro={montar:()=>{}};
          const anterior=pywebview.api;
          pywebview.api=new Proxy({}, {get:(_,nome)=>async (...args)=>{
            if(nome==='usuario_ler')return {nome:'Pessoa',email:'teste@example.com'};
            if(nome==='perfil_resumo')return {arquivos:5};
            if(nome==='perfil_acesso')return {autenticado:true,requer_acesso:false,email:'teste@example.com'};
            if(nome==='perfil_nuvem'){
              chamadas.push({nome,args});
              if(args[0]==='conferir')return {id:'remoto',texto:'perfil sintético'};
              return {ativo:true,conta:'teste@example.com',mensagem:'Perfil salvo no Drive',versoes:[{id:'remoto',revisao:'123456789abc'}],conferencia:'token'};
            }
            if(nome==='perfil_conferir')return {perfil:{nome:'Pessoa'},resumo:{novo:1,igual:0,conflito:0},conferencia:'previa',avisos:[],arquivos:[]};
            return anterior[nome](...args);
          }});
        }""")
    def test_acesso_na_lateral_sem_botao_em_configuracoes(self):
        self.page.evaluate('perfilAbrir(true)')
        self.page.get_by_role('button',name='Backup e sincronização do perfil',exact=True).click()
        self.assertTrue(self.page.locator('.perfil-portatil').is_visible())
        self.assertEqual(self.page.locator('#perfil-portatil-bt').count(),0)
        self.page.locator('[data-nuvem="ativar"]').click()
        self.assertIn('teste@example.com',self.page.locator('.perfil-nuvem-status').inner_text())
        self.page.locator('[data-nuvem="conferir"]').click()
        self.assertTrue(self.page.locator('.perfil-portatil footer').is_visible())
        self.page.locator('.perfil-aplicar').click()
        self.page.wait_for_function("chamadas.some(c=>c.nome==='perfil_nuvem'&&c.args[0]==='restaurar')")
        r=self.page.evaluate("chamadas.find(c=>c.nome==='perfil_nuvem'&&c.args[0]==='restaurar')")
        self.assertEqual(r['args'][1:3],['remoto','previa'])
        self.assertEqual(self.erros,[])
