"""Drive e PCs sintéticos no D; nenhum acesso à conta ou aos dados reais."""
import contextlib
import copy
import io
import json
import tempfile
import threading
import unittest
from email.parser import BytesParser
from email.policy import default
from pathlib import Path
from unittest.mock import patch

import perfil_nuvem as nuvem
import perfil_portatil as perfil


class DriveFalso:
    def __init__(self):
        self.email='teste@example.com';self.arquivos={};self.conteudos={};self.n=0
        self.trava=threading.RLock()
    def _lock(self): return self.trava
    def _exigir_escrita(self): return 'token-so-do-teste'
    def _pedido(self, metodo, caminho, access, corpo=None, **params):
        if caminho=='about': return {'user':{'emailAddress':self.email}}
        if metodo=='POST': return self.adicionar(corpo)
        arquivos=list(self.arquivos.values());q=params['q']
        if "'root' in parents" in q: arquivos=[a for a in arquivos if a['mimeType']=='application/vnd.google-apps.folder']
        else: arquivos=[a for a in arquivos if a['mimeType']=='application/json']
        if "name = 'acesso-kanicode.json'" in q: arquivos=[a for a in arquivos if a['name']=='acesso-kanicode.json']
        return {'files':copy.deepcopy(arquivos)}
    def adicionar(self, meta):
        self.n+=1;id='arquivo_'+str(self.n);self.arquivos[id]=dict(meta,id=id);return {'id':id}
    def abrir(self, req):
        if req.get_method()=='GET':
            id=req.full_url.split('/files/')[1].split('?')[0]
            return contextlib.closing(io.BytesIO(self.conteudos[id]))
        cabecalho=('Content-Type: '+req.get_header('Content-type')+'\r\nMIME-Version: 1.0\r\n\r\n').encode()
        partes=list(BytesParser(policy=default).parsebytes(cabecalho+req.data).iter_parts())
        meta=json.loads(partes[0].get_payload(decode=True));conteudo=partes[1].get_payload(decode=True)
        r=self.adicionar(meta);self.conteudos[r['id']]=conteudo
        return contextlib.closing(io.BytesIO(json.dumps(r).encode()))


class PerfilNuvemTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir='D:/kanivete_testes');self.addCleanup(self.temp.cleanup)
        self.raiz=Path(self.temp.name);self.app=self.raiz/'app';self.app.mkdir()
        self.drive=DriveFalso();self.a=self.pc('a');self.b=self.pc('b')
        self.mock=patch.object(nuvem,'_abrir',side_effect=self.drive.abrir);self.mock.start();self.addCleanup(self.mock.stop)
    def pc(self, nome):
        dados=self.raiz/nome;(dados/'perfil').mkdir(parents=True)
        perfil._gravar(dados/'perfil/usuario.json',json.dumps({'email':'teste@example.com','nome':'Pessoa'}))
        return nuvem.PerfilNuvem(self.drive,dados,self.app)
    def restaurar(self, pc):
        return lambda t,c,p: perfil.aplicar(t,c,p,pc.dados,self.app)
    def executar(self, pc, acao='sincronizar', **kw):
        from perfil_acesso import AcessoPerfil
        acesso=AcessoPerfil(pc)
        if not acesso.status()['autenticado']:
            cadastrado=any(a['name']=='acesso-kanicode.json' for a in self.drive.arquivos.values())
            acesso.executar('entrar' if cadastrado else 'cadastrar',{'email':pc._email(),'senha':'senha-ficticia-para-testes','confirmacao':'senha-ficticia-para-testes','lembrar':False})
        return pc.executar(acao,self.restaurar(pc),**kw)
    def nota(self, pc, texto): (pc.dados/'kani_notas.md').write_text(texto,encoding='utf-8')
    def importar(self, pc):
        r=self.executar(pc,'ativar');id=r['versoes'][0]['id']
        t=self.executar(pc,'conferir',escolha=id)['texto']
        token=perfil.previa(t,pc.dados,self.app)['conferencia']
        return self.executar(pc,'restaurar',escolha=id,conferencia=token,politica='substituir')
    def test_primeiro_envio_persistencia_e_pausa(self):
        self.nota(self.a,'Jeito de trabalhar');r=self.executar(self.a,'ativar')
        self.assertTrue(r['ativo']);self.assertEqual(sum(a['name'].startswith('perfil-') for a in self.drive.arquivos.values()),1)
        self.assertEqual(next(iter(self.drive.arquivos.values()))['name'],'KaniCode')
        self.assertNotIn('token-so-do-teste',next(iter(self.drive.conteudos.values())).decode())
        self.executar(self.a);self.assertEqual(sum(a['name'].startswith('perfil-') for a in self.drive.arquivos.values()),1)
        self.executar(self.a,'pausar');self.nota(self.a,'Mudou');self.executar(self.a)
        self.assertEqual(sum(a['name'].startswith('perfil-') for a in self.drive.arquivos.values()),1)
        outro=nuvem.PerfilNuvem(self.drive,self.a.dados,self.app)
        self.assertFalse(outro.status()['ativo'])
    def test_novo_pc_encontra_sem_sobrescrever_e_restaura_com_backup(self):
        self.nota(self.a,'Memória original');self.executar(self.a,'ativar')
        self.nota(self.b,'Local do notebook');r=self.executar(self.b,'ativar')
        self.assertEqual(len(r['versoes']),1);self.assertEqual(sum(a['name'].startswith('perfil-') for a in self.drive.arquivos.values()),1)
        self.assertEqual((self.b.dados/'kani_notas.md').read_text(),'Local do notebook')
        resultado=self.importar(self.b)
        self.assertTrue(Path(resultado['backup']).exists())
        self.assertEqual((self.b.dados/'kani_notas.md').read_text(encoding='utf-8'),'Memória original')
    def test_dois_pcs_atualizam_sem_perder_historico(self):
        self.nota(self.a,'Inicial');self.executar(self.a,'ativar');self.importar(self.b)
        self.nota(self.a,'Atualizado');self.executar(self.a);r=self.executar(self.b)
        self.assertIn('atualizado do Drive',r['mensagem'])
        self.assertEqual((self.b.dados/'kani_notas.md').read_text(encoding='utf-8'),'Atualizado')
        self.assertEqual(sum(a['name'].startswith('perfil-') for a in self.drive.arquivos.values()),2)
    def test_conta_errada_impede_leitura_e_envio(self):
        self.drive.email='outra@example.com'
        with self.assertRaisesRegex(ValueError,'não corresponde'):self.executar(self.a,'ativar')
        self.assertEqual(self.drive.arquivos,{})
    def test_troca_de_conta_exige_ativacao_explicita(self):
        self.executar(self.a,'ativar');self.drive.email='nova@example.com'
        perfil._gravar(self.a.dados/'perfil/usuario.json',json.dumps({'email':'nova@example.com'}))
        with self.assertRaisesRegex(ValueError,'conta mudou'):self.a.executar()
        self.assertEqual(sum(a['name'].startswith('perfil-') for a in self.drive.arquivos.values()),1)
    def test_mudancas_nos_dois_pcs_exigem_escolha(self):
        self.nota(self.a,'Inicial');self.executar(self.a,'ativar');self.importar(self.b)
        self.nota(self.a,'Desktop');self.executar(self.a);self.nota(self.b,'Notebook')
        r=self.executar(self.b);self.assertIn('diferentes',r['mensagem'])
        self.assertEqual(sum(a['name'].startswith('perfil-') for a in self.drive.arquivos.values()),2)
        self.executar(self.b,'publicar',conferencia=r['conferencia'])
        self.assertEqual(sum(a['name'].startswith('perfil-') for a in self.drive.arquivos.values()),3)
        self.executar(self.a)
        self.assertEqual((self.a.dados/'kani_notas.md').read_text(encoding='utf-8'),'Notebook')
    def test_conferencia_antiga_nao_publica_mudancas_novas(self):
        self.nota(self.a,'Inicial');r=self.executar(self.a,'ativar');self.nota(self.a,'Mudei')
        with self.assertRaisesRegex(ValueError,'mudaram'):self.executar(self.a,'publicar',conferencia=r['conferencia'])
        self.assertEqual(sum(a['name'].startswith('perfil-') for a in self.drive.arquivos.values()),1)
    def test_corrida_preserva_ramos_e_publicacao_converge(self):
        self.nota(self.a,'Inicial');r=self.executar(self.a,'ativar');pasta=next(iter(self.drive.arquivos))
        base=r['versoes'][0]['id'];self.nota(self.a,'Ramo A')
        self.a._enviar('token',pasta,perfil.montar(self.a.dados,self.app),[base])
        self.nota(self.b,'Ramo B');self.b._enviar('token',pasta,perfil.montar(self.b.dados,self.app),[base])
        r=self.executar(self.b,'ativar');self.assertEqual(len(r['versoes']),2)
        # Mesmo conteúdo de um dos ramos deve criar um novo nó, sem ciclo.
        r=self.executar(self.b,'publicar',conferencia=r['conferencia'])
        self.assertEqual(len(r['versoes']),1);self.assertEqual(sum(a['name'].startswith('perfil-') for a in self.drive.arquivos.values()),4)
    def test_download_corrompido_nao_restaura(self):
        self.nota(self.a,'Inicial');r=self.executar(self.a,'ativar');id=r['versoes'][0]['id']
        self.drive.conteudos[id]=b'{}'
        with self.assertRaises((ValueError,KeyError)):self.executar(self.b,'conferir',escolha=id)
        self.assertFalse((self.b.dados/'kani_notas.md').exists())
    def test_rotina_nova_nao_entra_automaticamente(self):
        self.executar(self.a,'ativar');self.importar(self.b)
        perfil._gravar(self.a.dados/'perfil/rotinas.json',json.dumps({'rotinas':[{'name':'minha','description':'Teste','cmd':['programa'],'args':{}}]}))
        self.executar(self.a);r=self.executar(self.b)
        self.assertIn('conferir',r['mensagem']);self.assertFalse((self.b.dados/'perfil/rotinas.json').exists())
    def test_exporta_cerebro_cadastro_e_memorias_sem_contas(self):
        perfil._gravar(self.a.dados/'cerebro/neuronios.json','[]')
        perfil._gravar(self.a.dados/'contas/pessoal/projects/projeto/memory/jeito.md','Meu jeito')
        perfil._gravar(self.a.dados/'contas/token.json','{"segredo":"NAO_LEVAR"}')
        texto=perfil._json(perfil.montar(self.a.dados,self.app));itens=perfil.validar(texto)['itens']
        self.assertIn('cerebro/neuronios.json',itens);self.assertIn('perfil/usuario.json',itens)
        self.assertIn('cerebro/memorias/projeto/jeito.md',itens);self.assertNotIn('NAO_LEVAR',texto)
        self.executar(self.a,'ativar');self.importar(self.b)
        self.assertTrue((self.b.dados/'cerebro/memorias/projeto/jeito.md').exists())


if __name__=='__main__': unittest.main()
