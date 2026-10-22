"""Executa unittest na cópia. Evita conexão Python acidental ao app vivo na porta 9222."""
from pathlib import Path
import socket
import sys
import unittest


def main():
    raiz, teste = (Path(v).resolve() for v in sys.argv[1:3])
    if not teste.is_relative_to(raiz) or not teste.is_file():
        raise SystemExit("teste fora da cópia")
    conectar = socket.socket.connect
    def seguro(self, destino):
        if isinstance(destino, tuple) and len(destino) > 1 and destino[1] == 9222:
            raise PermissionError("porta 9222 proibida nos testes; use instância de teste 9333")
        return conectar(self, destino)
    socket.socket.connect = seguro
    sys.path.insert(0, str(raiz))
    suite = unittest.defaultTestLoader.discover(str(teste.parent), pattern=teste.name)
    if suite.countTestCases() == 0:
        raise SystemExit("nenhum teste unittest encontrado")
    r = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if r.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
