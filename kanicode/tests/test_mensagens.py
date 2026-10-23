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
