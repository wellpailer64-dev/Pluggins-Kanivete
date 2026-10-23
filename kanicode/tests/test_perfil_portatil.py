"""Perfil portátil em dados sintéticos: migração, conflitos, exclusões e recuperação de erro."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import perfil_portatil as perfil


class PerfilTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir='D:/kanivete_testes');self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.origem=self.base/'origem';self.destino=self.base/'destino';self.app=self.base/'app'
        for p in (self.origem,self.destino,self.app):p.mkdir()
        self.gravar(self.app/'rotinas.json',{'rotinas':[{'name':'minha_rotina','description':'Teste','cmd':['programa','{nome}'],'args':{'nome':{'type':'string'}}}]})
        (self.app/'motor.py').write_text('# ferramenta integrada',encoding='utf-8')
        self.gravar(self.origem/'estado.json',{'quem':'kani','sons_bolinha':False,'fixa':True,'projeto':'D:/Privado','contas':[{'email':'privado@teste'}],'voz':True})
        (self.origem/'kani_notas.md').write_text('Lembre-se do meu jeito de trabalhar.',encoding='utf-8')
        self.gravar(self.origem/'preferencias/organizacao.json',{'contexto':'Manter numeração existente.'})
        self.gravar(self.origem/'conexoes/google.dpapi.json',{'token':'SEGREDO_NAO_EXPORTAR'})
        self.gravar(self.origem/'contratos/modelo.json',{'objetivo':'Modelo de contrato'})
        (self.origem/'regras').mkdir();(self.origem/'regras/projeto.md').write_text('Não fazer push.',encoding='utf-8')
        self.texto=json.dumps(perfil.montar(self.origem,self.app),ensure_ascii=False)

    def gravar(self,p,valor):
        p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(valor,ensure_ascii=False),encoding='utf-8')

    def conferir(self):return perfil.previa(self.texto,self.destino,self.app)

    def aplicar(self,politica='manter'):
        return perfil.aplicar(self.texto,self.conferir()['conferencia'],politica,self.destino,self.app)

    def test_exportacao_leva_memorias_regras_contratos_e_rotinas(self):
        pacote=perfil.validar(self.texto)
        for nome in ['kani_notas.md','regras/projeto.md','contratos/modelo.json','preferencias/organizacao.json','rotinas.json']:
            self.assertIn(nome,pacote['itens'])
        self.assertNotIn('SEGREDO_NAO_EXPORTAR',self.texto)
        self.assertNotIn('privado@teste',self.texto)
        self.assertNotIn('D:/Privado',self.texto)
        self.assertNotIn('voz',json.loads(pacote['itens']['estado_portatil.json']['texto']))

    def test_previa_nao_altera_o_destino(self):
        antes=list(self.destino.rglob('*'));r=self.conferir()
        self.assertEqual(antes,list(self.destino.rglob('*')))
        self.assertGreater(r['resumo']['novo'],0)

    def test_restauracao_em_outro_pc_preserva_campos_da_maquina(self):
        self.gravar(self.destino/'estado.json',{'projeto':'E:/Meu projeto','voz':False,'sessoes':{'uma':'local'}})
        r=self.aplicar('substituir')
        e=json.loads((self.destino/'estado.json').read_text())
        self.assertEqual(e['projeto'],'E:/Meu projeto');self.assertFalse(e['voz']);self.assertEqual(e['quem'],'kani')
        self.assertEqual(e['sessoes'],{'uma':'local'})
        self.assertEqual((self.destino/'kani_notas.md').read_text(encoding='utf-8'),'Lembre-se do meu jeito de trabalhar.')
        self.assertTrue(Path(r['backup']).exists())
        self.assertEqual(json.loads((self.destino/'perfil/identidade.json').read_text())['id'],json.loads(self.texto)['perfil']['id'])

    def test_conflito_mantem_valor_local_por_padrao(self):
        (self.destino/'kani_notas.md').write_text('Ensinamento do notebook',encoding='utf-8')
        self.assertEqual(self.conferir()['resumo']['conflito'],2)  # estado portátil vazio e memória local
        r=self.aplicar()
        self.assertEqual((self.destino/'kani_notas.md').read_text(encoding='utf-8'),'Ensinamento do notebook')
        self.assertGreater(r['conflitos_mantidos'],0)
        self.assertTrue((self.destino/'regras/projeto.md').exists())

    def test_dados_mudaram_depois_da_previa_exige_nova_conferencia(self):
        token=self.conferir()['conferencia']
        (self.destino/'kani_notas.md').write_text('Mudou agora',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'nova conferência'):
            perfil.aplicar(self.texto,token,'substituir',self.destino,self.app)
        self.assertEqual((self.destino/'kani_notas.md').read_text(encoding='utf-8'),'Mudou agora')

    def test_integridade_e_versao(self):
        p=json.loads(self.texto);p['itens']['kani_notas.md']['texto']='alterado'
        with self.assertRaisesRegex(ValueError,'Integridade'):perfil.validar(json.dumps(p))
        p=json.loads(self.texto);p['versao']=99
        with self.assertRaises(ValueError):perfil.validar(json.dumps(p))

    def test_caminhos_e_credenciais_nao_podem_ser_injetados(self):
        for nome in ['../fora.md','regras/../../fora.md','C:/fora.md','regras/CON.md','conexoes/google.dpapi.json','motor.py','perfil/identidade.json']:
            p=json.loads(self.texto);p['itens'][nome]={'texto':'teste','sha256':perfil._hash('teste')}
            with self.subTest(nome=nome),self.assertRaises(ValueError):perfil.validar(json.dumps(p))

    def test_configuracao_de_maquina_nao_pode_ser_injetada(self):
        p=json.loads(self.texto);p['itens']['estado_portatil.json']['texto']=json.dumps({'voz':True})
        with self.assertRaisesRegex(ValueError,'máquina'):perfil.validar(json.dumps(p))

    def test_erro_no_meio_reverte_os_arquivos_ja_gravados(self):
        self.gravar(self.destino/'estado.json',{'quem':'claude','projeto':'E:/local'})
        (self.destino/'kani_notas.md').write_text('Anterior',encoding='utf-8')
        anterior=(self.destino/'estado.json').read_bytes();original=perfil._gravar;falhou=[]
        def gravar(p,t):
            if Path(p).name=='kani_notas.md' and not falhou:
                falhou.append(True);raise OSError('Falha simulada')
            original(p,t)
        token=self.conferir()['conferencia']
        with patch.object(perfil,'_gravar',side_effect=gravar),self.assertRaises(OSError):
            perfil.aplicar(self.texto,token,'substituir',self.destino,self.app)
        self.assertEqual((self.destino/'estado.json').read_bytes(),anterior)
        self.assertEqual((self.destino/'kani_notas.md').read_text(encoding='utf-8'),'Anterior')

    def test_rotinas_restauradas_ficam_nos_dados_e_nao_no_codigo(self):
        original=(self.app/'rotinas.json').read_bytes();self.aplicar('substituir')
        self.assertEqual((self.app/'rotinas.json').read_bytes(),original)
        self.assertTrue((self.destino/'perfil/rotinas.json').exists())
        self.assertIn('minha_rotina',perfil.rotinas(self.destino,self.app))

    def test_rotina_invalida_nao_substitui_as_instaladas(self):
        self.gravar(self.destino/'perfil/rotinas.json',{'rotinas':[{'name':'codex','cmd':['erro']}]})
        self.assertIn('minha_rotina',perfil.rotinas(self.destino,self.app))
        self.assertNotIn('codex',perfil.rotinas(self.destino,self.app))

    def test_importacao_repetida_nao_regrava_os_arquivos(self):
        self.aplicar('substituir');r=self.aplicar('substituir')
        self.assertEqual(r['restaurados'],0)

    def test_instalacao_diferente_avisa_sobre_as_ferramentas(self):
        (self.app/'motor.py').write_text('# outra versão',encoding='utf-8')
        self.assertTrue(any('instalação' in a for a in self.conferir()['avisos']))

    def test_exportar_nao_sobrescreve_pacotes_anteriores(self):
        a=perfil.exportar(self.origem,self.app);b=perfil.exportar(self.origem,self.app)
        self.assertNotEqual(a['caminho'],b['caminho']);self.assertTrue(Path(a['caminho']).exists())


if __name__=='__main__':unittest.main()
