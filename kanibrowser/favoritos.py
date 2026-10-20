"""Barra de favoritos do KaniBrowser: D:\\Kanivete\\KaniBrowser\\favoritos.json (fica entre aberturas do app).
Ícone de cada site baixado do próprio site (nada de serviço do Google), guardado em icones/<domínio>.png e servido pelo
servidor local da visão (visao.py, caminho com token)."""
import io, json, os, re, threading, urllib.parse, urllib.request

import kanibrowser as kb

ARQ = os.path.join(kb.RAIZ, "favoritos.json")
ICONES = os.path.join(kb.RAIZ, "icones")
INICIAIS = [
    ("ChatGPT", "https://chatgpt.com/"), ("Gemini", "https://gemini.google.com/"),
    ("WhatsApp", "https://web.whatsapp.com/"), ("Instagram", "https://www.instagram.com/"), ("Pinterest", "https://br.pinterest.com/"),
    ("Behance", "https://www.behance.net/"), ("Pandalab", "https://laboratoriopanda.com/"),
]
_trava = threading.Lock()


def _ler():
    if not os.path.isfile(ARQ):
        return [{"nome": n, "url": u} for n, u in INICIAIS]
    with open(ARQ, encoding="utf-8") as f:
        return json.load(f)


def _gravar(lista):
    os.makedirs(kb.RAIZ, exist_ok=True)
    tmp = ARQ + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(lista, f, ensure_ascii=False, indent=1)
    os.replace(tmp, ARQ)
    return lista


def dominio(url):
    return re.sub(r"^www\.", "", urllib.parse.urlparse(url).netloc.lower())


def listar():
    with _trava:
        lista = _ler()
    for f in lista:
        d = dominio(f["url"])
        f["icone"] = d if os.path.isfile(os.path.join(ICONES, d + ".png")) else ""
        if not f["icone"]:
            threading.Thread(target=icone, args=(f["url"],), daemon=True).start()
    return lista


def salvar(url, nome=None):
    """☆: adiciona (ou tira, se já estava). Devolve a lista."""
    with _trava:
        lista = _ler()
        if any(f["url"] == url for f in lista):
            lista = [f for f in lista if f["url"] != url]
        else:
            lista.append({"nome": (nome or dominio(url)).strip()[:40], "url": url})
        _gravar(lista)
    return listar()


def remover(url):
    with _trava:
        _gravar([f for f in _ler() if f["url"] != url])
    return listar()


def renomear(url, nome):
    with _trava:
        lista = _ler()
        for f in lista:
            if f["url"] == url:
                f["nome"] = nome.strip()[:40] or f["nome"]
        _gravar(lista)
    return listar()


def ordenar(urls):
    with _trava:
        lista = _ler()
        pos = {u: i for i, u in enumerate(urls)}
        lista.sort(key=lambda f: pos.get(f["url"], len(pos)))
        _gravar(lista)
    return listar()


def _baixar(u):
    req = urllib.request.Request(u, headers={"User-Agent": kb.UA})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read(), r.headers.get("Content-Type", ""), r.geturl()


def icone(url):
    """ícone do site (apple-touch-icon / icon do HTML, senão /favicon.ico) → PNG 64 px"""
    d = dominio(url)
    destino = os.path.join(ICONES, d + ".png")
    if os.path.isfile(destino):
        return destino
    from PIL import Image
    cands = []
    try:
        html, _, final = _baixar(url)
        html = html[:300000].decode("utf-8", "ignore")
        for m in re.finditer(r"<link[^>]+>", html, re.I):
            t = m.group(0)
            rel = re.search(r'rel=["\']([^"\']+)', t, re.I)
            href = re.search(r'href=["\']([^"\']+)', t, re.I)
            if rel and href and "icon" in rel.group(1).lower():
                tam = re.search(r'sizes=["\'](\d+)', t)
                cands.append((int(tam.group(1)) if tam else (180 if "apple" in rel.group(1).lower() else 32),
                              urllib.parse.urljoin(final, href.group(1))))
    except Exception:
        final = url
    cands.sort(key=lambda c: -min(c[0], 256))
    cands.append((16, urllib.parse.urljoin(final, "/favicon.ico")))
    for _, u in cands:
        if u.lower().endswith(".svg"):
            continue
        try:
            dados, tipo, _ = _baixar(u)
            im = Image.open(io.BytesIO(dados))
            if im.format == "ICO":   # .ico com vários tamanhos: o maior
                im.size = max(im.info.get("sizes", [im.size]))
            im = im.convert("RGBA")
            im.thumbnail((64, 64), Image.LANCZOS)
            os.makedirs(ICONES, exist_ok=True)
            im.save(destino)
            return destino
        except Exception:
            continue
    return ""
