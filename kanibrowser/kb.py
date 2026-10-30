"""Linha de comando do KaniBrowser para o agente. O navegador mora no processo que o abriu (canal privado; não há porta
do Chrome): PREFERÊNCIA = o navegador embutido do KaniCode (painel 🌐, aberto sozinho à vista; kanicode/navegador.py,
canal 127.0.0.1:47613 com chave); só sem o KaniCode aberto vai para o KANIVETE em modo agente (9222 ou --porta 9333).
--onde kanivete|kanicode força um dos dois. Depois de ir/abrir/nova/js/instagram/chatgpt/link sai "tela: <print>"
(JPEG da aba da Kani; o KaniCode mostra na conversa, no PC e no celular); --sem-foto não tira.

  Sem --aba, tudo roda na ABA DA KANI (o Pailer vê ao vivo no painel, à direita). Nenhuma janela do Chrome
  aparece: tudo é transmitido para dentro do Kanivete (visao.py).
  py -3.13 kb.py estado | abrir [url] | abas | ir <url> [--aba ID] | nova <url> | frente [--aba ID] | fechar --aba ID
  py -3.13 kb.py texto [--aba ID]          foto <arquivo.png> [--aba ID] [--inteira]
  py -3.13 kb.py imagens [--aba ID] [--min 250]
  py -3.13 kb.py baixar [--aba ID] [--max 20] [--min 250] (--demanda ID8 | --pasta P)
  py -3.13 kb.py anexar "<pasta ou a;b;c>"   (põe os arquivos no campo de envio aberto na página, ex. Fazer Entrega do Pandalab)
  py -3.13 kb.py destinos
  py -3.13 kb.py perfis                    (contas do navegador; > = a aberta)
  py -3.13 kb.py perfil <id|nome|e-mail>   (troca de conta: FECHA e reabre o navegador; só com motivo, e avise o Pailer)
  py -3.13 kb.py painel "estado|mostrar ID|nova URL|ir URL|fechar_aba ID|acao voltar|aparelho celular"   (abas do Pailer)
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
    """manda para o navegador embutido do KaniCode (preferência, 2026-10-23) ou, sem o KaniCode, para o KANIVETE"""
    if "x" not in _onde:
        _onde["x"] = onde
        if onde in ("auto", "kanicode"):
            # regra do Pailer (2026-10-23): o KaniCode é autossuficiente — o navegador mora no painel 🌐 dele, aberto à
            # vista (ao vivo, brilho verde-limão em volta enquanto a Kani mexe); o KANIVETE só quando o KaniCode não está aberto
            try:
                if not chamar_kanicode("painel", {}, 10).get("aberto"):
                    import time
                    for _ in range(60):   # o painel abre o KaniBrowser (e solta o do KANIVETE, se ele estiver com ele)
                        time.sleep(0.5)
                        if chamar_kanicode("painel", {}, 10).get("aberto"):
                            break
                _onde["x"] = "kanicode"
            except Exception:
                pass   # KaniCode fechado ou versão antiga (sem "painel"): segue o caminho antigo
        if _onde["x"] == "auto":
            try:
                aberto = chamar_kanivete(porta, "estado", {}, 15).get("aberto")
                if not aberto:
                    try:
                        chamar_kanicode("fechar_navegador", {}, 30)   # mesmo perfil não abre nos dois
                    except Exception:
                        pass
                    chamar_kanivete(porta, "abrir", {}, 120)
                    import time; time.sleep(4)          # a 1ª aba logo depois de abrir falhava ("Failed to open a new tab")
                _onde["x"] = "kanivete"
                mostrar_aba(porta)
            except Exception:
                _onde["x"] = "kanicode"
    if _onde["x"] == "kanicode":
        return chamar_kanicode(funcao, args, timeout)
    return chamar_kanivete(porta, funcao, args, timeout)


def mostrar_aba(porta):
    """traz a aba do KaniBrowser para a frente no KANIVETE (o Pailer vê a Visão da Kani ao vivo)"""
    chamar_kanivete(porta, None, expr="(async () => { if (typeof switchTool === 'function') switchTool('plugin-kanibrowser');"
                    " return JSON.stringify({ok: 1, r: 1}); })()", timeout=20)


def chamar_kanivete(porta, funcao, args=None, timeout=420, expr=None):
    from websockets.sync.client import connect
    with urllib.request.urlopen(f"http://127.0.0.1:{porta}/json", timeout=5) as r:
        alvo = next(t for t in json.loads(r.read()) if t.get("type") == "page" and "index.html" in t.get("url", ""))
    expr = expr or f"KPLUG.chamar('kanibrowser', {json.dumps(funcao)}, {json.dumps(args or {})}).then(r => JSON.stringify({{ok: 1, r}}), e => JSON.stringify({{ok: 0, e: e.message}}))"
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


def _anexar(alvo, c, exts=(".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".mov", ".pdf"), pedaco=150_000):
    """põe arquivos no último <input type=file> da aba da Kani (dispara change: o site vê como escolha do usuário).
    Vai em pedaços de base64 (o canal com o KaniCode não aguenta megas numa mensagem só)."""
    import base64, mimetypes
    if os.path.isdir(alvo or ""):
        arqs = sorted(os.path.join(alvo, n) for n in os.listdir(alvo) if n.lower().endswith(exts))
    else:
        arqs = [p for p in (alvo or "").split(";") if p]
    if not arqs or not all(os.path.isfile(p) for p in arqs):
        raise RuntimeError("anexar: passe uma pasta com imagens/vídeos ou arquivos separados por ';'")
    c("js_kani", codigo="window.__kbAnexo = []; 'ok'")
    for p in arqs:
        d = base64.b64encode(open(p, "rb").read()).decode()
        c("js_kani", codigo="window.__kbAnexo.push({n: %s, t: %s, d: ''}); 'ok'" % (
            json.dumps(os.path.basename(p)), json.dumps(mimetypes.guess_type(p)[0] or "application/octet-stream")))
        for i in range(0, len(d), pedaco):
            c("js_kani", codigo="window.__kbAnexo[window.__kbAnexo.length - 1].d += '%s'; 'ok'" % d[i:i + pedaco])
    return c("js_kani", codigo="""(() => { const ins = [...document.querySelectorAll('input[type=file]')];
        if (!ins.length) return 'nenhum campo de arquivo aberto na página';
        const dt = new DataTransfer();
        for (const f of window.__kbAnexo) { const b = Uint8Array.from(atob(f.d), c => c.charCodeAt(0)); dt.items.add(new File([b], f.n, {type: f.t})); }
        delete window.__kbAnexo;
        const i = ins[ins.length - 1]; i.files = dt.files;
        i.dispatchEvent(new Event('input', {bubbles: true})); i.dispatchEvent(new Event('change', {bubbles: true}));
        return dt.files.length + ' arquivo(s) anexado(s)'; })()""")


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
        elif a.cmd == "anexar":   # arquivos (pasta ou "a;b;c") no <input type=file> aberto na aba da Kani
            print(_anexar(a.arg, c))
        elif a.cmd == "destinos":
            for d in c("destinos"):
                print(d["id"][:8], d["cliente"], "|", d["nome"])
        elif a.cmd == "perfis":
            for x in chamar_kanicode("painel_cmd", {"o": "perfis"})["lista"]:
                print(("> " if x["atual"] else "  ") + x["id"], "|", x["nome"], "|", x["email"])
        elif a.cmd == "perfil":
            import time
            for _ in range(60):   # igual aos outros comandos: o painel abre sozinho
                if chamar_kanicode("painel", {}, 10).get("aberto"):
                    break
                time.sleep(.5)
            r = chamar_kanicode("painel_cmd", {"o": "perfil", "a": a.arg})
            print("perfil trocado:", a.arg, "| abas:", len(r.get("abas") or []))
        elif a.cmd == "painel":   # o painel 🌐 do KaniCode como o Pailer usa: painel estado|mostrar ID|nova URL|ir URL|fechar_aba ID|acao voltar|aparelho celular
            o, _, arg = (a.arg or "estado").partition(" ")
            r = chamar_kanicode("painel_cmd", {"o": o, **({"a": arg} if arg else {})})
            if isinstance(r, dict) and "abas" in r:
                for t in r["abas"]:
                    print(("> " if t["id"] == r.get("aba") else "  ") + t["id"][:8], ("[kani] " if t.get("kani") else "") + t["titulo"][:50], t["url"][:80])
                print("modo:", r.get("modo"), r.get("faixa"), r.get("tam"), "| trabalhando:", r.get("trabalhando"))
            else:
                print(r)
        elif a.cmd in ("frente", "fechar"):
            c(a.cmd, aba=a.aba); print("ok")
        else:
            print(__doc__); return 1
    except Exception as e:
        print("ERRO:", e); return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
