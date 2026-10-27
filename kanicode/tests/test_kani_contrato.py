"""Restrições, alvos e cálculos, com fontes sintéticas e sem serviços externos."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import kani_contrato as contrato
import kani_etapas
import kani_modo as kani
from kani_estado import Estado
from kani_orquestracao import Orquestrador, Ferramenta, etapa


class ContratoTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir='D:/kanivete_testes'); self.addCleanup(self.tmp.cleanup)
        self.pasta=Path(self.tmp.name)
        self.dados=patch.object(kani,'DADOS',str(self.pasta/'estado')); self.dados.start(); self.addCleanup(self.dados.stop)

    def tarefa(self,pedido):
        return {'pedido':pedido,'pasta':str(self.pasta),'etapas':[],'informacoes':[]}

    def test_negacao_nao_cria_obrigacao_de_salvar(self):
        pedido='Leia entrega.txt. Não salve nenhum txt e não consulte tarefas.'
        t=self.tarefa(pedido)
        self.assertNotIn('salvar_texto',[n for n,_ in kani_etapas.pendentes(t)])
        self.assertNotIn('salvar_texto',kani_etapas.relevantes(pedido,{'ler_arquivo':None,'salvar_texto':None}))
        self.assertTrue(contrato.proibida(pedido,'salvar_texto',{'nome':'novo.txt'}))
        self.assertTrue(contrato.proibida(pedido,'todo_listar',{}))

    def test_negacoes_de_leitura_e_tarefa_tambem_bloqueiam(self):
        pedido='Não leia confidencial.txt. Não anote nenhuma tarefa. Não crie tarefa alguma.'
        self.assertTrue(contrato.proibida(pedido,'ler_arquivo',{'caminho':'confidencial.txt'}))
        self.assertTrue(contrato.proibida(pedido,'todo_salvar',{'titulo':'Indevida'}))
        self.assertNotIn('todo_salvar',[n for n,_ in kani_etapas.pendentes(self.tarefa(pedido))])
        self.assertTrue(contrato.proibida('Não crie arquivos.','salvar_texto',{}))
        self.assertFalse(contrato.proibida('Não crie tarefa, mas salve arquivo novo.txt.','salvar_texto',{'nome':'novo.txt'}))

    def test_negacao_preserva_pedido_positivo_e_nome_com_extensao(self):
        pedido='Não salve antigo.txt e salve novo.txt.'
        self.assertIn('salve novo.txt',contrato.pedido_positivo(pedido))
        self.assertFalse(contrato.proibida(pedido,'salvar_texto',{'nome':'novo.txt'}))
        self.assertTrue(contrato.proibida(pedido,'salvar_texto',{'nome':'antigo.txt'}))

    def test_proibicao_bloqueia_plano_antes_de_qualquer_efeito(self):
        gravar=Mock()
        o=kani_etapas.construir(kani,str(self.pasta),editar=True,permitidas=['salvar_texto'])
        o.ferramentas['salvar_texto']=Ferramenta('Escrita simulada',gravar,lambda a,b,c:{'ok':True},False)
        e=etapa('gravar','Gravar','salvar_texto',{'nome':'novo.txt'})
        t=self.tarefa('Não salve nenhum arquivo.'); t.update(id='x',etapas=[])
        with self.assertRaises(PermissionError): o.antes_etapa(t,'salvar_texto',e['args'])
        gravar.assert_not_called()

    def test_criar_saida_nao_exige_leitura_do_arquivo_novo(self):
        self.assertEqual(contrato.arquivos_pedidos(self.tarefa('Crie novo.txt com o texto combinado.')),[])
        self.assertEqual(contrato.arquivos_pedidos(self.tarefa('Leia fonte.txt e salve saida.txt.')),['fonte.txt'])
        self.assertEqual(contrato.arquivos_pedidos(self.tarefa('Preciso descobrir o prazo em fonte.txt.')),['fonte.txt'])
        self.assertEqual(contrato.arquivos_pedidos(self.tarefa('Escreva saida.txt com o resumo de fonte.txt.')),['fonte.txt'])

    def test_cada_documento_precisa_de_leitura(self):
        t=self.tarefa('Compare primeiro.txt e segundo.txt.')
        contrato.atualizar(t,'ler_arquivo',{'caminho':str(self.pasta/'primeiro.txt')},'um')
        self.assertEqual(contrato.fontes_faltantes(t),['segundo.txt'])

    def test_arquivos_homonimos_em_pastas_distintas_sao_alvos_distintos(self):
        t=self.tarefa('Compare a/briefing.txt e b/briefing.txt.')
        contrato.atualizar(t,'ler_arquivo',{'caminho':str(self.pasta/'a/briefing.txt')},'primeiro')
        self.assertEqual(contrato.fontes_faltantes(t),['b/briefing.txt'])

    def test_nome_com_espacos_citado_ou_ja_confirmado(self):
        t=self.tarefa('Leia o arquivo "Minha Entrega.txt" e resuma.')
        self.assertEqual(contrato.arquivos_pedidos(t),['Minha Entrega.txt'])
        t['pedido']='Leia o arquivo Minha Entrega.txt e resuma.'
        contrato.atualizar(t,'ler_arquivo',{'caminho':str(self.pasta/'Minha Entrega.txt')},'confirmado')
        self.assertEqual(contrato.fontes_faltantes(t),[])
        caminho=str(self.pasta/'com espaços'/'Minha Entrega.txt')
        t=self.tarefa('Leia o arquivo '+caminho)
        self.assertEqual(contrato.arquivos_pedidos(t),[caminho])
        contrato.atualizar(t,'ler_arquivo',{'caminho':caminho},'confirmado')
        self.assertEqual(contrato.fontes_faltantes(t),[])

    def test_referencia_so_e_seguida_quando_usuario_pede(self):
        t=self.tarefa('Leia catalogo.json e depois o documento apontado.')
        contrato.atualizar(t,'ler_arquivo',{'caminho':str(self.pasta/'catalogo.json')},json.dumps({'documento':'resumo.md'}))
        self.assertEqual(contrato.fontes_faltantes(t),[str(self.pasta/'resumo.md')])
        t['pedido']='Leia catalogo.json e informe o assunto.'
        self.assertEqual(contrato.fontes_faltantes(t),[])

    def test_status_so_pode_ser_avaliado_depois_da_fonte(self):
        t=self.tarefa('Consulte tarefas somente se o status for liberado.')
        self.assertIsNone(contrato.condicao(t))
        contrato.atualizar(t,'ler_arquivo',{'caminho':str(self.pasta/'decisao.json')},'{"status":"rascunho"}')
        self.assertFalse(contrato.condicao(t))
        t['fontes_lidas'][str(self.pasta/'decisao.json')]['conteudo']='{"status":"liberado"}'
        self.assertTrue(contrato.condicao(t))

    def test_condicao_desconhecida_nao_vira_verdadeira(self):
        self.assertIsNone(contrato.condicao(self.tarefa('Consulte tarefas somente se estiver tudo pronto.')))

    def test_ramificacao_nao_proibe_consulta_do_ramo_verdadeiro(self):
        pedido='Consulte tarefas somente se o status for liberado. Se não, não consulte tarefas.'
        self.assertFalse(contrato.proibida(pedido,'todo_listar',{}))

    def test_total_usa_decimal_e_todos_os_itens(self):
        dados={'itens':[{'quantidade':3,'valor_unitario':'0.1'},{'quantidade':2,'valor_unitario':'4.25'}]}
        self.assertEqual(contrato.total_itens(dados),'8.80')
        dados['itens'].append({'quantidade':2})
        self.assertIsNone(contrato.total_itens(dados))

    def test_total_recusa_booleanos_e_nao_finitos(self):
        for valor in (True,'NaN','Infinity','__import__("os")'):
            self.assertIsNone(contrato.total_itens({'itens':[{'quantidade':1,'valor_unitario':valor}]}))

    def test_resposta_precisa_usar_total_conferido(self):
        t=self.tarefa('Calcule o total dos itens.')
        contrato.atualizar(t,'ler_arquivo',{'caminho':str(self.pasta/'orcamento.json')},'{"itens":[{"quantidade":4,"valor_unitario":12.5}]}')
        self.assertFalse(contrato.conferir_total(t,'Total: 150.'))
        self.assertTrue(contrato.conferir_total(t,'Total do orçamento: R$ 50,00.'))

    def test_filtro_usa_cliente_e_situacao_dos_dados(self):
        dados={'tarefas':[{'titulo':'Um','cliente':'Cedro','concluida':False},{'titulo':'Dois','cliente':'Cedro','concluida':True},{'titulo':'Três','cliente':'Maré','concluida':False}]}
        filtrado=contrato.filtrar_tarefas('Informe pendências do cliente Cedro.',dados)
        self.assertEqual([t['titulo'] for t in filtrado['tarefas']],['Um'])
        self.assertEqual(len(dados['tarefas']),3)

    def test_escolha_por_numero_nao_confunde_arquivos_homonimos(self):
        t=self.tarefa('Procure o briefing e peça que eu escolha antes de ler. Não escolha por conta própria.')
        t['candidatos_consulta']=[str(self.pasta/'a/briefing.txt'),str(self.pasta/'b/briefing.txt')]
        self.assertIsNone(contrato.escolhida(t))
        t['informacoes']=['não sei ainda']
        self.assertIsNone(contrato.escolhida(t))
        t['informacoes']=['2']
        self.assertEqual(contrato.escolhida(t),t['candidatos_consulta'][1])

    def montar(self, executar):
        o=kani_etapas.construir(kani,str(self.pasta),editar=False,permitidas=['ler_arquivo','buscar_arquivos','responder','todo_listar'])
        o.estado=Estado(self.pasta/'estado'); o.memoria=lambda pedido:''
        o.inferir=Mock(return_value=({'etapas':[{'objetivo':'Informar fontes','acao':'responder','args':{'mensagem':'Fontes lidas e conferidas.'}}]},0))
        return o

    def test_executor_completa_duas_fontes_antes_de_responder(self):
        for nome in ('primeiro.txt','segundo.txt'): (self.pasta/nome).write_text(nome,encoding='utf-8')
        chamadas=[]
        def executar(n,a,p):
            chamadas.append(Path(a['caminho']).name)
            return Path(a['caminho']).read_text(encoding='utf-8')
        with patch.object(kani,'_executar',executar):
            o=self.montar(executar)
            r=o.rodar('Encontre primeiro.txt e segundo.txt nesta pasta, leia ambos e compare.',str(self.pasta))
        self.assertTrue(r['ok'],r['texto']); self.assertEqual(chamadas,['primeiro.txt','segundo.txt'])

    def test_indice_segue_alvo_e_recupera_falha_transitoria(self):
        (self.pasta/'indice.json').write_text('{"documento":"resultado.txt"}',encoding='utf-8')
        (self.pasta/'resultado.txt').write_text('Confirmado',encoding='utf-8')
        chamadas=[]
        def executar(n,a,p):
            nome=Path(a['caminho']).name; chamadas.append(nome)
            if nome=='resultado.txt' and chamadas.count(nome)==1: raise TimeoutError('Indisponibilidade temporária')
            return Path(a['caminho']).read_text(encoding='utf-8')
        with patch.object(kani,'_executar',executar):
            o=self.montar(executar)
            r=o.rodar('Encontre indice.json e leia o documento apontado; informe o resultado.',str(self.pasta))
        self.assertTrue(r['ok'],r['texto']); self.assertEqual(chamadas,['indice.json','resultado.txt','resultado.txt'])

    def test_ambiguidade_aguarda_escolha_e_retomada_le_apenas_o_escolhido(self):
        candidatos=[]
        for nome in ('a','b'):
            p=self.pasta/nome/'briefing.txt'; p.parent.mkdir(); p.write_text(nome,encoding='utf-8'); candidatos.append(str(p))
        lidos=[]
        def executar(n,a,p):
            if n=='buscar_arquivos': return json.dumps({'arquivos':[{'caminho':x} for x in candidatos],'parcial':False})
            lidos.append(a['caminho']); return Path(a['caminho']).read_text(encoding='utf-8')
        with patch.object(kani,'_executar',executar):
            o=self.montar(executar)
            r=o.rodar('Procure o briefing e peça que eu escolha antes de ler. Não escolha por conta própria.',str(self.pasta))
            self.assertEqual(r['status'],'aguardando_informacao'); self.assertEqual(lidos,[])
            r=o.rodar('',str(self.pasta),retomar=r['execucao'],informacao='2')
        self.assertTrue(r['ok'],r['texto']); self.assertEqual(lidos,[candidatos[1]])


if __name__=='__main__': unittest.main()
