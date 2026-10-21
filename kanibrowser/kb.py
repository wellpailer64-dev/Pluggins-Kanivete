"""Linha de comando do KaniBrowser para o agente. O navegador mora no processo que o abriu (canal privado; não há porta
do Chrome): o KANIVETE em modo agente (porta 9222 do Pailer ou --porta 9333 de teste) se ele já está com o KaniBrowser
aberto; senão o KaniCode (kanicode/navegador.py, canal 127.0.0.1:47613 com chave) — funciona sem o KANIVETE aberto.
--onde kanivete|kanicode força um dos dois. Depois de ir/abrir/nova/js/instagram/chatgpt/link sai "tela: <print>"
(JPEG da aba da Kani; o KaniCode mostra na conversa, no PC e no celular); --sem-foto não tira.

  Sem --aba, tudo roda na ABA DA KANI (o Pailer vê ao vivo no painel, à direita). Nenhuma janela do Chrome
  aparece: tudo é transmitido para dentro do Kanivete (visao.py).
  py -3.13 kb.py estado | abrir [url] | abas | ir <url> [--aba ID] | nova <url> | frente [--aba ID] | fechar --aba ID
  py -3.13 kb.py texto [--aba ID]          foto <arquivo.png> [--aba ID] [--inteira]
  py -3.13 kb.py imagens [--aba ID] [--min 250]
  py -3.13 kb.py baixar [--aba ID] [--max 20] [--min 250] (--demanda ID8 | --pasta P)
  py -3.13 kb.py destinos
  py -3.13 kb.py js "<código JS>" | js @arquivo.js     (na aba da Kani; aceita async/Promise; volta o valor)
  py -3.13 kb.py chatgpt "<pergunta ou pedido de imagem>" [--pasta P]   (conta do Pailer; imagens salvas)
  py -3.13 kb.py instagram <@perfil>      link <url> (--demanda ID8 | --pasta P)      pesquisar "<termo>" [--max 3]
"""
import argparse, json, os, socket, sys, urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


CHAVE_KC = os.path.join(os.path.splitdrive(os.path.abspath(__file__))[0] + os.sep, "Kanivete", "KaniCode", "kb_chave.txt")
_onde = {}


def chamar_kanicode(funcao, args=None, timeout=420):
    try:
        with open(CHAVE_KC, encoding="utf-8") as f:
            ch = f.read().strip()
        s = socket.create_connection(("127.0.0.1", 47613), timeout=5)
    except OSError:
        raise RuntimeError("nem o KANIVETE em modo agente nem o KaniCode estão abertos")
    with s:
        s.settimeout(timeout)
        s.sendall(("kb " + ch + " " + json.dumps({"f": funcao, "a": args or {}}, ensure_ascii=False)).encode("utf-8") + b"\n")
        buf = b""
        while not buf.endswith(b"\n"):
            p = s.recv(1 << 16)
            if not p:
                break
            buf += p
    if not buf.strip():
        raise RuntimeError("o KaniCode não respondeu (versão antiga? reinicie o KaniCode)")
    v = json.loads(buf)
    if not v["ok"]:
        raise RuntimeError(v["e"])
    return v["r"]


def chamar(porta, funcao, args=None, timeout=420, onde="auto"):
    """manda para o KANIVETE (se ele já está com o navegador aberto) ou para o KaniCode"""
    if "x" not in _onde:
        _onde["x"] = onde
        if onde == "auto":
            try:
                _onde["x"] = "kanivete" if chamar_kanivete(porta, "estado", {}, 15).get("aberto") else "kanicode"
            except Exception:
                _onde["x"] = "kanicode"
    if _onde["x"] == "kanicode":
        return chamar_kanicode(funcao, args, timeout)
    return chamar_kanivete(porta, funcao, args, timeout)


def chamar_kanivete(porta, funcao, args=None, timeout=420):
    from websockets.sync.client import connect
    with urllib.request.urlopen(f"http://127.0.0.1:{porta}/json", timeout=5) as r:
        alvo = next(t for t in json.loads(r.read()) if t.get("type") == "page" and "index.html" in t.get("url", ""))
    expr = f"KPLUG.chamar('kanibrowser', {json.dumps(funcao)}, {json.dumps(args or {})}).then(r => JSON.stringify({{ok: 1, r}}), e => JSON.stringify({{ok: 0, e: e.message}}))"
    with connect(alvo["webSocketDebuggerUrl"], max_size=None, open_timeout=10) as ws:
        ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                            "params": {"expression": expr, "awaitPromise": True, "returnByValue": True}}))
        while True:
            m = json.loads(ws.recv(timeout=timeout))
            if m.get("id") == 1:
                v = json.loads(m["result"]["result"]["value"])
                if not v["ok"]:
                    raise RuntimeError(v["e"])
                return v["r"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd"); ap.add_argument("arg", nargs="?")
    ap.add_argument("--aba"); ap.add_argument("--min", type=int, default=250); ap.add_argument("--max", type=int, default=20)
    ap.add_argument("--demanda"); ap.add_argument("--pasta"); ap.add_argument("--inteira", action="store_true")
    ap.add_argument("--porta", default="9222")
    ap.add_argument("--onde", default="auto", choices=("auto", "kanivete", "kanicode"))
    ap.add_argument("--sem-foto", action="store_true")
    a = ap.parse_args()
    c = lambda f, **k: chamar(a.porta, f, {x: y for x, y in k.items() if y is not None}, onde=a.onde)
    r = _rodar(a, c)
    if r == 0 and not a.sem_foto and a.cmd in ("abrir", "ir", "nova", "js", "instagram", "chatgpt", "link"):
        try:
            p = c("vista")
            if p:
                print("tela:", p.replace("\\", "/"))
        except Exception:
            pass
    return r


def _rodar(a, c):
    try:
        if a.cmd in ("abrir", "abas", "estado"):
            r = c("abrir", url=a.arg) if a.cmd == "abrir" else c(a.cmd)
            for t in (r["abas"] if a.cmd == "estado" else r):
                print(t["id"][:8], t["titulo"][:60], t["url"][:90])
            if a.cmd == "estado":
                print("aberto:", r["aberto"])
        elif a.cmd == "ir":
            print(c("ir", url=a.arg, aba=a.aba))
        elif a.cmd == "nova":
            print(c("nova", url=a.arg)["id"][:8])
        elif a.cmd == "texto":
            print(c("texto", aba=a.aba))
        elif a.cmd == "foto":
            print(c("foto", aba=a.aba, caminho=a.arg, inteira=a.inteira))
        elif a.cmd == "imagens":
            for i in c("imagens", aba=a.aba, minimo=a.min):
                print(f"{i['w']}x{i['h']}  {i['grande'][:120]}")
        elif a.cmd == "baixar":
            ims = c("imagens", aba=a.aba, minimo=a.min)[:a.max]
            r = c("baixar_imagens", urls=[i["url"] for i in ims], demanda=a.demanda, pasta=a.pasta, aba=a.aba)
            print(f"{len(r['arquivos'])} imagem(ns) em {r['pasta']}; falhas: {len(r['falhas'])}")
        elif a.cmd == "instagram":
            r = c("instagram", usuario=a.arg, aba=a.aba)
            print("logado:", r["logado"], "|", " ".join(r["cabecalho"][:200].split()))
            for p in r["posts"]:
                print(p["link"], "|", p["alt"][:100])
        elif a.cmd == "link":
            r = c("baixar_link", url=a.arg, demanda=a.demanda, pasta=a.pasta)
            print(f"{len(r['arquivos'])} arquivo(s) em {r['pasta']}")
        elif a.cmd == "pesquisar":
            for r in c("pesquisar", termo=a.arg, n=a.max if a.max != 20 else 3):
                print("##", r["titulo"], "-", r["url"]); print(r["texto"][:3000]); print()
        elif a.cmd == "chatgpt":
            r = c("chatgpt", pergunta=a.arg, pasta=a.pasta)
            print(r["texto"]); [print("imagem:", i) for i in r["imagens"]]
        elif a.cmd == "js":
            cod = open(a.arg[1:], encoding="utf-8").read() if a.arg.startswith("@") else a.arg
            r = c("js_kani", codigo=cod)
            print(r if isinstance(r, str) else json.dumps(r, ensure_ascii=False))
        elif a.cmd == "destinos":
            for d in c("destinos"):
                print(d["id"][:8], d["cliente"], "|", d["nome"])
        elif a.cmd in ("frente", "fechar"):
            c(a.cmd, aba=a.aba); print("ok")
        else:
            print(__doc__); return 1
    except Exception as e:
        print("ERRO:", e); return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
