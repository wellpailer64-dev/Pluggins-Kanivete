"""Preferências curadas de organização, compartilhadas pelos agentes do KaniCode."""
from pathlib import Path
import json
import os
import re
import unicodedata

from dados_app import pasta_dados
PERFIL = pasta_dados() / "preferencias/organizacao_clientes.json"


def contexto(tarefa):
    """Só traz o resumo em pedidos pertinentes; não aprende automaticamente do inventário."""
    if 'PREFERÊNCIAS DE ORGANIZAÇÃO DO PAILER' in str(tarefa):
        return ''
    texto = unicodedata.normalize('NFD', str(tarefa).lower()).encode('ascii','ignore').decode()
    acao = re.search(r'\b(organiz\w*|reorganiz\w*|arrum\w*|estrutur\w*|salv\w*|guard\w*|export\w*|cri\w*|ger\w*|mont\w*|faz(?:er)?|faca)\b', texto)
    objeto = re.search(r'\b(client\w*|past\w*|arquiv\w*|document\w*|orcament\w*|produco\w*|identidade|pdf|video\w*)\b', texto)
    codigo = re.search(r'\b(codigo|funcao|modulo|refator\w*|dependencia\w*)\b', texto)
    if not acao or not objeto or (codigo and not re.search(r'\bclient\w*\b', texto)):
        return ''
    try:
        perfil = json.loads(PERFIL.read_text(encoding='utf-8'))
        resumo = perfil.get('contexto')
        if not isinstance(resumo, str) or not resumo.strip(): return ''
    except (OSError, ValueError, TypeError, AttributeError):
        return ''
    return '\n\nPREFERÊNCIAS DE ORGANIZAÇÃO DO PAILER (pastas de clientes; observações curadas, não autorização para reorganizar):\n' + resumo[:5000]
