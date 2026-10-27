"""To-do dos agentes: origem durável, pendências e conclusão explícita, com dados isolados no D."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import tarefas
import tarefas_agente as ta
import kanicode


class TarefasAgenteTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir='D:/kanivete_testes'); self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name); self.repo=ta.TarefasAgente(self.base)

    def pedido(self,aba='1',id='mensagem-1'):
        return self.repo.registrar(aba,id,'Ajustar o streaming.\nDepois conferir no celular.','codex',str(self.base))

    def test_origem_persistente_sem_duplicar_e_lista_pessoal_separada(self):
        a=self.pedido(); b=self.pedido()
        self.assertEqual(a['id'],b['id'])
        self.assertEqual(len(self.repo.listar()),1)
        self.assertEqual(ta.TarefasAgente(self.base).obter(a['id'])['texto'],a['texto'])
        tarefas.Tarefas(self.base).salvar('Comprar café')
        self.assertEqual(len(self.repo.listar()),1)
        self.assertNotIn('texto',self.repo.resumo()[0])
        self.assertNotEqual(self.pedido('2')['id'],a['id'])

    def test_finalizadas_somem_depois_de_24h(self):
        velha=self.pedido(id='m1'); nova=self.pedido(id='m2'); aberta=self.pedido(id='m3')
        self.repo.estado(velha['id'],'concluida','ok'); self.repo.estado(nova['id'],'cancelada','x')
        self.repo.estado(aberta['id'],'falha','caiu')
        dados=json.loads((self.base/'tarefas_agente.json').read_text(encoding='utf-8'))
        for i in dados:
            if i['id'] in (velha['id'],aberta['id']): i['atualizado']='2020-01-01T00:00:00'
        (self.base/'tarefas_agente.json').write_text(json.dumps(dados),encoding='utf-8')
        ids={i['id'] for i in self.repo.listar()}
        self.assertEqual(ids,{nova['id'],aberta['id']})
        self.assertEqual(len(json.loads((self.base/'tarefas_agente.json').read_text(encoding='utf-8'))),2)

    def test_fim_sem_erro_nao_prova_conclusao_e_adiamento_nao_e_sobrescrito(self):
        a=self.pedido()
        self.repo.estado(a['id'],'em_andamento',automatico=True)
        self.repo.estado(a['id'],'adiada','Falta testar no aparelho.')
        self.repo.estado(a['id'],'a_conferir',automatico=True)
        self.assertEqual(self.repo.obter(a['id'])['estado'],'adiada')
        self.repo.estado(a['id'],'concluida','Conferido no aparelho.')
        self.repo.estado(a['id'],'falha',automatico=True)
        self.assertTrue(self.repo.obter(a['id'])['concluida'])

    def test_pendencia_herda_pedido_e_nao_some_com_conclusao_do_pai(self):
        a=self.pedido(); b=self.repo.anotar(a['id'],'Conferir no celular')
        self.assertEqual(self.repo.anotar(a['id'],'Conferir no celular')['id'],b['id'])
        self.repo.estado(a['id'],'concluida','Implementação conferida.')
        self.assertFalse(self.repo.obter(b['id'])['concluida'])
        self.assertEqual(self.repo.obter(b['id'])['mensagem_id'],a['mensagem_id'])
        self.assertEqual(self.repo.obter(b['id'])['texto'],a['texto'])
        self.repo.estado(b['id'],'concluida','Teste executado.')
        self.assertTrue(self.repo.obter(b['id'])['concluida'])

    def test_reinicio_e_arquivo_corrompido_preservam_pendencia(self):
        a=self.pedido(); self.repo.estado(a['id'],'em_andamento')
        self.repo.recuperar()
        self.assertEqual(self.repo.obter(a['id'])['estado'],'falha')
        arq=self.base/'tarefas_agente.json'; arq.write_text('{invalido',encoding='utf-8')
        with self.assertRaises(ValueError): self.pedido(id='outra')
        self.assertEqual(arq.read_text(encoding='utf-8'),'{invalido')

    def test_pendencia_fica_com_a_aba_e_o_modelo_responsaveis(self):
        a=self.pedido(aba='71',id='m1'); self.repo.estado(a['id'],'adiada','falta física')
        with patch.object(ta,'TarefasAgente',return_value=self.repo):
            self.assertIn(a['id'],ta.contexto(str(self.base),'outro',aba='71',agente='codex'))
            self.assertNotIn(a['id'],ta.contexto(str(self.base),'outro',aba='74',agente='codex'))
            self.assertNotIn(a['id'],ta.contexto(str(self.base),'outro',aba='71',agente='claude'))

    def test_falha_antiga_cai_quando_pedido_novo_da_aba_e_atendido(self):
        velho=self.pedido(id='m1'); self.repo.estado(velho['id'],'falha','caiu')
        novo=self.pedido(id='m2'); self.repo.estado(novo['id'],'a_conferir','ok')
        self.assertEqual(self.repo.obter(velho['id'])['estado'],'cancelada')

    def test_contexto_curto_e_acoes_exigem_motivo(self):
        a=self.pedido(); self.repo.estado(a['id'],'em_andamento')
        classe=ta.TarefasAgente
        with patch.object(ta,'TarefasAgente',return_value=self.repo):
            texto=ta.contexto(str(self.base),a['texto'])
            self.assertIn(a['id'],texto)
            self.assertLess(len(texto),1800)
            with self.assertRaises(ValueError): ta.acao({'acao':'concluir','ref':a['id']})
            ta.acao({'acao':'concluir','ref':a['id'],'motivo':'Testado.'})
        self.assertTrue(classe(self.base).obter(a['id'])['concluida'])


class IntegracaoAgenteTest(unittest.TestCase):
    # Os métodos de armazenamento ficam na classe anterior; aqui só se exercitam os ganchos do app.
    def setUp(self):
        TarefasAgenteTest.setUp(self)
        with patch.object(kanicode,'DADOS',str(self.base)),patch.object(kanicode,'_ler_estado',return_value={}):
            self.app=kanicode.App()
        self.patch=patch.object(kanicode,'DADOS',str(self.base));self.patch.start();self.addCleanup(self.patch.stop)
        self.app._pasta=Mock(return_value=str(self.base));self.app._para_janela=Mock()
        self.app._fila_tentar=Mock();self.app._na_ui=Mock();self.app._bola_estado=Mock();self.app._bola_atividade=Mock()
        self.app._fala=None

    def test_fila_entrega_falha_conclusao_e_reabertura(self):
        self.app.mensagem_enviar('m1','Corrigir o botão',quem='codex')
        item=self.app._ctx().mensagens.itens[0]
        registro=self.repo.listar()[0]
        self.assertEqual(registro['mensagem_id'],'m1')
        item['estado']='enviando';self.app._fila_evento(item)
        item['estado']='enviada';self.app._fila_evento(item)
        self.assertFalse(self.repo.obter(registro['id'])['concluida'])
        self.app._todo_agente_finalizar(True,'Resposta enviada.')
        self.assertEqual(self.repo.obter(registro['id'])['estado'],'a_conferir')
        self.repo.estado(registro['id'],'concluida','Botão testado.')
        self.assertTrue(self.app.todo_agente_listar()[0]['concluida'])
        self.app.todo_agente_concluir(registro['id'],False)
        self.assertFalse(self.repo.obter(registro['id'])['concluida'])

    def test_interrupcao_nao_conclui_e_cancelamento_nao_vira_trabalho_feito(self):
        self.app.mensagem_enviar('m1','Corrigir o botão',quem='codex')
        item=self.app._ctx().mensagens.itens[0]
        item['estado']='enviando';self.app._fila_evento(item)
        self.app.parar()
        self.assertEqual(self.repo.listar()[0]['estado'],'falha')
        self.app.mensagem_enviar('m2','Ver depois',quem='codex')
        i=self.app._ctx().mensagens.itens[-1];i['estado']='cancelada';self.app._fila_evento(i)
        self.assertEqual(self.repo.listar()[-1]['estado'],'cancelada')
        self.assertFalse(self.repo.listar()[-1]['concluida'])

    def test_fila_ja_persistida_entra_no_todo_sem_executar(self):
        self.app._ctx().mensagens.adicionar({'id':'antiga','texto':'Pedido pendente','quem':'claude','pasta':str(self.base),'imagens':[]})
        self.app._todo_agente_restaurar()
        self.assertEqual(self.repo.listar()[0]['mensagem_id'],'antiga')
        self.app._todo_agente_restaurar()
        self.assertEqual(len(self.repo.listar()),1)
        self.app._fila_tentar.assert_not_called()


if __name__=='__main__': unittest.main()
