"""Cadastro/sessão sintéticos e DPAPI do Windows; nenhum dado ou Drive real."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import perfil_acesso as acesso
import perfil_nuvem as nuvem
import perfil_portatil as perfil
from test_perfil_nuvem import DriveFalso


class PerfilAcessoTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir='D:/kanivete_testes');self.addCleanup(self.temp.cleanup)
        self.raiz=Path(self.temp.name);self.app=self.raiz/'app';self.app.mkdir()
        self.drive=DriveFalso();self.a=self.pc('a');self.b=self.pc('b')
        self.mock=patch.object(nuvem,'_abrir',side_effect=self.drive.abrir);self.mock.start();self.addCleanup(self.mock.stop)
        self.campos={'email':'teste@example.com','senha':'senha-ficticia-longa','confirmacao':'senha-ficticia-longa','lembrar':True}
    def pc(self, nome):
        dados=self.raiz/nome;dados.mkdir()
        pc=nuvem.PerfilNuvem(self.drive,dados,self.app)
        self.addCleanup(acesso._SESSOES.pop,str(dados.resolve()),None)
        return pc
    def cadastrar(self): return acesso.AcessoPerfil(self.a).executar('cadastrar',self.campos)
    def test_cadastro_no_drive_sem_senha_legivel_e_fora_da_exportacao(self):
        r=self.cadastrar();self.assertTrue(r['autenticado']);self.assertTrue(r['lembrado'])
        pacote=perfil._json(perfil.montar(self.a.dados,self.app))
        for texto in list(self.drive.conteudos.values())+[p.read_bytes() for p in self.a.dados.rglob('*') if p.is_file()]:
            self.assertNotIn(self.campos['senha'].encode(),texto)
        self.assertNotIn('acesso.dpapi',pacote);self.assertNotIn('pbkdf',pacote)
        registros=[json.loads(b) for b in self.drive.conteudos.values()]
        self.assertEqual(registros[0]['iteracoes'],600000);self.assertEqual(len(registros[0]['hash']),64)
    def test_segundo_pc_exige_senha_certa_e_encontra_perfil(self):
        self.cadastrar();self.a.executar('ativar')
        perfil._gravar(self.b.dados/'perfil/usuario.json',perfil._json({'email':'teste@example.com'}))
        r=self.b.executar('ativar');self.assertTrue(r['requer_acesso'])
        with self.assertRaisesRegex(ValueError,'incorretos'):
            acesso.AcessoPerfil(self.b).executar('entrar',dict(self.campos,senha='senha-errada'))
        self.assertFalse(acesso.AcessoPerfil(self.b).status()['autenticado'])
        r=acesso.AcessoPerfil(self.b).executar('entrar',self.campos)
        self.assertTrue(r['autenticado']);self.assertEqual(len(self.b.executar('ativar')['versoes']),1)
    def test_lembrar_reabre_sessao_sem_salvar_senha(self):
        self.cadastrar();acesso._SESSOES.clear()
        self.assertTrue(acesso.AcessoPerfil(self.a).status()['autenticado'])
        self.assertTrue(self.a.executar('ativar')['ativo'])
    def test_sem_lembrar_sessao_termina_ao_reabrir(self):
        acesso.AcessoPerfil(self.a).executar('cadastrar',dict(self.campos,lembrar=False))
        self.assertTrue(acesso.AcessoPerfil(self.a).status()['autenticado']);acesso._SESSOES.clear()
        self.assertFalse(acesso.AcessoPerfil(self.a).status()['autenticado'])
    def test_sair_invalida_sessao_lembrada_sem_apagar_dados(self):
        self.cadastrar();perfil._gravar(self.a.dados/'kani_notas.md','memória')
        r=acesso.AcessoPerfil(self.a).executar('sair');acesso._SESSOES.clear()
        self.assertFalse(r['autenticado']);self.assertFalse(acesso.AcessoPerfil(self.a).status()['autenticado'])
        self.assertTrue((self.a.dados/'kani_notas.md').exists());self.assertEqual(len(self.drive.conteudos),1)
    def test_outra_conta_google_nao_cadastra(self):
        self.drive.email='outra@example.com'
        with self.assertRaisesRegex(ValueError,'não corresponde'):self.cadastrar()
        self.assertEqual(self.drive.arquivos,{})
    def test_nao_troca_senha_existente_ao_cadastrar_de_novo(self):
        self.cadastrar();antes=copy.deepcopy(self.drive.conteudos)
        with self.assertRaisesRegex(ValueError,'já tem senha'):
            acesso.AcessoPerfil(self.b).executar('cadastrar',dict(self.campos,senha='outra-senha-longa',confirmacao='outra-senha-longa'))
        self.assertEqual(self.drive.conteudos,antes)
    def test_cadastro_recusa_senha_curta_e_confirmacao_diferente(self):
        for campos in [dict(self.campos,senha='curta',confirmacao='curta'),dict(self.campos,confirmacao='diferente')]:
            with self.assertRaises(ValueError):acesso.AcessoPerfil(self.a).executar('cadastrar',campos)
        self.assertEqual(len(self.drive.conteudos),0)
    def test_perfil_nao_baixa_nem_publica_sem_sessao(self):
        self.cadastrar();r=self.a.executar('ativar');id=r['versoes'][0]['id']
        acesso.AcessoPerfil(self.a).executar('sair')
        for acao in ('conferir','restaurar','publicar'):
            with self.assertRaisesRegex(ValueError,'senha do KaniCode'):self.a.executar(acao,escolha=id)
        self.assertTrue(self.a.executar()['requer_acesso'])
    def test_alterar_registro_remoto_revoga_sessao_lembrada(self):
        self.cadastrar();self.a.executar('ativar')
        id=next(i for i,a in self.drive.arquivos.items() if a['name']=='acesso-kanicode.json')
        r=json.loads(self.drive.conteudos[id]);r['sal']='00'*16
        self.drive.conteudos[id]=json.dumps(r).encode()
        self.assertTrue(self.a.executar()['requer_acesso'])
        self.assertFalse(acesso.AcessoPerfil(self.a).status()['autenticado'])
    def test_dpapi_corrompido_nao_libera_acesso(self):
        self.cadastrar();acesso._SESSOES.clear()
        perfil._gravar(self.a.dados/'perfil/acesso.dpapi','arquivo inválido')
        self.assertFalse(acesso.AcessoPerfil(self.a).status()['autenticado'])


if __name__=='__main__': unittest.main()
