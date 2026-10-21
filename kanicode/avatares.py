"""Fotos locais dos perfis Chrome/Edge, associadas por e-mail; sem rede ou cookies."""
import base64
from functools import lru_cache
import io
import json
import os
from pathlib import Path


def _raizes():
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    return [local / "Google/Chrome/User Data", local / "Microsoft/Edge/User Data"]


@lru_cache(maxsize=64)
def _miniatura(caminho, modificado, tamanho):
    from PIL import Image, ImageOps
    if tamanho > 5_000_000:
        return None
    try:
        with Image.open(caminho) as im:
            if max(im.size) > 4096:
                return None
            foto = ImageOps.fit(im.convert("RGB"), (96, 96), method=Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            foto.save(buf, "PNG", optimize=True)
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except (OSError, ValueError):
        return None


def fotos(emails):
    """Retorna {email_normalizado: dataURL}. Sem correspondência, mantém as iniciais."""
    procurar = {str(e).strip().casefold() for e in emails if e}
    achadas = {}
    if not procurar:
        return achadas
    for raiz in _raizes():
        raiz = raiz.resolve()
        try:
            dados = json.loads((raiz / "Local State").read_text(encoding="utf-8"))
            perfis = ((dados.get("profile") or {}).get("info_cache") or {}) if isinstance(dados, dict) else {}
        except (OSError, ValueError):
            continue
        if not isinstance(perfis, dict):
            continue
        for nome, perfil in perfis.items():
            if not isinstance(perfil, dict):
                continue
            email = str(perfil.get("user_name") or perfil.get("edge_previously_signin_user_name") or "").strip().casefold()
            if email not in procurar or email in achadas:
                continue
            foto = perfil.get("gaia_picture_file_name")
            if not isinstance(foto, str) or not foto:
                continue
            caminho = (raiz / nome / foto).resolve()
            # O índice do navegador só pode apontar para uma imagem dentro de seus próprios perfis.
            if not caminho.is_relative_to(raiz):
                continue
            try:
                st = caminho.stat()
                imagem = _miniatura(str(caminho), st.st_mtime_ns, st.st_size)
                if imagem:
                    achadas[email] = imagem
            except OSError:
                continue
    return achadas
