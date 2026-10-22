"""Agente Big Pickle com decisões simuladas; nunca conecta ao app do usuário."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bigpickle_modo as bp
import kani_modo
import kanicode
import opencode_mvp as oc


def decisao(acao, **args):
    return json.dumps({"acao": acao, "args": args}), 3


class BigPickleModoTest(unittest.TestCase):
    def test_consulta_resultado_e_responde_sem_carregar_modelo_local(self):
        eventos = []
        with patch.object(oc, 'conversar', side_effect=[decisao('espaco_disco'), decisao('responder', mensagem='D tem espaço.')]) as chamar, \
             patch.object(kani_modo, '_executar', return_value='D: 12 GB livres') as executar, \
             patch.object(kani_modo.ajudantes, '_kani_subir') as local, patch.object(kani_modo, 'notas') as notas:
            r = bp.rodar('Consulte D', r'D:\kanivete_testes', eventos.append,
                         historico=[{'role': 'user', 'content': 'Meu nome é Pailer.'}])
        self.assertTrue(r['ok'])
        self.assertEqual(r['tokens'], 6)
        executar.assert_called_once_with('espaco_disco', {}, r'D:\kanivete_testes')
        local.assert_not_called()
        notas.assert_not_called()
        self.assertIn('D: 12 GB livres', str(chamar.call_args.args[0]))
        self.assertIn('Meu nome é Pailer.', str(chamar.call_args.args[0]))

    def test_prompt_agente_separado_do_teste_de_conversa(self):
        with tempfile.TemporaryDirectory(dir=r'D:\kanivete_testes') as pasta, patch.object(oc, 'BASE', Path(pasta)):
            conversa = json.loads(oc.ambiente()['OPENCODE_CONFIG_CONTENT'])
            agente = json.loads(oc.ambiente(agente=True)['OPENCODE_CONFIG_CONTENT'])
        self.assertIn('Somente conversa', conversa['agent']['kanicode-mvp']['prompt'])
        self.assertNotIn('Somente conversa', agente['agent']['kanicode-mvp']['prompt'])
        self.assertIn('PONTE KANICODE', agente['agent']['kanicode-mvp']['prompt'])
        self.assertEqual(agente['permission'], {'*': 'deny', 'read': 'ask'})
        self.assertEqual(agente['agent']['kanicode-mvp']['permission'], agente['permission'])

    def test_abertura_sem_observacao_e_corrigida(self):
        respostas = [decisao('responder', mensagem='O KANIVETE já está aberto.'),
                     decisao('abrir_kanivete'), decisao('responder', mensagem='Encontrei a janela aberta.')]
        with patch.object(oc, 'conversar', side_effect=respostas), patch.object(kani_modo, '_executar', return_value='CONFIRMADO: janela aberta') as executar:
            r = bp.rodar('Pode abrir o KANIVETE para mim?', '.', lambda ev: None)
        self.assertTrue(r['ok'])
        executar.assert_called_once_with('abrir_kanivete', {}, '.')

    def test_abertura_nao_observada_nunca_vira_sucesso(self):
        with patch.object(oc, 'conversar', return_value=decisao('responder', mensagem='O KANIVETE já está aberto.')) as chamar:
            r = bp.rodar('Pode abrir o KANIVETE para mim?', '.', lambda ev: None)
        self.assertFalse(r['ok'])
        self.assertEqual(chamar.call_count, 2)

    def test_abrir_app_confere_janela_e_nao_duplica(self):
        with patch.object(kani_modo, 'pedido_atual', ['Pode abrir o KANIVETE?']), \
             patch.object(kani_modo, '_janelas', return_value=[('CaniveteDoPailer.exe', 'KANIVETE', 123)]), \
             patch.object(kani_modo, '_garantir_kanivete') as iniciar:
            self.assertIn('CONFIRMADO', kani_modo._executar('abrir_kanivete', {}, '.'))
            iniciar.assert_not_called()
        with patch.object(kani_modo, 'pedido_atual', ['Pode abrir o KANIVETE?']), \
             patch.object(kani_modo, '_janelas', return_value=[]), \
             patch.object(kani_modo, '_garantir_kanivete', return_value='abri o KANIVETE') as iniciar:
            self.assertEqual(kani_modo._executar('abrir_kanivete', {}, '.'), 'abri o KANIVETE')
            iniciar.assert_called_once()

    def test_abrir_app_exige_pedido_e_nao_entra_em_planejar(self):
        with patch.object(kani_modo, 'pedido_atual', ['O KANIVETE está aberto?']), patch.object(kani_modo, '_janelas') as janelas:
            self.assertTrue(kani_modo._executar('abrir_kanivete', {}, '.').startswith('NÃO FEITO'))
            janelas.assert_not_called()
        with patch.object(oc, 'conversar', return_value=decisao('abrir_kanivete')), patch.object(kani_modo, '_executar') as executar:
            self.assertFalse(bp.rodar('Abra o KANIVETE', '.', lambda ev: None, editar=False)['ok'])
            executar.assert_not_called()

    def test_ferramenta_nao_liberada_nunca_executa(self):
        for acao in ('apagar_arquivo', 'fechar_kanivete', 'salvar_texto', 'inventada'):
            with patch.object(oc, 'conversar', return_value=decisao(acao)), patch.object(kani_modo, '_executar') as executar:
                r = bp.rodar('Faça isso', '.', lambda ev: None)
            self.assertFalse(r['ok'])
            executar.assert_not_called()

    def test_planejar_nao_abre_ferramenta(self):
        with patch.object(oc, 'conversar', return_value=decisao('abrir_ferramenta', nome='photo')), patch.object(kani_modo, '_executar') as executar:
            r = bp.rodar('Planeje a abertura', '.', lambda ev: None, editar=False)
        self.assertFalse(r['ok'])
        executar.assert_not_called()

    def test_json_invalido_nao_executa(self):
        for texto in ('Eu já fiz!', '[]', '{"acao":"espaco_disco","args":[]}'):
            with patch.object(oc, 'conversar', return_value=(texto, 1)), patch.object(kani_modo, '_executar') as executar:
                self.assertFalse(bp.rodar('Teste', '.', lambda ev: None)['ok'])
                executar.assert_not_called()

    def test_cancelar_apos_resposta_impede_acao(self):
        parar = threading.Event()
        def chamar(*args, **kwargs):
            parar.set()
            return decisao('espaco_disco')
        with patch.object(oc, 'conversar', side_effect=chamar), patch.object(kani_modo, '_executar') as executar:
            r = bp.rodar('Teste', '.', lambda ev: None, parar=parar)
        self.assertEqual(r['texto'], 'Parei.')
        executar.assert_not_called()

    def test_encaminhamento_nao_dispara_outro_agente(self):
        with patch.object(oc, 'conversar', return_value=decisao('passar_para_claude', motivo='Falta edição.')):
            r = bp.rodar('Edite o vídeo', '.', lambda ev: None)
        self.assertFalse(r.get('claude'))
        self.assertIn('Claude ou o Codex', r['texto'])
        self.assertIn('Falta edição', r['texto'])
        self.assertLess(len(r['texto']), 220)   # a falha numa frase; o relatório vai para o andamento

    def test_transporte_envia_contexto_por_stdin(self):
        processo = Mock()
        processo.communicate.return_value = ('{"type":"text","part":{"text":"OK"}}', '')
        processo.returncode = 0
        processo.poll.return_value = 0
        with tempfile.TemporaryDirectory(dir=r'D:\kanivete_testes') as pasta:
            with patch.object(oc, 'BASE', Path(pasta)), patch.object(oc, 'executavel', return_value='opencode.exe'), \
                 patch.object(oc.subprocess, 'Popen', return_value=processo) as iniciar:
                self.assertEqual(oc.conversar([{'role': 'user', 'content': 'Olá & teste'}])[0], 'OK')
        comando = iniciar.call_args.args[0]
        self.assertIn('--no-auto', comando)
        self.assertNotIn('Olá & teste', comando)
        self.assertIn('Olá & teste', processo.communicate.call_args.kwargs['input'])

    def test_cancelamento_encerra_somente_processo_criado(self):
        parar = threading.Event()
        processo = Mock()
        processo.poll.return_value = None
        def comunicar(**kwargs):
            if kwargs.get('input'):
                parar.set()
                raise subprocess.TimeoutExpired('opencode', 0.25)
            return '', ''
        processo.communicate.side_effect = comunicar
        with tempfile.TemporaryDirectory(dir=r'D:\kanivete_testes') as pasta:
            with patch.object(oc, 'BASE', Path(pasta)), patch.object(oc, 'executavel', return_value='opencode.exe'), \
                 patch.object(oc.subprocess, 'Popen', return_value=processo):
                with self.assertRaises(InterruptedError):
                    oc.conversar([{'role': 'user', 'content': 'Teste'}], parar)
        processo.kill.assert_called_once()
        self.assertFalse(oc._TRAVA.locked())


class BigPickleAppTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=r'D:\kanivete_testes')
        self.addCleanup(self.temp.cleanup)
        self.pasta = self.temp.name
        for nome, valor in (('DADOS', self.pasta), ('ESTADO', str(Path(self.pasta) / 'estado.json'))):
            p = patch.object(kanicode, nome, valor)
            p.start()
            self.addCleanup(p.stop)
        kanicode._gravar_estado(quem='pickle', projeto=self.pasta)
        self.app = kanicode.App()
        self.fim = threading.Event()
        self.app._bola_estado = lambda estado: self.fim.set() if estado != 'trabalhando' else None
        self.app._bola_atividade = Mock()
        self.app._na_ui = Mock()
        self.app._evento = Mock()
        self.app._para_janela = Mock()

    def pedir(self):
        self.fim.clear()
        import pickle_agente   # código e conversa vão para o OpenCode nativo (pickle_agente); app, para a ponte
        with patch.object(pickle_agente, 'rodar', return_value={'ok': True, 'texto': 'Resposta BP', 'tokens': 7}) as motor:
            self.app.ajudante('pickle', 'Pedido BP')
            self.assertTrue(self.fim.wait(3))
        return motor

    def test_selecao_historico_reabertura_e_nova(self):
        self.app.quem('pickle')
        self.assertEqual(self.app.info()['quem'], 'pickle')
        self.pedir()
        arquivo = Path(self.app._pickle_arquivo(self.pasta))
        self.assertEqual(self.app.historico()[-1]['texto'], 'Resposta BP')
        self.assertEqual(kanicode.App().historico()[-1]['quem'], 'pickle')
        self.app.quem('kani')
        self.assertEqual(self.app.historico(), [])
        self.app.quem('pickle')
        self.assertEqual(self.app.historico()[-1]['texto'], 'Resposta BP')
        self.app.nova()
        self.assertEqual(self.app.historico(), [])
        self.assertTrue(arquivo.exists())

    def test_contexto_por_pasta_e_modo_planejar(self):
        self.pedir()
        self.app._modo = 'plan'
        motor = self.pedir()
        self.assertFalse(motor.call_args.args[-1])
        self.assertIn('Resposta BP', str(motor.call_args.args[3]))
        kanicode._gravar_estado(projeto=str(Path(self.pasta) / 'outra'))
        self.assertEqual(self.app.historico(), [])


if __name__ == '__main__':
    unittest.main()
