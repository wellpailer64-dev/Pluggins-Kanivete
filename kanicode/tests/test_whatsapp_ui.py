"""WhatsApp sintético: painel, extração do DOM e captura de áudio sem conta real."""
from pathlib import Path
import unittest
import test_layout as layout

UI = Path(__file__).resolve().parents[1] / "ui"


@unittest.skipUnless(layout.sync_playwright, "Playwright opcional não instalado")
class WhatsAppUITest(unittest.TestCase):
    setUpClass = layout.LayoutTest.__dict__["setUpClass"]

    def setUp(self):
        layout.LayoutTest.setUp(self)
        self.page.set_viewport_size(dict(width=1100, height=1000))
        self.page.evaluate('''() => {
          window.waTeste = {ok:true, ligado:false, situacao:'Desligado', ignorados:[], palavras:[], audios:true, historico:[], pendentes:0};
          const anterior = pywebview.api;
          pywebview.api = new Proxy(anterior, {get(alvo,nome) {
            if (nome === 'whatsapp_estado') return async () => structuredClone(waTeste);
            if (nome === 'whatsapp_ligar') return async ligado => {waTeste.ligado=ligado; waTeste.situacao=ligado?'Monitorando':'Desligado'; return structuredClone(waTeste);};
            if (nome === 'whatsapp_configurar') return async dados => {Object.assign(waTeste,dados); return structuredClone(waTeste);};
            return alvo[nome];
          }});
        }''')

    def test_painel_ligar_filtros_edicao_e_troca_de_secao(self):
        p = self.page
        p.locator('#whatsapp-trilho').click()
        p.wait_for_selector('#whatsapp-painel', state='visible')
        p.wait_for_function("document.querySelector('#wa-audios').checked")
        p.locator('#wa-ligar').click()
        p.wait_for_function("document.querySelector('#wa-ligar').getAttribute('aria-pressed') === 'true'")
        p.locator('#wa-ignorados').fill('Grupo da família\nContato')
        p.locator('#wa-palavras').fill('propaganda')
        p.locator('#wa-audios').uncheck()
        p.wait_for_timeout(1600)
        self.assertEqual(p.locator('#wa-ignorados').input_value(), 'Grupo da família\nContato')
        p.locator('#wa-salvar').click()
        p.wait_for_function("waTeste.ignorados.length === 2 && !waTeste.audios")
        p.evaluate("waTeste.historico = [{conversa:'<img src=x onerror=alert(1)>', pessoa:'Ana', texto:'<script>erro</script>'}]")
        p.wait_for_selector('#wa-historico article')
        self.assertEqual(p.locator('#wa-historico img, #wa-historico script').count(), 0)
        p.locator('#wa-historico [data-ignorar]').click()
        p.wait_for_function("waTeste.ignorados.length === 3")
        pasta = Path('D:/kanivete_testes/whatsapp'); pasta.mkdir(parents=True, exist_ok=True)
        p.screenshot(path=str(pasta / 'painel.png'))
        p.locator('#saude-trilho').click()
        self.assertTrue(p.locator('#whatsapp-painel').is_hidden())
        self.assertEqual(p.locator('#whatsapp-trilho').get_attribute('aria-expanded'), 'false')
        self.assertTrue(p.evaluate('waTeste.ligado'))
        p.locator('#whatsapp-trilho').click()
        p.locator('#wa-ligar').click()
        p.wait_for_function('!waTeste.ligado')
        self.assertEqual(self.erros, [])

    def test_dom_so_recebidas_remetente_e_previa_nao_lida(self):
        p = self.page
        p.set_content('''<div id="pane-side"><div role="row"><span title="Grupo">Grupo</span>
          <span title="Bia: amanhã às 10h">Bia: amanhã às 10h</span><span aria-label="2 mensagens não lidas">2</span></div></div>
          <div id="main"><header><span title="Ana">Ana</span></header>
          <div class="message-in" data-id="false_a"><div data-pre-plain-text="[10:00, 27/10/2026] Ana: "><span class="selectable-text copyable-text">Olá</span></div></div>
          <div class="message-out" data-id="true_b"><span class="selectable-text copyable-text">Minha mensagem</span></div>
          <div class="message-in" data-id="false_c"><button aria-label="Reproduzir mensagem de voz"></button></div></div>''')
        d = p.evaluate((UI / 'whatsapp_observar.js').read_text(encoding='utf-8'))
        self.assertTrue(d['pronto'])
        self.assertEqual([m['id'] for m in d['mensagens']], ['false_a', 'false_c'])
        self.assertEqual(d['mensagens'][0]['pessoa'], 'Ana')
        self.assertEqual(d['mensagens'][0]['texto'], 'Olá')
        self.assertTrue(d['mensagens'][1]['audio'])
        self.assertIn('Bia:', d['previas'][0]['texto'])
        self.assertTrue(d['previas'][0]['nao_lidas'])

    def test_audio_capturado_restaura_player_e_nao_toca_outra_conversa(self):
        p = self.page
        p.set_content('''<div id="main"><header><span title="Ana">Ana</span></header>
          <div data-id="false_audio"><button aria-label="Reproduzir mensagem de voz">Play</button></div></div>''')
        p.evaluate('''() => {
          window.tocou = 0; window.pausou = 0;
          HTMLMediaElement.prototype.play = function () { tocou++; return Promise.resolve(); };
          window.original = HTMLMediaElement.prototype.play;
          document.querySelector('button').onclick = () => {
            window.mediaTeste = new Audio('data:audio/ogg;base64,T2dnUw==');
            mediaTeste.pause = () => {pausou++;}; mediaTeste.play();
          };
        }''')
        codigo = (UI / 'whatsapp_audio.js').read_text(encoding='utf-8')
        d = p.evaluate('(' + codigo + ')', dict(conversa='Ana', id='false_audio'))
        self.assertEqual(d['b64'], 'T2dnUw==')
        self.assertTrue(p.evaluate('HTMLMediaElement.prototype.play === original && !mediaTeste.muted'))
        self.assertEqual(p.evaluate('tocou'), 1)
        self.assertGreater(p.evaluate('pausou'), 0)
        d = p.evaluate('(' + codigo + ')', dict(conversa='Bia', id='false_audio'))
        self.assertIn('conversa mudou', d['erro'])
        self.assertEqual(p.evaluate('tocou'), 1)


if __name__ == '__main__':
    unittest.main()
