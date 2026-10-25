"""Separação de assunto, finalidade e autoria sem modelo, com persistência isolada no D."""
import unittest
from unittest.mock import patch
import test_cerebro_projetos as projetos
import perfil_cerebro as c


class ClassificacaoTest(unittest.TestCase):
    setUp = projetos.ProjetosTest.setUp
    tearDown = projetos.ProjetosTest.tearDown

    def guardar(self, titulo, texto, **campos):
        return c.guardar(titulo, texto, origem='fonte conferida', certeza='verificado', forcar=True, **campos)['chave']

    def test_separa_sistemas_e_nao_inventa_autoria(self):
        self.guardar('KANIVETE', 'Edição de vídeo no KANIVETE.')
        self.guardar('KaniCode', 'Interface do KaniCode.')
        self.guardar('Kani local', 'Qwen via Ollama: falha já corrigida.', tipo='licao')
        self.guardar('Conexão', 'O KaniCode abre ferramentas do KANIVETE.')
        nos = {n['titulo']: n for n in c.ler()['nos']}
        self.assertEqual(nos['KANIVETE']['ambitos'], ['kanivete'])
        self.assertEqual(nos['KaniCode']['ambitos'], ['kanicode'])
        self.assertEqual(nos['Kani local']['ambitos'], ['kani_local'])
        self.assertEqual(nos['Kani local']['finalidade'], 'aprendizado')
        self.assertEqual(nos['Kani local']['agente'], 'não registrado')
        self.assertEqual(set(nos['Conexão']['ambitos']), {'kanivete', 'kanicode'})

    def test_sem_evidencia_fica_a_classificar_caminho_nao_prova_assunto(self):
        r = self.guardar('API', 'Código em D:/KANIVETE/plugin/kanicode/modulo.py', area='dev')
        n = c._achar(r)
        self.assertEqual(n['ambitos'], ['revisar'])
        self.assertEqual(n['classificacao'], 'automática')

    def test_confirmacao_persistente_exige_origem(self):
        r = self.guardar('Receita', 'Resolver a consulta local com cache.', tipo='licao')
        args = {'acao':'classificar', 'ref':r, 'ambitos':['kani_local'], 'finalidade':'aprendizado', 'agente':'kani'}
        self.assertFalse(c.acao(args)['ok'])
        self.assertTrue(c.acao(dict(args, certeza='verificado', origem='registro da execução da Kani'))['ok'])
        c._MEM.update(chave=None)
        n = c.ler_neuronio(r)
        self.assertEqual(n['agente'], 'kani')
        self.assertEqual(n['classificacao'], 'confirmada')
        self.assertEqual(n['ambitos'], ['kani_local'])

    def test_filtro_na_consulta_no_mapa_e_nas_ligacoes(self):
        a = self.guardar('Exportação legenda KANIVETE', 'Exportação legenda vídeo KANIVETE.')
        b = self.guardar('Exportação legenda KaniCode', 'Exportação legenda vídeo KaniCode.', ligar=[a])
        self.assertNotIn(b, c.mapa(ambito='kanivete'))
        saida = c.consultar('exportação legenda', marcar=False, ambito='kanivete')
        self.assertEqual([n['chave'] for n in saida], [a])
        # A conexão explícita é conservada, mas não atravessa o filtro.
        self.assertTrue(any(l[2] == 1 for l in c.ler()['ligas']))
        self.assertFalse(c._compativeis(c._achar(a), c._achar(b)))
        with self.assertRaises(ValueError):
            c.consultar('exportação', ambito='inventado')

    def test_sem_ligacao_automatica_nem_duplicata_entre_sistemas(self):
        self.guardar('KANIVETE', 'exportação legenda vídeo montagem render composição')
        self.guardar('KaniCode', 'exportação legenda vídeo montagem render composição')
        self.assertEqual(c.ler()['ligas'], [])
        self.assertEqual(c.revisar()['juntar'], [])
        r = c.guardar('Exportação KANIVETE', 'exportação legenda vídeo montagem render composição KANIVETE',
                      origem='teste', certeza='verificado')
        self.assertFalse(r['guardado'], 'Mesmo sistema continua detectando duplicata.')
        r = c.guardar('Outro app', 'exportação legenda vídeo montagem render composição KaniCode',
                      origem='teste', certeza='verificado')
        self.assertFalse(r['guardado'], 'Não sugere atualizar o KANIVETE para guardar informação do KaniCode.')
        self.assertTrue(all(c._achar(n['chave'])['ambitos'] == ['kanicode'] for n in r['parecidos']))


if __name__ == '__main__':
    unittest.main()
