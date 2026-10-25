"""Atalho direito da KaniBall na janela real, com ponte simulada e sem voz real."""
import unittest
import test_layout as layout
import test_conexoes_ui as conexoes


@unittest.skipUnless(layout.sync_playwright, 'Playwright opcional não instalado')
class KaniBallFalaTest(unittest.TestCase):
    setUpClass = classmethod(conexoes.ConexoesUITest.setUpClass.__func__)

    def setUp(self):
        layout.LayoutTest.setUp(self)
        self.page.evaluate('''() => {
          window.falaTeste = false; window.falaGravacoes = [];
          const anterior = pywebview.api;
          pywebview.api = new Proxy(anterior, {get: (alvo, nome) => {
            if (nome === 'fala_sempre') return async on => {
              if (window.falhaFalaTeste) throw Error('simulada');
              if (on !== null) { falaTeste = on; falaGravacoes.push(on); }
              return falaTeste;
            };
            if (nome === 'rosto_quadros') return async () => ({fps:10, quadros:[]});
            return alvo[nome];
          }});
          falaSempreBotao(false); kbDoca(true);
        }''')
        self.page.wait_for_timeout(350)

    def tearDown(self):
        self.assertEqual(self.erros, [])

    def direito(self):
        # O alvo fica parcialmente atrás da faixa; contexto equivale ao clique na parte visível.
        self.page.locator('#kb-caixa').dispatch_event('contextmenu', {'button': 2})

    def test_um_clique_alterna_e_sincroniza_configuracoes(self):
        self.direito()
        self.page.wait_for_function("falaTeste === true")
        self.assertEqual(self.page.locator('.kb-aviso').inner_text(), 'Falar ativado')
        self.assertEqual(self.page.locator('#fala-sempre').get_attribute('aria-pressed'), 'true')
        caixa = self.page.locator('#kb-caixa').bounding_box()
        aviso = self.page.locator('.kb-aviso').bounding_box()
        self.assertLess(aviso['y'] + aviso['height'], caixa['y'])
        self.page.screenshot(path='D:/kanivete_testes/kaniball_fala.png')
        self.direito()
        self.page.wait_for_function("falaGravacoes.length === 2")
        self.assertEqual(self.page.locator('.kb-aviso').inner_text(), 'Falar desativado')
        self.assertEqual(self.page.locator('#fala-sempre').get_attribute('aria-pressed'), 'false')

    def test_duplo_clique_so_faz_cocegas(self):
        self.direito()
        self.page.wait_for_timeout(100)
        self.direito()
        self.page.wait_for_selector('.kb-fx', state='visible')
        self.assertIn('hihi', self.page.locator('.kb-clip').inner_text())
        self.page.wait_for_timeout(550)
        self.assertEqual(self.page.evaluate('falaGravacoes'), [])
        self.assertTrue(self.page.locator('.kb-aviso').is_hidden())

    def test_configuracoes_e_falha_da_ponte(self):
        self.page.locator('#fala-sempre').dispatch_event('click')
        self.page.wait_for_function('falaTeste === true')
        self.direito()
        self.page.wait_for_function('falaTeste === false')
        self.page.evaluate("() => { window.falhaFalaTeste = true; }")
        self.direito()
        self.page.wait_for_function("document.querySelector('.kb-aviso').textContent === 'Não deu para alterar a fala'")
        self.assertEqual(self.page.locator('#fala-sempre').get_attribute('aria-pressed'), 'false')


if __name__ == '__main__':
    unittest.main()
