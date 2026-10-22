"""Layout real, API local simulada e navegador isolado; nenhum agente é chamado."""
import base64
import io
import json
from pathlib import Path
import unittest

from PIL import Image
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


@unittest.skipUnless(sync_playwright, "Playwright opcional não instalado")
class LayoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.addClassCleanup(cls.playwright.stop)
        if not Path(cls.playwright.chromium.executable_path).exists():
            raise unittest.SkipTest("Chromium não instalado")
        cls.browser = cls.playwright.chromium.launch(headless=True)
        cls.addClassCleanup(cls.browser.close)

    def setUp(self):
        self.page = self.browser.new_page(viewport={"width": 600, "height": 740})
        self.addCleanup(self.page.close)
        self.page.set_default_timeout(3000)
        self.erros = []
        self.page.on("pageerror", lambda e: self.erros.append(str(e)))
        buf = io.BytesIO()
        Image.new("RGB", (16, 16), "#829570").save(buf, "PNG")
        foto = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
        contas = [{"id": "principal", "apelido": "Principal", "email": "principal@example.com", "foto": foto,
                   "logado": True, "cotas": {"h5": .32, "sem": .25}},
                  {"id": "workspace", "apelido": "Workspace", "email": "workspace@example.com", "foto": foto,
                   "logado": True, "cotas": {"h5": .7, "sem": .45}},
                  {"id": "panda", "apelido": "PandaLab", "email": "panda@example.com", "logado": True}]
        self.page.add_init_script("window.contasTeste = " + json.dumps(contas) + ";" + """
          window.chamadas = []; window.agenteTeste = 'claude'; window.modoTeste = 'auto';
          window.historicoTeste = [{t:'eu',texto:'Vamos organizar o próximo ajuste?'},
            {t:'kc',texto:'Tudo pronto. Qual parte do projeto vamos trabalhar agora?'}];
          window.gpuTeste = {disponivel:true,nome:'GPU de teste',uso:26,memoria_usada:2147483648,memoria_total:8589934592,temperatura:50};
          window.pywebview = {api: new Proxy({}, {get: (_, nome) => async (...args) => {
            chamadas.push({nome, args});
            if (nome === 'info') return {pasta:'D:/Projetos/Kanivete', quem:agenteTeste, fixa:true,
              ocupada:false, modo:modoTeste, limite:{h5:.32,sem:.25}};
            if (nome === 'modo') { modoTeste=args[0]; return modoTeste; }
            if (nome === 'expandir') return args[0];
            if (nome === 'quem') { agenteTeste=args[0]; return true; }
            if (nome === 'contas_listar' || nome === 'conta_atualizar') return {lista:contasTeste, ativa:'principal'};
            if (nome === 'historico') return historicoTeste;
            if (nome === 'gpu_info') return gpuTeste;
            if (nome === 'voz') return {on:false};
            return true;
          }})};
        """)
        self.page.goto((Path(__file__).resolve().parents[1] / "ui/janela.html").as_uri())
        self.page.evaluate("dispatchEvent(new Event('pywebviewready'))")
        self.page.wait_for_function("document.querySelector('#lado-contas .cnt img')?.complete")

    def evento(self, ev):
        self.page.evaluate("ev => kcEv(ev)", ev)

    def test_controles_nas_posicoes_pedidas_e_fotos(self):
        p = self.page
        self.assertEqual(p.locator('.topo button').count(), 3)
        self.assertEqual(p.locator('#ferramentas-menu button').count(), 8)
        self.assertEqual(p.get_by_role('button', name='OpenCode · teste Big Pickle', exact=True, include_hidden=True).count(), 1)
        self.assertEqual(p.locator('#lado-contas img').count(), 2)
        self.assertEqual(p.locator('#lado-contas .cnt').count(), 3)
        self.assertTrue(p.locator('#pastas-nav #pasta').is_visible())
        self.assertEqual(p.locator('.rodape #pasta, .rodape #modo-bt, .rodape #quem-bt').count(), 0)
        for a,b in [('#quem-bt','#modo-bt'),('#modo-bt','#texto')]:
            self.assertLess(p.locator(a).bounding_box()['x'],p.locator(b).bounding_box()['x'])
        p.click('#modo-bt')
        p.wait_for_function("document.querySelector('[data-modo-label]').textContent === 'Planejar'")
        p.click('#modo-bt')
        p.wait_for_function("document.querySelector('[data-modo-label]').textContent === 'Build'")
        p.click('#quem-bt')
        p.click('[data-q="codex"]')
        p.wait_for_function("document.querySelector('#quem-bt i img')?.getAttribute('src') === 'codex.svg'")
        self.assertEqual(self.erros, [])

    def test_bolinhas_seta_e_logo_claude(self):
        p = self.page
        for seletor, cor in [('#recolher','rgb(232, 232, 232)'),('#grande','rgb(212, 129, 74)'),('#sair','rgb(229, 83, 75)')]:
            self.assertEqual(p.locator(seletor).evaluate('(el) => getComputedStyle(el).backgroundColor'),cor)
            self.assertEqual(p.locator(seletor).evaluate('(el) => getComputedStyle(el).borderRadius'),'50%')
        p.click('#grande')
        p.wait_for_function("document.querySelector('#grande').getAttribute('aria-pressed') === 'true'")
        p.click('#grande')
        p.wait_for_function("document.querySelector('#grande').getAttribute('aria-pressed') === 'false'")
        self.assertEqual(p.locator('#lado-aj svg path').get_attribute('d'),'m14 7-5 5 5 5')
        p.click('#lado-aj')
        self.assertTrue(p.locator('#contas').is_visible())
        p.click('#quem-bt')
        self.assertEqual(p.locator('[data-q="claude"] img').get_attribute('src'),'claude.svg')
        p.wait_for_function("document.querySelector('[data-q=claude] img').naturalWidth > 0")
        self.assertEqual(self.erros, [])

    def test_saudacao_central_so_na_conversa_vazia(self):
        p = self.page
        self.assertTrue(p.locator('#saudacao').is_hidden())
        p.evaluate('async () => {historicoTeste=[]; await carregar();}')
        self.assertTrue(p.locator('#saudacao').is_visible())
        self.assertEqual(p.locator('#conversa').inner_text(),'')
        caixa = p.locator('.meio').bounding_box()
        centro = p.locator('#saudacao').bounding_box()
        self.assertAlmostEqual(centro['y']+centro['height']/2,caixa['y']+caixa['height']/2,delta=1)
        self.evento({'t':'eco_eu','de':'celular','texto':'Olá!'})
        self.assertTrue(p.locator('#saudacao').is_hidden())
        self.assertEqual(self.erros, [])

    def test_gpu_pausa_quando_janela_fica_oculta(self):
        p = self.page
        p.clock.install()
        p.click('#quem-bt'); p.click('[data-q="kani"]')
        p.wait_for_function("document.querySelector('#gpu-uso').textContent === 'GPU 26%'")
        p.evaluate("Object.defineProperty(document, 'hidden', {configurable:true,value:true}); document.dispatchEvent(new Event('visibilitychange'))")
        antes = p.evaluate("chamadas.filter(c => c.nome === 'gpu_info').length")
        p.clock.fast_forward(5000)
        self.assertEqual(p.evaluate("chamadas.filter(c => c.nome === 'gpu_info').length"),antes)
        p.evaluate("gpuTeste.uso=73; Object.defineProperty(document, 'hidden', {configurable:true,value:false}); document.dispatchEvent(new Event('visibilitychange'))")
        p.wait_for_function("document.querySelector('#gpu-uso').textContent === 'GPU 73%'")
        self.assertEqual(self.erros, [])

    def test_kani_gpu_atualiza_e_para_ao_sair(self):
        p = self.page
        self.assertFalse(p.evaluate("chamadas.some(c => c.nome === 'gpu_info')"))
        p.click('#quem-bt'); p.click('[data-q="kani"]')
        p.wait_for_function("document.querySelector('#gpu-uso').textContent === 'GPU 26%'")
        self.assertTrue(p.locator('#c5').is_hidden())
        self.assertTrue(p.locator('#csem').is_hidden())
        self.assertIn('ilimitada',p.locator('#kani-recursos').inner_text())
        self.assertEqual(p.locator('#gpu-memoria').inner_text(),'2.0 / 8.0 GB')
        p.evaluate('gpuTeste.uso=59; cotas({h5:.8,sem:.6});')
        p.wait_for_function("document.querySelector('#gpu-uso').textContent === 'GPU 59%'")
        self.assertTrue(p.locator('#c5').is_hidden())
        self.assertNotEqual(p.locator('#gpu-linha').get_attribute('points'),'')
        p.evaluate('gpuTeste={disponivel:false}')
        p.wait_for_function("document.querySelector('#gpu-uso').textContent.includes('indisponível')")
        self.assertEqual(p.locator('#gpu-memoria').inner_text(),'')
        self.assertEqual(p.locator('#gpu-linha').get_attribute('points'),'')
        p.click('#quem-bt'); p.click('[data-q="claude"]')
        p.wait_for_function("!document.querySelector('#c5').hidden")
        self.assertTrue(p.locator('#kani-recursos').is_hidden())
        antes = p.evaluate("chamadas.filter(c => c.nome === 'gpu_info').length")
        p.wait_for_timeout(1800)
        self.assertEqual(p.evaluate("chamadas.filter(c => c.nome === 'gpu_info').length"),antes)
        self.assertEqual(self.erros, [])

    def test_menu_e_atividades_so_expandem_com_clique(self):
        p = self.page
        self.assertTrue(p.locator('#ferramentas-menu').is_hidden())
        self.evento({"t":"ferr", "id":"bg", "nome":"Bash", "entrada":{"command":"teste", "run_in_background":True}})
        self.assertNotIn('aberto',p.locator('#atv').get_attribute('class'))
        self.assertLessEqual(p.locator('#atv').bounding_box()['width'],34)
        p.click('#ferramentas-bt')
        self.assertTrue(p.locator('#ferramentas-menu').is_visible())
        p.click('#som')
        self.assertTrue(p.locator('#ferramentas-menu').is_hidden())
        self.assertIn('Sons das ações',p.locator('#som').inner_text())
        p.click('#ferramentas-bt'); p.keyboard.press('Escape')
        self.assertTrue(p.locator('#ferramentas-menu').is_hidden())
        self.assertFalse(p.evaluate("chamadas.some(c => c.nome === 'esconder')"))
        p.click('#atv-trilho')
        p.wait_for_function("document.querySelector('#atv').classList.contains('aberto')")
        p.click('#atv-fechar')
        p.wait_for_function("!document.querySelector('#atv').classList.contains('aberto')")
        self.assertEqual(self.erros, [])

    def test_pastas_aparecem_por_operacao_e_somem_no_fim(self):
        self.evento({"t":"ferr","id":"a","nome":"Read","entrada":{"file_path":"D:/Projetos/Kanivete/frontend/js/app.js"}})
        self.assertIn('frontend/js',self.page.locator('#pastas-ativas').inner_text())
        self.evento({"t":"ferr","id":"b","nome":"Edit","entrada":{"file_path":"D:/Projetos/Kanivete/frontend/js/outro.js"}})
        self.evento({"t":"ferr_fim","id":"a","ok":True})
        self.assertEqual(self.page.locator('.pasta-ativa').count(),1)
        self.evento({"t":"ferr_fim","id":"b","ok":True})
        self.assertEqual(self.page.locator('.pasta-ativa').count(),0)
        self.evento({"t":"ajudante","quem":"codex","fase":"passo","operacao":"inicio","id":"1",
                     "entrada":{"command":"Get-Content 'D:/Projetos/Kanivete/Functions/editor.py'"}})
        self.assertIn('Functions',self.page.locator('#pastas-ativas').inner_text())
        self.evento({"t":"ajudante","quem":"codex","fase":"fim","ok":True})
        self.assertEqual(self.page.locator('.pasta-ativa').count(),0)
        self.assertTrue(self.page.locator('#pasta').is_visible())
        self.evento({"t":"ferr","id":"claude-ativo","nome":"Read","entrada":{"file_path":"D:/Projetos/Kanivete/docs/mapa.md"}})
        self.evento({"t":"ajudante","quem":"codex","fase":"fim","ok":True})
        self.assertIn('docs',self.page.locator('#pastas-ativas').inner_text())
        self.evento({"t":"fim"})
        self.assertEqual(self.page.locator('.pasta-ativa').count(),0)

    def test_larguras_pequenas_sem_corte_do_campo(self):
        for largura in (340,420,550):
            self.page.set_viewport_size({"width":largura,"height":740})
            self.assertGreater(self.page.locator('#texto').bounding_box()['width'],60)
            self.assertLessEqual(self.page.evaluate('document.body.scrollWidth'),largura)
        self.assertEqual(self.erros, [])

    def test_estilo_do_celular_preserva_entrada_e_navegacao(self):
        self.page.add_style_tag(path=str(Path(__file__).resolve().parents[1]/'ui/movel.css'))
        self.page.evaluate("document.documentElement.classList.add('movel')")
        self.page.set_viewport_size({'width':390,'height':844})
        self.assertTrue(self.page.locator('#pasta').is_visible())
        self.assertTrue(self.page.locator('#quem-bt').is_visible())
        self.assertTrue(self.page.locator('#modo-bt').is_visible())
        self.assertTrue(self.page.locator('#ferramentas-bt').is_hidden())
        self.assertGreater(self.page.locator('#texto').bounding_box()['width'],60)
        self.assertLessEqual(self.page.evaluate('document.body.scrollWidth'),390)


    def test_progresso_codex_preserva_mensagens_e_conclui_etapa(self):
        self.page.evaluate("quemDefinir('codex', false)")
        self.page.evaluate('ocupada(true)')
        self.evento({'t':'ajudante','quem':'codex','fase':'inicio','texto':'Corrigir'})
        self.evento({'t':'codex_progresso','id':'m1','texto':'Encontrei a causa. Vou corrigir soma.py.'})
        self.evento({'t':'codex_progresso','id':'m1','texto':'Encontrei a causa. Vou corrigir soma.py.'})
        self.evento({'t':'ajudante','quem':'codex','fase':'passo','id':'c1','operacao':'inicio','texto':'executando testes'})
        self.evento({'t':'ajudante','quem':'codex','fase':'passo','id':'c1','operacao':'fim','texto':'pensando','ok':True})
        self.evento({'t':'codex_progresso','id':'m2','texto':'<img src=x onerror=alert(1)> verificado'})
        self.assertEqual(self.page.locator('.codex-andamento p').count(), 1)
        self.assertEqual(self.page.locator('.codex-comentario').count(), 2)
        self.assertEqual(self.page.locator('.codex-comentario img[src="x"]').count(), 0)
        self.assertIn('✓ Concluído: executando testes', self.page.locator('.codex-andamento').inner_text())
        self.assertEqual(self.page.locator('.codex-andamento img').count(), 0)
        self.evento({'t':'codex_uso','uso':{'entrada':1000,'saida':33},'tokens':133})
        self.assertIn('33 tokens', self.page.locator('#num').inner_text())
        self.evento({'t':'ajudante_resposta','quem':'codex','texto':'<img src=x onerror=alert(1)> verificado','ok':True})
        self.assertEqual(self.page.locator('.codex-comentario').count(), 1)
        self.assertEqual(self.page.locator('.msg.aju').count(), 2)
        self.assertEqual(self.erros, [])

    def test_limite_redefinicao_e_saldo_atualizado(self):
        self.page.evaluate("""() => {
          window.resetsTeste = [];
          window.cotaTeste = {h5:1,sem:.2,atingido:true,redefinicoes:1,medido_em:123,
            h5_zera:1800000000, creditos_redefinicao:[{id:'credito1',status:'available'}]};
          const anterior = pywebview.api;
          pywebview.api = new Proxy(anterior, {get(alvo,nome) {
            if (nome === 'codex_limites') return async () => ({ok:true,cota:cotaTeste});
            if (nome === 'codex_redefinir') return async (...args) => {
              resetsTeste.push(args); cotaTeste = {...cotaTeste,h5:0,atingido:false,redefinicoes:0,medido_em:124};
              return {ok:true,cota:cotaTeste,mensagem:'Redefinição confirmada.'};
            };
            return alvo[nome];
          }});
          quemDefinir('codex', false);
        }""")
        self.page.wait_for_selector('.codex-redefinir', state='visible')
        self.assertIn('limite de uso atingido', self.page.locator('.codex-conta-estado').inner_text())
        self.page.set_viewport_size({'width':390,'height':844})
        self.page.screenshot(path=r'D:\kanivete_testes\kanicode_limites.png')
        self.page.click('.codex-redefinir')
        self.page.wait_for_function("resetsTeste.length === 1 && document.querySelector('.codex-reset-info').textContent.includes(': 0')")
        self.assertTrue(self.page.locator('.codex-redefinir').is_hidden())
        self.assertIn('0% usado', self.page.locator('.codex-janelas').inner_text())
        self.evento({'t':'codex_uso','uso':{},'cota':{'h5':1,'sem':.2}})
        self.assertIn('0% usado', self.page.locator('.codex-janelas').inner_text())
        self.assertEqual(len(self.page.evaluate('resetsTeste[0][0]')), 36)
        self.assertEqual(self.erros, [])

    def test_progresso_pickle_aparece_sem_interpretar_html(self):
        self.page.evaluate("quemDefinir('pickle', false)")
        self.evento({'t':'pickle_progresso','texto':'Concluído: codigo_testar. Próximo: revisão. <img src=x>'})
        self.assertIn('Concluído: codigo_testar', self.page.locator('#conversa').inner_text())
        self.assertEqual(self.page.locator('#conversa img[src="x"]').count(), 0)
        self.assertEqual(self.erros, [])

    def test_barra_de_codigo_expande_recolhe_e_preserva_texto(self):
        self.page.set_viewport_size({'width':390,'height':844})
        self.evento({'t':'codex_alteracao','arquivo':'soma.py','diff':'-return a-b\n+return a+b\n<img src=x>','rotulo':'Alterações desta tarefa.'})
        card = self.page.locator('.codigo-alteracao')
        self.assertFalse(card.evaluate('el => el.open'))
        card.locator('summary').click()
        self.assertTrue(card.evaluate('el => el.open'))
        self.assertIn('+return a+b', card.locator('pre').inner_text())
        self.assertEqual(card.locator('img').count(), 0)
        self.page.screenshot(path=r'D:\kanivete_testes\kanicode_diff.png')
        card.locator('summary').click()
        self.assertFalse(card.evaluate('el => el.open'))
        self.assertLessEqual(self.page.evaluate('document.body.scrollWidth'),390)
        self.assertEqual(self.erros, [])

    def test_revisao_mostra_diff_e_aplica_so_por_clique(self):
        self.page.evaluate("""() => {
          window.aplicacoesTeste = [];
          const anterior = pywebview.api;
          pywebview.api = new Proxy(anterior, {get(alvo,nome) {
            if (nome === 'codigo_revisar') return async () => ({ok:true,agente:'pickle',revisao:'revisao1',
              copia:'D:/kanivete_testes/copia',arquivos:['soma.py'],diff:'-return a-b\\n+return a+b',
              aplicada:false,verificacao:{ok:true},testes:{ok:true,arquivo:'test_soma.py',saida:'OK'},pode_aplicar:true});
            if (nome === 'codigo_aplicar') return async (...args) => {aplicacoesTeste.push(args);return {ok:true,arquivos:['soma.py'],backup:'D:/kanivete_testes/base'};};
            return alvo[nome];
          }});
        }""")
        self.page.click('#ferramentas-bt')
        self.page.get_by_role('button', name='Revisar código isolado', exact=True).click()
        self.page.wait_for_function("!document.querySelector('.codigo-aplicar').disabled")
        self.assertIn('+return a+b', self.page.locator('.codigo-diff').inner_text())
        self.assertEqual(self.page.evaluate('aplicacoesTeste.length'), 0)
        self.page.click('.codigo-aplicar')
        self.page.wait_for_function('aplicacoesTeste.length === 1')
        self.assertEqual(self.page.evaluate('aplicacoesTeste[0]'), ['pickle','revisao1'])
        self.assertEqual(self.erros, [])


if __name__ == '__main__':
    unittest.main()
