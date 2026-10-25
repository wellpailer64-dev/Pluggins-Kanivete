"""Ponte do KaniCode com o KANIVETE (Functions/plugins_pessoais.py só chama o que está em API_KANIVETE).

O KaniCode roda num processo à parte (kanicode.py): este módulo só abre, mostra, fecha e conta o estado dele.
"""
import base64, json, os, shutil, subprocess, sys

import kanicode as kc

API_KANIVETE = ("estado", "abrir", "fechar", "garantir", "atalhos", "atalho", "fundo", "progresso", "progresso_observador")


def progresso(itens):
    return kc.avisar('progresso ' + json.dumps(itens[:64], ensure_ascii=False)) == 'ok'


def progresso_observador():
    with open(os.path.join(kc.PASTA, 'progresso_kanivete.js'), encoding='utf-8') as f:
        return f.read()


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


def garantir():
    """"Abrir junto com o KANIVETE": abre só a bolinha se o KaniCode estiver fechado (aberto: não mexe na janela dele)"""
    if kc.avisar("ping") == "ok":
        return {"rodando": True, "ja_estava": True}
    return abrir()


def _atalhos(*a):
    """atalhos.py roda no Python 3.13 (pywin32), não no do KANIVETE (o .exe não traz o win32com)"""
    r = subprocess.run(["py", "-3.13", os.path.join(kc.PASTA, "atalhos.py"), *a], cwd=kc.PASTA, capture_output=True,
                       text=True, timeout=30, creationflags=0x08000000)   # CREATE_NO_WINDOW
    if r.returncode:
        raise RuntimeError((r.stderr.strip().splitlines() or ["atalhos falhou"])[-1])
    return json.loads(r.stdout)


def atalhos():
    return _atalhos("estado")


def atalho(lugar, ligar=True):
    """lugar = desktop | menu | inicio (iniciar com o Windows)"""
    if lugar not in ("desktop", "menu", "inicio"):
        raise ValueError("lugar inválido")
    return _atalhos("criar" if ligar else "apagar", lugar)


def fundo():
    """vídeo do lobby (o do Início do KANIVETE tingido de verde-limão) como data URL"""
    with open(os.path.join(kc.PASTA, "lobby.webm"), "rb") as f:
        return "data:video/webm;base64," + base64.b64encode(f.read()).decode()
