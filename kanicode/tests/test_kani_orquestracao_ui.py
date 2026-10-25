"""Cartão de aprovação/retomada em Chromium isolado com ponte simulada."""
from pathlib import Path
import unittest
import test_layout as layout
import test_conexoes_ui as conexoes


@unittest.skipUnless(layout.sync_playwright,'Playwright opcional não instalado')
class OrquestracaoUITest(unittest.TestCase):
    setUpClass=classmethod(conexoes.ConexoesUITest.setUpClass.__func__)

    def setUp(self):
        self.page=self.browser.new_page(); self.addCleanup(self.page.close)
        self.page.set_content('<div id="conversa"></div>')
        self.page.evaluate('''() => {
            window.chamadas=[]; window.pywebview={api:{kani_execucao:async (...args)=>{chamadas.push(args);return true;}}};
        }''')
        self.page.add_script_tag(path=str(Path(__file__).resolve().parents[1]/'ui/kani_execucoes.js'))

    def test_aprovacao_mostra_argumentos_e_exige_clique(self):
        self.page.evaluate('''() => KaniExecucoes.receber({execucao:'a'.repeat(32),status:'aguardando_aprovacao',
            aprovacao:{chave:'hash-concreto',acao:'gmail_rascunho',args:{para:'pedro@example.test',texto:'<img src=x onerror="window.falha=1">'}}},document.querySelector('#conversa'))''')
        self.assertIn('pedro@example.test',self.page.locator('pre').inner_text())
        self.assertEqual(self.page.locator('img').count(),0)
        self.assertEqual(self.page.evaluate('chamadas.length'),0)
        self.page.get_by_role('button',name='Aprovar esta ação').click()
        self.page.wait_for_function('chamadas.length===1')
        self.assertEqual(self.page.evaluate('chamadas[0].slice(0,4)'),['aprovar','a'*32,'hash-concreto',True])

    def test_retomada_com_informacao_e_estado_incerto_sem_botao(self):
        self.page.evaluate('''() => KaniExecucoes.receber({execucao:'b'.repeat(32),status:'aguardando_informacao',pergunta:'Qual Pedro?'},document.querySelector('#conversa'))''')
        self.page.locator('textarea').fill('pedro@example.test'); self.page.get_by_role('button',name='Retomar').click()
        self.page.wait_for_function('chamadas.length===1')
        self.assertEqual(self.page.evaluate('chamadas[0][4]'),'pedro@example.test')
        self.page.evaluate('''() => KaniExecucoes.receber({execucao:'b'.repeat(32),status:'incerta'},document.querySelector('#conversa'))''')
        self.assertEqual(self.page.locator('button').count(),0)


if __name__=='__main__': unittest.main()

