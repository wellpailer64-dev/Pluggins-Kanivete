"""Carga reproduzível no roteamento real da App, sem modelo, navegador, voz ou rede."""
import json
import os
from pathlib import Path
import statistics
import sys
import time
import tracemalloc
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import kanicode
from simulador_regressao import intercalar, Relogio


class CargaRegressaoTest(unittest.TestCase):
    def test_roteiro_e_relogio_reproduziveis(self):
        self.assertEqual(list(intercalar(2, 10, 42)), list(intercalar(2, 10, 42)))
        self.assertNotEqual(list(intercalar(2, 10, 42)), list(intercalar(2, 10, 43)))
        relogio = Relogio()
        self.assertEqual(relogio.avancar(2), 2)
        with self.assertRaises(ValueError):
            relogio.avancar(-1)

    def test_rajadas_preservam_ordem_aba_e_falha_independente(self):
        app = kanicode.App()
        app._codex_voz = Mock()
        app._falar_agora = Mock(return_value=False)
        app._bola_atividade = Mock()
        app._bola_estado = Mock()
        app._na_ui = Mock()
        app._todo_agente_finalizar = Mock()
        app._fila_tentar = Mock()
        for _ in range(7):
            app.aba_nova()
        recebidos = []
        app._janela = Mock()
        def receber(js):
            recebidos.append(json.loads(js[js.index('(') + 1:-1]))
        app._janela.evaluate_js = receber
        callbacks = {a: app._na_aba(a, app._evento) for a in app._abas}
        metricas = []
        for n_abas, blocos in ((1, 1000), (2, 500), (8, 1250)):
            recebidos.clear()
            roteiro = list(intercalar(n_abas, blocos, 42, falha_aba='1'))
            tempos, bytes_entrada = [], sum(len(json.dumps(e, ensure_ascii=False).encode('utf-8')) for _, e in roteiro)
            tracemalloc.start()
            inicial = tracemalloc.get_traced_memory()[0]
            inicio = time.perf_counter()
            for aba, ev in roteiro:
                t = time.perf_counter()
                callbacks[aba](dict(ev))
                tempos.append((time.perf_counter() - t) * 1000)
            duracao = time.perf_counter() - inicio
            atual, pico = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            self.assertEqual(len(recebidos), len(roteiro))
            for i in range(n_abas):
                aba = str(i + 1)
                texto = ''.join(e.get('d', '') for e in recebidos if e.get('aba') == aba and e['t'] == 'texto')
                self.assertEqual(texto, ''.join(f'{aba}:{j}:ação;' for j in range(blocos)))
                eventos = [e['t'] for e in recebidos if e.get('aba') == aba]
                self.assertEqual(eventos[-1], 'saiu' if aba == '1' else 'fim')
                self.assertFalse(app._abas[aba].ocupada())
            ordenados = sorted(tempos)
            metricas.append({'abas': n_abas, 'eventos': len(roteiro), 'bytes': bytes_entrada,
                             'ms': round(duracao * 1000, 2), 'eventos_s': round(len(roteiro) / duracao, 2),
                             'p50_despacho_ms': statistics.median(tempos), 'p95_despacho_ms': ordenados[int(.95 * (len(tempos) - 1))],
                             'memoria_inicial_bytes': inicial, 'memoria_final_bytes': atual, 'pico_bytes': pico,
                             'semente': 42, 'escopo': 'App Python até evaluate_js simulado; não mede DOM nem renderização'})
        destino = Path(os.environ.get('KANICODE_DADOS_TESTE', kanicode.DADOS)) / 'carga.json'
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps(metricas, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    unittest.main()
