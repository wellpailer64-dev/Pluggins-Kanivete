"""Fila, prioridade e interrupção por aba sem executar modelos nem abrir aplicativos."""
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import kanicode
import sessao


class MensagensTest(unittest.TestCase):
    def setUp(self):
        threads_antes=set(threading.enumerate())
        self.temp = tempfile.TemporaryDirectory(dir=r'D:\kanivete_testes', prefix='mensagens_')
        self.addCleanup(self.temp.cleanup)
        self.base = self.temp.name
        for nome, valor in [('DADOS', self.base), ('ESTADO', str(Path(self.base) / 'estado.json'))]:
            p = patch.object(kanicode, nome, valor); p.start(); self.addCleanup(p.stop)
        with patch.object(kanicode, '_ler_estado', return_value={}):
            self.app = kanicode.App()
        self.app._pasta = Mock(return_value=self.base)
        self.app._para_janela = Mock()
        self.app._na_ui = Mock()
        self.app._bola_estado = Mock()
        self.app._bola_atividade = Mock()
        self.app._codex_voz = Mock()
        self.app._fala = None
        self.enviadas = []
        self.app._sessao = SimpleNamespace(ocupada=True, parar=Mock())
        def enviar(texto, imagens, **op):
            self.enviadas.append((self.app._ctx().id, texto, imagens))
            self.app._sessao = SimpleNamespace(ocupada=True, parar=Mock())
            return True
        def ajudante(quem, texto, **op):
            self.enviadas.append((self.app._ctx().id, texto, []))
            self.app._ajudante_ativo = quem
            return True
        self.app.enviar = Mock(side_effect=enviar)
        self.app.ajudante = Mock(side_effect=ajudante)
        def encerrar_entregas():
            limite=time.monotonic()+3
            while True:
                vivas=[t for t in threading.enumerate() if t not in threads_antes and t.is_alive()]
                if not vivas: return
                if time.monotonic()>=limite: self.fail('A entrega não terminou antes da limpeza do teste.')
                for t in vivas: t.join(.1)
        self.addCleanup(encerrar_entregas)

    def esperar(self, teste):
        limite = time.monotonic() + 3
        while time.monotonic() < limite:
            if teste():
                return
            threading.Event().wait(.01)
        self.fail('A fila não chegou ao estado esperado')

    def terminar(self):
        if self.app._sessao:
            self.app._sessao.ocupada = False
        self.app._ajudante_ativo = None
        self.app._evento({'t':'fim','erro':False})

    def test_quatro_motores_aguardam_sem_interromper(self):
        for quem in ('claude', 'codex', 'kani', 'pickle'):
            with self.subTest(quem=quem):
                self.app._ctx().quem = quem
                self.app._sessao = SimpleNamespace(ocupada=quem=='claude', parar=Mock())
                self.app._ajudante_ativo = quem if quem != 'claude' else None
                antes = len(self.enviadas)
                self.app.mensagem_enviar('id-'+quem, 'Próxima '+quem, quem=quem)
                self.assertEqual(len(self.enviadas), antes)
                self.app._sessao.parar.assert_not_called()
                self.terminar()
                self.esperar(lambda: len(self.enviadas)==antes+1 and not self.app._ctx().mensagens.enviando)
                self.assertEqual(self.enviadas[-1][1], 'Próxima '+quem)

    def test_fifo_e_entrega_unica_com_anexos(self):
        imagem = {'dados':'base64', 'tipo':'image/png', 'mini':'data:image/png;base64,QQ=='}
        self.app.mensagem_enviar('1','Primeira',[imagem])
        self.app.mensagem_enviar('1','Primeira',[imagem])
        self.app.mensagem_enviar('2','Segunda')
        self.assertEqual(len(self.app.mensagens_fila()), 2)
        self.terminar()
        self.esperar(lambda: len(self.enviadas)==1 and not self.app._ctx().mensagens.enviando)
        self.assertEqual(self.enviadas[0][2], [imagem])
        self.assertEqual([i['id'] for i in self.app.mensagens_fila()], ['2'])
        self.terminar()
        self.esperar(lambda: len(self.enviadas)==2 and not self.app._ctx().mensagens.enviando)
        self.app.mensagem_enviar('1','Primeira',[imagem])
        self.assertEqual([i[1] for i in self.enviadas], ['Primeira','Segunda'])


    def test_editar_preserva_ordem_anexos_e_sincroniza_pedido(self):
        imagem = {'dados':'base64','mini':'data:image/png;base64,AA=='}
        self.app.mensagem_enviar('1','Primeira',[imagem])
        self.app.mensagem_enviar('2','Segunda')
        self.assertTrue(self.app.mensagem_editar('1','  Primeira corrigida\ncom detalhe  '))
        fila = self.app._ctx().mensagens
        self.assertEqual([i['id'] for i in fila.itens], ['1','2'])
        self.assertEqual(fila.itens[0]['imagens'], [imagem])
        self.assertEqual(fila.itens[0]['texto'], 'Primeira corrigida\ncom detalhe')
        from tarefas_agente import TarefasAgente
        tarefa = TarefasAgente(self.base).registrar('1','1','Ignorado','claude',self.base)
        self.assertEqual(tarefa['texto'], 'Primeira corrigida\ncom detalhe')
        self.assertEqual(self.enviadas, [])
        self.terminar()
        self.esperar(lambda: bool(self.enviadas))
        self.assertEqual(self.enviadas[0][1:], ('Primeira corrigida\ncom detalhe', [imagem]))

    def test_editar_recusa_mensagem_em_entrega(self):
        self.app.mensagem_enviar('1','Original')
        fila = self.app._ctx().mensagens
        item = fila.proxima()
        self.assertFalse(self.app.mensagem_editar('1','Alterada'))
        self.assertEqual(item['texto'], 'Original')
        fila.concluir(item, True)
        self.assertFalse(self.app.mensagem_editar('1','Alterada'))
        self.assertFalse(self.app.mensagem_editar('inexistente','Alterada'))

    def test_editar_preserva_pausa_prioridade_e_erro(self):
        self.app.mensagem_enviar('1','Original')
        fila = self.app._ctx().mensagens
        fila.urgente('1')
        fila.pausada = True
        self.assertTrue(self.app.mensagem_editar('1','Corrigida'))
        self.assertTrue(fila.pausada)
        self.assertEqual(fila.itens[0]['estado'], 'urgente')
        fila.itens[0].update(estado='falha',erro='Falha anterior')
        self.assertTrue(self.app.mensagem_editar('1','Outra correção'))
        self.assertEqual(fila.itens[0]['erro'], 'Falha anterior')
        self.assertTrue(fila.pausada)

    def test_edicao_persiste_e_volta_pausada(self):
        from mensagens import Fila
        arquivo = str(Path(self.base) / 'fila_edicao.json')
        fila = Fila(arquivo)
        fila.adicionar({'id':'1','texto':'Antes','quem':'claude','pasta':self.base,'imagens':[]})
        fila.editar('1','Depois')
        restaurada = Fila(arquivo, restaurar=True)
        self.assertEqual(restaurada.listar()[0]['texto'], 'Depois')
        self.assertTrue(restaurada.pausada)

    def test_editar_vazio_so_com_anexo_e_pickle_valida_comando(self):
        self.app.mensagem_enviar('1','Original')
        with self.assertRaises(ValueError): self.app.mensagem_editar('1','   ')
        with self.assertRaises(ValueError): self.app.mensagem_editar('1',None)
        self.assertEqual(self.app.mensagens_fila()[0]['texto'], 'Original')
        self.app.mensagem_enviar('2','Legenda',[{'dados':'imagem'}])
        self.assertTrue(self.app.mensagem_editar('2',''))
        self.app.mensagem_enviar('3','Pedido',quem='pickle')
        with self.assertRaises(ValueError): self.app.mensagem_editar('3','/model outro')

    def test_editar_nao_toca_outra_aba(self):
        self.app.mensagem_enviar('1','Da aba um')
        self.app.aba_nova()
        self.assertFalse(self.app.mensagem_editar('1','Mudança indevida'))
        self.app.aba_ativar('1')
        self.assertEqual(self.app.mensagens_fila()[0]['texto'], 'Da aba um')

    def test_editar_comando_nao_deixa_pedido_antigo_no_agente(self):
        from tarefas_agente import TarefasAgente
        self.app.mensagem_enviar('1','Pedido original')
        self.app.mensagem_editar('1','/clear')
        tarefa = TarefasAgente(self.base).registrar('1','1','Ignorado','claude',self.base)
        self.assertEqual(tarefa['estado'], 'cancelada')
        self.app.mensagem_editar('1','Pedido revisado')
        tarefa = TarefasAgente(self.base).obter(tarefa['id'])
        self.assertEqual((tarefa['texto'],tarefa['estado']), ('Pedido revisado','pendente'))

    def test_cancelar_tira_da_fila_sem_entregar(self):
        self.app.mensagem_enviar('1','Fica')
        self.app.mensagem_enviar('2','Cancelada')
        self.assertTrue(self.app.mensagem_cancelar('2'))
        self.assertFalse(self.app.mensagem_cancelar('2'))
        self.assertEqual(self.app._para_janela.call_args.args[0]['estado'], 'cancelada')
        self.terminar()
        self.esperar(lambda: len(self.enviadas)==1 and not self.app._ctx().mensagens.enviando)
        self.terminar()
        threading.Event().wait(.1)
        self.assertEqual([i[1] for i in self.enviadas], ['Fica'])
        self.assertEqual(self.app.mensagens_fila(), [])

    def test_urgente_interrompe_uma_vez_e_preserva_resto_da_fila(self):
        self.app.mensagem_enviar('1','Normal')
        self.app.mensagem_enviar('2','Urgente')
        with patch.object(self.app, 'parar') as parar:
            self.assertTrue(self.app.mensagem_urgente('2'))
            self.assertTrue(self.app.mensagem_urgente('2'))
            parar.assert_called_once_with(preservar_fila=True)
        self.assertFalse(self.enviadas)
        self.terminar()
        self.esperar(lambda: len(self.enviadas)==1 and not self.app._ctx().mensagens.enviando)
        self.assertEqual(self.enviadas[0][1], 'Urgente')
        self.assertEqual(self.app.mensagens_fila()[0]['texto'], 'Normal')
        self.assertFalse(self.app.mensagem_urgente('2'))
        self.terminar()
        self.esperar(lambda: len(self.enviadas)==2 and not self.app._ctx().mensagens.enviando)
        self.assertEqual(self.enviadas[1][1], 'Normal')

    def test_fim_simultaneo_a_urgencia_nao_interrompe_a_nova_mensagem(self):
        self.app.mensagem_enviar('1','Urgente')
        original = self.app._fila_evento
        interrompeu_antes = []
        def notificar(item):
            original(item)
            if item['estado'] == 'urgente':
                self.terminar()
                self.esperar(lambda: len(self.enviadas)==1 and not self.app._ctx().mensagens.enviando)
        self.app._fila_evento = notificar
        with patch.object(self.app, 'parar', side_effect=lambda **k: interrompeu_antes.append(len(self.enviadas))):
            self.app.mensagem_urgente('1')
        self.assertEqual(interrompeu_antes, [0])
        self.assertEqual(len(self.enviadas), 1)

    def test_parar_pausa_fila_e_urgencia_explicita_a_retoma(self):
        self.app.mensagem_enviar('1','Aguardar')
        self.app.parar()
        self.terminar()
        self.assertFalse(self.enviadas)
        self.assertTrue(self.app._ctx().mensagens.pausada)
        self.app.mensagem_urgente('1')
        self.esperar(lambda: len(self.enviadas)==1 and not self.app._ctx().mensagens.enviando)

    def test_filas_de_abas_independentes(self):
        self.app.mensagem_enviar('1','Da aba um')
        self.app._abas['2'] = kanicode._Aba('2','claude')
        self.app._aba_ativa = '2'
        self.app._sessao = SimpleNamespace(ocupada=True, parar=Mock())
        self.app.mensagem_enviar('2','Da aba dois')
        self.assertFalse(self.app.mensagem_urgente('1'))
        self.terminar()
        self.esperar(lambda: len(self.enviadas)==1 and not self.app._ctx().mensagens.enviando)
        self.assertEqual(self.enviadas[0][:2], ('2','Da aba dois'))
        self.app._aba_ativa = '1'
        self.assertEqual(self.app.mensagens_fila()[0]['texto'], 'Da aba um')

    def test_urgencia_durante_o_envio_inicial_nao_se_perde(self):
        entrando, liberar = threading.Event(), threading.Event()
        self.app._sessao.ocupada = False
        original = self.app.enviar.side_effect
        def lento(*a, **k):
            entrando.set()
            self.assertTrue(liberar.wait(3))
            return original(*a, **k)
        self.app.enviar.side_effect = lento
        with patch.object(self.app, 'parar') as parar:
            self.app.mensagem_enviar('1','Envio em andamento')
            self.assertTrue(entrando.wait(3))
            self.app.mensagem_enviar('2','Urgente')
            self.app.mensagem_urgente('2')
            liberar.set()
            self.esperar(lambda: parar.called and not self.app._ctx().mensagens.enviando)
            parar.assert_called_once_with(preservar_fila=True)
        self.assertEqual(len(self.enviadas),1)

    def test_falha_pausa_sem_repetir_e_mudanca_de_pasta_nao_desvia(self):
        self.app.mensagem_enviar('1','Primeira')
        self.app.mensagem_enviar('2','Segunda')
        self.app._pasta.return_value = self.base + '/outro'
        self.terminar()
        self.esperar(lambda: self.app._ctx().mensagens.pausada)
        self.assertFalse(self.enviadas)
        self.assertEqual(self.app.mensagens_fila()[0]['estado'], 'falha')
        self.app._fila_tentar()
        self.assertFalse(self.enviadas)

    def test_interrupcao_antiga_nao_mata_o_turno_urgente(self):
        s = sessao.Sessao(self.base, self.base, Mock())
        s.proc = SimpleNamespace(stdin=Mock(), poll=Mock(return_value=None), kill=Mock())
        s.ocupada = True
        s._turno = 1
        with patch.object(sessao.threading, 'Thread') as thread:
            s.parar()
        espera = thread.call_args.kwargs['target']
        s._turno = 2
        with patch.object(sessao.time, 'sleep'):
            espera()
        s.proc.kill.assert_not_called()
        s._turno = 1
        with patch.object(sessao.time, 'sleep'):
            espera()
        s.proc.kill.assert_called_once()


if __name__ == '__main__':
    unittest.main(verbosity=2)
