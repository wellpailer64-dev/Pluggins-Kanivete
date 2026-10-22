"""Drive isolado: OAuth/API simulados e dados de teste no D, sem conta real."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.parse
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import google_calendar as gc
import google_drive as gd


class DriveTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='drive_', dir=r'D:\kanivete_testes')
        self.addCleanup(self.temp.cleanup)
        self.origem = gc.Calendar(Path(self.temp.name) / 'calendar')
        self.d = gd.Drive(Path(self.temp.name) / 'drive', self.origem)
        self.client = {'client_id': 'teste.apps.googleusercontent.com', 'client_secret': 'segredo-teste'}
        self.token = {'access_token': 'acesso-teste', 'refresh_token': 'renovar-teste', 'expires_at': time.time() + 3600}
        self.origem._guardar_privado({'client': self.client, 'token': self.token})

    def conectar(self):
        self.d._guardar_privado({'client': self.client, 'token': self.token})

    def test_reutiliza_cliente_sem_copiar_autorizacao_calendar(self):
        s = self.d.usar_calendar()
        self.assertTrue(s['configurado'])
        self.assertFalse(s['conectado'])
        self.assertEqual(self.d._privado(), {'client': self.client})
        self.assertNotIn('segredo-teste', (self.d.dados / 'google.dpapi.json').read_text())
        self.assertNotIn('client_secret', json.dumps(s))
        self.assertNotIn('access_token', json.dumps(s))
        self.assertTrue(self.origem.status()['conectado'])

    def test_trocar_cliente_conectado_e_recusado(self):
        self.conectar()
        with self.assertRaises(gd.FalhaDrive):
            self.d.usar_calendar()
        self.assertEqual(self.d._privado()['token'], self.token)

    def test_busca_paginada_escapa_nome_e_so_consulta(self):
        self.conectar()
        resposta = {'files': [{'id': 'pasta', 'name': '<script>nome</script>', 'mimeType': 'application/vnd.google-apps.folder'}], 'nextPageToken': 'pagina-2'}
        with patch.object(gd, '_http', return_value=resposta) as http:
            r = self.d.buscar("cliente's\\ref", 'pagina-1')
        url, token = http.call_args.args
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        self.assertEqual(q['q'], ["trashed = false and name contains 'cliente\\'s\\\\ref'"])
        self.assertEqual(q['pageToken'], ['pagina-1'])
        self.assertEqual(q['pageSize'], ['50'])
        self.assertEqual(token, 'acesso-teste')
        self.assertEqual(r['proxima'], 'pagina-2')
        self.assertTrue(r['arquivos'][0]['pasta'])
        self.assertEqual(r['arquivos'][0]['url'], 'https://drive.google.com/drive/folders/pasta')
        self.assertNotIn('access_token', json.dumps(r))

    def test_busca_valida_entrada_e_exige_conexao(self):
        with patch.object(gd, '_http') as http:
            for busca, pagina in [('x' * 201, ''), ('', 'x' * 4097), (None, ''), ('', None), ('', '')]:
                with self.subTest(busca=str(busca)[:12]), self.assertRaises(gd.FalhaDrive):
                    self.d.buscar(busca, pagina)
            http.assert_not_called()

    def test_sync_e_desconexao_preservam_calendar(self):
        self.conectar()
        original = self.origem._privado()
        with patch.object(gd, '_http', side_effect=[{'user': {'emailAddress': 'teste@example.com'}}, {'files': [{'id': '1', 'name': 'Projeto'}]}]):
            s = self.d.sincronizar()
        self.assertEqual(s['conta'], 'teste@example.com')
        self.assertEqual(s['arquivos'][0]['nome'], 'Projeto')
        self.assertTrue(s['ultima_sync'])
        s = self.d.desconectar()
        self.assertFalse(s['conectado'])
        self.assertEqual(s['arquivos'], [])
        self.assertEqual(s['conta'], '')
        self.assertEqual(self.origem._privado(), original)

    def test_falha_na_api_preserva_cache_e_mostra_erro_drive(self):
        self.conectar()
        gc._salvar(self.d.dados / 'google.json', {'arquivos': [{'nome': 'Em cache'}]})
        with patch.object(gd, '_http', side_effect=gd.FalhaDrive('Ative a Drive API')):
            with self.assertRaises(gd.FalhaDrive):
                self.d.sincronizar()
        self.assertEqual(self.d.status()['arquivos'][0]['nome'], 'Em cache')
        self.assertIn('Drive API', self.d.status()['mensagem'])

    def test_cancelamento_nao_grava_token_tardio(self):
        cancelar = threading.Event()
        cancelar.set()
        with patch.object(self.d, '_login', return_value=self.token), patch.object(self.d, 'sincronizar') as sync:
            self.d._autorizar(self.client, cancelar)
        self.assertFalse(self.d.status()['conectado'])
        sync.assert_not_called()

    def test_oauth_pede_drive_sem_escopos_calendar(self):
        pedidos, erros, threads = [], [], []
        def abrir(url):
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            pedidos.append(q)
            def visitar():
                try:
                    callback = q['redirect_uri'][0] + '?' + urllib.parse.urlencode({'state': q['state'][0], 'code': 'teste'})
                    with urllib.request.urlopen(callback, timeout=3) as resposta:
                        self.assertEqual(resposta.status, 200)
                except Exception as exc:
                    erros.append(str(exc))
            t = threading.Thread(target=visitar); threads.append(t); t.start()
            return True
        token = {**self.token, 'scope': ' '.join(self.d.escopos), 'expires_in': 3600}
        with patch.object(gc.webbrowser, 'open', side_effect=abrir), patch.object(gc, '_http', return_value=token):
            self.d._login(self.client, threading.Event())
        for t in threads:
            t.join(3)
        self.assertFalse(erros)
        self.assertEqual(pedidos[0]['scope'], ['https://www.googleapis.com/auth/drive'])
        self.assertEqual(pedidos[0]['code_challenge_method'], ['S256'])

    def test_ferramenta_kani_devolve_resultado_e_falha_legivel(self):
        import kani_modo
        with patch.object(gd.drive, 'buscar', return_value={'arquivos': [], 'proxima': ''}) as buscar:
            r = kani_modo._executar('drive_buscar', {'busca': 'projeto'}, '')
        self.assertEqual(json.loads(r)['arquivos'], [])
        buscar.assert_called_once_with('projeto', '', '', False)
        with patch.object(gd.drive, 'buscar', side_effect=gd.FalhaDrive('Conecte o Drive')):
            self.assertIn('NÃO FEITO', kani_modo._executar('drive_buscar', {}, ''))


if __name__ == '__main__':
    unittest.main()
