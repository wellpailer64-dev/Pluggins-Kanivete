"""Integração real: Chrome por pipe privado e perfil descartável no D, sem conta real."""
import base64
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import kanibrowser as kb
import extensoes
import scripts_browser
import kb as cli
import ponte

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')
VIDEO = b''
PAGINA = '''<!doctype html><html lang="pt-BR"><title>Teste KaniCode</title><body>
<h1>Página de teste local</h1><label for="nome">Nome</label><input id="nome">
<input id="segredo" type="password" value="NAO_VAZAR"><textarea id="nota"></textarea>
<a href="/destino">Destino local</a><a href="/destino">Duplicado</a>
<img src="/imagem.png" alt="Imagem da fonte"><video src="/video.mp4"></video>
<input type="checkbox" id="aceite"><input type="radio" name="tamanho" id="pequeno">
<select id="idioma"><option value="pt">Português</option><option value="en">English</option></select>
<main><nav>MENU_IGNORAR</nav><article>CONTEUDO_PRINCIPAL</article></main>
<button id="atrasado" onclick="setTimeout(()=>document.querySelector('#status').textContent='Concluído',150)">Executar</button>
<span id="status"></span><input id="tecla" onkeydown="if(event.key==='Enter')document.querySelector('#status').textContent='Enter recebido'">
<script>window.eventos=[]; document.querySelector('#nome').addEventListener('input', e=>eventos.push(e.target.value));</script>
</body></html>'''.encode('utf-8')


class Servidor(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/redirecionar':
            self.send_response(302)
            self.send_header('Location', '/api')
            self.end_headers()
            return
        if self.path == '/imagem.png':
            dados, tipo = PNG, 'image/png'
        elif self.path == '/video.mp4':
            dados, tipo = VIDEO, 'video/mp4'
        elif self.path == '/api':
            dados, tipo = b'{"origem":"local","itens":[1,2,3]}', 'application/json'
        else:
            dados, tipo = PAGINA, 'text/html; charset=utf-8'
        self.send_response(200)
        self.send_header('Content-Type', tipo)
        self.send_header('Content-Length', str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def log_message(self, *args):
        pass


class ExtensaoReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global VIDEO
        raiz = Path('D:/kanivete_testes/extensao_browser')
        raiz.mkdir(parents=True, exist_ok=True)
        cls.pasta = Path(tempfile.mkdtemp(prefix='sessao_', dir=raiz))
        for var, nome in [('APPDATA', 'appdata'), ('LOCALAPPDATA', 'localappdata'), ('TEMP', 'tmp'), ('TMP', 'tmp')]:
            destino = cls.pasta / nome
            destino.mkdir(exist_ok=True)
            os.environ[var] = str(destino)
        video = cls.pasta / 'fonte.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=16x16:r=1',
                        '-t', '1', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(video)], check=True, timeout=20)
        VIDEO = video.read_bytes()
        cls.servidor = ThreadingHTTPServer(('127.0.0.1', 0), Servidor)
        threading.Thread(target=cls.servidor.serve_forever, daemon=True).start()
        cls.url = f'http://127.0.0.1:{cls.servidor.server_port}/'
        kb.RAIZ = str(cls.pasta)
        kb.PERFIL = str(cls.pasta / 'perfil')
        kb.SAIDA = str(cls.pasta / 'downloads')
        try:
            kb.abrir(cls.url)
            cls.aba = kb.aba_kani()
            kb.ir(cls.url + '?kani=1', cls.aba)
            for _ in range(60):
                if kb.js('document.readyState', cls.aba) == 'complete':
                    break
                time.sleep(.1)
        except Exception:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        # Só encerra o Chrome criado por este processo, com perfil de teste.
        kb.fechar_navegador()
        cls.servidor.shutdown()
        cls.servidor.server_close()

    def test_01_carregamento_real(self):
        estado = extensoes.estado()
        print('ESTADO_REAL', json.dumps(estado, ensure_ascii=False), flush=True)
        self.assertTrue(estado['carregada'], estado)
        self.assertTrue(kb._cmd('Extensions.getExtensions')['extensions'])

    def test_02_leitura_e_mapa_sem_senha(self):
        self.assertIn('Página de teste local', extensoes.executar('ler')['texto'])
        mapa = extensoes.executar('mapa')
        self.assertTrue(any(e['seletor'] == '#nome' and e['nome'] == 'Nome' for e in mapa['elementos']))
        self.assertNotIn('NAO_VAZAR', json.dumps(mapa))

    def test_03_digitacao_eventos_e_recusa_senha(self):
        self.assertTrue(extensoes.executar('digitar', {'seletor': '#nome', 'texto': 'Olá, Pailer!'})['digitado'])
        self.assertEqual(kb.js('document.querySelector("#nome").value', self.aba), 'Olá, Pailer!')
        self.assertIn('Olá, Pailer!', kb.js('eventos', self.aba))
        with self.assertRaisesRegex(kb.ErroKB, 'Tipo de campo não permitido'):
            extensoes.executar('digitar', {'seletor': '#segredo', 'texto': 'teste'})
        with self.assertRaisesRegex(kb.ErroKB, 'exatamente um campo'):
            extensoes.executar('digitar', {'seletor': 'input', 'texto': 'teste'})

    def test_04_midias_e_download_confirmado(self):
        midias = extensoes.executar('midias')
        self.assertEqual(midias['imagens'][0]['url'], self.url + 'imagem.png')
        self.assertEqual(midias['videos'][0]['url'], self.url + 'video.mp4')
        for recurso, esperado in [('imagem.png', PNG), ('video.mp4', VIDEO)]:
            r = extensoes.executar('baixar', {'url': self.url + recurso})
            for _ in range(60):
                estado = extensoes.executar('download', {'id': r['id']})
                if estado['estado'] in ('complete', 'interrupted'):
                    break
                time.sleep(.1)
            self.assertEqual(estado['estado'], 'complete', estado)
            caminho = Path(estado['arquivo']).resolve()
            self.assertTrue(caminho.is_relative_to(self.pasta.resolve()), str(caminho))
            self.assertEqual(caminho.read_bytes(), esperado)
        with self.assertRaisesRegex(kb.ErroKB, 'HTTP/HTTPS direta'):
            extensoes.executar('baixar', {'url': 'file:///C:/Windows/win.ini'})

    def test_05_biblioteca_real_e_limites(self):
        self.assertEqual(scripts_browser.comando()[0]['nome'], 'extrair_links')
        r = scripts_browser.comando('rodar', 'extrair_links')
        self.assertEqual(len(r['resultado']), 1)
        self.assertEqual(r['resultado'][0]['url'], self.url + 'destino')
        with self.assertRaisesRegex(ValueError, 'inválido'):
            scripts_browser.comando('rodar', '../motor')
        biblioteca = self.pasta / 'scripts'
        biblioteca.mkdir(exist_ok=True)
        (biblioteca / 'restrito.json').write_text(json.dumps({'origens': ['https://example.com'], 'altera_pagina': False}), encoding='utf-8')
        (biblioteca / 'restrito.js').write_text('return 1;', encoding='utf-8')
        anterior = scripts_browser.PASTA
        scripts_browser.PASTA = biblioteca
        try:
            with self.assertRaisesRegex(ValueError, 'Origem não autorizada'):
                scripts_browser.comando('rodar', 'restrito')
            (biblioteca / 'restrito.json').write_text(json.dumps({'origens': ['http://*'], 'altera_pagina': True}), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'permitir_alteracao'):
                scripts_browser.comando('rodar', 'restrito')
        finally:
            scripts_browser.PASTA = anterior

    def test_06_url_duplicada_recusada(self):
        extra = kb.nova(self.url + '?kani=1')['id']
        try:
            with self.assertRaisesRegex(kb.ErroKB, 'única aba'):
                extensoes.executar('ler')
        finally:
            kb.fechar(extra)
            for _ in range(30):
                tabs = kb._cmd('Target.getTargets', {'filter': [{'type': 'tab', 'exclude': False}]})['targetInfos']
                if sum(t.get('url') == self.url + '?kani=1' for t in tabs) == 1:
                    break
                time.sleep(.1)

    def test_07_motor_acorda_apos_suspensao(self):
        kb._cdp(self.aba, 'ServiceWorker.enable')
        kb._cdp(self.aba, 'ServiceWorker.stopAllWorkers')
        motor = f'chrome-extension://{kb._c["extensao_id"]}/motor.js'
        for _ in range(30):
            if not any(x.get('url') == motor for x in kb._cmd('Target.getTargets')['targetInfos']):
                break
            time.sleep(.1)
        self.assertFalse(any(x.get('url') == motor for x in kb._cmd('Target.getTargets')['targetInfos']))
        self.assertIn('Página de teste local', extensoes.executar('ler')['texto'])

    def test_08_reabertura_do_perfil(self):
        anterior = kb._c['extensao_id']
        kb.fechar_navegador()
        proc = kb._c['proc']
        proc.wait(timeout=15)
        kb.abrir(self.url)
        self.assertEqual(kb._c.get('extensao_id'), anterior, extensoes.estado())
        self.__class__.aba = kb.aba_kani()
        kb.ir(self.url + '?reinicio=1', self.aba)
        for _ in range(60):
            if kb.js('document.readyState', self.aba) == 'complete':
                break
            time.sleep(.1)
        self.assertIn('Página de teste local', extensoes.executar('ler')['texto'])

    def test_09_api_local_e_limites(self):
        r = extensoes.executar('api', {'url': '/api'})
        self.assertEqual(r['status'], 200)
        self.assertEqual(r['json']['itens'], [1, 2, 3])
        self.assertTrue(extensoes.executar('api', {'url': '/api', 'limite': 5})['truncado'])
        with self.assertRaisesRegex(kb.ErroKB, 'redirecionamento'):
            extensoes.executar('api', {'url': '/redirecionar'})
        with self.assertRaisesRegex(kb.ErroKB, 'mesma origem'):
            extensoes.executar('api', {'url': 'https://example.com/'})
        with self.assertRaisesRegex(kb.ErroKB, 'GET ou HEAD'):
            extensoes.executar('api', {'url': '/api', 'metodo': 'POST'})

    def test_10_cli_e_api_da_ponte(self):
        def chamar(funcao, **dados):
            self.assertIn(funcao, ponte.API_KANIVETE)
            return getattr(ponte, funcao)(**dados)
        entrada = self.pasta / 'entrada.json'
        entrada.write_text(json.dumps({'url': '/api'}), encoding='utf-8-sig')
        a = SimpleNamespace(cmd='extensao', arg='api', aba=None, dados='@' + str(entrada), nome=None, permitir_alteracao=False)
        saida = io.StringIO()
        with redirect_stdout(saida):
            self.assertEqual(cli._rodar(a, chamar), 0)
        self.assertEqual(json.loads(saida.getvalue())['json']['origem'], 'local')
        a.cmd, a.arg, a.dados = 'scripts', 'listar', '{}'
        saida = io.StringIO()
        with redirect_stdout(saida):
            self.assertEqual(cli._rodar(a, chamar), 0)
        self.assertEqual(json.loads(saida.getvalue())[0]['nome'], 'extrair_links')
        a.aba = self.aba
        with redirect_stdout(io.StringIO()):
            self.assertEqual(cli._rodar(a, chamar), 1)

    def test_11_descoberta_no_estado(self):
        r = ponte.estado()
        self.assertTrue(r['extensao']['carregada'])
        self.assertIn('scripts listar', r['extensao']['comandos'])
        a = SimpleNamespace(cmd='estado', arg=None)
        saida = io.StringIO()
        with redirect_stdout(saida):
            self.assertEqual(cli._rodar(a, lambda f: ponte.estado()), 0)
        self.assertIn('Extensão Olhos: carregada', saida.getvalue())
        self.assertIn('extensao estado|ler|mapa', saida.getvalue())
        saida = io.StringIO()
        with redirect_stdout(saida):
            self.assertEqual(cli._rodar(a, lambda f: {'aberto': True, 'abas': []}), 0)
        self.assertIn('sessão sem descoberta', saida.getvalue())

    def test_12_filtros_e_panorama(self):
        r = extensoes.comando('mapa', {'tipo': 'campos', 'seletor': '#nome'})
        self.assertEqual(r['encontrados'], 1)
        self.assertEqual(r['elementos'][0]['seletor'], '#nome')
        self.assertGreater(r['total'], r['encontrados'])
        r = extensoes.comando('mapa', {'tipo': 'links', 'texto': 'DESTÍNO', 'maximo': 1})
        self.assertEqual(r['encontrados'], 1)
        r = extensoes.comando('mapa', {'maximo': 1})
        self.assertTrue(r['truncado'])
        self.assertEqual(len(r['elementos']), 1)
        self.assertEqual(extensoes.comando('mapa', {'texto': 'inexistente_xyz'})['encontrados'], 0)
        with self.assertRaisesRegex(kb.ErroKB, 'Tipo deve'):
            extensoes.comando('mapa', {'tipo': 'invalido'})
        r = extensoes.comando('panorama', {'tipo': 'links', 'maximo': 1, 'limite': 20})
        self.assertEqual(len(r['texto']), 20)
        self.assertEqual(len(r['mapa']['elementos']), 1)
        self.assertTrue(r['mapa']['truncado'])
        self.assertTrue(r['midias']['imagens'])
        self.assertNotIn('NAO_VAZAR', json.dumps(r))

    def test_13_controles_e_leitura(self):
        self.assertTrue(extensoes.estado()['pronta'])
        extensoes.comando('selecionar', {'seletor': '#idioma', 'valor': 'en'})
        self.assertTrue(extensoes.comando('marcar', {'seletor': '#aceite', 'marcado': True})['confirmado'])
        self.assertTrue(extensoes.comando('marcar', {'seletor': '#pequeno', 'marcado': True})['marcado'])
        r = extensoes.comando('mapa', {'seletor': '#idioma'})['elementos'][0]
        self.assertTrue(r['opcoes'][1]['selecionada'])
        self.assertTrue(extensoes.comando('mapa', {'seletor': '#aceite'})['elementos'][0]['marcado'])
        with self.assertRaisesRegex(kb.ErroKB, 'Tipo de campo'):
            extensoes.comando('digitar', {'seletor': '#aceite', 'texto': 'errado'})
        r = extensoes.comando('ler', {'principal': True})
        self.assertIn('CONTEUDO_PRINCIPAL', r['texto'])
        self.assertNotIn('MENU_IGNORAR', r['texto'])
        self.assertLessEqual(len(extensoes.comando('panorama', {'max_imagens': 0})['midias']['imagens']), 0)

    def test_14_acoes_com_espera(self):
        r = extensoes.comando('clicar', {'seletor': '#atrasado', 'aguardar': {'texto': 'Concluído'}})
        self.assertTrue(r['confirmado'])
        r = extensoes.comando('tecla', {'seletor': '#tecla', 'tecla': 'Enter', 'aguardar': {'texto': 'Enter recebido'}})
        self.assertTrue(r['confirmado'])
        r = extensoes.comando('aguardar', {'seletor': '#nao_existe', 'prazo_ms': 150})
        self.assertFalse(r['confirmado'])
        with self.assertRaisesRegex(kb.ErroKB, 'Informe seletor'):
            extensoes.comando('clicar', {'seletor': '#atrasado', 'aguardar': {"prazo_ms": 150}})
        r = extensoes.comando('clicar', {'seletor': 'a[href="/destino"]:first-of-type', 'aguardar': {'url': '/destino'}})
        self.assertTrue(r['confirmado'])

    def test_15_motor_desatualizado(self):
        antes = extensoes.VERSAO
        try:
            extensoes.VERSAO = 'incompativel'
            self.assertFalse(extensoes.estado()['pronta'])
            with self.assertRaisesRegex(kb.ErroKB, 'desatualizado'):
                extensoes.comando('digitar', {'seletor': '#nome', 'texto': 'NAO_EXECUTAR'})
        finally:
            extensoes.VERSAO = antes
        extensoes.instalar()
        r = extensoes.estado()
        self.assertTrue(r['pronta'], r)


    def test_20_cobertura(self):
        kb.js('''document.body.insertAdjacentHTML('beforeend', `<section id="cobertura_teste" style="position:fixed;inset:0;z-index:99999;background:white">
          <button id="livre" style="position:absolute;left:10px;top:10px;width:100px;height:50px"><span>Filho</span></button>
          <button id="coberto" style="position:absolute;left:10px;top:80px;width:100px;height:50px">Coberto</button>
          <div id="tampa" style="position:absolute;left:10px;top:80px;width:100px;height:50px;background:red"></div>
          <button id="parcial" style="position:absolute;left:150px;top:80px;width:100px;height:50px">Parcial</button>
          <div style="position:absolute;left:150px;top:80px;width:50px;height:50px;background:red"></div>
          <button id="transparente" style="position:absolute;left:10px;top:150px;width:100px;height:50px">Passante</button>
          <div style="position:absolute;left:10px;top:150px;width:100px;height:50px;pointer-events:none;background:red"></div>
          <button id="fora" style="position:absolute;top:100000px">Fora</button></section>`);''', self.aba)
        try:
            r = extensoes.comando('mapa', {'regiao': '#cobertura_teste', 'cobertura': True})
            estados = {e['seletor']: e['cobertura'] for e in r['elementos']}
            self.assertEqual(estados['#livre']['estado'], 'livre')
            self.assertEqual(estados['#coberto']['estado'], 'bloqueado')
            self.assertEqual(estados['#coberto']['bloqueador']['seletor'], '#tampa')
            self.assertEqual(estados['#parcial']['estado'], 'parcial')
            self.assertEqual(estados['#transparente']['estado'], 'livre')
            self.assertEqual(estados['#fora']['estado'], 'fora_tela')
        finally:
            kb.js("document.querySelector('#cobertura_teste').remove()", self.aba)

    def test_19_tela_e_foco(self):
        kb.js('''document.body.insertAdjacentHTML('beforeend', `<section id="tela_teste" style="position:fixed;top:0;left:0">
          <input id="foco_teste" aria-label="Campo com foco">
          <button style="position:fixed;top:100000px">Fora da tela</button>
          <div style="height:1px;overflow:hidden"><button style="margin-top:100px">Recortado</button></div></section>`);
          document.querySelector('#foco_teste').focus();''', self.aba)
        try:
            r = extensoes.comando('panorama', {'regiao': '#tela_teste', 'na_tela': True})
            self.assertEqual(r['foco']['seletor'], '#foco_teste')
            self.assertEqual(r['mapa']['encontrados'], 1)
            self.assertTrue(r['mapa']['elementos'][0]['na_tela'])
            self.assertEqual(extensoes.comando('mapa', {'regiao': '#tela_teste'})['encontrados'], 3)
        finally:
            kb.js("document.querySelector('#tela_teste').remove()", self.aba)

    def test_18_regiao_e_paineis(self):
        kb.js('''document.body.insertAdjacentHTML('beforeend', `<section id="regiao_teste">TEXTO_REGIONAL
          <div role="menu" aria-label="Opções"><div role="menuitem">Item regional</div></div>
          <div role="dialog" hidden>PAINEL_OCULTO</div><button aria-expanded="true">Expandido</button></section>`);''', self.aba)
        try:
            r = extensoes.comando('panorama', {'regiao': '#regiao_teste'})
            self.assertIn('TEXTO_REGIONAL', r['texto'])
            self.assertNotIn('Página de teste local', r['texto'])
            self.assertEqual(r['total_paineis'], 1)
            self.assertEqual(r['paineis'][0]['tipo'], 'menu')
            self.assertTrue(any(e['tipo'] == 'menuitem' for e in r['mapa']['elementos']))
            self.assertTrue(any(e.get('expandido') for e in r['mapa']['elementos']))
            self.assertEqual(r['midias']['total_imagens'], 0)
            for seletor in ['#inexistente', 'div']:
                with self.assertRaisesRegex(kb.ErroKB, 'Região'):
                    extensoes.comando('ler', {'regiao': seletor})
        finally:
            kb.js("document.querySelector('#regiao_teste').remove()", self.aba)

    def test_17_seletores_e_acessibilidade(self):
        kb.js('''document.body.insertAdjacentHTML('beforeend', `<section id="acessibilidade">
          <span id="rotulo">Nome acessível</span><button aria-labelledby="rotulo" title="Identificador">Texto interno</button>
          <button aria-label="Atalho único">Abrir</button><button id="duplicado">Um</button><button id="duplicado">Dois</button>
          <div aria-disabled="true"><button id="bloqueado" onclick="window.clicouBloqueado=true">Bloqueado</button></div>
          <fieldset disabled><input id="campo_bloqueado"></fieldset></section>`);''', self.aba)
        try:
            r = extensoes.comando('mapa', {'seletor': '#acessibilidade *'})
            itens = r['elementos']
            self.assertTrue(any(e['nome'] == 'Nome acessível' for e in itens))
            alvo = next(e for e in itens if e['nome'] == 'Atalho único')
            self.assertIn('aria-label', alvo['seletor'])
            for e in itens:
                self.assertEqual(kb.js('document.querySelectorAll(' + json.dumps(e['seletor']) + ').length', self.aba), 1)
            for acao, dados in [('clicar', {'seletor': '#bloqueado'}), ('digitar', {'seletor': '#campo_bloqueado', 'texto': 'x'})]:
                with self.assertRaisesRegex(kb.ErroKB, 'indisponível'):
                    extensoes.comando(acao, dados)
            self.assertTrue(next(e for e in itens if e['nome'] == 'Bloqueado')['desabilitado'])
        finally:
            kb.js("document.querySelector('#acessibilidade').remove()", self.aba)

    def test_16_whatsapp_contexto(self):
        codigo = (Path(scripts_browser.PASTA) / 'whatsapp_contexto.js').read_text(encoding='utf-8')
        def rodar(dados):
            return kb.js('(async(dados)=>{' + codigo + '})(' + json.dumps(dados) + ')', self.aba)
        kb.js('''document.body.insertAdjacentHTML('beforeend', `<div id="main"><header>Conversa teste</header>
          <div role="row"><div data-id="1"><span data-pre-plain-text="[10:00] Pessoa: "><span class="selectable-text">Olá</span></span></div></div>
          <div role="row"><div data-id="2"><span class="selectable-text">Resposta</span></div></div>
          <footer><div contenteditable="true" role="textbox">RASCUNHO_PRIVADO</div></footer></div>`);''', self.aba)
        try:
            r = rodar({})
            self.assertEqual(r['mensagens'], [])
            self.assertTrue(r['editor']['tem_rascunho'])
            self.assertNotIn('RASCUNHO_PRIVADO', json.dumps(r))
            with self.assertRaisesRegex(kb.ErroKB, 'diferente'):
                rodar({'conversa': 'Outra', 'n': 2})
            with self.assertRaisesRegex(kb.ErroKB, 'Informe conversa'):
                rodar({'n': 2})
            r = rodar({'conversa': 'Conversa teste', 'n': 1})
            self.assertEqual(r['mensagens'][0]['texto'], 'Resposta')
            self.assertFalse(r['historico_completo'])
            with self.assertRaisesRegex(ValueError, 'Origem'):
                scripts_browser.comando('rodar', 'whatsapp_contexto')
        finally:
            kb.js("document.querySelector('#main').remove()", self.aba)


    def test_21_eventos_whatsapp(self):
        codigo = (Path(scripts_browser.PASTA) / 'whatsapp_eventos.js').read_text(encoding='utf-8')
        def rodar(dados=None):
            return kb.js('(async (dados) => {' + codigo + '})(' + json.dumps(dados or {}) + ')', self.aba)
        kb.js("document.body.insertAdjacentHTML('beforeend', '<div id=main><header>KaniCode</header><div role=row><div data-id=true_antigo><span class=selectable-text>Antigo</span></div></div></div>')", self.aba)
        try:
            self.assertEqual(rodar()['mensagens'][0]['id'], 'true_antigo')
            # Sem confirmação, o evento continua disponível depois de uma falha na ponte.
            self.assertEqual(rodar()['mensagens'][0]['id'], 'true_antigo')
            self.assertEqual(rodar({'confirmados': ['true_antigo']})['mensagens'], [])
            kb.js("document.querySelector('#main').insertAdjacentHTML('beforeend', '<div role=row><div data-id=true_novo><span class=selectable-text>Novo pedido</span></div></div>')", self.aba)
            time.sleep(.2)
            r = rodar()
            self.assertEqual([m['id'] for m in r['mensagens']], ['true_novo'])
            self.assertEqual(r['mensagens'][0]['quem'], 'Eu')
            self.assertEqual(rodar({'confirmados': ['true_novo']})['mensagens'], [])
            # A espera fica pendente sem consultas e acorda pela mutação do DOM.
            kb.js("setTimeout(() => document.querySelector('#main').insertAdjacentHTML('beforeend', '<div data-id=true_aviso><span class=selectable-text>Acordar</span></div>'), 150)", self.aba)
            inicio = time.monotonic()
            self.assertEqual(kb.js('globalThis.__kbWaEventos.esperar([], 60000)', self.aba), 'mensagem')
            self.assertLess(time.monotonic() - inicio, 1.5)
            self.assertEqual(rodar()['mensagens'][0]['id'], 'true_aviso')
            self.assertEqual(kb.js("globalThis.__kbWaEventos.esperar(['true_aviso'], 100)", self.aba), 'conferencia')
            self.assertEqual(kb.js('globalThis.__kbWaEventos.esperas.size', self.aba), 0)
            kb.js("document.querySelector('#main header').textContent='Outro'", self.aba)
            with self.assertRaisesRegex(kb.ErroKB, 'KaniCode'):
                rodar()
        finally:
            kb.js("globalThis.__kbWaEventos?.observador.disconnect(); delete globalThis.__kbWaEventos; document.querySelector('#main').remove()", self.aba)


if __name__ == '__main__':
    unittest.main(verbosity=2)
