"""Lista pessoal isolada no D; calendário, Kani e agendador simulados."""
import concurrent.futures
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tarefas as t
import compromissos as c
import google_calendar as gc
import kani_modo

class TarefasTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=r'D:\kanivete_testes')
        self.addCleanup(self.tmp.cleanup)
        self.p = Path(self.tmp.name)
        self.t = t.Tarefas(self.p)
    def test_persistencia_edicao_conclusao_e_reabertura(self):
        a = self.t.salvar('Comprar café', '2026-12-01', origem='kani')
        b = t.Tarefas(self.p)
        self.assertEqual(b.listar()[0]['origem'], 'kani')
        b.salvar('Comprar café e pão', '', a['id'])
        self.assertTrue(b.concluir(a['id'], True)['concluida'])
        self.assertFalse(self.t.concluir(a['id'], False)['concluida'])
        self.assertEqual(len(b.listar()), 1)
        self.assertEqual(b.listar()[0]['titulo'], 'Comprar café e pão')
    def test_entrada_invalida_e_arquivo_corrompido_preservado(self):
        for titulo, prazo in [('', ''), ('a'*301,''), ('Tarefa','2026-02-30')]:
            with self.assertRaises(ValueError): self.t.salvar(titulo, prazo)
        with self.assertRaises(ValueError): self.t.concluir('inexistente', True)
        with self.assertRaises(ValueError): self.t.concluir('id', 'false')
        self.p.joinpath('tarefas.json').write_text('corrompido')
        with self.assertRaises(ValueError): self.t.salvar('Não sobrescrever')
        self.assertEqual(self.p.joinpath('tarefas.json').read_text(), 'corrompido')
    def test_gravacoes_concorrentes_nao_perdem_itens(self):
        def gravar(n): return t.Tarefas(self.p).salvar(f'Tarefa {n}')
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(gravar, range(12)))
        self.assertEqual(len(self.t.listar()), 12)
    def test_ferramentas_da_kani_compartilham_a_lista(self):
        with patch.object(t, 'tarefas', self.t):
            r = json.loads(kani_modo._executar('todo_salvar', {'titulo':'Ligar para cliente'}, '.'))
            self.assertEqual(r['origem'], 'kani')
            kani_modo._executar('todo_concluir', {'id':r['id'],'concluida':True}, '.')
            self.assertTrue(self.t.listar()[0]['concluida'])
    def test_agenda_mescla_sem_duplicar_e_inclui_dia_inteiro(self):
        dia = (dt.datetime.now()+dt.timedelta(days=1)).date().isoformat()
        local = {'id':'l1','titulo':'Consulta','hora':'15:00','data':dia,'dias':[]}
        google = {'id':'google:g:e','titulo':'Feriado','inicio':dia,'dia_inteiro':True,'origem':'google','calendario':'Pessoal'}
        self.p.joinpath('agenda.json').write_text(json.dumps([{'id':'l1','titulo':'Consulta','inicio':dia+'T15:00','origem':'kani'}]))
        with patch.object(c,'PROXIMOS',str(self.p/'agenda.json')), patch.object(c,'AVISOS',str(self.p)), patch.object(c,'_ler',return_value={'itens':[local]}), patch.object(gc.calendar,'status',return_value={'conectado':True,'eventos':[google]}):
            r=t.agenda()
        self.assertEqual(len(r['itens']),2)
        self.assertTrue(r['google_conectado'])
    def test_lembrete_valida_antes_de_agendar(self):
        futuro=(dt.datetime.now()+dt.timedelta(days=1)).isoformat(timespec='minutes')
        with patch.object(c,'marcar',return_value={'id':'l1'}) as marcar:
            self.assertEqual(t.lembrar('Consulta',futuro,30)['id'],'l1')
            self.assertEqual(marcar.call_args.kwargs['antes'],30)
            with self.assertRaises(ValueError): t.lembrar('Consulta','2020-01-01T10:00')
            with self.assertRaises(ValueError): t.lembrar('Consulta',futuro,False)
            self.assertEqual(marcar.call_count,1)
