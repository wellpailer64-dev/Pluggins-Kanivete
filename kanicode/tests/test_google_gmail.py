"""Gmail isolado: sem conta real, envio ou acesso à rede."""
import base64
import email
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import google_calendar as gc
import google_gmail as gm

class GmailTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=r'D:\kanivete_testes')
        self.addCleanup(self.tmp.cleanup)
        self.origem = gc.Calendar(Path(self.tmp.name) / 'calendar')
        self.g = gm.Gmail(Path(self.tmp.name) / 'gmail', self.origem)
        self.origem._guardar_privado({'client': {'client_id':'teste.apps.googleusercontent.com', 'client_secret':'segredo'}, 'token': {'access_token':'privado'}})
    def test_oauth_independente_e_dpapi(self):
        s = self.g.usar_calendar()
        self.assertTrue(s['configurado']); self.assertFalse(s['conectado'])
        self.assertNotIn('token', self.g._privado())
        self.assertNotIn('segredo', (self.g.dados / 'google.dpapi.json').read_text())
        self.g.desconectar()
        self.assertTrue(self.origem.status()['conectado'])
    def test_busca_paginada_e_leitura_html_como_texto(self):
        with patch.object(self.g, '_access', return_value='acesso'), patch.object(gm, '_http', side_effect=[{'messages':[{'id':'abc'}], 'nextPageToken':'prox'}, {'id':'abc','payload':{'headers':[{'name':'Subject','value':'Cliente'}]}}]) as http:
            r = self.g.buscar('from:cliente', 'pagina')
            self.assertEqual(r['proxima'], 'prox')
            self.assertIn('pageToken=pagina', http.call_args_list[0].args[0])
        m = gm._mensagem({'id':'abc','payload':{'mimeType':'text/html','body':{'data':base64.urlsafe_b64encode(b'<p>Oi</p><script>alert(1)</script>').decode()}}})
        self.assertIn('Oi', m['texto']); self.assertNotIn('alert', m['texto'])
    def test_cria_somente_rascunho_mime(self):
        with patch.object(self.g, '_access', return_value='acesso'), patch.object(gm, '_http', return_value={'id':'r1'}) as http:
            r = self.g.rascunho('cliente@example.com', 'Orçamento', 'Olá!')
            self.assertEqual(r['id'], 'r1')
            self.assertEqual(http.call_args.args[0], 'drafts')
            raw = http.call_args.args[2]['message']['raw']
            m = email.message_from_bytes(base64.urlsafe_b64decode(raw))
            self.assertEqual(m['To'], 'cliente@example.com')
            self.assertIn('Olá!', m.get_payload(decode=True).decode())
    def test_recusa_injecao_e_id_antes_da_rede(self):
        with patch.object(gm, '_http') as http:
            for para, assunto in [('a@example.com\nBcc:x@example.com','Oi'), ('a@example.com','Oi\r\nBcc:x')]:
                with self.assertRaises(gm.FalhaGmail): self.g.rascunho(para, assunto, 'texto')
            with self.assertRaises(gm.FalhaGmail): self.g.ler('../profile')
            http.assert_not_called()
