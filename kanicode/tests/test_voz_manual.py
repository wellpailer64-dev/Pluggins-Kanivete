"""Botão 🎤: pausa para pensar não corta o pedido (só o 2º clique); o Ei Kani continua parando na pausa.
Sem microfone nem modelos: VAD falso (fala = bloco alto) e transcrição falsa (conta os trechos falados)."""
import os
import queue
import sys
import threading
import time
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import voz  # noqa: E402


class _VadFalso:
    def zerar(self):
        pass

    def fala(self, x):
        return 1.0 if np.abs(x).max() > 1000 else 0.0


def _audio():
    fala = np.full(int(voz.SR * 1.0), 5000, np.int16)
    pausa = np.zeros(int(voz.SR * 3.0), np.int16)
    return np.concatenate([fala, pausa, fala])


def _trechos(audio):
    alto = (np.abs(audio) > 1000).astype(np.int8)
    return f"{int((np.diff(alto) == 1).sum() + alto[0])} trechos"


class VozManualTest(unittest.TestCase):
    def _pedido(self, manual):
        saida = []
        v = voz.Voz(ao_texto=saida.append, ao_estado=lambda e: None)
        v._fila, v._ligada, v._bipe = queue.Queue(), True, lambda s: None
        v._transcrever = lambda a: _trechos((a * 32768).astype(np.int16))
        a = _audio()
        for i in range(0, len(a) - voz.BLOCO + 1, voz.BLOCO):
            v._fila.put(a[i:i + voz.BLOCO])

        def segundo_clique():
            while not v._fila.empty():
                time.sleep(0.02)
            time.sleep(0.2)
            v.terminar()
        threading.Thread(target=segundo_clique, daemon=True).start()
        v._manual = manual
        v._pedido(_VadFalso())
        return saida

    def test_botao_grava_ate_o_segundo_clique(self):
        self.assertEqual(self._pedido(True), ["2 trechos"])

    def test_ei_kani_para_na_pausa(self):
        self.assertEqual(self._pedido(False), ["1 trechos"])


if __name__ == "__main__":
    unittest.main()
