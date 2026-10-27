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

    estrito = os.environ.get('KANICODE_REGRESSAO') == '1'
    import weakref
    canais_locais = weakref.WeakSet()
    nulo = Path(os.devnull).resolve()

    def canal_proprio(endereco):
        if not isinstance(endereco, tuple) or len(endereco) < 2 or endereco[0] not in ('127.0.0.1', '::1') or endereco[1] in (9222, 9333, 47613):
            return False
        for s in list(canais_locais):
            try:
                if s.fileno() != -1 and s.getsockname()[1] == endereco[1]:
                    return True
            except OSError:
                pass
        return False

    def conferir(caminho):
        if isinstance(caminho, (str, bytes, os.PathLike)):
            p = Path(os.fsdecode(caminho)).resolve()
            if p == nulo:
                return   # DEVNULL descarta dados; não grava arquivo fora da área de testes
            if estrito and not p.is_relative_to(Path('D:/kanivete_testes').resolve()):
                raise PermissionError('regressão tentou gravar fora da área isolada: ' + str(p))
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
        elif evento == "socket.bind" and estrito:
            endereco = args[1]
            if isinstance(endereco, tuple) and len(endereco) > 1 and endereco[0] in ('127.0.0.1', '::1') and endereco[1] == 0:
                canais_locais.add(args[0])   # asyncio/Playwright: somente porta efêmera criada neste processo
        elif evento == "socket.connect":
            if estrito and not canal_proprio(args[1]):
                raise PermissionError('rede externa ou serviço real bloqueado na bateria simulada')
            if isinstance(args[1], tuple) and len(args[1]) > 1 and args[1][1] == 9222:
                raise PermissionError("porta 9222 proibida nos testes")
    sys.addaudithook(auditar)


class ResultadoRegistrado(unittest.TextTestResult):
    """Registra começo e fim de cada caso, inclusive skips, subtestes e interrupções."""
    def startTest(self, test):
        super().startTest(test)
        import time
        self._inicio_caso = time.perf_counter()
        self._estado_caso, self._motivo_caso = 'aprovado', ''
        self._registrar({'evento': 'inicio', 'caso': test.id()})

    def _registrar(self, evento):
        import json
        destino = os.environ.get('KANICODE_RESULTADO_TESTE')
        if not destino:
            return
        p = Path(destino).resolve()
        if not p.is_relative_to(Path('D:/kanivete_testes').resolve()):
            raise ValueError('resultado de teste fora da área isolada')
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open('a', encoding='utf-8') as f:
            f.write(json.dumps(evento, ensure_ascii=False) + '\n')

    def addError(self, test, err):
        self._estado_caso, self._motivo_caso = 'falhou', self._exc_info_to_string(err, test)
        super().addError(test, err)

    def addFailure(self, test, err):
        self._estado_caso, self._motivo_caso = 'falhou', self._exc_info_to_string(err, test)
        super().addFailure(test, err)

    def addSkip(self, test, reason):
        self._estado_caso, self._motivo_caso = 'ignorado', reason
        super().addSkip(test, reason)

    def addExpectedFailure(self, test, err):
        self._estado_caso, self._motivo_caso = 'ignorado', 'falha esperada: ' + self._exc_info_to_string(err, test)
        super().addExpectedFailure(test, err)

    def addUnexpectedSuccess(self, test):
        self._estado_caso, self._motivo_caso = 'falhou', 'sucesso inesperado de caso marcado como falha esperada'
        super().addUnexpectedSuccess(test)

    def addSubTest(self, test, subtest, err):
        if err is not None:
            self._estado_caso, self._motivo_caso = 'falhou', self._exc_info_to_string(err, test)
        super().addSubTest(test, subtest, err)

    def stopTest(self, test):
        import time
        self._registrar({'evento': 'fim', 'caso': test.id(), 'status': self._estado_caso,
                         'motivo': self._motivo_caso, 'ms': round((time.perf_counter() - self._inicio_caso) * 1000, 3)})
        super().stopTest(test)

def main():
    proteger()
    raiz = Path(__file__).resolve().parent
    suite = unittest.defaultTestLoader.discover(str(raiz / "tests"), pattern=sys.argv[1])
    if not suite.countTestCases():
        raise RuntimeError("nenhum teste encontrado")
    import faulthandler
    prazo = int(os.environ.get('KANICODE_TESTE_PRAZO', '180'))
    faulthandler.dump_traceback_later(max(1, prazo - 2))
    try:
        r = unittest.TextTestRunner(verbosity=2, resultclass=ResultadoRegistrado).run(suite)
        r._registrar({'evento': 'suite_fim', 'casos': r.testsRun, 'ok': r.wasSuccessful()})
    finally:
        faulthandler.cancel_dump_traceback_later()
    return 0 if r.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())

