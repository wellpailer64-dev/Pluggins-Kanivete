"""Executa uma suíte com proteção contra gravações nos dados reais do KaniCode."""
import os
from pathlib import Path
import sys
import unittest


def proteger(protegidos=None):
    if os.environ.get("KANICODE_TESTE") != "1":
        raise RuntimeError("use verificar.py para preparar o ambiente isolado")
    from dados_app import pasta_dados
    pasta_dados()   # também recusa configuração de teste fora da área permitida
    protegidos = [Path(p).resolve() for p in (protegidos if protegidos is not None else ("D:/Kanivete/KaniCode", "D:/Kanivete/casa"))]

    def conferir(caminho):
        if isinstance(caminho, (str, bytes, os.PathLike)):
            p = Path(os.fsdecode(caminho)).resolve()
            if any(p == base or p.is_relative_to(base) for base in protegidos):
                raise PermissionError("teste tentou gravar nos dados reais: " + str(p))

    def auditar(evento, args):
        if evento == "open":
            modo, flags = args[1:3]
            if (isinstance(modo, str) and any(c in modo for c in "wax+")) or (isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)):
                conferir(args[0])
        elif evento in ("os.remove", "os.rmdir", "os.mkdir", "os.chmod", "os.utime", "os.truncate"):
            conferir(args[0])
        elif evento in ("os.rename", "os.link", "os.symlink"):
            conferir(args[0]); conferir(args[1])
        elif evento == "socket.connect" and isinstance(args[1], tuple) and len(args[1]) > 1 and args[1][1] == 9222:
            raise PermissionError("porta 9222 proibida nos testes")
    sys.addaudithook(auditar)


def main():
    proteger()
    raiz = Path(__file__).resolve().parent
    suite = unittest.defaultTestLoader.discover(str(raiz / "tests"), pattern=sys.argv[1])
    if not suite.countTestCases():
        raise RuntimeError("nenhum teste encontrado")
    r = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if r.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())

