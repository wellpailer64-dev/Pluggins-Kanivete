"""Janela WebView2 invisível e motor simulado, executados só pelo teste de integração."""
import json
import os
from pathlib import Path
import sys
import time


def main():
    base = Path(sys.argv[1]).resolve()
    if not base.is_relative_to(Path('D:/kanivete_testes').resolve()):
        raise ValueError('teste fora da pasta permitida')
    os.environ['KANICODE_TESTE'] = '1'
    os.environ['KANICODE_DADOS_TESTE'] = str(base / 'dados')
    raiz = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(raiz))
    import kanicode
    import ajudantes
    import anexos_locais
    import webview
    dados = Path(kanicode.DADOS)
    dados.mkdir(parents=True, exist_ok=True)
    sid = '00000000-0000-0000-0000-000000000012'
    chave = os.path.normcase(os.path.realpath(raiz)) + '#aba12'
    estado = {'abas':[{'id':'12','quem':'codex'},{'id':'15','quem':'claude'}],
              'aba_ativa':'12','projeto':str(raiz),'codex_sessoes':{chave:sid}}
    (dados / 'estado.json').write_text(json.dumps(estado), encoding='utf-8')
    (dados / 'conversas_codex').mkdir(exist_ok=True)
    eventos = [{'t':'eu','texto':'Pedido anterior simulado'},
               {'t':'ajudante_resposta','quem':'codex','texto':'Histórico simulado recuperado','ok':True}]
    (dados / 'conversas_codex' / (sid+'.jsonl')).write_text(''.join(json.dumps(e)+'\n' for e in eventos), encoding='utf-8')
    chamadas = []
    def motor(texto, pasta, **kw):
        chamadas.append(texto)
        kw['ao_evento']({'t':'ajudante','quem':'codex','fase':'inicio'})
        return dict(ok=True,texto='Resposta simulada da ponte nativa.',tokens=0,ms=1,sessao=sid)
    ajudantes.codex = motor
    class Ponte(kanicode.App):
        _falhar = False
        def _ajudante_iniciar(self, *args, **kw):
            if self._falhar:
                raise RuntimeError('falha controlada na ponte nativa')
            return super()._ajudante_iniciar(*args, **kw)
        def contas_listar(self): return {'lista':[], 'ativa':'principal'}
        def conta_atualizar(self): return self.contas_listar()
        def codex_limites(self, forcar=False): return {'ok':False}
        def codex_identidade(self): return {'ok':False}
        def sons_acoes(self, on=None): return False
        def voz(self, on=None): return {'on':False}
        def compromissos(self): return []
        def preparar(self): return True
    app = Ponte(); app._aberta = True
    app._janela = webview.create_window('Teste isolado da ponte', str(raiz/'ui/janela.html'), js_api=app,
                                       hidden=True, width=1000, height=800)
    app._janela.events.loaded += lambda: anexos_locais.ligar(app._janela)
    resultado = {}
    def esperar(js):
        limite = time.monotonic()+12
        while time.monotonic()<limite:
            if app._janela.evaluate_js(js): return
            time.sleep(.1)
        raise TimeoutError('condição não observada na ponte nativa')
    def conferir():
        try:
            app._janela.events.loaded.wait(15)
            esperar("document.querySelector('#conversa').textContent.includes('Histórico simulado recuperado')")
            resultado['historico_recuperado'] = True
            app._janela.evaluate_js("texto.value='Pedido novo simulado';ajustar();document.getElementById('enviar').click()")
            esperar("!K.ocupada && document.querySelector('#conversa').textContent.includes('Resposta simulada da ponte nativa.')")
            resultado['motor_chamado'] = len(chamadas)==1
            app._falhar = True
            app._janela.evaluate_js("texto.value='Pedido preservado';ajustar();document.getElementById('enviar').click()")
            esperar("!K.ocupada && document.querySelector('#conversa').textContent.includes('falha controlada na ponte nativa')")
            resultado['pedido_preservado'] = app._janela.evaluate_js("texto.value === 'Pedido preservado'")
            resultado['sem_reenvio_automatico'] = len(chamadas)==1
            resultado['diagnostico_gravado'] = (dados/'janela_diagnostico.jsonl').exists()
        except Exception as e:
            resultado['erro'] = str(e)
        finally:
            (base/'resultado.json').write_text(json.dumps(resultado,ensure_ascii=False),encoding='utf-8')
            app._janela.destroy()
    webview.start(conferir,gui='edgechromium',storage_path=str(dados/'webview'))


if __name__ == '__main__':
    main()

