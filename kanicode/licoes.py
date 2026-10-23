"""Regras e lições por projeto: o que entra sozinho nos contratos do Codex (modo Equipe, etapa 5).

- Regras: `<DADOS>/regras/<projeto>.md`, curtas, valem para toda tarefa daquele projeto (ex.: KANIVETE = py -3.13,
  testes no disco D, nada de commit/push).
- Lições: `<DADOS>/licoes/<projeto>.jsonl`, uma por linha {data, texto, tags}. O Claude grava depois de revisar
  (ferramenta "licao"); entram no contrato as que têm palavras em comum com a tarefa (as mais parecidas primeiro).
<projeto> = nome da pasta do projeto em minúsculas, sem espaços.
"""
import json, os, re, time, unicodedata
import organizacao_pailer

from dados_app import pasta_dados
DADOS = str(pasta_dados())
_PALAVRA = re.compile(r"[a-z0-9_./-]{4,}")
_VAZIAS = {"para", "como", "isso", "esta", "este", "essa", "esse", "deve", "pode", "fazer", "quando", "sempre", "nunca",
           "antes", "depois", "arquivo", "arquivos", "teste", "tarefa", "codigo", "sobre", "entre", "mais", "menos", "tudo"}


def projeto(pasta):
    return re.sub(r"[^a-z0-9]+", "-", os.path.basename(os.path.normpath(pasta)).lower()).strip("-") or "projeto"


def _norm(t):
    return unicodedata.normalize("NFD", str(t).lower()).encode("ascii", "ignore").decode()


def _palavras(t):
    return {p for p in _PALAVRA.findall(_norm(t)) if p not in _VAZIAS}


def regras(pasta):
    p = os.path.join(DADOS, "regras", projeto(pasta) + ".md")
    try:
        with open(p, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def todas(pasta):
    p = os.path.join(DADOS, "licoes", projeto(pasta) + ".jsonl")
    if not os.path.isfile(p):
        return []
    with open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def relevantes(pasta, tarefa, n=6):
    alvo = _palavras(tarefa)
    pontos = []
    for i, l in enumerate(todas(pasta)):
        comum = alvo & _palavras(l["texto"] + " " + " ".join(l.get("tags") or []))
        if comum:
            pontos.append((len(comum), i, l))
    return [l for _, _, l in sorted(pontos, key=lambda x: (-x[0], -x[1]))[:n]]


def gravar(pasta, texto, tags=None):
    texto = " ".join(str(texto).split())
    if not texto:
        return False
    if any(_norm(l["texto"]) == _norm(texto) for l in todas(pasta)):   # já sabida
        return False
    os.makedirs(os.path.join(DADOS, "licoes"), exist_ok=True)
    with open(os.path.join(DADOS, "licoes", projeto(pasta) + ".jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"data": time.strftime("%Y-%m-%d"), "texto": texto, "tags": list(tags or [])}, ensure_ascii=False) + "\n")
    return True


def anexo(pasta, tarefa):
    """o texto que vai junto do contrato: regras do projeto + lições parecidas com a tarefa"""
    partes = []
    r = regras(pasta)
    if r:
        partes.append("REGRAS DESTE PROJETO (valem sempre):\n" + r)
    ls = relevantes(pasta, tarefa)
    if ls:
        partes.append("ARMADILHAS JÁ CONHECIDAS (lições de tarefas anteriores; evite repetir):\n" + "\n".join("- " + l["texto"] for l in ls))
    preferencia = organizacao_pailer.contexto(tarefa)
    if preferencia:
        partes.append(preferencia.strip())
    return "\n\n".join(partes)
