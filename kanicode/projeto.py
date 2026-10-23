"""Painel Projeto do KaniCode (como o do Codex): árvore de arquivos ao vivo, alterações do git e leitura de arquivo.

Tudo só LÊ: nada aqui grava no projeto. Caminhos sempre relativos à raiz (o repositório git da pasta da conversa, ou a
própria pasta sem git) e conferidos para não sair dela.
"""
import os, subprocess

IGNORAR = {".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache", ".pytest_cache", ".idea", ".vs"}
MAX_LER = 400_000
_SEM_JANELA = 0x08000000   # CREATE_NO_WINDOW


def _git(raiz, *args, timeout=8):
    r = subprocess.run(["git", "-c", "core.quotepath=false", *args], cwd=raiz, capture_output=True, timeout=timeout,
                       creationflags=_SEM_JANELA)
    return r.stdout.decode("utf-8", "replace") if r.returncode == 0 else None


def raiz(pasta):
    """a raiz do repositório git que contém a pasta (ou a própria pasta)"""
    try:
        t = _git(pasta, "rev-parse", "--show-toplevel", timeout=4)
        if t and t.strip():
            return os.path.normpath(t.strip())
    except Exception:
        pass
    return os.path.normpath(pasta)


def _dentro(base, rel):
    alvo = os.path.realpath(os.path.join(base, rel or ""))
    b = os.path.realpath(base)
    if os.path.normcase(alvo) != os.path.normcase(b) and not os.path.normcase(alvo).startswith(os.path.normcase(b) + os.sep):
        raise ValueError("fora do projeto")
    return alvo


def _status(base):
    """{caminho relativo com /: letra} — M alterado, A novo no índice, ? novo, D apagado, R renomeado"""
    saida = _git(base, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if saida is None:
        return None
    st, partes, i = {}, saida.split("\0"), 0
    while i < len(partes):
        p = partes[i]
        i += 1
        if len(p) < 4:
            continue
        x, y, arq = p[0], p[1], p[3:]
        if x == "R" or x == "C":
            i += 1   # o nome antigo vem depois
        letra = "?" if x == "?" else "D" if "D" in (x, y) else "A" if x == "A" else "R" if x == "R" else "M"
        st[arq] = letra
    return st


def arvore(pasta, sub=""):
    """itens de uma pasta (pastas primeiro), com a marca do git e se há alteração dentro (pastas)"""
    base = raiz(pasta)
    alvo = _dentro(base, sub)
    st = _status(base) or {}
    pre = (sub.replace("\\", "/").strip("/") + "/") if sub else ""
    itens = []
    try:
        with os.scandir(alvo) as it:
            for e in it:
                if e.name in IGNORAR:
                    continue
                rel = pre + e.name
                d = e.is_dir(follow_symlinks=False)
                marca = st.get(rel, "")
                if d and not marca:
                    marca = "•" if any(k.startswith(rel + "/") for k in st) else ""
                itens.append({"n": e.name, "rel": rel, "d": d, "st": marca})
    except OSError as ex:
        return {"ok": False, "erro": str(ex)}
    itens.sort(key=lambda x: (not x["d"], x["n"].lower()))
    return {"ok": True, "raiz": base, "nome": os.path.basename(base) or base, "sub": pre, "itens": itens}


def alteracoes(pasta):
    """arquivos alterados em relação ao último commit, com +/− linhas, ramo e quantos commits à frente"""
    base = raiz(pasta)
    st = _status(base)
    if st is None:
        return {"ok": False, "erro": "Esta pasta não é um repositório git.", "raiz": base}
    num = {}
    for linha in (_git(base, "diff", "HEAD", "--numstat") or "").splitlines():
        p = linha.split("\t")
        if len(p) == 3:
            num[p[2]] = (int(p[0]) if p[0].isdigit() else 0, int(p[1]) if p[1].isdigit() else 0)
    itens = []
    for arq, letra in sorted(st.items()):
        mais, menos = num.get(arq, (0, 0))
        if letra == "?":
            try:
                with open(os.path.join(base, arq), "rb") as f:
                    dados = f.read(MAX_LER)
                mais = 0 if b"\0" in dados else dados.count(b"\n") + (1 if dados and not dados.endswith(b"\n") else 0)
            except OSError:
                pass
        itens.append({"arq": arq, "st": letra, "mais": mais, "menos": menos})
    ramo = (_git(base, "branch", "--show-current") or "").strip() or "(sem ramo)"
    frente = (_git(base, "rev-list", "--count", "@{u}..HEAD") or "").strip()
    return {"ok": True, "raiz": base, "ramo": ramo, "frente": int(frente) if frente.isdigit() else None, "itens": itens,
            "mais": sum(i["mais"] for i in itens), "menos": sum(i["menos"] for i in itens)}


def diff(pasta, arq):
    """diferença unificada de um arquivo (novo = tudo entra)"""
    base = raiz(pasta)
    caminho = _dentro(base, arq)
    st = (_status(base) or {}).get(arq.replace("\\", "/"), "")
    if st == "?":
        texto = ler(pasta, arq)
        if not texto.get("ok") or texto.get("binario"):
            return {"ok": True, "binario": True, "texto": ""}
        linhas = texto["texto"].splitlines()
        return {"ok": True, "texto": f"@@ -0,0 +1,{len(linhas)} @@\n" + "\n".join("+" + l for l in linhas)}
    t = _git(base, "diff", "HEAD", "--no-color", "-U3", "--", arq)
    if t is None:
        return {"ok": False, "erro": "git diff falhou"}
    if "Binary files" in t[:400] and "@@" not in t:
        return {"ok": True, "binario": True, "texto": ""}
    corpo = t[t.find("@@"):] if "@@" in t else t
    return {"ok": True, "texto": corpo[:MAX_LER], "cortado": len(corpo) > MAX_LER, "existe": os.path.exists(caminho)}


def ler(pasta, arq):
    base = raiz(pasta)
    caminho = _dentro(base, arq)
    try:
        tam = os.path.getsize(caminho)
        with open(caminho, "rb") as f:
            dados = f.read(MAX_LER)
    except OSError as ex:
        return {"ok": False, "erro": str(ex)}
    if b"\0" in dados[:8000]:
        return {"ok": True, "binario": True, "tam": tam, "texto": ""}
    return {"ok": True, "texto": dados.decode("utf-8", "replace"), "tam": tam, "cortado": tam > MAX_LER,
            "caminho": caminho}


def buscar(pasta, termo):
    """até 300 arquivos cujo caminho contém o termo (git ls-files + novos; sem git, varre a pasta)"""
    base = raiz(pasta)
    t = (termo or "").lower().replace("\\", "/").strip()
    if not t:
        return {"ok": True, "itens": []}
    lista = _git(base, "ls-files", "-z", "--cached", "--others", "--exclude-standard", timeout=10)
    if lista is not None:
        todos = [a for a in lista.split("\0") if a]
    else:
        todos = []
        for d, pastas, arqs in os.walk(base):
            pastas[:] = [p for p in pastas if p not in IGNORAR]
            rel = os.path.relpath(d, base).replace("\\", "/")
            todos += [(f if rel == "." else rel + "/" + f) for f in arqs]
            if len(todos) > 50_000:
                break
    st = _status(base) or {}
    achados = [a for a in todos if t in a.lower()]
    achados.sort(key=lambda a: (t not in a.rsplit("/", 1)[-1].lower(), len(a)))
    return {"ok": True, "itens": [{"rel": a, "st": st.get(a, "")} for a in achados[:300]], "total": len(achados)}
