"""Depois de mexer no código do KaniCode: aplica no KaniCode aberto (sem o Pailer fechar e abrir).

Só a janela mudou (ui/, .css/.js) = recarrega a página; algum .py mudou = reinicia o processo (volta aberto, na mesma
conversa). No meio de uma resposta, espera ela terminar. Rodar: py -3.13 recarregar.py [--recarregar | --reiniciar]
"""
import sys

import kanicode as kc

acao = "reiniciar" if "--reiniciar" in sys.argv else "recarregar" if "--recarregar" in sys.argv else "atualizar"
r = kc.avisar(acao)
print({None: "KaniCode fechado: nada a fazer", "nada": "nada mudou desde que abriu",
       "?": "KaniCode antigo (sem este comando): feche e abra uma vez"}.get(r, r))
