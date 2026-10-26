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
            if (nome === 'maximizar') { window.janelaMaximizadaTeste = args[0]; return args[0]; }
            if (nome === 'maximizada') return !!window.janelaMaximizadaTeste;
            if (nome === 'quem') { agenteTeste=args[0]; return true; }
            if (nome === 'contas_listar' || nome === 'conta_atualizar') return {lista:contasTeste, ativa:'principal'};
            if (nome === 'historico') return historicoTeste;
            if (nome === 'gpu_info') return gpuTeste;
            if (nome === 'voz') return {on:false};
            if (nome === 'google_status') return {configurado:false,conectado:false,conectando:false,
              mensagem:'',conta:'',ultima_sync:null,calendarios:[],selecionados:[],eventos:[],antes:10,avisos:{}};
            return true;
          }})};
        """)
        self.page.goto((Path(__file__).resolve().parents[1] / "ui/janela.html").as_uri())
        self.page.evaluate("dispatchEvent(new Event('pywebviewready'))")
        self.page.wait_for_function("document.querySelector('#lado-contas .cnt img')?.complete")

    def evento(self, ev):
        self.page.evaluate("ev => kcEv(ev)", ev)

    def test_aba_codigo_atualiza_conteudo_e_colore_sem_executar_html(self):
        self.evento({'t':'codex_alteracao', 'arquivo':'exemplo.py', 'conteudo':'def soma(x):\n    return x + 1',
                     'diff':'@@ -1 +1 @@\n-x=1\n+x=2', 'adicionadas':1, 'removidas':1})
        self.page.evaluate("document.getElementById('codigo-aba').click()")
        self.assertEqual(self.page.locator('.codigo-painel select').input_value(), 'exemplo.py')
        self.assertIn('+1 / −1', self.page.locator('.codigo-resumo').inner_text())
        self.assertGreater(self.page.locator('.codigo-painel .sintaxe-palavra').count(), 0)
        self.evento({'t':'codex_alteracao', 'arquivo':'exemplo.py', 'conteudo':'x = 3', 'adicionadas':2, 'removidas':1})
        self.assertEqual(self.page.locator('.codigo-painel code').inner_text(), 'x = 3')
        html = self.page.evaluate("KCResposta.md('```python\\nprint(\"<img src=x onerror=alert(1)>\")\\n```')")
        self.assertIn('sintaxe-texto', html)
        self.assertNotIn('<img src=x', html)
        self.page.evaluate("conversa.replaceChildren()")
        self.page.wait_for_function("document.querySelector('.codigo-painel select').options.length === 0")
        self.assertEqual(self.erros, [])

    def test_controles_nas_posicoes_pedidas_e_fotos(self):
        p = self.page
        self.assertEqual(p.locator('.topo button').count(), 5)   # + 🌐 navegador
        self.assertEqual(p.locator('#ferramentas-menu button').count(), 6)
        self.assertEqual(p.get_by_role('button', name='OpenCode · teste Big Pickle', exact=True, include_hidden=True).count(), 1)
        self.assertEqual(p.locator('#lado-contas img').count(), 2)
        self.assertEqual(p.locator('#lado-contas .cnt').count(), 3)
        self.assertTrue(p.locator('#status #pastas-nav #pasta').is_visible())
        self.assertEqual(p.locator('#status #c5, #status #csem').count(), 2)
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

        p.wait_for_selector('#contas', state='visible')
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

    def test_ferramentas_e_configuracoes_ficam_separadas(self):
        p = self.page
        self.assertTrue(p.locator('#ferramentas-menu').is_hidden())
        self.evento({"t":"ferr", "id":"bg", "nome":"Bash", "entrada":{"command":"teste", "run_in_background":True}})
        self.assertNotIn('aberto', p.locator('#atv').get_attribute('class'))
        p.click('#atv-trilho')
        self.assertEqual(p.locator('#atv-trilho').get_attribute('aria-label'), 'Ferramentas')
        self.assertTrue(p.locator('#atv #ferramentas-menu').is_visible())
        self.assertEqual(p.locator('#ferramentas-menu .ferramentas-grupo h3').all_text_contents(), ['CONVERSA E CÓDIGO', 'ARQUIVOS'])
        self.assertEqual(p.locator('#ferramentas-codigo button').count(), 5)
        self.assertEqual(p.locator('#ferramentas-arquivos button').count(), 1)
        self.assertEqual(p.locator('#ferramentas-menu #som, #ferramentas-menu #fixar, #ferramentas-menu #config-conexoes').count(), 0)
        p.click('#ferramentas-bt')
        self.assertTrue(p.locator('#config-menu').is_visible())
        self.assertTrue(p.locator('#config-menu #perfil-portatil-bt').is_visible())
        p.click('#som')
        self.assertTrue(p.locator('#ferramentas-menu').is_visible())
        self.assertTrue(p.locator('#config-menu').is_visible())
        p.keyboard.press('Escape')
        self.assertTrue(p.locator('#config-menu').is_hidden())
        self.assertTrue(p.locator('#ferramentas-menu').is_visible())
        p.screenshot(path=r'D:/kanivete_testes/kanicode_painel_ferramentas.png')
        p.get_by_text('Atividade da conversa', exact=True).click()
        self.assertTrue(p.locator('#atv-lista').is_visible())
        p.click('#codigo-aba')
        self.assertTrue(p.locator('#ferramentas-conteudo').is_hidden())
        self.assertTrue(p.locator('.codigo-painel').is_visible())
        p.click('#codigo-atividades')
        self.assertTrue(p.locator('#ferramentas-menu').is_visible())
        p.click('#atv-fechar')
        self.assertTrue(p.locator('#painel-ajuste').is_hidden())
        self.assertEqual(self.erros, [])

    def test_envio_com_erro_preserva_pedido_e_mostra_diagnostico(self):
        p = self.page
        p.evaluate("""() => {
          quemDefinir('codex', false);
          const anterior = pywebview.api;
          pywebview.api = new Proxy(anterior, {get(alvo, nome) {
            if (nome === 'ajudante') return async () => { throw new Error('falha controlada da ponte'); };
            return alvo[nome];
          }});
        }""")
        p.fill('#texto', 'Pedido que precisa permanecer disponível')
        p.click('#enviar')
        p.wait_for_function("document.querySelector('#conversa').textContent.includes('falha controlada da ponte')")
        self.assertEqual(p.locator('#texto').input_value(), 'Pedido que precisa permanecer disponível')
        self.assertFalse(p.evaluate('K.ocupada'))
        self.assertTrue(p.evaluate("chamadas.some(c => c.nome === 'janela_diagnostico' && c.args[0] === 'envio')"))
        self.assertEqual(self.erros, [])

    def test_divisoria_arrasta_guarda_e_respeita_o_tamanho_da_janela(self):
        p = self.page
        p.set_viewport_size({'width': 1100, 'height': 740})
        p.click('#atv-trilho')
        ajuste = p.locator('#painel-ajuste')
        self.assertEqual(ajuste.get_attribute('aria-valuenow'), '270')
        self.assertEqual(p.evaluate("chamadas.filter(c => c.nome === 'painel_espaco').at(-1).args"), [270])
        p.wait_for_function("Math.abs(document.querySelector('#ferramentas-painel').getBoundingClientRect().width - 270) < 1")
        caixa = ajuste.bounding_box()
        x, y = caixa['x'] + caixa['width']/2, caixa['y'] + 100
        p.mouse.move(x, y); p.mouse.down(); p.mouse.move(x-160, y, steps=8); p.mouse.up()
        self.assertEqual(ajuste.get_attribute('aria-valuenow'), '430')
        self.assertEqual(p.evaluate("localStorage.getItem('kanicode-painel-largura')"), '430')
        self.assertAlmostEqual(p.locator('#ferramentas-painel').bounding_box()['width'], 430, delta=1)
        p.click('#codigo-aba')
        self.assertAlmostEqual(p.locator('.codigo-painel').bounding_box()['width'], 430, delta=1)
        p.click('#codigo-atividades')
        p.screenshot(path=r'D:/kanivete_testes/kanicode_painel_regulavel.png')
        p.set_viewport_size({'width': 700, 'height': 740})
        p.wait_for_function("Number(document.querySelector('#painel-ajuste').getAttribute('aria-valuenow')) <= 280")
        p.wait_for_function("document.querySelector('#ferramentas-painel').getBoundingClientRect().width <= 280")
        self.assertGreaterEqual(p.locator('.meio').bounding_box()['width'], 320)
        p.set_viewport_size({'width': 1100, 'height': 740})
        p.wait_for_function("document.querySelector('#painel-ajuste').getAttribute('aria-valuenow') === '430'")
        self.assertEqual(p.evaluate("chamadas.filter(c => c.nome === 'painel_espaco').length"), 1)
        p.reload(); p.evaluate("dispatchEvent(new Event('pywebviewready'))")
        p.click('#atv-trilho')
        self.assertEqual(ajuste.get_attribute('aria-valuenow'), '430')
        ajuste.focus(); p.keyboard.press('ArrowRight')
        self.assertEqual(ajuste.get_attribute('aria-valuenow'), '410')
        p.keyboard.press('Home')
        self.assertEqual(ajuste.get_attribute('aria-valuenow'), '270')
        p.click('#atv-fechar')
        self.assertTrue(ajuste.is_hidden())
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

    def test_pastas_internas_ocultas_e_projeto_adicional_na_barra(self):
        p = self.page
        p.evaluate("""async () => {
          const anterior = pywebview.api;
          window.pastaBarraTeste = 'D:/Projetos/Kanivete';
          pywebview.api = new Proxy(anterior, {get(alvo, nome) {
            if (nome === 'info') return async () => ({pasta:pastaBarraTeste,
              pastas_internas:['D:/Projetos/Kanivete','D:/Plugins/kanicode'],quem:'claude',limite:{h5:.32,sem:.25}});
            return alvo[nome];
          }});
          await carregar();
        }""")
        self.assertEqual(p.locator('[data-pasta-nome]').inner_text(), '')
        self.assertTrue(p.locator('#status #pasta').is_visible())
        self.assertTrue(p.locator('#status #c5').is_visible())
        p.evaluate("async () => {pastaBarraTeste='D:/Plugins/kanicode';await carregar();}")
        self.assertEqual(p.locator('[data-pasta-nome]').inner_text(), '')
        p.evaluate("async () => {pastaBarraTeste='D:/Clientes/Loja';await carregar();}")
        self.assertEqual(p.locator('[data-pasta-nome]').inner_text(), 'Loja')
        self.assertIn('D:/Clientes/Loja', p.locator('#pasta').get_attribute('title'))
        for largura in (340, 420, 600):
            p.set_viewport_size({'width':largura,'height':740})
            p.evaluate("K.ocupada=true;K.faz='Processando os arquivos do projeto';K.t0=Date.now()-2000;K.tokMsg=10000;status();")
            self.assertLessEqual(p.evaluate('document.body.scrollWidth'), largura)
            self.assertTrue(p.locator('#c5').is_visible())
        p.screenshot(path=r'D:\kanivete_testes\kanicode_barra_status.png')
        self.assertEqual(self.erros, [])

    def test_enter_enfileira_e_duplo_clique_prioriza_nos_quatro_motores(self):
        p = self.page
        p.evaluate("""() => {
          window.filaTeste=[];
          const anterior=pywebview.api;
          pywebview.api=new Proxy(anterior,{get(alvo,nome){
            if(nome==='mensagens_fila') return async()=>filaTeste;
            if(nome==='mensagem_enviar') return async(id,texto,imagens,quem)=>{
              chamadas.push({nome,args:[id,texto,imagens,quem]});
              const item={id,texto,minis:imagens.map(i=>i.mini),quem,estado:'pendente'};
              filaTeste.push(item);kcEv({t:'fila_mensagem',...item});return item;
            };
            if(nome==='mensagem_urgente') return async(id)=>{
              chamadas.push({nome,args:[id]});
              const item=filaTeste.find(i=>i.id===id);item.estado='urgente';kcEv({t:'fila_mensagem',...item});return true;
            };
            return alvo[nome];
          }});
        }""")
        for quem in ('claude','codex','kani','pickle'):
            p.evaluate("q=>{quemDefinir(q,false);ocupada(true);window.bolhaAndamento=bolha('kc','Resposta em andamento');K.bolha=bolhaAndamento;}", quem)
            p.fill('#texto','Pedido seguinte '+quem)
            self.assertEqual(p.locator('#enviar').inner_text(), 'Enfileirar')
            p.press('#texto','Enter')
            p.wait_for_function('q=>chamadas.some(c=>c.nome===\"mensagem_enviar\"&&c.args[3]===q)',arg=quem)
            self.assertTrue(p.evaluate('K.bolha===bolhaAndamento && K.ocupada'))
            self.assertEqual(p.input_value('#texto'), '')
            b=p.locator('.mensagem-pendente').last
            self.assertIn('Na fila',b.inner_text())
            b.dblclick()
            p.wait_for_function('q=>filaTeste.some(i=>i.quem===q&&i.estado===\"urgente\")',arg=quem)
            self.assertIn('Urgente',b.inner_text())
        self.assertFalse(p.evaluate("chamadas.some(c=>['parar','enviar','ajudante'].includes(c.nome))"))
        p.evaluate('ocupada(false)')
        p.evaluate('async()=>await carregar()')
        self.assertEqual(p.locator('[data-mensagem-id]').count(),4)
        item=p.evaluate('filaTeste[0]')
        self.evento({'t':'fila_mensagem',**item,'estado':'enviando'})
        self.evento({'t':'fila_mensagem',**item,'estado':'enviada'})
        self.evento({'t':'eco_eu','de':'fila','texto':item['texto'],'minis':[]})
        self.assertEqual(p.locator('[data-mensagem-id]').count(),4)
        self.assertFalse(p.locator('[data-mensagem-id="'+item['id']+'"]').locator('.mensagem-fila-nota').count())
        self.assertEqual(self.erros, [])

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

    def test_andamento_codex_recolhe_anterior_quando_comeca_nova_rodada(self):
        self.page.evaluate("quemDefinir('codex', false)")
        self.evento({'t':'ajudante','quem':'codex','fase':'inicio','texto':'Organizar'})
        self.evento({'t':'ajudante','quem':'codex','fase':'passo','id':'a','operacao':'inicio','texto':'primeira etapa'})
        blocos = self.page.locator('.codex-andamento')
        self.assertTrue(blocos.nth(0).evaluate('(el) => el.open'))
        self.evento({'t':'ajudante','quem':'codex','fase':'passo','id':'a','operacao':'fim','texto':'pensando','ok':True})
        self.assertTrue(blocos.nth(0).evaluate('(el) => el.open'))
        self.evento({'t':'codex_progresso','id':'m','texto':'Primeira etapa concluída. Vou continuar.'})
        self.evento({'t':'ajudante','quem':'codex','fase':'passo','id':'b','operacao':'inicio','texto':'segunda etapa'})
        self.assertEqual(blocos.count(), 2)
        self.assertFalse(blocos.nth(0).evaluate('(el) => el.open'))
        self.assertTrue(blocos.nth(1).evaluate('(el) => el.open'))
        self.assertIn('✓ Concluído: primeira etapa', blocos.nth(0).text_content())
        # Ainda é possível consultar manualmente um andamento anterior.
        blocos.nth(0).locator('summary').click()
        self.assertTrue(blocos.nth(0).evaluate('(el) => el.open'))
        self.evento({'t':'ajudante_resposta','quem':'codex','texto':'Concluído','ok':True})
        self.evento({'t':'ajudante','quem':'codex','fase':'inicio','texto':'Outro pedido'})
        self.evento({'t':'ajudante','quem':'codex','fase':'passo','id':'c','operacao':'inicio','texto':'terceira etapa'})
        self.assertEqual(blocos.count(), 3)
        self.assertEqual(self.page.locator('.codex-andamento[open]').count(), 1)
        self.assertTrue(blocos.nth(2).evaluate('(el) => el.open'))
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
        self.page.click('#codex-conta-lateral')
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

    def test_codex_na_lateral_com_foto_e_limites(self):
        self.page.evaluate("""() => {
          const anterior = pywebview.api;
          pywebview.api = new Proxy(anterior, {get(alvo, nome) {
            if (nome === 'codex_identidade') return async () => ({ok:true, email:'codex@exemplo.com', plano:'pro', logado:true,
              foto:'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aFooAAAAASUVORK5CYII='});
            if (nome === 'codex_limites') return async () => ({ok:true,cota:{h5:.25,sem:.6,h5_zera:1800000000}});
            return alvo[nome];
          }});
          quemDefinir('codex', false);
        }""")
        p = self.page
        p.click('#codex-conta-lateral')
        p.wait_for_function("document.querySelector('#codex-conta-lateral').title.includes('25%')")
        p.click('#codex-conta-lateral')
        self.assertTrue(p.locator('#codex-conta-lateral .foto-ct img').is_visible())
        self.assertTrue(p.locator('.codex-conta').is_hidden())
        self.assertEqual(p.locator('.rodape .codex-conta').count(), 0)
        p.click('#codex-conta-lateral')
        self.assertIn('codex@exemplo.com', p.locator('.codex-identificacao').inner_text())
        self.assertIn('60% usado', p.locator('.codex-janelas').inner_text())
        p.click('#conversa', position={'x':200, 'y':20})
        self.assertTrue(p.locator('.codex-conta').is_hidden())
        p.click('#lado-aj')

        p.wait_for_selector('.lado.aberto')
        p.wait_for_selector('#codex-conta-lateral .codex-email', state='visible')
        self.assertIn('codex@exemplo.com', p.locator('#codex-conta-lateral .codex-email').inner_text())
        p.screenshot(path=r'D:\kanivete_testes\codex_lateral.png')
        self.assertEqual(self.erros, [])

    def test_erros_claude_mostram_motivo_e_diagnostico(self):
        self.evento({'t':'fim','erro':True,'mensagem':'Exportação interrompida por falta de espaço',
                     'diagnostico':'D:/kanivete_testes/continuidade/eventos.jsonl'})
        self.assertIn('falta de espaço', self.page.locator('#conversa').inner_text())
        self.assertIn('eventos.jsonl', self.page.locator('#conversa').inner_text())
        self.evento({'t':'saiu','erro':'processo terminou com código 9',
                     'diagnostico':'D:/kanivete_testes/continuidade/eventos.jsonl'})
        self.assertIn('receberá o registro de retomada', self.page.locator('#conversa').inner_text())
        self.evento({'t':'aviso','texto':'Não foi possível guardar a continuidade: disco indisponível'})
        self.assertIn('disco indisponível', self.page.locator('#conversa').inner_text())
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
        self.page.click('#atv-trilho')
        self.page.get_by_role('button', name='Revisar código isolado', exact=True).click()
        self.page.wait_for_function("!document.querySelector('.codigo-aplicar').disabled")
        self.assertIn('+return a+b', self.page.locator('.codigo-diff').inner_text())
        self.assertEqual(self.page.evaluate('aplicacoesTeste.length'), 0)
        self.page.click('.codigo-aplicar')
        self.page.wait_for_function('aplicacoesTeste.length === 1')
        self.assertEqual(self.page.evaluate('aplicacoesTeste[0]'), ['pickle','revisao1'])
        self.assertEqual(self.erros, [])


    def test_cota_ao_vivo_atualiza_lateral_e_preserva_semana(self):
        self.page.evaluate("kcEv({t:'limite',conta:'principal',h5:.83,lido:2000})")
        self.assertEqual(self.page.locator('#lado-contas [data-id="principal"] small').inner_text(), '83%')
        self.page.locator('#c5').click()
        self.assertIn('25%', self.page.locator('#uso').inner_text())
        self.page.evaluate("kcEv({t:'limite',conta:'principal',sem:.68,lido:2001})")
        self.assertIn('68%', self.page.locator('#uso').inner_text())
        self.assertEqual(self.page.locator('#lado-contas [data-id="principal"] small').inner_text(), '83%')
        self.assertEqual(self.erros, [])

    def test_medicao_de_outra_conta_nao_altera_cota_ativa(self):
        self.page.evaluate("kcEv({t:'limite',conta:'workspace',h5:.91,lido:2000})")
        self.assertEqual(self.page.locator('#lado-contas [data-id="workspace"] small').inner_text(), '91%')
        self.assertIn('32%', self.page.locator('#c5').inner_text())
        self.assertEqual(self.erros, [])

    def test_troca_automatica_atualiza_painel_sem_misturar_janelas(self):
        self.page.evaluate("""kcEv({t:'conta_trocada', texto:'Continuando com outra conta', dados:{ativa:'nova',
            lista:[{id:'nova',apelido:'Nova',logado:true,cotas:{h5:.8}}]}})""")
        self.assertEqual(self.page.locator('#lado-contas .ativa small').inner_text(), '80%')
        self.page.locator('#c5').click()
        self.assertNotIn('25%', self.page.locator('#uso').inner_text())
        self.assertEqual(self.erros, [])



    def test_codex_resposta_atrasada_nao_regride_porcentagem(self):
        self.evento({'t':'codex_uso','cota':{'h5':.84,'sem':.62,'medido_em':2000}})
        self.evento({'t':'codex_uso','cota':{'h5':.2,'sem':.1,'medido_em':1000}})
        self.assertIn('84%', self.page.locator('#codex-conta-lateral').inner_text())
        self.assertIn('62% usado', self.page.locator('.codex-janelas').inner_text())
        self.assertEqual(self.erros, [])


if __name__ == '__main__':
    unittest.main()
