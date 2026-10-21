"""Atalhos do KaniCode no Windows: área de trabalho, menu Iniciar e iniciar com o PC (pasta Inicializar).

O KaniCode não precisa do KANIVETE aberto: o atalho chama o pythonw do 3.13 com o kanicode.py (sem console). Todos levam
o mesmo AppUserModelID do processo (kanicode.AUMID), para o ícone fixado na barra de tarefas ser o da janela aberta.
Fixar na barra o Windows 11 só deixa a pessoa fazer (botão direito no atalho › Fixar na barra de tarefas).
Rodar: py -3.13 atalhos.py estado | criar desktop|menu|inicio | apagar desktop|menu|inicio   (responde JSON)
"""
import json, os, sys

import kanicode as kc

ICO = os.path.join(kc.DADOS, "kanicode.ico")
NOME = "KaniCode.lnk"


def _pastas():
    from win32com.shell import shell, shellcon
    p = lambda c: shell.SHGetFolderPath(0, c, None, 0)
    return {"desktop": p(shellcon.CSIDL_DESKTOPDIRECTORY), "menu": p(shellcon.CSIDL_PROGRAMS), "inicio": p(shellcon.CSIDL_STARTUP)}


def _pythonw():
    w = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return w if os.path.isfile(w) else sys.executable


def _icone():
    if not os.path.isfile(ICO):
        from PIL import Image
        os.makedirs(kc.DADOS, exist_ok=True)
        Image.open(os.path.join(kc.PASTA, "icone.png")).convert("RGBA").save(ICO, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64)])
    return ICO


def estado():
    return {k: os.path.isfile(os.path.join(p, NOME)) for k, p in _pastas().items()}


def criar(lugar):
    import pythoncom
    from win32com.propsys import propsys, pscon
    from win32com.shell import shell
    lnk = pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink)
    lnk.SetPath(_pythonw())
    lnk.SetArguments(f'"{os.path.join(kc.PASTA, "kanicode.py")}"')
    lnk.SetWorkingDirectory(kc.PASTA)
    lnk.SetIconLocation(_icone(), 0)
    lnk.SetDescription("KaniCode — converse com o Claude numa bolinha na área de trabalho")
    ps = lnk.QueryInterface(propsys.IID_IPropertyStore)
    ps.SetValue(pscon.PKEY_AppUserModel_ID, propsys.PROPVARIANTType(kc.AUMID))
    ps.Commit()
    lnk.QueryInterface(pythoncom.IID_IPersistFile).Save(os.path.join(_pastas()[lugar], NOME), 0)
    return estado()


def apagar(lugar):
    try:
        os.remove(os.path.join(_pastas()[lugar], NOME))
    except FileNotFoundError:
        pass
    return estado()


if __name__ == "__main__":
    a = sys.argv[1:] or ["estado"]
    print(json.dumps({"estado": estado, "criar": criar, "apagar": apagar}[a[0]](*a[1:])))
