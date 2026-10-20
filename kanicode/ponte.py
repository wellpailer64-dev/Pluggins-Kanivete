"""Ponte do KaniCode com o KANIVETE (Functions/plugins_pessoais.py só chama o que está em API_KANIVETE).

O KaniCode roda num processo à parte (kanicode.py): este módulo só abre, mostra, fecha e conta o estado dele.
"""
import os, shutil, subprocess, sys

import kanicode as kc

API_KANIVETE = ("estado", "abrir", "fechar")


def estado():
    return {"rodando": kc.avisar("ping") == "ok", "versao": kc.VERSAO, "dados": kc.DADOS}


def _python():
    """um Python com o pywebview, sem janela de console (o KANIVETE pode ser o .exe, que não serve de Python)"""
    if not getattr(sys, "frozen", False):
        w = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if os.path.isfile(w):
            return [w]
    pyw = shutil.which("pyw")
    if pyw:
        return [pyw, "-3.13"]
    raise RuntimeError("não achei o Python 3.13 (pyw) para abrir o KaniCode")


def abrir():
    """abre o KaniCode (ou traz a janela dele, se já estiver aberto). Processo solto: não fecha junto com o KANIVETE."""
    if kc.avisar("mostrar") == "ok":
        return {"rodando": True, "ja_estava": True}
    flags = 0x00000008 | 0x00000200   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    cmd = _python() + [os.path.join(kc.PASTA, "kanicode.py")]
    try:
        subprocess.Popen(cmd, cwd=kc.PASTA, creationflags=flags | 0x01000000, close_fds=True)   # + CREATE_BREAKAWAY_FROM_JOB
    except OSError:
        subprocess.Popen(cmd, cwd=kc.PASTA, creationflags=flags, close_fds=True)   # o job do app não deixa sair dele
    return {"rodando": True, "ja_estava": False}


def fechar():
    return {"fechado": kc.avisar("sair") == "ok"}
