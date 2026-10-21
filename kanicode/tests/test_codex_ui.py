"""Página real em navegador headless, com API simulada; não toca no app aberto."""
from pathlib import Path
import unittest

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


@unittest.skipUnless(sync_playwright, "Playwright opcional não instalado")
class InterfaceCodexTest(unittest.TestCase):
    def test_fluxo_codex_e_transicao_para_claude(self):
        with sync_playwright() as p:
            if not Path(p.chromium.executable_path).exists():
                self.skipTest("Chromium do Playwright não instalado")
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1000, "height": 800})
            page.set_default_timeout(5000)
            erros = []
            page.on("pageerror", lambda e: erros.append(str(e)))
            page.add_init_script("""
              window.chamadas = [];
              window.agenteTeste = 'codex';
              window.falharTeste = false;
              window.pywebview = {api: new Proxy({}, {get: (_, nome) => async (...args) => {
                chamadas.push(nome);
                if (nome === 'info') return {pasta: 'D:/teste', quem: agenteTeste, fixa: true, ocupada: false,
                  modo: 'auto', cota_codex: {h5:0.1, sem:0.2, h5_zera:9999999999, sem_zera:9999999999}};
                if (nome === 'quem') { agenteTeste = args[0]; return true; }
                if (nome === 'historico') return agenteTeste === 'codex' ? [
                  {t:'eu', texto:'Pedido anterior'}, {t:'ajudante_resposta', quem:'codex', texto:'Resposta anterior', ok:true}
                ] : [];
                if (nome === 'contas_listar' || nome === 'conta_atualizar') return {lista:[], ativa:'principal'};
                if (nome === 'voz') return {on:false};
                if (nome === 'ajudante' && falharTeste) throw new Error('motor indisponível');
                return true;
              }})};
            """)
            page.goto((Path(__file__).resolve().parents[1]/"ui/janela.html").as_uri())
            page.evaluate("dispatchEvent(new Event('pywebviewready'))")
            page.wait_for_function("document.querySelector('#conversa').textContent.includes('Resposta anterior')")
            self.assertNotIn("preparar", page.evaluate("chamadas"))
            page.fill("#texto", "Teste simples")
            page.click("#enviar")
            page.wait_for_function("chamadas.includes('ajudante')")
            page.evaluate("kcEv({t:'ajudante', quem:'codex', fase:'inicio', texto:'começando'})")
            page.evaluate("kcEv({t:'ajudante', quem:'codex', fase:'passo', texto:'executando teste'})")
            self.assertIn("executando teste", page.locator("#faz").inner_text())
            page.click("#enviar")  # enquanto ocupado, o mesmo botão chama Parar
            page.wait_for_function("chamadas.includes('parar')")
            page.evaluate("""() => {
              const uso = {novos:100, cache:900, saida:20, raciocinio:5};
              kcEv({t:'ajudante', quem:'codex', fase:'fim', ok:true, tokens:120, uso});
              kcEv({t:'ajudante_resposta', quem:'codex', ok:true, texto:'Pronto', tokens:120, uso});
            }""")
            self.assertIn("20 tokens", page.locator("#num").inner_text())
            page.click("#c5")
            painel = page.locator("#uso").inner_text()
            self.assertIn("Codex · entrada nova", painel)
            self.assertIn("Codex · entrada em cache", painel)
            self.assertRegex(painel, r"Tokens escritos \(Claude\)\s+0")
            page.click("#c5")
            page.evaluate("falharTeste = true")
            page.fill("#texto", "Falhe para testar a interface")
            page.click("#enviar")
            page.wait_for_function("document.querySelector('#conversa').textContent.includes('motor indisponível')")
            self.assertNotIn("Parar", page.locator("#enviar").inner_text())
            page.click("#quem-bt")
            page.click('[data-q="claude"]')
            page.wait_for_function("chamadas.includes('preparar')")
            self.assertEqual(erros, [])
            browser.close()


if __name__ == "__main__":
    unittest.main()
