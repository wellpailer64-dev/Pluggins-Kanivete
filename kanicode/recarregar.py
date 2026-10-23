"""Depois de mexer no código do KaniCode: aplica no KaniCode aberto (sem o Pailer fechar e abrir).

Sem reiniciar sempre que der (2026-10-23, kanicode._quente): .css = troca na página na hora; .js/.html = recarrega só a
página (a tarefa em andamento continua); .py de módulo com RECARREGAVEL = True = recarregado dentro do processo. Outro
.py (ex.: kanicode.py) = reinicia o processo (volta aberto, na mesma conversa), esperando a resposta terminar. Rodar: py -3.13 recarregar.py [--recarregar | --reiniciar]
"""
import sys

import kanicode as kc

acao = "reiniciar" if "--reiniciar" in sys.argv else "recarregar" if "--recarregar" in sys.argv else "atualizar"
r = kc.avisar(acao)
print({None: "KaniCode fechado: nada a fazer", "nada": "nada mudou desde que abriu",
       "?": "KaniCode antigo (sem este comando): feche e abra uma vez"}.get(r, r))
