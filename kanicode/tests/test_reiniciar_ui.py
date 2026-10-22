"""Botão no layout real com ponte simulada e navegador isolado."""
import unittest
import test_layout as layout
from test_conexoes_ui import ConexoesUITest


@unittest.skipUnless(layout.sync_playwright, 'Playwright opcional não instalado')
class ReiniciarUITest(unittest.TestCase):
    setUpClass = classmethod(ConexoesUITest.setUpClass.__func__)
    setUp = layout.LayoutTest.setUp

    def tearDown(self):
        self.assertEqual(self.erros, [])

    def test_posicao_e_agendamento_sem_duplo_pedido(self):
        p = self.page
        p.evaluate('''() => { const anterior=pywebview.api;
          pywebview.api=new Proxy(anterior,{get:(alvo,nome)=>nome==='reiniciar' ? async()=>{
            chamadas.push({nome,args:[]}); return 'depois:reiniciar';
          } : alvo[nome]}); }''')
        self.assertEqual(p.locator('#reiniciar').evaluate('(e)=>e.nextElementSibling.id'), 'recolher')
        p.click('#reiniciar')
        self.assertTrue(p.locator('#reiniciar').is_disabled())
        self.assertIn('Reinício agendado', p.locator('#reiniciar').get_attribute('title'))
        self.assertEqual(p.evaluate("chamadas.filter(c=>c.nome==='reiniciar').length"), 1)
        self.assertTrue(p.get_by_text('O KaniCode vai reiniciar quando as tarefas em andamento terminarem.', exact=True).is_visible())
        p.screenshot(path=r'D:\kanivete_testes\reiniciar_topo.png')

    def test_falha_da_ponte_permite_tentar_novamente(self):
        p = self.page
        p.evaluate('''() => { const anterior=pywebview.api;
          pywebview.api=new Proxy(anterior,{get:(alvo,nome)=>nome==='reiniciar' ? async()=>{
            throw new Error('Falha de teste');
          } : alvo[nome]}); }''')
        p.click('#reiniciar')
        self.assertFalse(p.locator('#reiniciar').is_disabled())
        self.assertTrue(p.get_by_text('Não foi possível reiniciar o KaniCode: Falha de teste', exact=True).is_visible())


if __name__ == '__main__':
    unittest.main()
