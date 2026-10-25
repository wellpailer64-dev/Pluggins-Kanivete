"""Perfil do usuário do KaniCode: foto, nome e informações básicas (seção do avatar, no alto da coluna das contas)."""
import base64
import io
import json
import os

from dados_app import pasta_dados

PASTA = os.path.join(pasta_dados(), "perfil")
ARQ = os.path.join(PASTA, "usuario.json")
FOTO = os.path.join(PASTA, "foto.png")
CAMPOS = ("nome", "apelido", "email", "empresa", "funcao", "cidade", "telefone", "site")
PADRAO = {"nome": "Pailer", "apelido": "Pailer"}


def ler():
    try:
        with open(ARQ, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    d = {k: str(d.get(k) or PADRAO.get(k, "")) for k in CAMPOS}
    d["foto"] = None
    try:
        with open(FOTO, "rb") as f:
            d["foto"] = "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")
    except OSError:
        pass
    return d


def salvar(campos):
    atual = {k: v for k, v in ler().items() if k in CAMPOS}
    for k, v in (campos or {}).items():
        if k in CAMPOS:
            atual[k] = str(v or "").strip()[:200]
    os.makedirs(PASTA, exist_ok=True)
    tmp = ARQ + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(atual, f, ensure_ascii=False, indent=2)
    os.replace(tmp, ARQ)
    return ler()


def foto(data_url):
    """data URL de imagem → foto quadrada 256 px em PNG; vazio apaga"""
    if not data_url:
        try:
            os.remove(FOTO)
        except OSError:
            pass
        return ler()
    from PIL import Image, ImageOps
    bruto = base64.b64decode(data_url.split(",", 1)[1])
    if len(bruto) > 25_000_000:
        raise ValueError("Imagem grande demais.")
    with Image.open(io.BytesIO(bruto)) as im:
        im = ImageOps.exif_transpose(im)
        quadro = ImageOps.fit(im.convert("RGB"), (256, 256), method=Image.Resampling.LANCZOS)
    os.makedirs(PASTA, exist_ok=True)
    quadro.save(FOTO + ".tmp.png", "PNG", optimize=True)
    os.replace(FOTO + ".tmp.png", FOTO)
    return ler()
