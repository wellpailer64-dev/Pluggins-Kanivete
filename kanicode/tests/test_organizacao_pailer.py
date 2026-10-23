"""Preferências só em tarefas pertinentes, sem alterar os materiais observados."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import organizacao_pailer as organizacao
import codex_contexto
import kani_modo
import licoes


class OrganizacaoTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir='D:/kanivete_testes'); self.addCleanup(self.tmp.cleanup)
        self.perfil=Path(self.tmp.name)/'perfil.json'
        self.perfil.write_text(json.dumps({'contexto':'Manter o padrão local. Não aprender com pastas desorganizadas.'}),encoding='utf-8')
        p=patch.object(organizacao,'PERFIL',self.perfil);p.start();self.addCleanup(p.stop)
        p=patch.object(licoes,'DADOS',self.tmp.name);p.start();self.addCleanup(p.stop)

    def test_so_tarefas_pertinentes_recebem_preferencias(self):
        for pedido in ['Organize as pastas da cliente Camila','Salve o orçamento em PDF','Crie uma pasta para o cliente']:
            self.assertIn('padrão local',organizacao.contexto(pedido))
        for pedido in ['Bom dia','Qual o clima?','Reorganize o código fonte','Corrija o módulo de arquivos']:
            self.assertEqual(organizacao.contexto(pedido),'')

    def test_perfil_ausente_ou_invalido_nao_inventa_preferencias(self):
        self.perfil.write_text('json quebrado',encoding='utf-8')
        self.assertEqual(organizacao.contexto('Organize as pastas da cliente'),'')
        self.perfil.unlink()
        self.assertEqual(organizacao.contexto('Organize as pastas da cliente'),'')

    def test_contexto_nao_altera_o_perfil(self):
        antes=self.perfil.read_bytes(); organizacao.contexto('Organize arquivos do cliente')
        self.assertEqual(antes,self.perfil.read_bytes())

    def test_licoes_compartilha_preferencias_entre_projetos(self):
        r=licoes.anexo(self.tmp.name,'Organize as pastas do cliente')
        self.assertIn('padrão local',r)
        self.assertEqual(licoes.anexo(self.tmp.name,'Qual a previsão do tempo?'),'')

    def test_codex_recebe_em_nova_sessao_e_retomada(self):
        for retomar in [False,True]:
            r=codex_contexto.preparar('Organize os arquivos da cliente',self.tmp.name,True,retomar)
            self.assertEqual(r.count('PREFERÊNCIAS DE ORGANIZAÇÃO DO PAILER'),1)

    def test_regras_no_pedido_nao_ocultam_preferencias(self):
        r=codex_contexto.preparar('Organize arquivos do cliente. REGRAS DESTE PROJETO: não apagar.',self.tmp.name,True,False)
        self.assertIn('padrão local',r)

    def test_nao_duplica_perfil_ja_incluido_pela_equipe(self):
        tarefa='Organize arquivos do cliente'+organizacao.contexto('Organize arquivos do cliente')
        r=codex_contexto.preparar(tarefa,self.tmp.name,True,False)
        self.assertEqual(r.count('PREFERÊNCIAS DE ORGANIZAÇÃO DO PAILER'),1)

    def test_kani_recebe_perfil_no_contexto_sem_organizar_por_conta_propria(self):
        capturados=[]
        def chamar(msgs,porta):
            capturados.append(msgs[0]['content'])
            return {'acao':'responder','args':{'mensagem':'Qual pasta você quer organizar?'},'pensamento':''},1
        with patch.object(kani_modo.ajudantes,'_kani_subir',return_value=123),patch.object(kani_modo,'_chamar',side_effect=chamar),patch.object(kani_modo,'notas',return_value=''),patch.object(kani_modo,'_dica_habilidades',return_value=''),patch.object(kani_modo,'_executar') as executar:
            r=kani_modo._rodar_pedido('Organize as pastas da cliente',self.tmp.name,Mock())
        self.assertTrue(r['ok'],r)
        self.assertIn('não autorização para reorganizar',capturados[0])
        self.assertIn('padrão local',capturados[0]);executar.assert_not_called()


if __name__=='__main__':unittest.main()
