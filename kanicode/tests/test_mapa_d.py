"""Mapa do disco em dados sintéticos no D; inclui notificações reais do Windows."""
from pathlib import Path
import os
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mapa_d


class MapaDTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir='D:/kanivete_testes')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.raiz = self.base / 'arquivos'; self.raiz.mkdir()
        self.banco = self.base / 'indice' / 'teste.sqlite3'
        self.i = mapa_d.Indice(self.raiz, self.banco)
        self.addCleanup(self.i.fechar)

    def procurar(self, busca, **kw):
        return mapa_d.buscar(busca, banco=self.banco, **kw)['arquivos']

    def criar(self, caminho, texto='teste'):
        p = self.raiz / caminho; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(texto,encoding='utf-8'); return p

    def test_busca_por_cliente_acento_e_extensao(self):
        p = self.criar('Camila/Orçamento.pdf'); self.criar('Camila/foto.jpg')
        self.i.reconstruir()
        r=self.procurar('camila orcamento',extensao='pdf')
        self.assertEqual(len(r),1); self.assertEqual(r[0]['caminho'],mapa_d.chave(p))
        self.assertTrue(p.exists())

    def test_listagem_e_busca_de_pastas(self):
        self.criar('Camila/orcamento.pdf'); self.i.reconstruir()
        self.assertEqual(self.procurar('Camila',pastas=True)[0]['nome'],'Camila')
        self.assertEqual(mapa_d.listar(self.raiz,banco=self.banco)['itens'][0]['nome'],'Camila')

    def test_exclusao_nao_devolve_caminho_velho(self):
        p=self.criar('camila.pdf'); self.i.reconstruir(); p.unlink()
        self.assertEqual(self.procurar('camila'),[])
        self.i.atualizar(p)
        self.assertEqual(self.i.db.execute('SELECT count(*) FROM itens WHERE pasta=0').fetchone()[0],0)

    def test_mover_pasta_atualiza_descendentes(self):
        self.criar('Camila/orcamento.pdf'); self.i.reconstruir()
        antiga=self.raiz/'Camila'; nova=self.raiz/'Cliente Camila'; antiga.rename(nova)
        self.i.atualizar(antiga); self.i.atualizar(nova)
        r=self.procurar('camila',extensao='pdf')
        self.assertEqual(len(r),1); self.assertIn('cliente camila',r[0]['caminho'])

    def test_reconferencia_recupera_mudancas_sem_monitor(self):
        p=self.criar('velho.pdf'); self.i.reconstruir()
        p.rename(self.raiz/'novo.pdf'); self.i.reconstruir()
        self.assertEqual(self.procurar('velho'),[]); self.assertEqual(len(self.procurar('novo')),1)

    def test_filtro_de_raiz_trata_porcentagem_e_sublinhado_literal(self):
        self.criar('cliente_10%/camila.pdf'); self.criar('clienteX10ZZ/camila.pdf'); self.i.reconstruir()
        self.assertEqual(len(self.procurar('camila',raiz=self.raiz/'cliente_10%')),1)

    def test_pasta_indisponivel_nao_apaga_indice(self):
        self.criar('camila.pdf'); self.i.reconstruir()
        self.i.raiz=str(self.base/'inexistente'); self.i.reconstruir()
        self.assertEqual(self.i.db.execute('SELECT count(*) FROM itens WHERE pasta=0').fetchone()[0],1)
        self.assertEqual(mapa_d.status(self.banco)['estado'],'indisponivel')

    def test_banco_e_juncoes_nao_entram_no_mapa(self):
        self.i.reconstruir()
        self.assertEqual(self.procurar('sqlite3'),[])
        self.assertFalse(mapa_d.dentro(self.base/'arquivos2',self.raiz))

    def test_sem_monitor_indica_copia_possivelmente_desatualizada(self):
        self.i.reconstruir()
        self.assertTrue(mapa_d.status(self.banco)['parcial'])

    def test_perda_de_eventos_dispara_reconferencia(self):
        banco = self.base / 'recuperacao' / 'teste.sqlite3'
        parar = threading.Event(); callbacks = []
        def monitor(raiz, receber, fim, pronto, erro):
            callbacks.append(receber); pronto.set(); fim.wait(10)
        import mapa_d_monitor
        with patch.object(mapa_d_monitor, 'monitorar', side_effect=monitor):
            t = threading.Thread(target=mapa_d.servico, args=(self.raiz, banco, parar), daemon=True); t.start()
            try:
                limite = time.monotonic() + 10
                while mapa_d.status(banco).get('estado') != 'pronto' and time.monotonic() < limite: time.sleep(.1)
                self.criar('perdido.pdf')
                callbacks[0](None)   # buffer de notificações estourou: não há nomes individuais
                while time.monotonic() < limite:
                    if mapa_d.buscar('perdido', banco=banco)['arquivos']: break
                    time.sleep(.1)
                self.assertEqual(len(mapa_d.buscar('perdido', banco=banco)['arquivos']), 1)
            finally:
                parar.set(); t.join(5)
        self.assertFalse(t.is_alive())

    @unittest.skipUnless(os.name=='nt','Monitor nativo do Windows')
    def test_monitor_real_cria_altera_move_e_exclui(self):
        # Banco separado para o serviço usar conexão própria na thread dele.
        banco=self.base/'vivo'/'teste.sqlite3'
        parar=threading.Event()
        t=threading.Thread(target=mapa_d.servico,args=(self.raiz,banco,parar),daemon=True)
        t.start()
        def aguardar(fn):
            fim=time.monotonic()+15
            while time.monotonic()<fim:
                if fn(): return
                time.sleep(.15)
            self.fail('O monitor não atualizou o índice no prazo')
        try:
            aguardar(lambda: mapa_d.status(banco).get('estado')=='pronto')
            self.assertEqual(mapa_d.status(banco).get('monitor'),'windows')
            p=self.criar('Camila/orcamento.pdf')
            consulta=lambda:mapa_d.buscar('Camila',extensao='pdf',banco=banco)['arquivos']
            aguardar(lambda:len(consulta())==1)
            p.write_text('novo conteudo maior',encoding='utf-8')
            aguardar(lambda:consulta()[0]['tamanho']==len('novo conteudo maior'))
            pasta=self.raiz/'Camila'; destino=self.raiz/'Cliente Camila'; pasta.rename(destino)
            aguardar(lambda:len(consulta())==1 and 'cliente camila' in consulta()[0]['caminho'])
            (destino/'orcamento.pdf').unlink()
            aguardar(lambda:not consulta())
        finally:
            parar.set(); t.join(8)
        self.assertFalse(t.is_alive())


if __name__=='__main__': unittest.main()
