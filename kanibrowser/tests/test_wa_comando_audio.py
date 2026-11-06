"""Fluxo de pedidos por áudio sem conta real, envios ou execução de demandas."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import wa_comando as comando


class AudioComando(unittest.TestCase):
    def test_audio_proprio(self):
        m = {'id': 'audio1', 'quem': 'Eu', 'audio': '0:10'}
        with patch.object(comando, 'wa', return_value=json.dumps({'id': 'audio1', 'texto': 'Prepare a demanda'})) as wa:
            self.assertIn('Prepare a demanda', comando.pedido_mensagem(m))
            self.assertIn('--audio-id', wa.call_args.args)

    def test_ignora_outros_e_marca(self):
        with patch.object(comando, 'wa') as wa:
            self.assertIsNone(comando.pedido_mensagem({'quem': 'Outra pessoa', 'audio': '0:10'}))
            self.assertIsNone(comando.pedido_mensagem({'quem': 'Eu', 'txt': '[KANI] resposta'}))
            wa.assert_not_called()

    def test_marca_sem_emoji_nao_vira_pedido(self):
        for texto in ['KANI: Recebi seu pedido.', '*KANI*: Resposta', '\U0001f7e2 KANI: Resposta']:
            self.assertFalse(comando.e_pedido('Eu', texto))
            self.assertIsNone(comando.pedido_mensagem({'quem': 'Eu', 'txt': texto}))

    def test_falhas_nao_sao_pedidos(self):
        for texto, mid in [('', 'a'), ('(sem fala)', 'a'), ('(não transcrevi: falha)', 'a'), ('pedido', 'outro')]:
            with patch.object(comando, 'wa', return_value=json.dumps({'id': mid, 'texto': texto})):
                with self.assertRaises(RuntimeError):
                    comando.pedido_mensagem({'id': 'a', 'quem': 'Eu', 'audio': '0:10'})

    def test_deduplica_id_e_nao_executa_historico(self):
        antigo = {'id': 'antigo', 'quem': 'Eu', 'audio': '0:10'}
        novo = {'id': 'novo', 'quem': 'Eu', 'audio': '0:10'}
        avisos = comando.queue.Queue()
        vistos = []
        with patch.object(comando, 'salvar_vistos'), patch.object(comando, 'log'), \
             patch.object(comando, 'guardar', return_value=True) as guardar, patch.object(comando, 'etapa'):
            primeira = comando.receber({'conversa': 'KaniCode', 'mensagens': [antigo]}, vistos, True, avisos)
            for _ in range(2):
                primeira = comando.receber({'conversa': 'KaniCode', 'mensagens': [antigo, novo]}, vistos, primeira, avisos)
            self.assertEqual(avisos.qsize(), 1)
            self.assertEqual(avisos.get()['id'], 'novo')
            guardar.assert_called_once_with(novo)

    def test_aviso_antes_do_preparo(self):
        eventos = []
        m = {'id': 'a', 'quem': 'Eu', 'audio': True}
        with patch.object(comando, 'etapa'), patch.object(comando, 'log'), \
             patch.object(comando, 'responder', side_effect=lambda t: eventos.append(t)), \
             patch.object(comando, 'pedido_mensagem', side_effect=lambda m: eventos.append('preparo') or 'pedido'), \
             patch.object(comando, 'registrar'), patch.object(comando, 'entregar_gerente', return_value={'aba': 1}):
            comando.confirmar_recebimento(m)
            comando.processar(m)
        self.assertEqual(eventos[0], 'Estou ouvindo seu \u00e1udio!')
        self.assertEqual(eventos[1], 'preparo')

    def test_falha_transcricao_nao_entrega(self):
        with patch.object(comando, 'etapa'), patch.object(comando, 'avisar') as aviso, \
             patch.object(comando, 'pedido_mensagem', side_effect=RuntimeError('falha')), \
             patch.object(comando, 'entregar_gerente') as entregar:
            comando.processar({'id': 'a'})
            entregar.assert_not_called()
            aviso.assert_called_once()

    def test_conversa_errada_nao_persiste(self):
        with patch.object(comando, 'guardar') as guardar:
            with self.assertRaises(RuntimeError):
                comando.receber({'conversa': 'Outro', 'mensagens': []}, [], False, comando.queue.Queue())
            guardar.assert_not_called()

    def test_fila_persistida_deduplica(self):
        import tempfile
        with tempfile.TemporaryDirectory(dir='D:/kanivete_testes') as pasta, patch.object(comando, 'PASTA', pasta):
            m = {'id': 'a', 'quem': 'Eu', 'txt': 'pedido'}
            self.assertTrue(comando.guardar(m))
            self.assertFalse(comando.guardar(m))
            with patch.object(comando, 'log'):
                comando.etapa('a', 'encaminhado', 'aba=1')
            self.assertEqual(comando.estado_recepcao()[0]['estado'], 'encaminhado')



if __name__ == '__main__':
    unittest.main(verbosity=2)
