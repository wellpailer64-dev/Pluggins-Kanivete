"""KaniBrowser hospedado pelo KaniCode: o Chrome do Kanivete sem precisar do KANIVETE aberto.

O navegador é aberto por ESTE processo (canal privado por pipe, como no KANIVETE: kanibrowser.py) e fecha junto com o
KaniCode; os logins ficam no perfil (D:\\Kanivete\\KaniBrowser\\perfil). Quem manda é o kb.py, pelo canal de controle do
KaniCode (127.0.0.1:47613) com a chave de DADOS/kb_chave.txt: "kb <chave> {"f": função da ponte, "a": {argumentos}}".
"""
import json, os, secrets, sys

PASTA = os.path.dirname(os.path.abspath(__file__))
KB = os.path.join(os.path.dirname(PASTA), "kanibrowser")


def chave(dados):
    arq = os.path.join(dados, "kb_chave.txt")
    try:
        with open(arq, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        c = secrets.token_urlsafe(24)
        os.makedirs(dados, exist_ok=True)
        with open(arq, "w", encoding="utf-8") as f:
            f.write(c)
        return c


def _ponte(projeto):
    for p in (KB, projeto):   # projeto (KANIVETE): Functions.drive_publico do "link"
        if p and p not in sys.path:
            sys.path.append(p)
    # o ponte.py do KaniBrowser, pelo caminho: "import ponte" pegaria o ponte.py do próprio KaniCode
    if "kb_ponte" not in sys.modules:
        import importlib.util
        spec = importlib.util.spec_from_file_location("kb_ponte", os.path.join(KB, "ponte.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        sys.modules["kb_ponte"] = mod
    return sys.modules["kb_ponte"]


def chamar(linha, dados, projeto):
    """linha = '<chave> <json>' → resposta JSON {"ok", "r"|"e"}"""
    ch, _, resto = linha.partition(" ")
    if not secrets.compare_digest(ch, chave(dados)):
        return {"ok": 0, "e": "chave errada"}
    try:
        p = json.loads(resto)
        mod = _ponte(projeto)
        f = p.get("f")
        if f not in mod.API_KANIVETE:
            return {"ok": 0, "e": f"função desconhecida: {f}"}
        return {"ok": 1, "r": getattr(mod, f)(**(p.get("a") or {}))}
    except Exception as e:
        msg = str(e)
        if "fechou" in msg or "Browser.getVersion" in msg:
            msg += " (o KaniBrowser pode estar aberto no KANIVETE: feche lá ou abra o KANIVETE em modo agente)"
        return {"ok": 0, "e": msg}
