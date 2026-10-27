"""Nenhum módulo pode mudar argtypes/restype/errcheck em ctypes.windll: ele é o mesmo para o processo todo e o
pywebview usa as mesmas funções (2026-10-23: SetWindowPos tipado em navegador_painel.py fez o chat parar de abrir).
Quem precisa tipar usa uma cópia própria: ctypes.WinDLL("user32")."""
import ast
from pathlib import Path
import unittest

PLUGINS = Path(__file__).resolve().parents[2]
PASTAS = ("kanicode", "kanibrowser", "pandalab")
TIPOS = {"argtypes", "restype", "errcheck"}


def _cadeia(no):
    """ctypes.windll.user32.SetWindowPos -> ["ctypes", "windll", "user32", "SetWindowPos"] (None se não for nome.atrib...)"""
    partes = []
    while isinstance(no, ast.Attribute):
        partes.append(no.attr)
        no = no.value
    if not isinstance(no, ast.Name):
        return None
    return [no.id] + partes[::-1]


def _compartilhada(no, apelidos):
    """a expressão é ctypes.windll.<dll>[.<função>] ou um apelido disso?"""
    c = _cadeia(no)
    return bool(c) and ("windll" in c or c[0] in apelidos)


def problemas(fonte, nome="?"):
    arvore = ast.parse(fonte, nome)
    apelidos = set()   # nomes que apontam para ctypes.windll.<dll> ou para uma função dela
    achados = []
    for no in ast.walk(arvore):
        if isinstance(no, ast.Assign):
            pares = []
            for alvo in no.targets:
                if isinstance(alvo, ast.Tuple) and isinstance(no.value, ast.Tuple):
                    pares += zip(alvo.elts, no.value.elts)
                else:
                    pares.append((alvo, no.value))
            for alvo, valor in pares:
                if isinstance(alvo, ast.Name) and _compartilhada(valor, apelidos):
                    apelidos.add(alvo.id)
    for no in ast.walk(arvore):
        alvos = no.targets if isinstance(no, ast.Assign) else [no.target] if isinstance(no, ast.AugAssign) else []
        for alvo in alvos:
            if isinstance(alvo, ast.Attribute) and alvo.attr in TIPOS and _compartilhada(alvo.value, apelidos):
                achados.append(f"{nome}:{alvo.lineno}: {ast.unparse(alvo)}")
    return achados


class DllIsoladasTest(unittest.TestCase):
    def test_despertador_usa_DLL_propria_sem_agendar_no_sistema(self):
        import ctypes
        import datetime
        from unittest.mock import Mock, patch
        import cenas
        agora = datetime.datetime.now().astimezone()
        proxima = agora + datetime.timedelta(minutes=10)
        dll = Mock()
        dll.CreateWaitableTimerW.return_value = 123
        dll.SetWaitableTimer.return_value = True
        with patch.object(ctypes, 'WinDLL', return_value=dll) as abrir, \
             patch.object(ctypes, 'windll', Mock()), \
             patch.object(cenas, '_timer', {'h':None, 'alvo':None}), \
             patch.object(cenas, '_proxima', return_value=proxima):
            cenas._armar_despertador({}, agora)
            self.assertEqual(cenas._timer['alvo'], proxima - datetime.timedelta(seconds=40))
            abrir.assert_called_once_with('kernel32')
            self.assertEqual(dll.SetWaitableTimer.call_args.args[0], 123)
            self.assertTrue(dll.SetWaitableTimer.call_args.args[-1])
            dll.CancelWaitableTimer.assert_not_called()

    def test_detecta_os_jeitos_comuns(self):
        self.assertTrue(problemas("import ctypes\nctypes.windll.user32.SetWindowPos.argtypes = []"))
        self.assertTrue(problemas("import ctypes\nu32 = ctypes.windll.user32\nu32.SetWindowPos.argtypes = []"))
        self.assertTrue(problemas("import ctypes\nu, g = ctypes.windll.user32, ctypes.windll.gdi32\ng.X.restype = int"))
        self.assertTrue(problemas("import ctypes\nf = ctypes.windll.user32.F\nf.argtypes = []"))
        self.assertFalse(problemas("import ctypes\nu32 = ctypes.WinDLL('user32')\nu32.SetWindowPos.argtypes = []"))
        self.assertFalse(problemas("import ctypes\nctypes.windll.user32.SetWindowPos(0, 0, 1, 2, 3, 4, 0)"))

    def test_nenhum_modulo_tipa_o_windll_compartilhado(self):
        achados = []
        for pasta in PASTAS:
            for arq in sorted((PLUGINS / pasta).rglob("*.py")):
                if {"tests", "__pycache__", "android", ".git"} & set(arq.relative_to(PLUGINS).parts):
                    continue
                achados += problemas(arq.read_text(encoding="utf-8"), str(arq.relative_to(PLUGINS)))
        self.assertEqual(achados, [], "use ctypes.WinDLL('<dll>') em vez de ctypes.windll.<dll> para tipar funções")


if __name__ == "__main__":
    unittest.main()
