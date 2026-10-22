"""Seletor e conversa reais em página isolada, com API simulada."""
from pathlib import Path
import unittest

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


@unittest.skipUnless(sync_playwright, 'Playwright opcional não instalado')
class BigPickleInterfaceTest(unittest.TestCase):
    def test_seletor_envio_parar_historico_e_limites(self):
        with sync_playwright() as p:
            if not Path(p.chromium.executable_path).exists():
                self.skipTest('Chromium do Playwright não instalado')
            navegador = p.chromium.launch(headless=True)

            pagina = navegador.new_page(viewport={'width': 550, 'height': 760})
            pagina.set_default_timeout(5000)
            erros = []
            pagina.on('pageerror', lambda e: erros.append(str(e)))
            pagina.add_init_script('''
              window.chamadas = []; window.agenteTeste = 'pickle';
              window.pywebview = {api: new Proxy({}, {get: (_, nome) => async (...args) => {
                chamadas.push({nome, args});
                if (nome === 'info') return {pasta:'D:/teste', quem:agenteTeste, fixa:true, ocupada:false, modo:'auto'};
                if (nome === 'quem') { agenteTeste = args[0]; return true; }
                if (nome === 'historico') return agenteTeste === 'pickle' ? [
                  {t:'eu', texto:'Oi BP'}, {t:'ajudante_resposta', quem:'pickle', texto:'Resposta anterior BP', ok:true}
                ] : [];
                if (nome === 'contas_listar' || nome === 'conta_atualizar') return {lista:[], ativa:'principal'};
                if (nome === 'voz') return {on:false};
                return true;
              }})};
            ''')
            pagina.goto((Path(__file__).resolve().parents[1] / 'ui/janela.html').as_uri())
            pagina.evaluate("dispatchEvent(new Event('pywebviewready'))")
            pagina.wait_for_function("document.querySelector('#conversa').textContent.includes('Resposta anterior BP')")
            self.assertIn('Big Pickle', pagina.locator('#quem-bt').inner_text())
            self.assertTrue(pagina.locator('#kani-recursos').is_hidden())
            self.assertTrue(pagina.locator('#c5').is_hidden())
            self.assertFalse(pagina.evaluate("chamadas.some(c => c.nome === 'preparar' || c.nome === 'gpu_info')"))
            pagina.fill('#texto', 'Consulte D')
            pagina.click('#enviar')
            pagina.wait_for_function("chamadas.some(c => c.nome === 'ajudante')")
            self.assertEqual(pagina.evaluate("chamadas.find(c => c.nome === 'ajudante').args"), ['pickle', 'Consulte D'])
            pagina.click('#enviar')
            pagina.wait_for_function("chamadas.some(c => c.nome === 'parar')")
            pagina.evaluate("kcEv({t:'ajudante_resposta',quem:'pickle',texto:'Parei.',ok:false,tokens:5})")
            pagina.fill('#texto', '/comando')
            pagina.click('#enviar')
            self.assertFalse(pagina.evaluate("chamadas.some(c => c.nome === 'enviar')"))
            for comando in ('/clear', '/nova', '/new'):
                pagina.fill('#texto', comando)
                pagina.click('#enviar')
                pagina.wait_for_function("comando => chamadas.some(c => c.nome === 'enviar' && c.args[0] === comando)", arg=comando)
                pagina.evaluate("kcEv({t:'local',acao:'recarregar'})")
                pagina.wait_for_function('!K.ocupada')
            self.assertEqual(pagina.evaluate("chamadas.filter(c => c.nome === 'ajudante').length"), 1)
            pagina.fill('#texto', '')
            pagina.click('#quem-bt')
            pagina.click('[data-q="kani"]')
            pagina.wait_for_function("agenteTeste === 'kani'")
            pagina.click('#quem-bt')
            pagina.click('[data-q="pickle"]')
            pagina.wait_for_function("document.querySelector('#conversa').textContent.includes('Resposta anterior BP')")
            pagina.set_viewport_size({'width': 360, 'height': 700})
            self.assertLessEqual(pagina.evaluate('document.documentElement.scrollWidth'), 360)
            pagina.screenshot(path=r'D:\kanivete_testes\bigpickle_seletor.png')
            self.assertEqual(erros, [])
            navegador.close()


if __name__ == '__main__':
    unittest.main()
