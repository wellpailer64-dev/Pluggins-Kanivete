"""Ponte do plugin Pandalab com o KANIVETE (Functions/plugins_pessoais.py chama só o que está em API_KANIVETE)."""
import os, subprocess

import pandalab as pl
import pastas

API_KANIVETE = ("estado", "entrar", "sair", "listar", "detalhe", "baixar", "abrir_pasta", "clientes", "criar", "tipos",
                "mudar_status", "comentar", "finais")


def estado():
    try:
        return {"logado": True, **pl.quem()}
    except pl.ErroPanda:
        return {"logado": False}


def entrar(usuario, senha):
    return {"nome": pl.login(usuario, senha)}


def sair():
    pl.sair()
    return True


def listar(status="abertas", cliente=None, busca=None):
    return pl.demandas(status or None, cliente or None, busca or None)


def detalhe(id):
    d = pl.demanda(id)
    d["pasta"] = pastas.pasta_demanda(d)
    d["pasta_existe"] = bool(d["pasta"] and os.path.isdir(d["pasta"]))
    return d


def baixar(id, mes=None):
    raiz, feitos = pl.baixar(id, mes=mes)
    return {"pasta": raiz, "arquivos": feitos}


def abrir_pasta(id):
    d = pl.demanda(id)
    p = pastas.pasta_demanda(d)
    if not p or not os.path.isdir(p):
        raise pl.ErroPanda("A pasta ainda não existe: baixe o material primeiro.")
    subprocess.Popen(["explorer", p])
    return p


def clientes():
    return pl.clientes()


def tipos():
    return pl.TIPOS


def criar(titulo, cliente_id, tipo="estatico", descricao=""):
    return pl.criar(titulo, cliente_id, tipo, descricao)


def mudar_status(id, status):
    return pl.mudar_status(id, status)


def comentar(id, texto):
    return pl.comentar(id, texto)


def finais(id, conteudo=False):
    """conteudo=True devolve os arquivos em base64 (para a janela de entrega do site, dentro do Kanivete)."""
    import base64, mimetypes
    r = pl.finais(id)
    if conteudo:
        dados = []
        for a in r["arquivos"]:
            with open(a, "rb") as f:
                dados.append({"nome": os.path.basename(a), "tipo": mimetypes.guess_type(a)[0] or "application/octet-stream",
                              "b64": base64.b64encode(f.read()).decode()})
        r["dados"] = dados
    return r
