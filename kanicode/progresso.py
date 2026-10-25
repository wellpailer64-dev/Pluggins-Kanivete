"""Progresso compartilhado, sem conversa, tokens ou histórico em disco."""
import math
import threading
import time

_trava = threading.Lock()
_itens = {}


def registrar(dados):
    id = str(dados.get('id', ''))[:160]
    if not id or dados.get('tipo') not in ('render', 'download'):
        raise ValueError('Operação inválida')
    pct = dados.get('pct')
    if pct is not None:
        pct = float(pct)
        if not math.isfinite(pct):
            raise ValueError('Progresso inválido')
        pct = max(0, min(100, pct))
    estado = dados.get('estado', 'ativo')
    if estado not in ('ativo', 'concluido', 'erro', 'cancelado'):
        raise ValueError('Estado inválido')
    item = {'id': id, 'tipo': dados['tipo'], 'titulo': str(dados.get('titulo') or dados['tipo'])[:140],
            'pct': 100 if estado == 'concluido' else pct, 'estado': estado,
            'detalhe': str(dados.get('detalhe') or '')[:240], 'atualizado': time.monotonic()}
    with _trava:
        _itens[id] = item
        if len(_itens) > 64:
            del _itens[min(_itens, key=lambda k: _itens[k]['atualizado'])]
    return True


def listar():
    agora = time.monotonic()
    with _trava:
        for id, item in list(_itens.items()):
            if agora - item['atualizado'] > (3600 if item['estado'] == 'ativo' else 10):
                del _itens[id]
        return [dict(item, sem_sinal=agora - item['atualizado'] > 25)
                for item in _itens.values()]
