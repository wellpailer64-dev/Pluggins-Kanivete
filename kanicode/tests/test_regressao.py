"""Verificador de regressão: o próprio bloqueio precisa falhar quando a evidência é insuficiente."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import regressao
import verificar


class RegressaoTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir='D:/kanivete_testes')
        self.addCleanup(self.temp.cleanup)
        self.raiz = Path(self.temp.name) / 'projeto'
        self.raiz.mkdir(); (self.raiz / 'tests').mkdir()
        for nome in ('teste_isolado.py', 'dados_app.py'):
            shutil.copyfile(verificar.RAIZ / nome, self.raiz / nome)
        for nome in ('mini.py', 'verificar.py', 'regressao.py'):
            (self.raiz / nome).write_text('valor = 1\n', encoding='utf-8')
        self.caso = self.raiz / 'tests/test_caso.py'
        self.caso.write_text('import unittest\nclass Caso(unittest.TestCase):\n def test_ok(self): self.assertEqual(2+2,4)\n', encoding='utf-8')
        self.m = {'versao': 1, 'centrais': ['mini.py'], 'grupos': [
            {'id': 'basico', 'comportamento': 'Sempre funciona', 'essencial': True, 'rapido': True,
             'arquivos': ['mini.py'], 'testes': ['tests/test_caso.py'], 'prazo_s': 10}]}
        self.salvar_catalogo()
        self.saida = Path(self.temp.name) / 'execucao'

    def salvar_catalogo(self):
        (self.raiz / regressao.CATALOGO).write_text(json.dumps(self.m), encoding='utf-8')

    def test_inventario_nao_executa_imports_e_lista_pendentes(self):
        (self.raiz / 'tests/test_desconhecido.py').write_text("raise RuntimeError('não importe')", encoding='utf-8')
        inv = regressao.inventario(self.raiz)
        self.assertEqual([i['tipo'] for i in inv], ['simulado', 'pendente'])
        sel = regressao.selecionar(self.raiz, 'completa')
        self.assertTrue(sel['lacunas'])

    def test_arquivo_central_seleciona_transversal_sem_duplicar(self):
        s = regressao.selecionar(self.raiz, alterados=['mini.py'])
        self.assertEqual(list(s['testes']), ['tests/test_caso.py'])
        self.assertTrue(any('transversal' in m for m in s['motivos']['basico']))
        with self.assertRaises(ValueError):
            regressao.selecionar(self.raiz, alterados=['../fora.py'])

    def grupo_adicional(self):
        (self.raiz / 'extra.py').write_text('valor=2', encoding='utf-8')
        (self.raiz / 'tests/test_extra.py').write_text('import unittest\nclass Extra(unittest.TestCase):\n def test_ok(self): pass\n', encoding='utf-8')
        self.m['grupos'].append({'id':'extra','comportamento':'Área adicional','essencial':False,'rapido':False,
                                 'arquivos':['extra.py'],'testes':['tests/test_extra.py'],'prazo_s':10})
        self.salvar_catalogo()

    def test_completa_inclui_grupo_nao_essencial_revisado(self):
        self.grupo_adicional()
        s = regressao.selecionar(self.raiz, 'completa')
        self.assertFalse(s['lacunas'])
        self.assertIn('tests/test_extra.py', s['testes'])

    def test_transversal_amplia_impacto_central_sem_virar_essencial(self):
        self.grupo_adicional()
        self.m['grupos'][-1]['transversal'] = True
        self.salvar_catalogo()
        self.assertNotIn('tests/test_extra.py', regressao.selecionar(self.raiz)['testes'])
        self.assertIn('tests/test_extra.py', regressao.selecionar(self.raiz, alterados=['mini.py'])['testes'])

    def test_integracao_real_e_explicitada_e_nao_executada(self):
        (self.raiz / 'tests/test_real.py').write_text('raise RuntimeError("não importe")', encoding='utf-8')
        self.m['classificacoes'] = {'tests/test_real.py':{'tipo':'real','motivo':'Integração externa'}}
        self.salvar_catalogo()
        s = regressao.selecionar(self.raiz, 'completa')
        self.assertFalse(s['lacunas'])
        self.assertNotIn('tests/test_real.py', s['testes'])
        self.assertEqual(s['excluidos'][0]['tipo'], 'real')
        s = regressao.selecionar(self.raiz, alterados=['tests/test_real.py'])
        self.assertTrue(s['lacunas'])

    def test_impacto_amplia_sem_inchar_bateria_essencial(self):
        self.grupo_adicional()
        self.assertNotIn('tests/test_extra.py', regressao.selecionar(self.raiz)['testes'])
        self.assertNotIn('tests/test_extra.py', regressao.selecionar(self.raiz, alterados=['mini.py'])['testes'])
        self.assertIn('tests/test_extra.py', regressao.selecionar(self.raiz, alterados=['extra.py'])['testes'])

    def test_arquivo_nao_classificado_e_dependencia_pendente_bloqueiam(self):
        (self.raiz / 'novo.py').write_text('x=1', encoding='utf-8')
        s = regressao.selecionar(self.raiz, alterados=['novo.py'])
        with patch.object(regressao, 'rodar_suite') as rodar:
            self.assertEqual(regressao.executar(self.raiz, s, self.saida, verificar.Scripts), 1)
        rodar.assert_not_called()
        (self.raiz / 'tests/test_outro.py').write_text('', encoding='utf-8')
        areas = {'exemplo': ('novo.py', 'tests/test_outro.py')}
        self.assertTrue(any('classificar' in l for l in regressao.selecionar(self.raiz, alterados=['novo.py'], areas=areas)['lacunas']))

    def test_catalogo_recusa_grupo_duplicado_e_teste_ausente(self):
        self.m['grupos'].append(dict(self.m['grupos'][0]))
        self.salvar_catalogo()
        with self.assertRaises(ValueError):
            regressao.carregar(self.raiz)
        self.m['grupos'].pop()
        self.m['grupos'][0]['testes'] = ['tests/test_inexistente.py']
        self.salvar_catalogo()
        with self.assertRaises(ValueError):
            regressao.carregar(self.raiz)

    def test_classificacao_nao_esconde_simulado_sem_grupo(self):
        self.m['classificacoes'] = {'tests/test_caso.py': {'tipo': 'simulado', 'motivo': 'tentativa inválida'}}
        self.salvar_catalogo()
        with self.assertRaises(ValueError):
            regressao.carregar(self.raiz)

    def test_suite_registra_casos_e_pasta_exclusiva(self):
        r = regressao.rodar_suite(self.raiz, self.saida, 'tests/test_caso.py', 10, 1)
        self.assertEqual(r['status'], 'aprovado', r)
        self.assertEqual(len(r['casos']), 1)
        a, env_a = regressao.ambiente_suite(self.saida, 'a')
        b, env_b = regressao.ambiente_suite(self.saida, 'b')
        self.assertNotEqual(env_a['APPDATA'], env_b['APPDATA'])
        self.assertTrue(Path(env_a['PYTHONPYCACHEPREFIX']).is_relative_to(a))
        self.assertTrue(Path(env_a['CEREBRO_PASTA_MODELO']).is_relative_to(a))
        self.assertNotEqual(env_a['CEREBRO_PASTA_MODELO'], env_b['CEREBRO_PASTA_MODELO'])

    def test_skip_nao_produz_aprovacao_falsa(self):
        self.caso.write_text('import unittest\nclass Caso(unittest.TestCase):\n @unittest.skip("recurso indisponível")\n def test_x(self): pass\n', encoding='utf-8')
        r = regressao.rodar_suite(self.raiz, self.saida, 'tests/test_caso.py', 10, 1)
        self.assertEqual(r['status'], 'incompleto', r)
        self.assertEqual(r['casos'][0]['status'], 'ignorado')

    def test_timeout_guarda_diagnostico_e_encerra_so_o_teste(self):
        self.caso.write_text('import unittest,time\nclass Caso(unittest.TestCase):\n def test_trava(self): time.sleep(60)\n', encoding='utf-8')
        r = regressao.rodar_suite(self.raiz, self.saida, 'tests/test_caso.py', 2, 1)
        self.assertEqual(r['status'], 'timeout')
        self.assertIn('test_trava', Path(r['eventos']).read_text(encoding='utf-8'))
        self.assertIn('Timeout', Path(r['log']).read_text(encoding='utf-8'))

    def test_saida_zero_antes_do_fim_nao_e_aprovacao(self):
        self.caso.write_text('import unittest,os\nclass Caso(unittest.TestCase):\n def test_a(self): pass\n def test_b(self): os._exit(0)\n', encoding='utf-8')
        r = regressao.rodar_suite(self.raiz, self.saida, 'tests/test_caso.py', 10, 1)
        self.assertEqual(r['status'], 'incompleto')

    def test_socketpair_do_asyncio_nao_libera_servicos_reais(self):
        self.caso.write_text('import unittest,socket,asyncio\nclass Caso(unittest.TestCase):\n'
                            ' def test_local(self):\n'
                            '  loop=asyncio.new_event_loop(); loop.close()\n'
                            '  with self.assertRaises(PermissionError): socket.socket().connect(("127.0.0.1",47613))\n', encoding='utf-8')
        r = regressao.rodar_suite(self.raiz, self.saida, 'tests/test_caso.py', 10, 1)
        self.assertEqual(r['status'], 'aprovado', r)

    def test_rede_e_escrita_externa_bloqueadas_no_filho(self):
        alvo = Path(self.temp.name) / 'fora_permitida.txt'
        # Usa um caminho do próprio projeto, fora da área de saídas, sem tentar escrever em dados reais.
        proibido = str(verificar.RAIZ / 'regressao_nao_deve_criar.txt')
        self.caso.write_text('import unittest,socket,os\nfrom pathlib import Path\nclass Caso(unittest.TestCase):\n'
                            ' def test_isolamento(self):\n'
                            '  with open(os.devnull, "w") as nulo: nulo.write("descartar sem criar arquivo")\n'
                            '  with self.assertRaises(PermissionError): socket.socket().connect(("127.0.0.1",47613))\n'
                            f'  with self.assertRaises(PermissionError): Path({proibido!r}).write_text("bloquear")\n', encoding='utf-8')
        r = regressao.rodar_suite(self.raiz, self.saida, 'tests/test_caso.py', 10, 1)
        self.assertEqual(r['status'], 'aprovado', r)
        self.assertFalse(Path(proibido).exists())

    def test_evidencia_aprovada_reprovada_e_desatualizada(self):
        s = regressao.selecionar(self.raiz)
        self.assertEqual(regressao.executar(self.raiz, s, self.saida, verificar.Scripts), 0)
        arq = self.saida / 'resultado.json'
        regressao.validar_liberacao(self.raiz, arq)
        r = json.loads(arq.read_text(encoding='utf-8'))
        r['status'] = 'falhou'
        arq.write_text(json.dumps(r), encoding='utf-8')
        with self.assertRaises(ValueError):
            regressao.validar_liberacao(self.raiz, arq)
        r['status'] = 'aprovado'
        completos = r['resultados']; r['resultados'] = []
        arq.write_text(json.dumps(r), encoding='utf-8')
        with self.assertRaises(ValueError):
            regressao.validar_liberacao(self.raiz, arq)
        r['resultados'] = completos; arq.write_text(json.dumps(r), encoding='utf-8')
        (self.raiz / 'mini.py').write_text('valor = 2', encoding='utf-8')
        with self.assertRaises(ValueError):
            regressao.validar_liberacao(self.raiz, arq)

    def test_reinicio_nao_ocorre_quando_bateria_falha(self):
        with patch.object(sys, 'argv', ['verificar.py','--bateria','essencial','--reiniciar']), \
             patch.object(regressao, 'executar', return_value=1), \
             patch('socket.create_connection') as conectar:
            self.assertEqual(verificar.main(), 1)
        conectar.assert_not_called()


if __name__ == '__main__':
    unittest.main()
