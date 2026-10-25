"""Formulário de acesso do perfil com ponte simulada e navegador isolado."""
import unittest
import test_layout as layout


@unittest.skipUnless(layout.sync_playwright,'Playwright opcional não instalado')
class PerfilAcessoUITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls): layout.LayoutTest.setUpClass.__func__(cls)
    def setUp(self):
        layout.LayoutTest.setUp(self)
        self.page.evaluate("""() => {
          window.Cerebro={montar:()=>{}};window.acessoTeste=false;window.erroAcessoTeste=false;
          const anterior=pywebview.api;
          pywebview.api=new Proxy({}, {get:(_,nome)=>async (...args)=>{
            if(nome==='usuario_ler')return {nome:'Pessoa',email:'teste@example.com'};
            if(nome==='perfil_resumo')return {arquivos:5};
            if(nome==='perfil_acesso'){
              chamadas.push({nome,args});
              if(erroAcessoTeste&&args[0]!=='status')throw Error('E-mail ou senha do KaniCode incorretos.');
              if(args[0]==='entrar'||args[0]==='cadastrar')acessoTeste=true;
              if(args[0]==='sair')acessoTeste=false;
              return {autenticado:acessoTeste,requer_acesso:!acessoTeste,email:'teste@example.com',mensagem:acessoTeste?'Acesso liberado.':'Entre no perfil.'};
            }
            if(nome==='perfil_nuvem'){
              chamadas.push({nome,args});return {ativo:true,autenticado:acessoTeste,requer_acesso:!acessoTeste,mensagem:'Perfil salvo no Drive',versoes:[],conferencia:'token'};
            }
            return anterior[nome](...args);
          }});
        }""")
        self.page.evaluate('perfilAbrir(true)')
        self.page.get_by_role('button',name='Backup e sincronização do perfil',exact=True).click()
    def preencher(self):
        self.page.locator('.perfil-acesso-email').fill('teste@example.com')
        self.page.locator('.perfil-acesso-senha').fill('senha-ficticia-longa')
    def test_cadastro_envia_confirmacao_lembra_e_limpa_campos(self):
        self.assertTrue(self.page.locator('[data-nuvem="ativar"]').is_disabled())
        self.page.locator('.perfil-acesso-modo').click();self.preencher()
        self.page.locator('.perfil-acesso-confirmar input').fill('senha-ficticia-longa')
        self.page.get_by_role('button',name='Salvar meu acesso',exact=True).click()
        self.page.wait_for_function("chamadas.some(c=>c.nome==='perfil_nuvem'&&c.args[0]==='ativar')")
        c=self.page.evaluate("chamadas.find(c=>c.nome==='perfil_acesso'&&c.args[0]==='cadastrar')")
        self.assertTrue(c['args'][1]['lembrar']);self.assertEqual(c['args'][1]['senha'],c['args'][1]['confirmacao'])
        self.assertEqual(self.page.locator('.perfil-acesso-senha').input_value(),'')
        self.assertFalse(self.page.locator('.perfil-acesso-form').is_visible());self.assertEqual(self.erros,[])
    def test_senha_errada_mostra_erro_sem_liberar_sincronizacao(self):
        self.page.evaluate('erroAcessoTeste=true');self.preencher()
        self.page.get_by_role('button',name='Entrar no meu perfil',exact=True).click()
        self.page.wait_for_function("document.querySelector('.perfil-acesso-status').textContent.includes('incorretos')")
        self.assertTrue(self.page.locator('[data-nuvem="ativar"]').is_disabled())
        self.assertEqual(self.page.locator('.perfil-acesso-senha').input_value(),'');self.assertEqual(self.erros,[])
    def test_entrar_e_sair_nao_deixa_previa_ativa(self):
        self.preencher();self.page.get_by_role('button',name='Entrar no meu perfil',exact=True).click()
        self.page.locator('.perfil-acesso-sair').click()
        self.assertTrue(self.page.locator('.perfil-acesso-form').is_visible())
        self.assertTrue(self.page.locator('[data-nuvem="ativar"]').is_disabled());self.assertEqual(self.erros,[])
