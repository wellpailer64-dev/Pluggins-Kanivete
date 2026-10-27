"""Acordo entre modelos, revisões, reservas e ponte do Colab, sem agentes ou app reais."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import colab
import fios
import kanicode


def proposta():
    return {'acao': 'propor', 'contrato': 'GET /api/itens retorna [{id,nome}]. Interface chama essa rota.',
            'tarefas': [{'aba': '1', 'titulo': 'API', 'arquivos': ['api.py']},
                        {'aba': '2', 'titulo': 'Interface', 'arquivos': ['ui/index.html', 'ui/site.css']}]}


class PlanoTest(unittest.TestCase):
    def test_aprovacao_dos_dois_e_integracao(self):
        s = colab.atualizar(colab.criar('1', '2', 'Site'), '1', proposta())
        with self.assertRaises(ValueError):
            colab.atualizar(s, '1', {'acao': 'executar', 'revisao': 1})
        for aba in ('1', '2'):
            s = colab.atualizar(s, aba, {'acao': 'aprovar', 'revisao': 1})
        s = colab.atualizar(s, '1', {'acao': 'executar', 'revisao': 1})
        self.assertEqual(s['fase'], 'execucao')
        with self.assertRaises(ValueError):
            colab.atualizar(s, '1', {'acao': 'finalizar', 'evidencia': 'cedo demais'})
        for aba in ('1', '2'):
            s = colab.atualizar(s, aba, {'acao': 'concluir_tarefa', 'evidencia': 'Sintaxe e teste da parte passaram'})
        self.assertEqual(s['fase'], 'integracao')
        s = colab.atualizar(s, '1', {'acao': 'finalizar', 'evidencia': 'Frontend consultou a API real no teste conjunto'})
        self.assertEqual(s['fase'], 'concluido')

    def test_revisao_invalida_aprovacoes(self):
        s = colab.atualizar(colab.criar('1', '2', 'Site'), '1', proposta())
        s = colab.atualizar(s, '2', {'acao': 'aprovar', 'revisao': 1})
        novo = colab.atualizar(s, '1', proposta())
        self.assertEqual(novo['aprovacoes'], [])
        self.assertEqual(s['aprovacoes'], ['2'])
        with self.assertRaises(ValueError):
            colab.atualizar(novo, '2', {'acao': 'aprovar', 'revisao': 1})

    def test_reservas_e_caminhos(self):
        for arq in ('API.PY', './api.py', '../fora.py', 'D:/fora.py', 'ui/*'):
            p = proposta(); p['tarefas'][1]['arquivos'] = [arq]
            with self.subTest(arq=arq), self.assertRaises(ValueError):
                colab.atualizar(colab.criar('1', '2', 'Site'), '1', p)
        p = proposta(); p['tarefas'][0]['arquivos'] = ['ui']
        with self.assertRaises(ValueError):
            colab.atualizar(colab.criar('1', '2', 'Site'), '1', p)

    def test_fio_colab_e_bidirecional(self):
        lista, _ = fios.criar([], '1', '2', 'colab')
        self.assertTrue(fios.achar(lista, '2', '1', 'comando'))
        self.assertIn('aba 1', fios.contexto('2', lista, {}))
        self.assertIsNone(fios.achar(lista, '3', '1', 'comando'))


class PonteTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir='D:/kanivete_testes')
        self.addCleanup(self.temp.cleanup)
        p = patch.object(kanicode, 'ESTADO', str(Path(self.temp.name) / 'estado.json'))
        p.start(); self.addCleanup(p.stop)
        self.app = kanicode.App.__new__(kanicode.App)
        self.app._abas = {a: SimpleNamespace(pasta=self.temp.name, quem=q, ocupada=Mock(return_value=False))
                          for a, q in [('1', 'claude'), ('2', 'codex')]}
        self.app._para_janela = Mock()
        self.app._colab_enviar = Mock()
        self.f = self.app.colab_criar('1', '2', 'Site com API')

    def chamar(self, de, dados):
        return self.app.colab_atualizar(de, '2' if de == '1' else '1', dados)

    def test_plano_dispara_parceiro_e_continua_integracao(self):
        self.chamar('1', proposta())
        for a in ('1', '2'):
            self.chamar(a, {'acao': 'aprovar', 'revisao': 1})
        self.chamar('1', {'acao': 'executar', 'revisao': 1})
        self.assertEqual(self.app._colab_enviar.call_args.args[0], '2')
        self.app._abas['1'].ocupada.return_value = True
        self.chamar('1', {'acao': 'concluir_tarefa', 'evidencia': 'API testada'})
        self.app._abas['1'].ocupada.return_value = False
        self.chamar('2', {'acao': 'concluir_tarefa', 'evidencia': 'Interface testada'})
        self.assertEqual(self.app.colab_consultar(self.f['id'])['fase'], 'integracao')
        self.assertEqual(self.app._colab_enviar.call_args.args[0], '1')

    def test_integracao_espera_coordenador_terminar(self):
        self.chamar('1', proposta())
        for a in ('1', '2'):
            self.chamar(a, {'acao': 'aprovar', 'revisao': 1})
        self.chamar('1', {'acao': 'executar', 'revisao': 1})
        self.chamar('1', {'acao': 'concluir_tarefa', 'evidencia': 'API pronta'})
        self.app._abas['1'].ocupada.return_value = True
        with patch.object(kanicode.threading, 'Timer') as timer:
            self.chamar('2', {'acao': 'concluir_tarefa', 'evidencia': 'Interface pronta'})
            self.assertTrue(timer.return_value.start.called)
            self.assertEqual(self.app._colab_enviar.call_args.args[0], '2')
            self.app._abas['1'].ocupada.return_value = False
            timer.call_args.args[1]()
        self.assertEqual(self.app._colab_enviar.call_args.args[0], '1')

    def test_aviso_com_parceiro_ocupado_e_erro_sem_fio(self):
        self.app._abas['2'].ocupada.return_value = True
        r = self.app.fio_chamar('1', '2', 'colab', json.dumps({'acao': 'avisar', 'texto': 'API pronta'}))
        self.assertEqual(json.loads(r)['diario'][-1]['texto'], 'API pronta')
        self.assertEqual(self.app._colab_enviar.call_count, 0)
        self.assertTrue(self.app.fio_chamar('3', '2', 'colab', '{}').startswith('ERRO:'))
        self.assertTrue(self.app.fio_chamar('1', '2', 'colab', '[]').startswith('ERRO:'))

    def test_colab_nao_confunde_fio_antigo_e_recusa_troca_de_projeto(self):
        lista = self.app.fios()
        reverso, _ = fios.criar([], '2', '1', 'comando')
        self.app._fios_gravar(reverso + lista)
        self.assertEqual(self.chamar('2', {'acao': 'avisar', 'texto': 'Acordo recebido'})['diario'][-1]['aba'], '2')
        self.app._abas['2'].pasta = 'D:/outro_projeto'
        with self.assertRaises(ValueError):
            self.chamar('1', proposta())

    def test_falha_disparo_nao_deixa_execucao_falsa(self):
        self.chamar('1', proposta())
        for a in ('1', '2'):
            self.chamar(a, {'acao': 'aprovar', 'revisao': 1})
        self.app._colab_enviar.side_effect = RuntimeError('motor indisponível')
        with self.assertRaises(ValueError):
            self.chamar('1', {'acao': 'executar', 'revisao': 1})
        self.assertEqual(self.app.colab_consultar(self.f['id'])['fase'], 'planejamento')


if __name__ == '__main__':
    unittest.main()
