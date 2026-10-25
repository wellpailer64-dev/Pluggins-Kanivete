"""Abas na janela (abas.js): faixa, aba de trás guardando eventos, troca devolvendo a conversa certa."""
import json
from pathlib import Path
import unittest

from playwright.sync_api import sync_playwright


class AbasUiTest(unittest.TestCase):
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
        self.page.add_init_script("""
          window.chamadas = [];
          window.ABAS_T = {ativa: '1', lista: [{id: '1', quem: 'pickle', nome: '', ocupada: false}]};
          window.HIST = {'1': [{t: 'eu', texto: 'pedido da aba um'}], '2': []};
          const copia = () => JSON.parse(JSON.stringify(ABAS_T));
          window.pywebview = {api: new Proxy({}, {get: (_, nome) => async (...args) => {
            chamadas.push({nome, args});
            const aba = ABAS_T.lista.find(a => a.id === ABAS_T.ativa);
            if (nome === 'info') return {pasta: 'D:/P', quem: aba.quem, fixa: true, ocupada: false, modo: 'auto', limite: null};
            if (nome === 'historico') return HIST[ABAS_T.ativa] || [];
            if (nome === 'contas_listar' || nome === 'conta_atualizar') return {lista: [], ativa: ''};
            if (nome === 'abas') return copia();
            if (nome === 'aba_nova') { const id = String(ABAS_T.lista.length + 1); ABAS_T.lista.push({id, quem: aba.quem, nome: '', ocupada: false}); ABAS_T.ativa = id; return copia(); }
            if (nome === 'aba_ativar') { ABAS_T.ativa = String(args[0]); return copia(); }
            if (nome === 'aba_fechar') { ABAS_T.lista = ABAS_T.lista.filter(a => a.id !== String(args[0])); if (ABAS_T.ativa === String(args[0])) ABAS_T.ativa = ABAS_T.lista[0].id; return copia(); }
            if (nome === 'quem') { aba.quem = args[0]; return true; }
            if (nome === 'voz') return {on: false};
            if (nome === 'rosto_quadros') return {fps: 10, quadros: [['................','................','................','................','................','....w#....w#....','....##....##....','....##....##....','................','...p........p...','......#..#......','.......##.......','................','................','................','................']]};
            if (nome === 'ajudante') return true;
            return true;
          }})};
        """)
        self.page.goto((Path(__file__).resolve().parents[1] / "ui/janela.html").as_uri())
        self.page.evaluate("dispatchEvent(new Event('pywebviewready'))")
        self.page.wait_for_selector("#abas-chat .aba-chat")

    def ev(self, ev):
        self.page.evaluate("ev => kcEv(ev)", ev)

    def texto_conversa(self):
        return self.page.locator("#conversa").inner_text()

    def test_aba_de_tras_guarda_e_devolve(self):
        p = self.page
        self.assertEqual(p.locator(".aba-chat").count(), 1)
        self.assertTrue(p.locator("#abas-chat + .corpo").is_visible())   # abas no topo da conversa
        self.assertEqual(p.locator(".aba-x").count(), 0)                     # a única aba não fecha
        # aba 1 começa uma tarefa (o Big Pickle trabalhando)
        p.fill("#texto", "faz um flyer de pizzaria")
        p.press("#texto", "Enter")
        p.wait_for_function("K.ocupada")
        self.assertIn("Faz um flyer", p.locator(".aba-chat.on .aba-nome").inner_text())   # a aba ganha o assunto do pedido
        self.assertEqual(p.locator(".aba-chat.on .aba-mod").inner_text(), "Big Pickle")      # e o modelo embaixo
        p.wait_for_selector(".aba-chat.on .aba-trab")                                        # trabalhando: barrinhas
        self.ev({"t": "ferr", "id": "a1", "nome": "rodar_comando", "entrada": {"comando": "py refs.py"}, "aba": "1"})
        # nova aba enquanto a 1 trabalha: livre, conversa vazia, dá para trocar de agente
        p.click(".aba-mais")
        p.wait_for_function("document.querySelectorAll('.aba-chat').length === 2 && KC_ABAS.ativa === '2'")
        self.assertFalse(p.evaluate("K.ocupada"))
        self.assertNotIn("flyer", self.texto_conversa())
        self.assertTrue(p.locator('.aba-chat[data-aba="1"] .aba-trab').count())
        p.evaluate("quemDefinir('claude')")
        self.assertEqual(p.evaluate("K.quem"), "claude")
        # eventos da aba 1 chegam com a 2 aberta: não aparecem aqui
        self.ev({"t": "ferr_fim", "id": "a1", "ok": True, "saida": "ok", "aba": "1"})
        self.ev({"t": "ajudante_resposta", "quem": "pickle", "texto": "Flyer montado no Photo", "ok": True, "tokens": 3, "aba": "1"})
        self.assertNotIn("Flyer montado", self.texto_conversa())
        self.assertTrue(p.locator('.aba-chat[data-aba="1"] .aba-ponto.pronto').count())   # verde: terminou
        # evento da aba aberta aparece normal
        self.ev({"t": "texto_novo", "aba": "2"}); self.ev({"t": "texto", "d": "oi da aba dois", "aba": "2"})
        self.assertIn("oi da aba dois", self.texto_conversa())
        # volta para a 1: a conversa dela, com o que chegou enquanto estava atrás
        p.click('.aba-chat[data-aba="1"] .aba-nome')
        p.wait_for_function("KC_ABAS.ativa === '1'")
        t = self.texto_conversa()
        self.assertIn("faz um flyer", t); self.assertIn("Flyer montado no Photo", t); self.assertNotIn("oi da aba dois", t)
        self.assertFalse(p.evaluate("K.ocupada"))
        self.assertEqual(p.evaluate("K.quem"), "pickle")
        self.assertEqual(p.locator('.aba-chat[data-aba="1"] .aba-ponto.pronto').count(), 0)   # visto: o aviso some
        # e a 2 de novo, intacta
        p.click('.aba-chat[data-aba="2"] .aba-nome')
        p.wait_for_function("KC_ABAS.ativa === '2'")
        self.assertIn("oi da aba dois", self.texto_conversa())
        self.assertEqual(p.evaluate("K.quem"), "claude")
        # fechar a 2
        p.click('.aba-chat[data-aba="2"] .aba-x')
        p.wait_for_function("KC_ABAS.ativa === '1' && document.querySelectorAll('.aba-chat').length === 1")
        self.assertIn("Flyer montado", self.texto_conversa())
        self.assertEqual(self.erros, [])

    def test_outro_aparelho_cria_renomeia_e_fecha(self):
        """o evento "abas" do servidor: o que o celular faz aparece no PC na hora (e vice-versa)"""
        p = self.page
        lista = lambda *ids: [{"id": i, "quem": "claude", "nome": "", "ocupada": False} for i in ids]
        # o celular criou a aba 2 (a do PC continua a 1)
        p.evaluate("ABAS_T.lista.push({id: '2', quem: 'claude', nome: '', ocupada: false})")
        self.ev({"t": "abas", "ativa": "1", "lista": lista("1", "2"), "aba": "1"})
        p.wait_for_function("document.querySelectorAll('.aba-chat').length === 2 && KC_ABAS.ativa === '1'")
        # mensagem enviada do celular na aba 2: o PC marca a aba como trabalhando, sem misturar na conversa
        self.ev({"t": "eco_eu", "texto": "pedido do celular", "de": "movel-x", "aba": "2"})
        self.ev({"t": "inicio", "aba": "2"})
        p.wait_for_selector('.aba-chat[data-aba="2"] .aba-trab')
        self.assertNotIn("pedido do celular", self.texto_conversa())
        # renomeada lá
        l = lista("1", "2"); l[1].update(nome="Do celular", manual=True)
        self.ev({"t": "abas", "ativa": "1", "lista": l, "aba": "1"})
        p.wait_for_function("document.querySelector('.aba-chat[data-aba=\"2\"] .aba-nome').textContent === 'Do celular'")
        # trocar para a 2 mostra o que veio do celular (aba nunca aberta aqui: vem do disco)
        p.evaluate("HIST['2'] = [{t: 'eu', texto: 'pedido do celular'}]")
        p.click('.aba-chat[data-aba="2"] .aba-nome')
        p.wait_for_function("KC_ABAS.ativa === '2'")
        self.assertIn("pedido do celular", self.texto_conversa())
        # o celular fechou a aba aberta aqui: o PC vai para a que o servidor escolheu
        p.evaluate("ABAS_T.lista = ABAS_T.lista.filter(a => a.id !== '2'); ABAS_T.ativa = '1'")
        self.ev({"t": "abas", "ativa": "1", "lista": lista("1"), "aba": "1"})
        p.wait_for_function("KC_ABAS.ativa === '1' && document.querySelectorAll('.aba-chat').length === 1")
        self.assertIn("pedido da aba um", self.texto_conversa())
        self.assertNotIn("pedido do celular", self.texto_conversa())
        self.assertEqual(self.erros, [])

    def test_evento_abas_durante_troca_espera(self):
        p = self.page
        p.click(".aba-mais")   # o próprio aba_nova manda o evento no meio da troca
        p.evaluate("KC_ABAS.mudando = true")
        self.ev({"t": "abas", "ativa": "2", "lista": [{"id": "1", "quem": "pickle", "nome": "", "ocupada": False},
                                                      {"id": "2", "quem": "pickle", "nome": "", "ocupada": False},
                                                      {"id": "3", "quem": "claude", "nome": "", "ocupada": False}], "aba": "1"})
        self.assertEqual(p.locator(".aba-chat").count(), 2)
        p.evaluate("KC_ABAS.mudando = false; KC_ABAS.reconectou()")
        p.wait_for_function("document.querySelectorAll('.aba-chat').length === 2")   # lista real do servidor vence
        self.assertEqual(self.erros, [])

    def test_atalhos_e_renomear(self):
        p = self.page
        p.keyboard.press("Control+n")
        p.wait_for_function("KC_ABAS.ativa === '2'")
        p.keyboard.press("Control+Tab")
        p.wait_for_function("KC_ABAS.ativa === '1'")
        p.dblclick('.aba-chat[data-aba="2"] .aba-nome')
        p.fill(".caixa input", "Pesquisa")
        p.click(".caixa .ok")
        p.wait_for_function("document.querySelector('.aba-chat[data-aba=\"2\"] .aba-nome').textContent === 'Pesquisa'")
        self.assertIn({"nome": "aba_renomear", "args": ["2", "Pesquisa"]}, p.evaluate("chamadas"))
        p.keyboard.press("Control+w")
        p.wait_for_function("document.querySelectorAll('.aba-chat').length === 1")
        self.assertEqual(self.erros, [])

    def test_tab_troca_e_deixa_texto_pronto(self):
        p = self.page
        p.keyboard.press("Control+n")
        p.wait_for_function("KC_ABAS.ativa === '2'")
        for tecla, aba in [("Tab", "1"), ("Tab", "2"), ("Shift+Tab", "1")]:
            p.keyboard.press(tecla)
            p.wait_for_function(f"KC_ABAS.ativa === '{aba}' && document.activeElement.id === 'texto'")
            p.keyboard.type("pronto")
            self.assertTrue(p.input_value("#texto").endswith("pronto"))
        self.assertEqual(self.erros, [])

    def test_modelo_pergunta_e_kaniball(self):
        p = self.page
        self.ev({"t": "inicio", "modelo": "claude-opus-5-5", "aba": "1"})
        p.evaluate("quemDefinir('claude')")
        p.wait_for_function("document.querySelector('.aba-chat.on .aba-mod').textContent === 'Opus 5.5'")
        # esperando a minha resposta: bolinha vermelha
        self.ev({"t": "permissao", "id": "x1", "nome": "Bash", "entrada": {"command": "ls"}, "aba": "1"})
        p.wait_for_selector(".aba-chat.on .aba-ponto.pergunta")
        # aba de trás com pergunta também fica vermelha
        p.click(".aba-mais")
        p.wait_for_function("KC_ABAS.ativa === '2'")
        self.ev({"t": "pergunta", "id": "q1", "perguntas": [{"pergunta": "Qual?", "opcoes": [{"label": "A"}]}], "aba": "1"})
        p.wait_for_selector('.aba-chat[data-aba="1"] .aba-ponto.pergunta')
        # KaniBall: entra, espia por cima da faixa e só o alto da cabeça fica para fora
        alvo = p.evaluate("kbDocaAlvo()")
        st = p.evaluate("(() => { const r = document.getElementById('status').getBoundingClientRect(); return {top: r.top, right: r.right}; })()")
        self.assertEqual(alvo["y"], st["top"] - 64)
        p.evaluate("kbDoca(true)")
        p.wait_for_timeout(900)
        r = p.evaluate("document.getElementById('kb-caixa').getBoundingClientRect().toJSON()")
        clip = p.evaluate("document.querySelector('.kb-clip').getBoundingClientRect().toJSON()")
        self.assertAlmostEqual(clip["bottom"], st["top"], delta=1)        # o recorte termina na faixa
        self.assertTrue(st["top"] - 50 < r["top"] < st["top"] - 20)        # afundou: 20–50 px para fora
        # Ctrl+Q recolhe e deixa a bolinha com o teclado
        p.keyboard.press("Control+q")
        p.wait_for_function("chamadas.some(c => c.nome === 'esconder' && c.args[0] === true)")
        p.evaluate("kbDoca(false); kbDoca('fora')")
        self.assertTrue(p.evaluate("document.getElementById('kb-doca').hidden"))
        self.assertEqual(self.erros, [])


if __name__ == "__main__":
    unittest.main()
