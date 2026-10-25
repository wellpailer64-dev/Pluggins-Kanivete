"""Fios entre chats (fios.py): criar, permissões, resposta depois do pedido, limite e contexto."""
import sys, time, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fios as F


class FiosTest(unittest.TestCase):
    def test_permissoes_e_resposta(self):
        lista, f = F.criar([], '1', '2', 'comando')
        self.assertTrue(F.achar(lista, '1', '2', 'comando') and F.achar(lista, '1', '2'))
        self.assertIsNone(F.achar(lista, '2', '1'))                       # quem obedece não manda de volta
        lista, _ = F.criar(lista, '3', '2', 'leitura')
        self.assertIsNone(F.achar(lista, '3', '2', 'comando'))            # leitura não manda
        with self.assertRaises(ValueError):
            F.criar(lista, '1', '1')
        ev = [{'t': 'eu', 'texto': 'oi'}, {'t': 'kc', 'texto': 'velho'},
              {'t': 'eu', 'texto': F.pedido('A', '1', 'faz x', 'abc123')}, {'t': 'kc', 'texto': 'feito x'}]
        self.assertEqual(F.resposta_apos(ev, 'abc123'), 'feito x')
        self.assertEqual(F.mensagens(ev)[2]['quem'], 'fio')
        self.assertEqual(F.normalizar(lista + [{'de': '1', 'para': '1', 'modo': 'leitura'}], {'1', '2', '3'}), lista)
        self.assertEqual(F.normalizar(lista, {'1', '2'}), [f])            # aba fechada leva os fios dela

    def test_limite_e_contexto(self):
        h = {'f': [time.time()] * F.LIMITE_ENVIOS}
        self.assertFalse(F.pode_enviar(h, 'f'))
        self.assertTrue(F.pode_enviar({'f': [time.time() - F.JANELA_S - 1] * 20}, 'f'))
        lista, _ = F.criar([], '1', '2', 'leitura')
        txt = F.contexto('1', lista, {'2': {'nome': 'B', 'quem': 'kani'}})
        self.assertIn('mcp__equipe__chat', txt); self.assertIn('só LER', txt)
        self.assertEqual(F.contexto('2', lista, {}), '')


if __name__ == '__main__':
    unittest.main()
