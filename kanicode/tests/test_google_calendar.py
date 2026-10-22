"""Calendar isolado: arquivos temporários, OAuth/API simulados; nunca usa conta ou tarefas reais."""
import datetime as dt
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch, Mock
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import google_calendar as gc
import compromissos as cp


class CalendarTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='calendar_', dir=r'D:\kanivete_testes')
        self.addCleanup(self.temp.cleanup)
        self.c = gc.Calendar(Path(self.temp.name) / 'conexoes')
        self.client = {'client_id': 'teste.apps.googleusercontent.com', 'client_secret': 'segredo-de-teste'}

    def conectado(self, vencido=False):
        self.c._guardar_privado({'client': self.client, 'token': {
            'access_token': 'acesso-teste', 'refresh_token': 'renovacao-teste',
            'expires_at': 0 if vencido else time.time() + 3600}})

    def salvar_estado(self, **values):
        e = self.c._estado()
        e.update(values)
        gc._salvar(self.c.dados / 'google.json', e)

    def test_importacao_desktop_e_dpapi_sem_segredos_na_interface(self):
        p = Path(self.temp.name) / 'oauth.json'
        p.write_text(json.dumps({'installed': self.client}), encoding='utf-8')
        s = self.c.importar(p)
        self.assertTrue(s['configurado'])
        self.assertFalse(s['conectado'])
        self.assertEqual(self.c._privado()['client'], self.client)
        self.assertNotIn('segredo-de-teste', (self.c.dados / 'google.dpapi.json').read_text())
        self.assertNotIn('client_secret', json.dumps(s))
        self.assertNotIn('client_id', json.dumps(s))

    def test_recusa_cliente_web_sem_apagar_configuracao(self):
        self.conectado()
        p = Path(self.temp.name) / 'oauth.json'
        p.write_text(json.dumps({'web': self.client}))
        with self.assertRaises(gc.FalhaCalendar):
            self.c.importar(p)
        self.assertTrue(self.c.status()['conectado'])

    def test_login_exige_configuracao(self):
        with patch.object(gc.webbrowser, 'open') as browser:
            with self.assertRaises(gc.FalhaCalendar):
                self.c.conectar()
            browser.assert_not_called()

    def test_refresh_preserva_refresh_token(self):
        self.conectado(vencido=True)
        with patch.object(gc, '_http', return_value={'access_token': 'novo', 'expires_in': 3600}) as http:
            self.assertEqual(self.c._access(self.c._privado()), 'novo')
        self.assertEqual(http.call_args.args[1]['grant_type'], 'refresh_token')
        self.assertEqual(self.c._privado()['token']['refresh_token'], 'renovacao-teste')
        self.assertNotIn('novo', json.dumps(self.c.status()))

    def test_paginacao_calendar_e_eventos(self):
        self.conectado()
        inicio = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=2)).isoformat()
        respostas = [
            {'items': [{'id': 'a@test', 'primary': True, 'summary': 'Pessoal'}], 'nextPageToken': 'pag2'},
            {'items': [{'id': 'b@test', 'summary': 'Trabalho'}]},
            {'items': [{'id': 'e1', 'summary': 'Reunião', 'start': {'dateTime': inicio}}], 'nextPageToken': 'ev2'},
            {'items': [{'id': 'e2', 'start': {'date': '2026-11-01'}},
                       {'id': 'e3', 'status': 'cancelled', 'start': {'dateTime': inicio}}]},
        ]
        with patch.object(gc, '_http', side_effect=respostas) as http:
            s = self.c.sincronizar()
        self.assertEqual(s['selecionados'], ['a@test'])
        self.assertEqual(len(s['eventos']), 2)
        self.assertEqual(s['conta'], 'a@test')
        self.assertIn('pageToken=pag2', http.call_args_list[1].args[0])
        self.assertIn('calendars/a%40test/events', http.call_args_list[2].args[0])
        self.assertIn('singleEvents=true', http.call_args_list[2].args[0])
        self.assertEqual(len(self.c.ocorrencias(dt.datetime.now(), dt.datetime.now() + dt.timedelta(days=1))), 1)

    def test_selecao_vazia_nao_volta_ao_principal(self):
        self.conectado()
        self.salvar_estado(selecionados=[], calendarios=[{'id': 'a', 'nome': 'A', 'principal': True}])
        with patch.object(gc, '_http', return_value={'items': [{'id': 'a', 'primary': True}]}) as http:
            s = self.c.selecionar([], 25)
        self.assertEqual(s['selecionados'], [])
        self.assertEqual(s['antes'], 25)
        http.assert_called_once()

    def test_validacao_selecao_e_antecedencia(self):
        for ids, antes in [(['intruso'], 10), ([], 0), ([], 1441), ([], True), ('a', 10)]:
            with self.subTest(ids=ids, antes=antes), self.assertRaises(gc.FalhaCalendar):
                self.c.selecionar(ids, antes)

    def test_erro_de_rede_preserva_cache_e_expoe_erro(self):
        self.conectado()
        self.salvar_estado(eventos=[{'titulo': 'Reunião em cache'}])
        with patch.object(gc, '_http', side_effect=gc.FalhaCalendar('Sem internet')):
            with self.assertRaises(gc.FalhaCalendar):
                self.c.sincronizar()
        self.assertEqual(self.c.status()['eventos'][0]['titulo'], 'Reunião em cache')
        self.assertEqual(self.c.status()['mensagem'], 'Sem internet')

    def test_desconectar_remove_tokens_cache_preserva_cliente(self):
        self.conectado()
        self.salvar_estado(eventos=[{'titulo': 'Privado'}], conta='conta@example.com')
        self.c.desconectar()
        self.assertEqual(self.c._privado(), {'client': self.client})
        self.assertEqual(self.c.status()['eventos'], [])
        self.assertEqual(self.c.status()['conta'], '')
        self.assertTrue(self.c._cancelar.is_set())

    def test_autorizacao_cancelada_nao_reconecta(self):
        cancelar = threading.Event()
        cancelar.set()
        with patch.object(self.c, '_login', return_value={'refresh_token': 'x'}), patch.object(self.c, 'sincronizar') as sync:
            self.c._autorizar(self.client, cancelar)
        self.assertFalse(self.c.status()['conectado'])
        sync.assert_not_called()

    def test_fim_do_login_prepara_avisos_mesmo_sem_tela_aberta(self):
        callback = Mock()
        with patch.object(self.c, '_login', return_value={'refresh_token': 'x'}), patch.object(self.c, 'sincronizar'):
            self.c._autorizar(self.client, threading.Event(), callback)
        callback.assert_called_once()

    def test_oauth_loopback_pkce_e_state(self):
        threads, erros, pedidos = [], [], []
        def abrir(url):
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            pedidos.append(q)
            def visitar():
                try:
                    try:
                        urllib.request.urlopen(q['redirect_uri'][0] + '?state=errado&code=intruso', timeout=3)
                        erros.append('state inválido aceito')
                    except urllib.error.HTTPError as e:
                        self.assertEqual(e.code, 400)
                    callback = q['redirect_uri'][0] + '?' + urllib.parse.urlencode({'state': q['state'][0], 'code': 'codigo-teste'})
                    with urllib.request.urlopen(callback, timeout=3) as r:
                        self.assertEqual(r.status, 200)
                except Exception as e:
                    erros.append(str(e))
            t = threading.Thread(target=visitar)
            threads.append(t)
            t.start()
            return True
        token = {'access_token': 'x', 'refresh_token': 'y', 'scope': ' '.join(gc.SCOPES), 'expires_in': 3600}
        with patch.object(gc.webbrowser, 'open', side_effect=abrir), patch.object(gc, '_http', return_value=token) as http:
            r = self.c._login(self.client, threading.Event())
        for t in threads:
            t.join(3)
        self.assertEqual(erros, [])
        self.assertEqual(pedidos[0]['code_challenge_method'], ['S256'])
        self.assertTrue(pedidos[0]['redirect_uri'][0].startswith('http://127.0.0.1:'))
        self.assertEqual(http.call_args.args[1]['code'], 'codigo-teste')
        self.assertIn('code_verifier', http.call_args.args[1])
        self.assertGreater(r['expires_at'], time.time())

    def test_login_cancelado_e_navegador_indisponivel(self):
        with patch.object(gc.webbrowser, 'open', return_value=False), self.assertRaises(gc.FalhaCalendar):
            self.c._login(self.client, threading.Event())
        cancelar = threading.Event()
        cancelar.set()
        with patch.object(gc.webbrowser, 'open', return_value=True), self.assertRaises(gc.FalhaCalendar):
            self.c._login(self.client, cancelar)

    def test_fuso_convertido_e_cache_antigo_sem_alarme(self):
        self.conectado()
        agora = dt.datetime.now()
        inicio = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=2)
        evento = gc._evento({'id': 'e', 'start': {'dateTime': inicio.isoformat()}}, {'id': 'a', 'nome': 'A'})
        self.salvar_estado(eventos=[evento], ultima_sync=dt.datetime.now(dt.timezone.utc).isoformat())
        ocorrencias = self.c.ocorrencias(agora, agora + dt.timedelta(hours=3))
        self.assertEqual(ocorrencias[0]['inicio'], inicio.astimezone().replace(tzinfo=None))
        self.salvar_estado(ultima_sync=(dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=3)).isoformat())
        self.assertEqual(self.c.ocorrencias(agora, agora + dt.timedelta(hours=3)), [])

    def test_http_nao_vaza_corpo_do_erro(self):
        erro = urllib.error.HTTPError(gc.TOKEN_URL, 400, 'bad', {}, io.BytesIO(b'{"secret":"segredo"}'))
        with patch.object(gc.urllib.request, 'urlopen', side_effect=erro), self.assertRaises(gc.FalhaCalendar) as cm:
            gc._http(gc.TOKEN_URL, {'a': 'b'})
        self.assertNotIn('segredo', str(cm.exception))


class AvisosCalendarTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='avisos_', dir=r'D:\kanivete_testes')
        self.addCleanup(self.temp.cleanup)
        self.av = Path(self.temp.name)
        self.addCleanup(patch.stopall)
        patch.object(cp, 'AVISOS', str(self.av)).start()
        patch.object(cp, 'PROXIMOS', str(self.av / 'agenda.json')).start()

    def evento(self):
        return {'id': 'google:a:e', 'titulo': 'Reunião', 'obs': '', 'antes': 10, 'origem': 'google',
                'inicio': dt.datetime.now().replace(second=0, microsecond=0) + dt.timedelta(hours=2)}

    def test_preparacao_nao_recria_alarme_existente(self):
        evento = self.evento()
        existentes = set()
        def run(args, **kwargs):
            if '/Create' in args:
                existentes.add('\\' + args[args.index('/TN') + 1])
            return Mock(returncode=0)
        with patch.object(cp, '_ocorrencias', return_value=[evento]), \
                patch.object(cp, '_tarefas_kani', side_effect=lambda: existentes.copy()), \
                patch.object(cp, '_gravar_fala'), patch.object(cp.subprocess, 'run', side_effect=run) as tarefas:
            cp.preparar()
            cp.preparar()
        self.assertEqual(tarefas.call_count, 1)
        self.assertEqual(json.loads((self.av / 'agenda.json').read_text())[0]['origem'], 'google')
        self.assertEqual(len(list(self.av.glob('*.wav.json'))), 1)

    def test_erro_ao_agendar_nao_vira_sucesso(self):
        with patch.object(cp, '_ocorrencias', return_value=[self.evento()]), \
                patch.object(cp, '_tarefas_kani', return_value=set()), patch.object(cp, '_gravar_fala'), \
                patch.object(cp.subprocess, 'run', side_effect=cp.subprocess.CalledProcessError(1, 'schtasks')):
            with self.assertRaises(cp.subprocess.CalledProcessError):
                cp.preparar()
        self.assertFalse((self.av / 'agenda.json').exists())

    def test_pythonw_sem_console_registra_e_executa(self):
        import ast
        from types import SimpleNamespace
        fonte = Path(cp.__file__).read_text(encoding='utf-8')
        principal = next(n for n in ast.parse(fonte).body if isinstance(n, ast.If)
                         and ast.unparse(n.test) == "__name__ == '__main__'")
        # Executa só a inicialização de streams do bloco principal, sem chamar CLI real.
        inicio = ast.Module(body=principal.body[:2], type_ignores=[])
        falso_sys = SimpleNamespace(stdout=None, stderr=None)
        contexto = {'sys': falso_sys, 'os': cp.os, 'AVISOS': str(self.av)}
        exec(compile(inicio, '<pythonw-teste>', 'exec'), contexto)
        try:
            self.assertIs(falso_sys.stdout, falso_sys.stderr)
            print('aviso sem console', file=falso_sys.stdout)
            self.assertIn('aviso sem console', (self.av / 'agendador.log').read_text(encoding='utf-8'))
        finally:
            falso_sys.stdout.close()

    def test_aviso_google_desconectado_nao_toca(self):
        wav = str(self.av / 'a.wav')
        Path(wav + '.json').write_text(json.dumps({'id': 'google:a:e', 'inicio': self.evento()['inicio'].isoformat()}))
        with patch.object(gc.calendar, 'ocorrencias', return_value=[]), patch('winsound.PlaySound') as tocar:
            cp.tocar(wav)
        tocar.assert_not_called()


if __name__ == '__main__':
    unittest.main()
