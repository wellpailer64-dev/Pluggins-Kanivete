"""Filtros do cérebro no navegador com dados isolados, sem conectar ao app em uso."""
import unittest
from pathlib import Path
import test_layout as layout
import test_conexoes_ui as conexoes
import test_cerebro_projetos as projetos
import perfil_cerebro as c


@unittest.skipUnless(layout.sync_playwright, 'Playwright opcional não instalado')
class ClassificacaoUITest(unittest.TestCase):
    setUpClass = classmethod(conexoes.ConexoesUITest.setUpClass.__func__)

    def setUp(self):
        projetos.ProjetosTest.setUp(self)
        layout.LayoutTest.setUp(self)
        for nome, texto, tipo in [('KANIVETE', 'Edição no KANIVETE', 'project'),
                                  ('KaniCode', 'Interface do KaniCode', 'processo'),
                                  ('Kani local', 'Qwen via Ollama: correção conferida', 'licao')]:
            r = c.guardar(nome, texto, tipo=tipo, certeza='verificado', origem='teste', forcar=True)
            if nome == 'Kani local':
                c.classificar(r['chave'], ['kani_local'], 'aprendizado', 'registro da Kani', 'verificado', 'kani')
        dados = c.ler()
        self.page.expose_function('cerebroDadosTeste', lambda: dados)
        self.page.expose_function('cerebroConsultaTeste', lambda tema, ambito=None: c.consultar(tema, marcar=False, ambito=ambito))
        self.page.evaluate('''() => {
          const anterior=pywebview.api;
          pywebview.api=new Proxy(anterior,{get:(alvo,nome)=> {
            if(nome==='cerebro_ler') return () => cerebroDadosTeste();
            if(nome==='cerebro_consultar') return (t,a) => cerebroConsultaTeste(t,a);
            return alvo[nome];
          }});
          const el=document.createElement('div');el.id='cerebro-teste';el.className='cerebro grande';document.body.appendChild(el);
          localStorage.setItem('cerebro-som','0');
        }''')
        codigo = (Path(__file__).resolve().parents[1] / 'ui/cerebro.js').read_text(encoding='utf-8')
        codigo = codigo.replace('window.Cerebro = { montar, tocar };',
            "window.Cerebro = { montar, tocar, selecionarTeste: chave => { C.sel=C.pts.find(p=>p.no?.chave===chave); cartao(C.sel); }, audioTeste: () => ({ambiente:SOM.ambiente?.gain.value, notas:SOM.notas?.gain.value, ligado:SOM.ambienteLigado}), visiveis: () => C.pts.filter(p => p.no && visivel(p)).map(p => p.titulo), cartaoTeste: () => cartao(C.pts.find(p => p.no && visivel(p))) };")
        self.page.add_script_tag(content=codigo)
        self.page.evaluate("async () => { await Cerebro.montar(document.querySelector('#cerebro-teste'), {nome:'Pailer'}); }")

    def tearDown(self):
        projetos.ProjetosTest.tearDown(self)
        self.assertEqual(self.erros, [])

    def test_filtros_sistemas_finalidade_autoria_e_cartao(self):
        p = self.page
        self.assertEqual(len(p.evaluate('Cerebro.visiveis()')), 3)

        for ambito, nome in [('kanivete','KANIVETE'), ('kanicode','KaniCode'), ('kani_local','Kani local')]:
            p.select_option('[data-cer-filtro="ambito"]', ambito)
            self.assertEqual(p.evaluate('Cerebro.visiveis()'), [nome])
        p.select_option('[data-cer-filtro="finalidade"]', 'aprendizado')
        p.select_option('[data-cer-filtro="agente"]', 'kani')
        self.assertEqual(p.evaluate('Cerebro.visiveis()'), ['Kani local'])
        p.evaluate('Cerebro.cartaoTeste()')
        cartao = p.locator('#cerebro-teste .cer-cartao').inner_text()
        self.assertIn('Registrado por: kani', cartao)
        self.assertIn('Classificação confirmada', cartao)
        self.assertIn('Evitar repetir erro', cartao)
        p.screenshot(path='D:/kanivete_testes/cerebro_classificacao.png')
        p.select_option('[data-cer-filtro="ambito"]', 'kanivete')
        self.assertEqual(p.evaluate('Cerebro.visiveis()'), [])
        self.assertTrue(p.locator('#cerebro-teste .cer-cartao').is_hidden())
        for campo in ('ambito','finalidade','agente'):
            p.select_option(f'[data-cer-filtro="{campo}"]', '')
        self.assertEqual(len(p.evaluate('Cerebro.visiveis()')), 3)

    def test_microfone_de_qualquer_aba_silencia_e_libera_sons(self):
        p = self.page
        p.locator('#cerebro-teste [data-c="som"]').click()
        p.wait_for_function('Cerebro.audioTeste().ambiente > .4')
        p.evaluate("kcEv({t:'microfone_prioridade', ativo:true, aba:'outra'})")
        p.wait_for_function('Cerebro.audioTeste().ambiente < .001 && Cerebro.audioTeste().notas < .001')
        self.assertFalse(p.evaluate('Cerebro.audioTeste().ligado'))
        p.evaluate("kcEv({t:'microfone_prioridade', ativo:false, aba:'outra'})")
        p.wait_for_function('Cerebro.audioTeste().ambiente > .4 && Cerebro.audioTeste().notas > .8')
        self.assertTrue(p.evaluate('Cerebro.audioTeste().ligado'))


if __name__ == '__main__':
    unittest.main()
