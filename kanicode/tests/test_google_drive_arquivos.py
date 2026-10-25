"""Operações e transferências isoladas, sem Drive real nem seletores nativos."""
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
import urllib.error
import urllib.parse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import google_drive_arquivos as ops
import google_calendar as gc
import test_google_drive as base


class Resposta(io.BytesIO):
    def __init__(self, dados=b'', status=200, headers=None):
        super().__init__(json.dumps(dados).encode() if isinstance(dados, dict) else dados)
        self.status = status
        self.headers = headers or {}


class OperacoesDriveTest(unittest.TestCase):
    setUp = base.DriveTest.setUp

    def completo(self):
        self.d._guardar_privado({'client': self.client, 'token': {**self.token, 'scope': ops.ESCOPO_TOTAL}})

    def test_autorizacao_antiga_nao_permite_escrita(self):
        self.d._guardar_privado({'client': self.client, 'token': {**self.token, 'scope': 'https://www.googleapis.com/auth/drive.readonly'}})
        self.assertFalse(self.d.status()['controle_total'])
        origem = Path(self.temp.name) / 'arquivo.txt'; origem.write_bytes(b'teste')
        with patch.object(self.d, '_pedido') as pedido:
            for funcao in [lambda: self.d.criar_pasta('Pasta'), lambda: self.d.renomear('a', 'Novo'), lambda: self.d.mover('a', 'b'), lambda: self.d.lixeira('a'), lambda: self.d.enviar(origem)]:
                with self.assertRaisesRegex(gc.FalhaCalendar, 'controle total'):
                    funcao()
            pedido.assert_not_called()

    def test_cria_renomeia_move_lixeira_e_restaura(self):
        self.completo()
        with patch.object(self.d, '_pasta', return_value='destino'), patch.object(self.d, '_pedido', return_value={'id':'nova','name':'Cliente','mimeType':ops.PASTA}) as pedido:
            self.assertEqual(self.d.criar_pasta('Cliente')['id'], 'nova')
            self.assertEqual(pedido.call_args.args[:2], ('POST', 'files'))
            self.assertEqual(pedido.call_args.args[3]['parents'], ['destino'])
        with patch.object(self.d, '_pedido', return_value={'id':'a','name':'Novo nome'}) as pedido:
            self.d.renomear('a', 'Novo nome')
            self.assertEqual(pedido.call_args.args[3], {'name':'Novo nome'})
        with patch.object(self.d, '_pasta', return_value='destino'), patch.object(self.d, '_arquivo', return_value={'id':'a','parents':['origem']}), patch.object(self.d, '_pedido', return_value={'id':'a','parents':['destino']}) as pedido:
            self.d.mover('a', 'destino')
            self.assertEqual(pedido.call_args.kwargs['addParents'], 'destino')
            self.assertEqual(pedido.call_args.kwargs['removeParents'], 'origem')
        for restaurar in [False, True]:
            with patch.object(self.d, '_pedido', return_value={'id':'a','trashed':not restaurar}) as pedido:
                self.d.lixeira('a', restaurar)
                self.assertEqual(pedido.call_args.args[0], 'PATCH')
                self.assertEqual(pedido.call_args.args[3], {'trashed':not restaurar})
        self.assertTrue(self.origem.status()['conectado'])

    def test_recusa_destinos_invalidos_e_resposta_nao_confirmada(self):
        self.completo()
        with patch.object(self.d, '_pasta', return_value='a'), patch.object(self.d, '_pedido') as pedido:
            with self.assertRaises(gc.FalhaCalendar):
                self.d.mover('a', 'a')
            pedido.assert_not_called()
        with patch.object(self.d, '_pedido', return_value={'id':'a','name':'Outro'}):
            with self.assertRaisesRegex(gc.FalhaCalendar, 'não confirmou'):
                self.d.renomear('a', 'Novo')
        for id in ['../outro', 'a?alt=media', '', None]:
            with self.assertRaises(gc.FalhaCalendar):
                self.d.lixeira(id)
        with self.assertRaises(gc.FalhaCalendar):
            self.d.lixeira('a', 'false')

    def test_busca_por_pasta_e_lixeira(self):
        self.completo()
        import google_drive as gd
        with patch.object(gd, '_http', return_value={'files':[]} ) as http:
            self.d.buscar('', '', 'pasta_1', True)
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(http.call_args.args[0]).query)
        self.assertEqual(query['q'], ["trashed = true and 'pasta_1' in parents"])

    def test_upload_em_blocos_sem_carregar_arquivo_inteiro(self):
        self.completo()
        arquivo = Path(self.temp.name) / 'grande.bin'
        arquivo.write_bytes(b'x' * (4 * 1024 * 1024 + 3))
        pedidos = []
        def abrir(req, parcial=False):
            pedidos.append(req)
            if req.method == 'POST':
                return Resposta(headers={'Location':'https://www.googleapis.com/upload/drive/v3/files?upload_id=teste'})
            if len(pedidos) == 2:
                return Resposta(status=308, headers={'Range':'bytes=0-4194303'})
            return Resposta({'id':'enviado','name':arquivo.name,'size':str(arquivo.stat().st_size)})
        with patch.object(self.d, '_pasta', return_value='root'), patch.object(ops, '_abrir', side_effect=abrir):
            r = self.d.enviar(arquivo)
        self.assertEqual(r['id'], 'enviado')
        self.assertEqual([len(p.data) for p in pedidos[1:]], [4 * 1024 * 1024, 3])
        self.assertEqual(pedidos[2].get_header('Content-range'), 'bytes 4194304-4194306/4194307')

    def test_upload_recusa_sessao_externa_e_nao_repete_envio(self):
        self.completo()
        arquivo = Path(self.temp.name) / 'a.txt'; arquivo.write_bytes(b'abc')
        with patch.object(self.d, '_pasta', return_value='root'), patch.object(ops, '_abrir', return_value=Resposta(headers={'Location':'https://exemplo.com/upload'})) as abrir:
            with self.assertRaisesRegex(gc.FalhaCalendar, 'sessão'):
                self.d.enviar(arquivo)
            abrir.assert_called_once()
        with patch.object(self.d, '_pasta', return_value='root'), patch.object(ops, '_abrir', side_effect=gc.FalhaCalendar('Sem rede')) as abrir:
            with self.assertRaises(gc.FalhaCalendar):
                self.d.enviar(arquivo)
            abrir.assert_called_once()

    def test_upload_vazio_e_validacao_do_total(self):
        self.completo()
        arquivo = Path(self.temp.name) / 'vazio.txt'; arquivo.write_bytes(b'')
        with patch.object(self.d, '_pasta', return_value='root'), patch.object(self.d, '_pedido', return_value={'id':'vazio','name':'vazio.txt','size':'0'}):
            self.assertEqual(self.d.enviar(arquivo)['id'], 'vazio')
        with patch.object(self.d, '_pasta', return_value='root'), patch.object(self.d, '_pedido', return_value={'id':'vazio','name':'vazio.txt','size':'10'}):
            with self.assertRaisesRegex(gc.FalhaCalendar, 'confirmar'):
                self.d.enviar(arquivo)

    def test_download_atomico_sem_sobrescrita(self):
        self.completo()
        pasta = Path(self.temp.name)
        with patch.object(self.d, '_arquivo', return_value={'id':'a','name':'arquivo.txt','mimeType':'text/plain','size':'3'}), patch.object(ops, '_abrir', return_value=Resposta(b'abc')):
            r = self.d.baixar('a', pasta)
        alvo = Path(r['caminho']); self.assertEqual(alvo.read_bytes(), b'abc')
        self.assertEqual(r['bytes'], 3)
        import progresso
        self.assertTrue(any(i['id'] == 'drive:a' and i['estado'] == 'concluido' for i in progresso.listar()))
        with patch.object(self.d, '_arquivo', return_value={'id':'a','name':'arquivo.txt','mimeType':'text/plain','size':'4'}), patch.object(ops, '_abrir') as abrir:
            with self.assertRaisesRegex(gc.FalhaCalendar, 'Já existe'):
                self.d.baixar('a', pasta)
            abrir.assert_not_called()
        self.assertEqual(alvo.read_bytes(), b'abc')
        self.assertEqual(list(pasta.glob('*.part')), [])

    def test_download_incompleto_nao_publica_arquivo(self):
        self.completo()
        pasta = Path(self.temp.name)
        with patch.object(self.d, '_arquivo', return_value={'id':'a','name':'truncado.txt','mimeType':'text/plain','size':'10'}), patch.object(ops, '_abrir', return_value=Resposta(b'ab')):
            with self.assertRaisesRegex(gc.FalhaCalendar, 'incompleto'):
                self.d.baixar('a', pasta)
        self.assertFalse((pasta / 'truncado.txt').exists())
        import progresso
        self.assertTrue(any(i['id'] == 'drive:a' and i['estado'] == 'erro' for i in progresso.listar()))
        self.assertFalse(list(pasta.glob('*.part')))

    def test_exporta_documento_google_pdf_e_nome_seguro(self):
        self.completo()
        with patch.object(self.d, '_arquivo', return_value={'id':'doc','name':'../Relatório','mimeType':'application/vnd.google-apps.document'}), patch.object(ops, '_abrir', return_value=Resposta(b'%PDF')) as abrir:
            r = self.d.baixar('doc', self.temp.name, 'pdf')
        self.assertEqual(Path(r['caminho']).parent, Path(self.temp.name))
        self.assertTrue(r['nome'].endswith('.pdf'))
        self.assertIn('/export?', abrir.call_args.args[0].full_url)
        self.assertIn('mimeType=application%2Fpdf', abrir.call_args.args[0].full_url)
        for nome in ['CON', 'AUX.txt', 'COM1.txt']:
            self.assertTrue(ops._nome_local(nome).startswith('_'))

    def test_pasta_e_tipo_nao_exportavel_nao_fazem_download(self):
        self.completo()
        for tipo in [ops.PASTA, 'application/vnd.google-apps.shortcut']:
            with patch.object(self.d, '_arquivo', return_value={'id':'a','mimeType':tipo}), patch.object(ops, '_abrir') as abrir:
                with self.assertRaises(gc.FalhaCalendar):
                    self.d.baixar('a', self.temp.name)
                abrir.assert_not_called()

    def test_nova_conta_nao_reutiliza_cache_antigo(self):
        self.completo()
        gc._salvar(self.d.dados / 'google.json', {'conta':'antiga@example.com','arquivos':[{'nome':'privado'}]})
        self.d._guardar_privado({'client':self.client, 'token':{**self.token,'refresh_token':'outra-conta','scope':ops.ESCOPO_TOTAL}})
        self.assertEqual(self.d.status()['arquivos'], [])
        self.assertEqual(self.d.status()['conta'], '')

    def test_api_python_com_caminhos_explicitos_nao_abre_dialogos(self):
        import kanicode
        import google_drive
        app = kanicode.App.__new__(kanicode.App); app._janela = Mock()
        with patch.object(google_drive.drive, 'enviar', return_value={'id':'a'}) as enviar, patch.object(google_drive.drive, 'baixar', return_value={'caminho':'D:/teste'}) as baixar:
            app.drive_enviar('D:/origem.txt', 'root')
            app.drive_baixar('a', 'D:/destino')
        enviar.assert_called_once_with('D:/origem.txt', 'root')
        baixar.assert_called_once_with('a', 'D:/destino', '')
        app._janela.create_file_dialog.assert_not_called()

    def test_erros_http_nao_expoem_corpo_privado(self):
        for codigo in [401, 403, 404, 500]:
            erro = urllib.error.HTTPError('https://www.googleapis.com/drive/v3/files', codigo, 'erro', {}, io.BytesIO(b'segredo-token'))
            with patch.object(ops.urllib.request, 'urlopen', side_effect=erro):
                with self.assertRaises(gc.FalhaCalendar) as falha:
                    ops._abrir(Mock())
            self.assertNotIn('segredo-token', str(falha.exception))


if __name__ == '__main__':
    unittest.main()
