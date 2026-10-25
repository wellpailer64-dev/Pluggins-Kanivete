"""Visão Board (board.js): cartões das abas, chat de verdade no aberto, prévia nos outros, mover/zoom e fios."""
import os
from pathlib import Path
import unittest

from playwright.sync_api import sync_playwright


class BoardUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.addClassCleanup(cls.playwright.stop)
        if not Path(cls.playwright.chromium.executable_path).exists():
            raise unittest.SkipTest("Chromium não instalado")
        cls.browser = cls.playwright.chromium.launch(headless=True)
        cls.addClassCleanup(cls.browser.close)

    def setUp(self):
        self.page = self.browser.new_page(viewport={"width": 1200, "height": 800})
        self.addCleanup(self.page.close)
        self.page.set_default_timeout(3000)
        self.erros = []
        self.page.on("pageerror", lambda e: self.erros.append(str(e)))
        self.page.add_init_script("""
          localStorage.clear();
          window.chamadas = [];
          window.ABAS_T = {ativa: '1', lista: [{id: '1', quem: 'claude', nome: 'Principal', manual: true, ocupada: false},
                                               {id: '2', quem: 'kani', nome: 'Ajudante', manual: true, ocupada: false}]};
          window.FIOS = [];
          const copia = () => JSON.parse(JSON.stringify(ABAS_T));
          window.pywebview = {api: new Proxy({}, {get: (_, nome) => async (...args) => {
            chamadas.push({nome, args});
            const aba = ABAS_T.lista.find(a => a.id === ABAS_T.ativa);
            if (nome === 'info') return {pasta: 'D:/P', quem: aba.quem, fixa: true, ocupada: false, modo: 'auto', limite: null};
            if (nome === 'historico') return ABAS_T.ativa === '1' ? [{t: 'eu', texto: 'pedido da aba um'}] : [{t: 'eu', texto: 'oi kani'}];
            if (nome === 'contas_listar' || nome === 'conta_atualizar') return {lista: [], ativa: ''};
            if (nome === 'abas') return copia();
            if (nome === 'aba_ativar') { ABAS_T.ativa = String(args[0]); return copia(); }
            if (nome === 'aba_previa') return args[0] === '2' ? [{quem: 'pailer', texto: 'oi kani'}, {quem: 'kani', texto: 'Oi! Em que posso ajudar?'}] : [{quem: 'pailer', texto: 'pedido da aba um'}];
            if (nome === 'fios') return FIOS;
            if (nome === 'fio_criar') { FIOS = [{id: 'f1', de: String(args[0]), para: String(args[1]), modo: args[2]}]; setTimeout(() => kcEv({t: 'fios', lista: FIOS, aba: '1'}), 10); return FIOS[0]; }
            if (nome === 'voz') return {on: false};
            if (nome === 'rosto_quadros') return {fps: 10, quadros: [['................']]};
            return true;
          }})};
        """)
        self.page.goto((Path(__file__).resolve().parents[1] / "ui/janela.html").as_uri())
        self.page.evaluate("dispatchEvent(new Event('pywebviewready'))")
        self.page.wait_for_selector("#abas-chat .aba-chat")

    def test_board_ao_vivo_sem_selecionar(self):
        p = self.page
        p.click(".aba-board")
        p.wait_for_selector(".bd-card[data-aba='2'] .bd-fala")
        self.assertEqual(p.evaluate("KC_ABAS.ativa"), "1")
        p.evaluate("kcEv({t: 'inicio', aba: '2'}); kcEv({t: 'texto_novo', aba: '2'}); kcEv({t: 'texto', d: 'Escrevendo ', aba: '2'}); kcEv({t: 'texto', d: 'agora mesmo', aba: '2'})")
        p.wait_for_function("(document.querySelector(\".bd-card[data-aba='2'] .bd-aovivo\") || {}).textContent?.includes('Escrevendo agora mesmo')")
        p.evaluate("kcEv({t: 'ferr', nome: 'Bash', aba: '2'})")
        p.wait_for_function("(document.querySelector(\".bd-card[data-aba='2'] .bd-ferr\") || {}).textContent?.includes('Bash')")
        self.assertTrue(p.locator(".bd-card[data-aba='2'] .bd-aovivo").is_visible())
        b = p.evaluate("KC_BOARD.estado.cards['2']")
        self.assertGreaterEqual(b["w"], 1000)
        p.screenshot(path="D:/kanivete_testes/kanicode/board_aovivo.png")
        self.assertEqual(self.erros, [])

    def test_kaniball_no_board(self):
        p = self.page
        p.click(".aba-board")
        p.wait_for_selector(".bd-bola")
        p.evaluate("KC_BOARD.ajustar()")
        # cai do alto e pousa no topo de um chat
        p.wait_for_function("KC_BOLA.estado.modo === 'chao' && KC_BOLA.estado.sobre", timeout=5000)
        b = p.evaluate("({y: KC_BOLA.estado.y, sobre: KC_BOLA.estado.sobre})")
        topo = p.evaluate(f"KC_BOARD.estado.cards['{b['sobre']}'].y")
        self.assertAlmostEqual(b["y"], topo - 26, delta=1)
        # encostar na cordinha pendurada: ela balança
        p.evaluate("""(() => { const Q = KC_BOLA.estado, c = KC_BOARD.cordas.get('p:1'), q = c.pts[12];
          Object.assign(Q, {modo: 'ar', sobre: null, plano: [], passo: null, x: q.x - 40, y: q.y, vx: 600, vy: -100}); })()""")
        x0 = p.evaluate("KC_BOARD.cordas.get('p:1').pts[17].x")
        p.wait_for_timeout(250)
        self.assertGreater(abs(p.evaluate("KC_BOARD.cordas.get('p:1').pts[17].x") - x0), 3)
        # andar no fio: cria fio 1→2 e manda andar nele; a corda cede e ela chega ao chat 2
        p.evaluate("kcEv({t: 'fios', lista: [{id: 'f9', de: '1', para: '2', modo: 'leitura'}], aba: '1'})")
        p.wait_for_function("KC_BOARD.cordas.get('f:f9')", timeout=3000)
        p.wait_for_function("KC_BOLA.estado.modo === 'chao'", timeout=6000)
        p.evaluate("""(() => { const Q = KC_BOLA.estado, c = KC_BOARD.estado.cards['1'];
          Object.assign(Q, {sobre: '1', dx: c.w - 20, plano: [{tipo: 'corda', fio: 'f9'}], passo: null, salto: 0, truque: null}); })()""")
        p.wait_for_function("KC_BOLA.estado.modo === 'corda'", timeout=4000)
        p.wait_for_timeout(400)
        p.screenshot(path="D:/kanivete_testes/kanicode/bola_corda.png")
        p.wait_for_function("KC_BOLA.estado.modo === 'chao' && KC_BOLA.estado.sobre === '2'", timeout=15000)
        # arremessar com o mouse
        bx = p.locator(".bd-bola").bounding_box()
        x, y = bx["x"] + bx["width"] / 2, bx["y"] + bx["height"] / 2
        p.mouse.move(x, y); p.mouse.down(); p.mouse.move(x - 80, y - 120, steps=4); p.mouse.up()
        self.assertEqual(p.evaluate("KC_BOLA.estado.modo"), "ar")
        p.wait_for_timeout(200)
        p.screenshot(path="D:/kanivete_testes/kanicode/bola_board.png")
        # sai do Board: a bola some
        p.keyboard.press("Control+b")
        p.wait_for_function("!document.querySelector('.bd-bola')", timeout=3000)
        self.assertEqual(self.erros, [])

    def centro(self, sel):
        b = self.page.locator(sel).bounding_box()
        return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2

    def test_board_cartoes_mover_zoom_fio_e_volta(self):
        p = self.page
        p.click(".aba-board")
        p.wait_for_selector(".bd-card[data-aba='2'] .bd-fala")
        self.assertTrue(p.locator("#board").is_visible())
        self.assertTrue(p.locator("#lado").is_visible())   # a barra lateral continua no Board
        self.assertFalse(p.locator("#kb-doca").is_visible())   # uma KaniBall só (a do quadro)
        # o aberto tem o chat de verdade (caixa de texto), o outro a prévia
        self.assertTrue(p.locator(".bd-card[data-aba='1'] .entrada #texto").is_visible())
        self.assertIn("Em que posso ajudar", p.locator(".bd-card[data-aba='2'] .bd-previa").inner_text())
        # arrastar o cartão pelo cabeçalho
        p.evaluate("KC_BOARD.ajustar()")
        antes = p.evaluate("KC_BOARD.estado.cards['2'].x")
        x, y = self.centro(".bd-card[data-aba='2'] .bd-tit")
        p.mouse.move(x, y); p.mouse.down(); p.mouse.move(x + 120, y + 40, steps=5); p.mouse.up()
        self.assertGreater(p.evaluate("KC_BOARD.estado.cards['2'].x"), antes + 50)
        # zoom com a rodinha no fundo
        z0 = p.evaluate("KC_BOARD.estado.vista.z")
        p.mouse.move(600, 760); p.mouse.wheel(0, -300)
        self.assertGreater(p.evaluate("KC_BOARD.estado.vista.z"), z0)
        p.evaluate("KC_BOARD.ajustar()")
        # zoom nítido: CSS zoom (o texto é redesenhado), não transform scale (imagem esticada)
        self.assertEqual(p.evaluate("document.querySelector('.bd-mundo').style.transform"), "")
        # arrastar pelo meio (prévia) também move; clicar sem arrastar não
        antes = p.evaluate("KC_BOARD.estado.cards['2'].y")
        x, y = self.centro(".bd-card[data-aba='2'] .bd-previa")
        p.mouse.move(x, y); p.mouse.down(); p.mouse.move(x, y + 60, steps=5); p.mouse.up()
        self.assertGreater(p.evaluate("KC_BOARD.estado.cards['2'].y"), antes + 30)
        self.assertEqual(p.evaluate("KC_ABAS.ativa"), "1")
        # cada chat tem a cordinha pendurada com o pino; puxar o pino do 1 mostra a corda JÁ durante o puxão
        p.wait_for_selector(".bd-fios circle.pino[data-pino='1']")
        x, y = self.centro(".bd-fios circle.pino[data-pino='1']")
        x2, y2 = self.centro(".bd-card[data-aba='2'] .bd-previa")
        p.mouse.move(x, y); p.mouse.down(); p.mouse.move((x + x2) / 2, (y + y2) / 2, steps=6)
        p.wait_for_timeout(120)
        self.assertTrue(p.evaluate("(t => getComputedStyle(t).display !== 'none' && (t.getAttribute('d') || '').length > 20)(document.querySelector('.bd-fios .temp'))"))
        os.makedirs("D:/kanivete_testes/kanicode", exist_ok=True)
        p.screenshot(path="D:/kanivete_testes/kanicode/board_puxando.png")
        p.mouse.move(x2, y2, steps=4); p.mouse.up()
        p.click(".bd-menu button[data-v='comando']")
        p.wait_for_selector(".bd-fios g[data-fio='f1'] path.linha.comando")
        self.assertTrue(any(c["nome"] == "fio_criar" and c["args"] == ["1", "2", "comando"] for c in p.evaluate("chamadas")))
        p.evaluate("kcEv({t: 'fio_ativo', id: 'f1', on: true, aba: '1'})")
        p.wait_for_selector(".bd-fios path.linha.vivo")
        p.evaluate("KC_BOARD.ajustar()")
        p.wait_for_timeout(900)   # a corda assenta
        p.screenshot(path="D:/kanivete_testes/kanicode/board.png")
        # clicar na prévia abre aquele chat no cartão
        p.click(".bd-card[data-aba='2'] .bd-previa")
        p.wait_for_function("KC_ABAS.ativa === '2' && document.querySelector(\".bd-card[data-aba='2'] .entrada\")")
        # volta às abas: o chat volta para o lugar
        p.keyboard.press("Control+b")
        p.wait_for_function("!document.body.classList.contains('board')")
        self.assertTrue(p.locator(".corpo .meio #conversa").count() == 1)
        self.assertTrue(p.locator(".entrada #texto").is_visible())
        self.assertEqual(p.locator("#board .entrada").count(), 0)
        # nas abas normais: a que manda tem ⚡ e a que obedece ⇠
        self.assertIn("⚡", p.locator(".aba-chat[data-aba='1'] .aba-fio").inner_text())
        self.assertTrue(p.locator(".aba-chat[data-aba='2'] .aba-fio.obedece").is_visible())
        p.hover(".aba-chat[data-aba='1']")
        p.wait_for_selector(".aba-chat[data-aba='2'].fio-par")
        p.screenshot(path="D:/kanivete_testes/kanicode/abas_fio.png", clip={"x": 0, "y": 30, "width": 600, "height": 50})
        # de volta ao Board: a lâmina sobre a corda e o corte (as metades caem e somem; o fio é apagado)
        p.keyboard.press("Control+b")
        p.wait_for_selector(".bd-fios g[data-fio='f1'] path.toque")
        p.wait_for_timeout(600)
        pt = p.evaluate("""(() => { const el = document.querySelector(".bd-fios g[data-fio='f1'] path.toque"), L = el.getTotalLength(),
            q = el.getPointAtLength(L * 0.4), m = el.getScreenCTM(); return {x: q.x * m.a + m.e, y: q.y * m.d + m.f}; })()""")
        p.mouse.move(pt["x"], pt["y"])
        self.assertIn("data:image/svg", p.evaluate(f"getComputedStyle(document.elementFromPoint({pt['x']}, {pt['y']})).cursor"))
        p.mouse.down(); p.mouse.up()
        p.wait_for_selector(".bd-fios .cortes path.corte")
        p.screenshot(path="D:/kanivete_testes/kanicode/board_corte.png")
        self.assertTrue(any(c["nome"] == "fio_apagar" and c["args"] == ["f1"] for c in p.evaluate("chamadas")))
        self.assertEqual(p.locator(".bd-fios g[data-fio='f1']").count(), 0)
        p.wait_for_function("!document.querySelector('.bd-fios .cortes path')", timeout=4000)
        self.assertEqual(self.erros, [])


if __name__ == "__main__":
    unittest.main()
