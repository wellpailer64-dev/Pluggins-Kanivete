"""Contratos isolados: nenhuma conta, rede ou entrega real participa dos testes."""
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import panda
import pandalab as pl
import pandalab_entregas as pe


class EntregasTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir='D:/kanivete_testes')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.pasta = self.base / 'finais'
        self.pasta.mkdir()
        for n in (1, 2, 10):
            (self.pasta / f'slide_{n}.png').write_bytes(f'arte {n}'.encode())
        (self.pasta / 'fonte.iknv').write_bytes(b'editavel')
        self.eid = '11111111-1111-1111-1111-111111111111'
        self.entregas = [{'id': self.eid, 'short_id': 1172, 'title': 'Medo de dirigir',
                          'instagram_username': 'Carlinhos PE', 'client': {'name': 'Carlinhos Peruíbe'},
                          'content_type': 'carrossel', 'post_caption': 'Legenda preservada', 'is_approved': False}]
        self.antigos = [{'id': f'22222222-2222-2222-2222-{n:012d}', 'delivery_id': self.eid,
                         'file_path': f'https://drive/antigo{n}', 'file_type': 'image/png', 'position': n}
                        for n in range(3)]
        self.itens = copy.deepcopy(self.antigos)
        self.uploads, self.escritas = [], []
        self.falhar_upload = None
        self.falhar_insert = False
        self.falhar_delete = False
        self.ignorar_insert = False
        self.ignorar_delete = False
        for alvo, valor in ((patch.object(pe, 'OPERACOES', self.base / 'operacoes'), None),
                            (patch.object(pl, '_ler', side_effect=self.ler), None),
                            (patch.object(pl, '_gravar', side_effect=self.gravar), None),
                            (patch.object(pl, '_subir_drive', side_effect=self.subir), None),
                            (patch.object(pl, '_http', side_effect=AssertionError('Rede proibida no teste')), None)):
            alvo.start()
            self.addCleanup(alvo.stop)

    def ler(self, tabela, **params):
        rows = self.entregas if tabela == 'deliveries' else self.itens
        rows = copy.deepcopy(rows)
        for chave in ('id', 'short_id', 'delivery_id'):
            if chave in params:
                rows = [r for r in rows if str(r.get(chave)) == params[chave][3:]]
        if tabela == 'delivery_items':
            rows.sort(key=lambda i: (i['position'], i['id']))
        inicio = int(params.get('offset', 0))
        return rows[inicio:inicio + int(params.get('limit', 1000))]

    def gravar(self, metodo, tabela, corpo, filtro=''):
        self.escritas.append((metodo, tabela, copy.deepcopy(corpo), filtro))
        self.assertEqual(tabela, 'delivery_items')
        if metodo == 'POST':
            if not self.ignorar_insert:
                for i in corpo:
                    self.assertNotIn(i['id'], {x['id'] for x in self.itens})
                    self.itens.append(dict(i))
                    if self.falhar_insert:
                        self.falhar_insert = False
                        raise pl.ErroPanda('Timeout após inclusão parcial')
            return []  # A confirmação vem da leitura, inclusive quando a API omite a representação.
        self.assertEqual(metodo, 'DELETE')
        ids = filtro.split('id=in.(', 1)[1].rstrip(')').split(',')
        if not self.ignorar_delete:
            for i in list(self.itens):
                if i['id'] in ids:
                    self.itens.remove(i)
                    if self.falhar_delete:
                        self.falhar_delete = False
                        raise pl.ErroPanda('Timeout após exclusão parcial')
        return []

    def subir(self, caminho, cliente, titulo):
        self.uploads.append(Path(caminho).name)
        if len(self.uploads) == self.falhar_upload:
            self.falhar_upload = None
            raise pl.ErroPanda('Upload sem confirmação')
        return {'nome': Path(caminho).name, 'tipo': 'image/png',
                'link': f'https://drive/novo{len(self.uploads)}'}

    def trocar(self, **kw):
        return pe.substituir('1172', str(self.pasta), sim=True, **kw)

    def operacao(self):
        return pe.operacoes('1172')[0]

    def test_busca_por_titulo_cliente_numero_acentos_e_paginacao(self):
        self.assertEqual(len(pe.entregas('medo', 'peruibe')), 1)
        self.assertEqual(pe.entregas('1172')[0]['id'], self.eid)
        self.entregas.extend({'id': f'outro-{i}', 'title': 'Outro'} for i in range(205))
        self.assertEqual(len(pe.entregas()), 206)
        self.assertEqual(pe.entrega('11111111')['short_id'], 1172)
        self.assertEqual(pe.entrega(self.eid)['short_id'], 1172)

    def test_referencia_ambigua_nao_altera_nada(self):
        self.entregas.append({'id': 'outro', 'short_id': 20, 'title': 'Medo de pilotar'})
        with self.assertRaisesRegex(pl.ErroPanda, '2 entregas'):
            pe.entrega('medo')
        self.assertFalse(self.escritas)

    def test_previa_sem_escrita_sem_journal_sem_upload(self):
        r = pe.substituir('1172', str(self.pasta))
        self.assertTrue(r['previa'])
        self.assertEqual(r['arquivos'], ['slide_1.png', 'slide_2.png', 'slide_10.png'])
        self.assertFalse(self.uploads or self.escritas)
        self.assertFalse(pe.OPERACOES.exists())

    def test_substituicao_conferida_e_repeticao_sem_upload(self):
        antes = copy.deepcopy(self.entregas)
        r = self.trocar()
        self.assertEqual(r['fase'], 'concluida')
        self.assertEqual([i['position'] for i in self.itens], [0, 1, 2])
        self.assertEqual(self.entregas, antes)
        self.assertEqual([m for m, *_ in self.escritas], ['POST', 'DELETE'])
        self.assertIn('Drive são preservados', r['destino_antigos'])
        self.assertEqual(self.trocar()['operacao'], r['operacao'])
        self.assertEqual(len(self.uploads), 3)

    def test_upload_incerto_bloqueia_reenvio_e_preserva_antigos(self):
        self.falhar_upload = 2
        with self.assertRaises(pl.ErroPanda):
            self.trocar()
        self.assertEqual(self.itens, self.antigos)
        with self.assertRaisesRegex(pl.ErroPanda, 'repetir-incerto'):
            self.trocar()
        self.assertEqual(len(self.uploads), 2)
        self.assertFalse(self.escritas)
        self.trocar(repetir_incerto=True)
        self.assertEqual(self.uploads, ['slide_1.png', 'slide_2.png', 'slide_2.png', 'slide_10.png'])

    def test_inclusao_parcial_retomada_sem_upload_ou_anexo_duplicado(self):
        self.falhar_insert = True
        with self.assertRaises(pl.ErroPanda):
            self.trocar()
        self.assertEqual(len(self.itens), 4)
        self.assertTrue({i['id'] for i in self.antigos} <= {i['id'] for i in self.itens})
        self.trocar()
        self.assertEqual(len(self.itens), 3)
        self.assertEqual(len(self.uploads), 3)

    def test_exclusao_parcial_retomada_sem_reenvio(self):
        self.falhar_delete = True
        with self.assertRaises(pl.ErroPanda):
            self.trocar()
        self.assertEqual(self.operacao()['fase'], 'removendo')
        self.trocar()
        self.assertEqual(len(self.itens), 3)
        self.assertEqual(len(self.uploads), 3)

    def test_sistema_nao_aplica_inclusao_preserva_todos_antigos(self):
        self.ignorar_insert = True
        with self.assertRaisesRegex(pl.ErroPanda, 'não aplicou'):
            self.trocar()
        self.assertEqual(self.itens, self.antigos)
        self.assertFalse(any(m == 'DELETE' for m, *_ in self.escritas))

    def test_sistema_nao_aplica_exclusao_nao_declara_sucesso(self):
        self.ignorar_delete = True
        with self.assertRaisesRegex(pl.ErroPanda, 'não confirmou'):
            self.trocar()
        self.assertEqual(self.operacao()['fase'], 'removendo')
        self.ignorar_delete = False
        self.trocar()
        self.assertEqual(len(self.itens), 3)

    def test_arquivos_modificados_nao_reutilizam_uploads_antigos(self):
        self.ignorar_insert = True
        with self.assertRaises(pl.ErroPanda):
            self.trocar()
        (self.pasta / 'slide_1.png').write_bytes(b'correcao diferente')
        with self.assertRaisesRegex(pl.ErroPanda, 'arquivos diferentes'):
            self.trocar()
        self.assertEqual(len(self.uploads), 3)

    def test_alteracao_concorrente_bloqueia_descarte(self):
        self.falhar_insert = True
        with self.assertRaises(pl.ErroPanda):
            self.trocar()
        self.itens[0]['file_path'] = 'https://drive/alteracao-de-outra-pessoa'
        with self.assertRaisesRegex(pl.ErroPanda, 'outra operação'):
            self.trocar()
        self.assertFalse(any(m == 'DELETE' for m, *_ in self.escritas))

    def test_recuperacao_de_concluida_e_repeticao(self):
        r = self.trocar()
        previa = pe.recuperar('1172', r['operacao'])
        self.assertTrue(previa['previa'])
        pe.recuperar('1172', r['operacao'], sim=True)
        self.assertEqual({pe._chave(i) for i in self.itens}, {pe._chave(i) for i in self.antigos})
        pe.recuperar('1172', r['operacao'], sim=True)
        self.assertEqual(len(self.itens), 3)

    def test_recuperacao_interrompida_pode_ser_retomada(self):
        r = self.trocar()
        self.falhar_insert = True
        with self.assertRaises(pl.ErroPanda):
            pe.recuperar('1172', r['operacao'], sim=True)
        pe.recuperar('1172', r['operacao'], sim=True)
        self.assertEqual({pe._chave(i) for i in self.itens}, {pe._chave(i) for i in self.antigos})

    def test_trava_impede_segunda_operacao_na_mesma_entrega(self):
        with pe._trava(self.eid):
            with self.assertRaisesRegex(pl.ErroPanda, 'Já há'):
                self.trocar()

    def test_cli_json_separa_progresso_e_previa_sem_escrita(self):
        saida, progresso = io.StringIO(), io.StringIO()
        with patch.object(sys, 'argv', ['panda.py', 'substituir-artes', '1172', '--pasta', str(self.pasta), '--json']), \
                patch('sys.stdout', saida), patch('sys.stderr', progresso):
            self.assertEqual(panda.main(), 0)
        self.assertTrue(json.loads(saida.getvalue())['previa'])
        self.assertFalse(self.uploads or self.escritas)

    def test_cli_escrita_e_falha_tem_codigo_de_saida(self):
        with patch.object(sys, 'argv', ['panda.py', 'substituir-artes', '1172', '--pasta', str(self.pasta), '--sim', '--json']), \
                patch('sys.stdout', new_callable=io.StringIO) as saida, patch('sys.stderr', new_callable=io.StringIO):
            self.assertEqual(panda.main(), 0)
            self.assertEqual(json.loads(saida.getvalue())['fase'], 'concluida')
        with patch.object(sys, 'argv', ['panda.py', 'recuperar-entrega', '1172', '--operacao', '../invalido', '--sim']), \
                patch('sys.stdout', new_callable=io.StringIO):
            self.assertEqual(panda.main(), 1)

    def test_links_repetidos_nao_descartam_artes_anteriores(self):
        with patch.object(pl, '_subir_drive', return_value={'nome': 'arte.png', 'tipo': 'image/png', 'link': 'https://drive/repetido'}):
            with self.assertRaisesRegex(pl.ErroPanda, 'links repetidos'):
                self.trocar()
        self.assertEqual(self.itens, self.antigos)
        self.assertFalse(self.escritas)

    def test_operacao_nao_pode_ser_recuperada_em_outra_entrega(self):
        r = self.trocar()
        self.entregas.append({'id': 'outra', 'short_id': 1173, 'title': 'Outra entrega'})
        escritas = len(self.escritas)
        with self.assertRaisesRegex(pl.ErroPanda, 'outra entrega'):
            pe.recuperar('1173', r['operacao'], sim=True)
        self.assertEqual(len(self.escritas), escritas)

    def test_arquivo_vazio_e_pasta_ausente_sao_recusados(self):
        with self.assertRaises(pl.ErroPanda):
            pe.substituir('1172', None, sim=True)
        (self.pasta / 'slide_1.png').write_bytes(b'')
        with self.assertRaisesRegex(pl.ErroPanda, 'vazio'):
            self.trocar()
        self.assertFalse(self.uploads or self.escritas)


if __name__ == '__main__':
    unittest.main()
