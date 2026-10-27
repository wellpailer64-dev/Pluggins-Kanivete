"""Colab e mensagens integrais no Board, em Chromium isolado e com ponte simulada."""
from test_board_ui import BoardUiTest
import unittest


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(ColabUiTest(n) for n in (
        "test_codex_logs_e_texto_completo_sem_abrir_aba", "test_colab_criar_e_atualizar_sem_trocar_chat"))


class ColabUiTest(BoardUiTest):
    def test_codex_logs_e_texto_completo_sem_abrir_aba(self):
        p = self.page
        p.click('.aba-board')
        p.wait_for_selector('.bd-card[data-aba="2"] .bd-fala')
        p.evaluate("""kcEv({t:'ajudante',quem:'codex',fase:'inicio',aba:'2'});
          kcEv({t:'codex_progresso',id:'x',texto:'A'.repeat(1600)+'FIM_INTEGRAL',aba:'2'});
          kcEv({t:'ajudante',quem:'codex',fase:'passo',texto:'executando teste',entrada:{command:'py -3.13 teste.py'},aba:'2'});
          kcEv({t:'ajudante',quem:'codex',fase:'passo',operacao:'fim',saida:'TESTE_PASSOU',ok:true,aba:'2'});""")
        p.wait_for_function("document.querySelector('.bd-card[data-aba=\"2\"] .bd-aovivo')?.textContent.includes('FIM_INTEGRAL')")
        p.wait_for_function("document.querySelector('.bd-card[data-aba=\"2\"] .bd-aovivo')?.textContent.includes('TESTE_PASSOU')")
        self.assertEqual(p.evaluate('KC_ABAS.ativa'), '1')
        self.assertIn('py -3.13 teste.py', p.locator('.bd-card[data-aba="2"] .bd-aovivo').inner_text())
        p.screenshot(path='D:/kanivete_testes/colab/board_logs.png')
        self.assertEqual(self.erros, [])

    def test_colab_criar_e_atualizar_sem_trocar_chat(self):
        p = self.page
        p.evaluate("""window.SCOLAB = {membros:['1','2'],coordenador:'1',objetivo:'Site de teste',fase:'planejamento',revisao:0,aprovacoes:[],tarefas:[],contrato:'',diario:[]};
          const anterior = pywebview.api;
          pywebview.api = new Proxy({}, {get:(_,nome) => async (...args) => {
            if(nome === 'colab_criar') { FIOS=[{id:'c1',de:'1',para:'2',modo:'colab'}]; kcEv({t:'fios',lista:FIOS}); return FIOS[0]; }
            if(nome === 'colab_consultar') return SCOLAB;
            if(nome === 'colab_planejar') { chamadas.push({nome,args}); return true; }
            return anterior[nome](...args);
          }}); void 0;""")
        p.click('.aba-board'); p.click('[data-acao="colab"]')
        p.fill('.colab-objetivo', 'Site de teste')
        p.click('.colab-criar')
        p.wait_for_function("chamadas.some(c=>c.nome==='colab_planejar')")
        p.evaluate("SCOLAB.fase='execucao'; SCOLAB.revisao=1; SCOLAB.aprovacoes=['1','2']; SCOLAB.diario=[{aba:'2',texto:'Interface pronta para API'}]; kcEv({t:'colab',id:'c1',estado:SCOLAB})")
        p.wait_for_function("document.querySelector('.colab-estado').textContent.includes('Interface pronta para API')")
        self.assertIn('Executando em paralelo', p.locator('.colab-estado').inner_text())
        self.assertEqual(p.evaluate('KC_ABAS.ativa'), '1')
        p.screenshot(path='D:/kanivete_testes/colab/colab_plano.png')
        self.assertEqual(self.erros, [])
