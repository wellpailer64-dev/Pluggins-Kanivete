"""Referências vivas do PC: índice existente, limites e conexões verificáveis; sem varrer o disco."""
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import test_cerebro_projetos as projetos
import perfil_cerebro as c
import mapa_d

FONTE_PC = c._fonte_pc


class CerebroPCTest(unittest.TestCase):
    def setUp(self):
        projetos.ProjetosTest.setUp(self)
        p=patch.object(c,'_fonte_pc',FONTE_PC); p.start(); self.patches.append(p)
        self.raiz=Path(self.tmp.name)/'documentos'; self.raiz.mkdir()
        self.banco=Path(self.tmp.name)/'mapa_d'/'indice.sqlite3'
        self.indice=mapa_d.Indice(self.raiz,self.banco)
        self.listar_original=mapa_d.listar
        # A raiz consultada em produção é D:/; o teste consulta somente sua árvore isolada.
        def listar(_pasta, limite=40, banco=None):
            return self.listar_original(self.raiz,limite=limite,banco=self.banco)
        p=patch.object(mapa_d,'listar',side_effect=listar); p.start(); self.patches.append(p)
        c._PC_CACHE.update(base=None,quando=0,pastas=[])

    def tearDown(self):
        self.indice.fechar()
        projetos.ProjetosTest.tearDown(self)
        c._PC_CACHE.update(base=None,quando=0,pastas=[])

    def reconstruir(self):
        self.indice.reconstruir()
        c._PC_CACHE['quando']=0

    def test_pastas_sao_referencias_e_renomeacao_atualiza_sem_duplicar_memorias(self):
        pasta=self.raiz/'Cliente'; pasta.mkdir()
        self.reconstruir()
        primeiro=c.ler()
        self.assertEqual({n['titulo'] for n in primeiro['nos']},{'Mapa vivo do disco D','Cliente'})
        self.assertTrue(all(n['grupo']=='caminhos' and n['area']=='pc' for n in primeiro['nos']))
        self.assertFalse(os.path.exists(c.ARQ_PROPRIOS))
        # Move somente a pasta de teste, cujo caminho resolvido fica na área de testes.
        destino=self.raiz/'Cliente novo'
        self.assertTrue(pasta.resolve().is_relative_to(Path('D:/kanivete_testes').resolve()))
        self.assertTrue(destino.resolve().is_relative_to(Path('D:/kanivete_testes').resolve()))
        pasta.rename(destino)
        self.reconstruir()
        segundo=c.ler()
        self.assertEqual({n['titulo'] for n in segundo['nos']},{'Mapa vivo do disco D','Cliente novo'})
        self.assertFalse(os.path.exists(c.ARQ_PROPRIOS))

    def test_limite_cache_e_pastas_nao_viram_preferencias(self):
        for i in range(30): (self.raiz/f'Pasta {i:02}').mkdir()
        self.reconstruir()
        with patch.object(mapa_d,'iniciar',side_effect=AssertionError('não iniciar outra indexação')):
            a=c.ler()
            leituras=mapa_d.listar.call_count
            c.ler()
        self.assertEqual(mapa_d.listar.call_count,leituras)
        self.assertEqual(len(a['nos']),25)
        self.assertTrue(all(n['tipo']=='reference' for n in a['nos']))
        self.assertEqual(c.revisar()['juntar'],[])
        self.assertEqual(c._candidatos(a,10**10),[])

    def test_organizacao_e_projeto_ligam_ao_mapa_e_a_pasta(self):
        pasta=self.raiz/'Trabalhos'; pasta.mkdir(); self.reconstruir()
        r=c.guardar('Organização de pastas','Observar o padrão local antes de organizar materiais do cliente.',
                    tipo='processo',certeza='pailer',origem='conversa',forcar=True)
        projeto=c.projeto_em_andamento('Campanha',{'pasta':str(pasta),'resumo':'Produção confirmada.'},'conversa','pailer')
        dados=c.ler(); nos={n['chave']:n for n in dados['nos']}
        self.assertEqual(nos[r['chave']]['grupo'],'organizacao')
        self.assertEqual(nos[r['chave']]['ambitos'],['pc'])
        ref=next(n for n in dados['nos'] if n.get('pc',{}).get('pasta')==mapa_d.chave(pasta))
        pares={(min(a,b),max(a,b)) for a,b,k,w in dados['ligas'] if k==1}
        self.assertIn(tuple(sorted([nos[projeto['chave']]['id'],ref['id']])),pares)
        self.assertIn(tuple(sorted([nos[r['chave']]['id'],nos['pc:mapa_d']['id']])),pares)

    def test_indice_indisponivel_mantem_ponto_de_entrada_sem_inventar_pastas(self):
        mapa_d.listar.side_effect=OSError('indisponível')
        self.assertEqual([n['chave'] for n in c.ler()['nos']],['pc:mapa_d'])
        self.assertIn('pc:mapa_d',c.mapa(ambito='pc'))


if __name__ == '__main__':
    unittest.main()
