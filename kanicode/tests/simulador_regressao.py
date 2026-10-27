"""Roteiros determinísticos: só simula a fronteira do motor, não a lógica do aplicativo."""
import random


class Relogio:
    def __init__(self):
        self.agora = 0

    def avancar(self, segundos):
        if segundos < 0:
            raise ValueError('o relógio não volta')
        self.agora += segundos
        return self.agora


def roteiro(aba, blocos=10, falhar=False):
    yield {'t': 'inicio'}
    yield {'t': 'texto_novo'}
    for i in range(blocos):
        yield {'t': 'texto', 'd': f'{aba}:{i}:ação;'}
    yield {'t': 'saiu', 'erro': 'falha simulada'} if falhar else {'t': 'fim'}


def intercalar(abas=2, blocos=10, semente=42, falha_aba=None):
    """Mantém a ordem dentro de cada aba; varia só a intercalação entre elas."""
    rng = random.Random(semente)
    filas = {str(i + 1): iter(roteiro(str(i + 1), blocos, str(i + 1) == falha_aba)) for i in range(abas)}
    while filas:
        aba = rng.choice(list(filas))
        try:
            yield aba, next(filas[aba])
        except StopIteration:
            del filas[aba]
