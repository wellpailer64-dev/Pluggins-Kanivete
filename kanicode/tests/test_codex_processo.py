"""Processos locais reais reproduzem pipes cheios, silêncio e cancelamento; sem API."""
import ctypes
import os
from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import codex_processo


class ProcessoCodexTest(unittest.TestCase):
    def executar(self, codigo, entrada="", receber=None, parar=None, prazo=3):
        self.linhas = []
        return codex_processo.executar([sys.executable, "-u", "-c", codigo], str(Path.cwd()), entrada,
                                      receber or self.linhas.append, lambda: None, parar=parar, prazo=prazo)

    def test_stderr_cheio_antes_de_ler_prompt_grande(self):
        r = self.executar("import sys; sys.stderr.write('E'*300000); sys.stderr.flush(); "
                          "s=sys.stdin.read(); print(len(s)); print('ação')", "a" * 2_000_000)
        self.assertEqual(r["codigo"], 0)
        self.assertFalse(r["estourou"])
        self.assertEqual(self.linhas, ["2000000\n", "ação\n"])
        self.assertLessEqual(len(r["erro"]), 6000)

    def test_saida_nao_zero_preserva_erro(self):
        r = self.executar("import sys; sys.stderr.write('erro concreto'); sys.exit(2)")
        self.assertEqual(r["codigo"], 2)
        self.assertIn("erro concreto", r["erro"])

    def test_prazo_sem_qualquer_saida(self):
        r = self.executar("import time; time.sleep(60)", prazo=0.4)
        self.assertTrue(r["estourou"])
        self.assertFalse(r["cancelado"])
        self.assertLess(r["ms"], 3000)

    def test_cancelamento_nao_e_timeout(self):
        parar = threading.Event()
        r = self.executar("import time; print('pronto'); time.sleep(60)",
                          receber=lambda linha: parar.set(), parar=parar)
        self.assertTrue(r["cancelado"])
        self.assertFalse(r["estourou"])
        self.assertLess(r["ms"], 3000)

    @unittest.skipUnless(os.name == "nt", "Job Object do Windows")
    def test_cancelamento_encerra_processo_filho(self):
        parar = threading.Event()
        filhos = []
        def receber(linha):
            filhos.append(int(linha))
            parar.set()
        r = self.executar("import subprocess,sys,time; "
                          "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
                          "print(p.pid); time.sleep(60)", receber=receber, parar=parar)
        self.assertTrue(r["cancelado"])
        self.assertEqual(len(filhos), 1)
        from ctypes import wintypes
        k = ctypes.WinDLL("kernel32")
        k.OpenProcess.restype = wintypes.HANDLE
        h = k.OpenProcess(0x100000, False, filhos[0])
        if h:
            try:
                self.assertNotEqual(k.WaitForSingleObject(wintypes.HANDLE(h), 1000), 258,
                                    "o filho continuou vivo depois de Parar")
            finally:
                k.CloseHandle(wintypes.HANDLE(h))

    @unittest.skipUnless(os.name == "nt", "Job Object do Windows")
    def test_filho_com_pipe_herdado_nao_prende_fim(self):
        r = self.executar("import subprocess,sys; "
                          "subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); print('fim')")
        self.assertEqual(r["codigo"], 0)
        self.assertFalse(r["estourou"])
        self.assertEqual(self.linhas, ["fim\n"])
        self.assertLess(r["ms"], 2000)


if __name__ == "__main__":
    unittest.main()
