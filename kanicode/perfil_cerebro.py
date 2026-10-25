"""Cérebro do Pailer (perfil do KaniCode) — ferramenta de consulta do Claude, vitrine da evolução para o Pailer.

Neurônios vêm de quatro fontes: memórias do Claude (contas/*/projects/*/memory), lições do Codex (licoes/*.jsonl),
preferências curadas (preferencias/*.md), o perfil (perfil/usuario.json) e os neurônios PRÓPRIOS do cérebro
(cerebro/neuronios.json, escritos por `guardar`). Ligações: [[links]] das memórias + os 3 de assunto mais parecido (TF-IDF).
Cada neurônio tem vida (cerebro/vida.json): nasce, ganha força quando é usado e serve, apaga devagar sem uso e pode ser
descartado (vai para cerebro/arquivo.json, nunca some de vez). Método completo em CEREBRO.md."""
import ast
import glob
import hashlib
import json
import math
import os
import re
import sys
import threading
import time
import unicodedata
from collections import Counter

from dados_app import pasta_dados

DADOS = pasta_dados()
PASTA = os.path.join(DADOS, "cerebro")
ARQ_PROPRIOS = os.path.join(PASTA, "neuronios.json")
ARQ_VIDA = os.path.join(PASTA, "vida.json")
ARQ_ARQUIVO = os.path.join(PASTA, "arquivo.json")
ARQ_HIST = os.path.join(PASTA, "historico.jsonl")
_TRAVA = threading.RLock()

TIPOS = {"user": "Quem sou", "feedback": "Como trabalho", "project": "Projeto", "reference": "Referência", "licao": "Lição",
         "preferencia": "Preferência", "perfil": "Perfil", "fato": "Fato", "processo": "Processo", "habilidade": "Habilidade",
         "conhecimento": "Conhecimento", "contato": "Contato", "pesquisa": "Pesquisa"}
# grupo dentro do lobo: jeito de trabalhar × projetos × saber
GRUPO = {"feedback": "jeito", "preferencia": "jeito", "licao": "jeito", "processo": "jeito", "project": "projetos",
         "user": "saber", "perfil": "saber", "reference": "saber", "fato": "saber", "habilidade": "saber",
         "conhecimento": "saber", "contato": "saber", "pesquisa": "saber"}
GRUPOS = {"jeito": "Jeito de trabalhar", "andamento": "Projetos em andamento", "projetos": "Projetos", "saber": "Saber",
          "caminhos": "Caminhos do PC", "organizacao": "Organização e aprendizados",
          "aprendizados": "Aprendizados", "ferramentas": "Ferramentas"}
AMBITOS = {"kanivete": "KANIVETE", "kanicode": "KaniCode", "kani_local": "Kani local",
           "pc": "PC", "geral": "Pailer / geral", "revisar": "A classificar"}
FINALIDADES = {"regra": "Orientar o trabalho", "projeto": "Acompanhar projeto", "aprendizado": "Evitar repetir erro",
               "procedimento": "Como executar", "referencia": "Consultar informação"}


def _classificacao(n, registros):
    """Organização por sinais explícitos; nunca presume que uma memória foi aprendida pela Kani."""
    if n.get("ferramenta_kani"):
        return {"ambitos": ["kani_local"], "finalidade": "referencia", "agente": "não registrado", "classificacao": "referência viva"}
    salvo = registros.get(n["chave"])
    if salvo:
        return dict(salvo, classificacao="confirmada")
    if n.get("pc"):
        return {"ambitos": ["pc"], "finalidade": "referencia", "agente": "não registrado", "classificacao": "referência viva"}
    # O caminho da fonte pode conter o nome do app pai: não serve para definir o assunto.
    texto = _sem_acento(n["titulo"] + " " + n.get("desc", "") + " " + n.get("texto", "").split("\nfonte:")[0])
    texto = re.sub(r"[a-z]:[/\\][^\n]+", "", texto)
    ambitos = []
    for a, padrao in (("kanivete", r"\bkanivete\b"), ("kanicode", r"\bkanicode\b"),
                      ("kani_local", r"\bkani local\b|\b(?:ollama|qwen)\b|\bmodelo local\b")):
        if re.search(padrao, texto):
            ambitos.append(a)
    assunto = _sem_acento(n["titulo"] + " " + n.get("desc", "")).replace("_", " ")
    if re.search(r"\bpc\b|\bmapa (?:vivo|do disco|disco)|\bpastas de clientes\b|\borganizacao (?:de |das |dos )?(?:pastas|arquivos|clientes)\b", assunto):
        ambitos.append("pc")
    if not ambitos:
        ambitos = ["geral" if n.get("area") in ("eu", "clientes", "design", "video", "audio") or
                   n["tipo"] in ("perfil", "preferencia", "user") else "revisar"]
    finalidade = {"feedback": "regra", "preferencia": "regra", "project": "projeto", "licao": "aprendizado",
                  "processo": "procedimento"}.get(n["tipo"], "referencia")
    return {"ambitos": ambitos, "finalidade": finalidade, "agente": "não registrado", "classificacao": "automática"}


def _compativeis(a, b):
    aa, bb = set(a["ambitos"]), set(b["ambitos"])
    return "revisar" not in aa | bb and bool(aa & bb or "geral" in aa | bb)


def classificar(ref, ambitos, finalidade, origem, certeza, agente=None):
    """Metadados separados: também classifica memórias importadas sem reescrever a fonte."""
    if certeza not in CERTEZAS or not isinstance(origem, str) or not origem.strip():
        return {"ok": False, "motivo": "Classificar exige certeza e origem verificável."}
    if not isinstance(ambitos, list) or not ambitos or any(a not in AMBITOS for a in ambitos):
        raise ValueError("Informe ambitos válidos (kanivete, kanicode, kani_local, pc, geral, revisar).")
    if finalidade not in FINALIDADES:
        raise ValueError("Finalidade inválida.")
    if agente not in (None, "pailer", "claude", "codex", "kani", "pickle", "não registrado"):
        raise ValueError("Agente inválido; informe só quando a autoria estiver comprovada.")
    n = _achar(ref)
    with _TRAVA:
        arq = os.path.join(PASTA, "classificacao.json")
        registros = _jler(arq, {})
        registro = {"ambitos": list(dict.fromkeys(ambitos)), "finalidade": finalidade,
                    "agente": agente or n.get("agente", "não registrado"),
                    "origem_classificacao": origem.strip(), "certeza_classificacao": certeza}
        if registros.get(n["chave"]) == registro:
            return {"ok": True, "alterado": False, "chave": n["chave"]}
        registros[n["chave"]] = registro
        _jgravar(arq, registros)
        _registro("classificou", n["titulo"], [n["chave"]])
    return {"ok": True, "alterado": True, "chave": n["chave"]}


def _no_ambito(n, ambito):
    return not ambito or ambito in n["ambitos"]


# lobos: área → palavras (sem acento); "eu" recebe o perfil e as memórias do tipo user
AREAS = [
    ("kani", "Kani", []),
    ("pc", "PC", ["mapa do disco", "pastas de clientes", "organizacao de arquivos", "organizacao de pastas"]),
    ("eu", "Quem sou eu", ["pailer", "perfil", "pessoal", "casa", "agenda", "rotina", "familia", "saude"]),
    ("design", "Design", ["carrossel", "flyer", "logo", "logotipo", "design", "photo", "vetor", "diagram", "arte", "tipograf", "identidade",
                          "psd", "imagem", "foto", "pinterest", "behance", "marca", "slide", "orcamento", "acabamento", "barras"]),
    ("video", "Vídeo", ["video", "edicao", "reels", "motion", "montagem", "export", "encoder", "legenda", "timeline", "premiere", "comp",
                        "drone", "corte", "teaser", "clipe", "estabiliz", "rastre", "roto", "autoframe", "multicam", "transic", "4k", "mogrt"]),
    ("audio", "Áudio", ["audio", "som", "voz", "musica", "sfx", "mixer", "equaliz", "narra", "sound", "radio", "ruido", "noise", "remix"]),
    ("ia", "IA", ["kani", "modelo", "gerador", "worker", "llm", "qwen", "claude", "ollama", "codex", "cerebro", "ia "]),
    ("dev", "Desenvolvimento", ["kanicode", "kanivete", "teste", "build", "release", "codigo", "plugin", "python", "api", "patch", "mapa",
                                "recarreg", "disco", "tokens", "app", "browser", "ponte", "lux", "3d", "hardware"]),
    ("clientes", "Clientes", ["cliente", "carlinhos", "pedro", "helo", "magnet", "pandalab", "panda", "diego", "alessandro", "oficina",
                              "nautic", "dago", "cultsp", "gaia", "edgar", "baile", "whatsapp"]),
]
AREA_IDS = [a for a, _, _ in AREAS]
PARADAS = set("para com sem que uma uns umas como mais pelo pela pelos pelas sobre entre onde quando depois antes cada todo toda todos todas "
              "isso esse essa este esta nao sim tambem feito feita fazer usar usa ser sao foi tem ter the and".split())
DIA = 86400


def _sem_acento(t):
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()


def _jler(caminho, padrao):
    try:
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return padrao


def _jgravar(caminho, valor):
    os.makedirs(PASTA, exist_ok=True)
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(valor, f, ensure_ascii=False, indent=1)
    os.replace(tmp, caminho)


def _pastas():
    vistas, saida = set(), []
    portateis = glob.glob(os.path.join(DADOS, "cerebro", "memorias", "*"))
    for p in glob.glob(os.path.join(DADOS, "contas", "*", "projects", "*", "memory")) + portateis:
        r = os.path.realpath(p)
        if r not in vistas:
            vistas.add(r)
            saida.append(p)
    return saida


def _projeto(pasta):
    nome = os.path.basename(pasta) if os.path.basename(os.path.dirname(pasta)) == "memorias" else os.path.basename(os.path.dirname(pasta))
    for corte in ("CLIENTES-", "PYTHON-", "COLAB-", "PANDA-LAB-", "Desktop-", "HD-PAILER-"):
        if corte in nome:
            nome = nome.split(corte, 1)[1]
    return re.sub(r"-+", " ", nome).strip()[:40] or "Geral"


def _ler_md(caminho):
    with open(caminho, encoding="utf-8", errors="replace") as f:
        txt = f.read()
    meta, corpo = {}, txt
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", txt, re.S)
    if m:
        corpo = m.group(2)
        for linha in m.group(1).splitlines():
            k = re.match(r"^\s*(name|description|type)\s*:\s*(.*)$", linha)
            if k:
                meta[k.group(1)] = k.group(2).strip().strip("'\"")
    return meta, corpo.strip()


def _area(tipo, texto):
    if tipo in ("user", "perfil"):
        return "eu"
    t = _sem_acento(texto)
    notas = {a: sum(t.count(p) for p in pals) for a, _, pals in AREAS if a != "eu"}
    melhor = max(notas, key=notas.get)
    return melhor if notas[melhor] else "dev"


def _termos(t):
    """palavras sem acento, cortadas no radical (carrossel/carrosseis, edicao/edicoes caem juntas)"""
    return [w[:7] for w in re.findall(r"[a-z0-9]{3,}", _sem_acento(t)) if w not in PARADAS]


def _vetores(textos):
    """TF-IDF normalizado (dicionários), sem dependências"""
    cont = [Counter(_termos(t)) for t in textos]
    df = Counter(w for c in cont for w in c)
    n = len(textos) or 1
    idf = {w: math.log((n + 1) / (d + 1)) + 1 for w, d in df.items()}
    return [_norm(c, idf) for c in cont], idf


def _norm(cont, idf):
    v = {w: (1 + math.log(k)) * idf[w] for w, k in cont.items() if w in idf}
    norma = math.sqrt(sum(x * x for x in v.values())) or 1
    return {w: x / norma for w, x in v.items()}


def _cos(a, b):
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(w, 0) for w, x in a.items())


def _titulo(nome):
    t = re.sub(r"^(feedback|project|reference|user)[_-]", "", nome).replace("_", " ").replace("-", " ").strip()
    return t[:1].upper() + t[1:]


# ── fontes ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def _fonte_memorias():
    vistos = set()
    for pasta in _pastas():
        proj = _projeto(pasta)
        for arq in glob.glob(os.path.join(pasta, "*.md")):
            if os.path.basename(arq).upper() == "MEMORY.MD":
                continue
            try:
                meta, corpo = _ler_md(arq)
                criado = os.path.getmtime(arq)
            except OSError:
                continue
            nome = meta.get("name") or os.path.splitext(os.path.basename(arq))[0]
            if nome in vistos:
                continue
            vistos.add(nome)
            tipo = meta.get("type") or next((t for t in ("feedback", "project", "reference") if nome.startswith(t)), "user")
            yield {"chave": "mem:" + nome, "nome": nome, "titulo": _titulo(nome), "tipo": tipo, "fonte": "memória",
                   "desc": meta.get("description", ""), "texto": corpo, "projeto": proj, "criado": criado, "arquivo": arq,
                   "links": re.findall(r"\[\[([^\]]+)\]\]", corpo)}


def _fonte_licoes():
    for arq in glob.glob(os.path.join(DADOS, "licoes", "*.jsonl")):
        proj = os.path.splitext(os.path.basename(arq))[0].replace("-", " ").upper()
        try:
            linhas = open(arq, encoding="utf-8").read().splitlines()
        except OSError:
            continue
        for l in linhas:
            try:
                d = json.loads(l)
            except ValueError:
                continue
            txt = d.get("texto", "")
            if not txt:
                continue
            criado = time.mktime(time.strptime(d["data"], "%Y-%m-%d")) if d.get("data") else os.path.getmtime(arq)
            yield {"chave": "lic:" + hashlib.sha1(txt.encode()).hexdigest()[:10], "titulo": txt.split(":")[0][:60].rstrip("."),
                   "tipo": "licao", "fonte": "lição", "desc": txt[:220], "texto": txt + ("\ntags: " + ", ".join(d.get("tags") or []) if d.get("tags") else ""),
                   "projeto": proj, "criado": criado, "links": []}


def _fonte_preferencias():
    for arq in glob.glob(os.path.join(DADOS, "preferencias", "*.md")):
        try:
            txt = open(arq, encoding="utf-8").read()
        except OSError:
            continue
        nome = os.path.splitext(os.path.basename(arq))[0]
        primeira = next((l.strip("# ").strip() for l in txt.splitlines() if l.strip()), nome)
        yield {"chave": "pref:" + nome, "titulo": _titulo(nome), "tipo": "preferencia", "fonte": "preferência",
               "desc": primeira[:200], "texto": txt, "projeto": "Geral", "criado": os.path.getmtime(arq), "links": [], "arquivo": arq,
               "certeza": "observação curada; regras individuais ainda não validadas" if nome == "organizacao_clientes" else "confirmado"}


def _fonte_perfil():
    arq = os.path.join(DADOS, "perfil", "usuario.json")
    d = _jler(arq, {})
    if not d:
        return
    rot = {"nome": "Nome", "apelido": "Me chamar de", "email": "E-mail", "telefone": "Telefone", "empresa": "Empresa",
           "funcao": "Função", "cidade": "Cidade", "site": "Site"}
    linhas = [f"{r}: {d[k]}" for k, r in rot.items() if d.get(k)]
    yield {"chave": "perfil:dados", "titulo": "Dados do perfil", "tipo": "perfil", "fonte": "perfil",
           "desc": " · ".join(str(d[k]) for k in ("nome", "funcao", "empresa", "cidade") if d.get(k)), "texto": "\n".join(linhas),
           "projeto": "Perfil", "criado": os.path.getmtime(arq), "links": []}


def _fonte_proprios():
    for n in _jler(ARQ_PROPRIOS, []):
        yield {"chave": "pro:" + n["id"], "titulo": n["titulo"], "tipo": n.get("tipo") or "fato", "fonte": "cérebro",
               "desc": n.get("texto", "")[:220], "texto": n.get("texto", "") + ("\nfonte: " + n["origem"] if n.get("origem") else ""),
               "projeto": n.get("projeto") or "Geral", "criado": n.get("criado") or time.time(), "links": n.get("ligar") or [],
               "area": n.get("area"), "tags": n.get("tags") or [], "certeza": n.get("certeza") or "pailer",
               "ficha": n.get("ficha"), "atualizado": n.get("atualizado"), "origem": n.get("origem"),
               "natureza": ("obsoleto" if n.get("expira") and n["expira"] < time.time() else n.get("natureza") or "fato"),
               "expira": n.get("expira")}


_PC_CACHE = {"base": None, "quando": 0, "pastas": []}


def _pc_pastas():
    """Só a raiz já indexada, no máximo 24 pastas; não percorre o disco nem interpreta preferências."""
    agora = time.monotonic()
    if _PC_CACHE["base"] != str(DADOS) or agora - _PC_CACHE["quando"] > 15:
        import mapa_d
        banco = os.path.join(DADOS, "mapa_d", "indice.sqlite3")
        try:
            r = mapa_d.listar("D:/", limite=40, banco=banco)
            pastas = [(p["caminho"], p["nome"]) for p in r.get("itens", []) if p.get("pasta")][:24]
        except Exception:
            pastas = []
        _PC_CACHE.update(base=str(DADOS), quando=agora, pastas=pastas)
    return _PC_CACHE["pastas"]


def _fonte_ferramentas_kani():
    """Catálogo vivo, lido sem importar o motor nem executar suas ferramentas."""
    for nome in ("kani_modo.py", "codigo_agente.py"):
        caminho = os.path.join(os.path.dirname(__file__), nome)
        with open(caminho, encoding="utf-8-sig") as arq:
            arvore = ast.parse(arq.read())
        for no in arvore.body:
            if not isinstance(no, ast.Assign) or not any(isinstance(a, ast.Name) and a.id == "FERRAMENTAS" for a in no.targets):
                continue
            for ferramenta, descricao in ast.literal_eval(no.value).items():
                yield {"chave": "kani:ferramenta:" + ferramenta, "tipo": "reference", "fonte": caminho,
                       "area": "kani", "projeto": "Kani local", "criado": 0, "certeza": "verificado",
                       "titulo": ferramenta, "desc": "Ferramenta da Kani local · " + descricao[:160],
                       "texto": descricao + "\nFonte: " + nome + ":FERRAMENTAS. Cadastro não comprova execução; conexões e permissões precisam estar disponíveis.",
                       "tags": ["kani local", "ferramenta", ferramenta], "links": [], "ferramenta_kani": True}


def _fonte_pc():
    base = {"tipo": "reference", "fonte": "mapa vivo", "area": "pc", "projeto": "PC", "criado": 0,
            "certeza": "verificado", "tags": ["pc", "pastas", "mapa do disco"]}
    yield dict(base, chave="pc:mapa_d", titulo="Mapa vivo do disco D", desc="Pastas e caminhos atualizados pelo mapa do PC.",
               texto="Consultar o mapa vivo para localizar arquivos e navegar nas pastas. O índice informa a cobertura e a saúde do monitor. "
                     "Resultado parcial não prova ausência. Nomes e caminhos não são preferências de organização.",
               links=[], pc={"pasta": "D:/", "mapa": True})
    for caminho, nome in _pc_pastas():
        chave = "pc:" + hashlib.sha1(caminho.lower().encode()).hexdigest()[:12]
        yield dict(base, chave=chave, titulo=nome, desc="Pasta principal do PC · referência do mapa vivo.",
                   texto=f"Caminho indexado: {caminho}\nConsultar o mapa para ver o conteúdo atual antes de usar.",
                   links=["pc:mapa_d"], pc={"pasta": caminho})


# ── vida: uso, força, apagar ──────────────────────────────────────────────────────────────────────────────────────
def _vitalidade(n, v, agora):
    """0..1: o que é usado e serve fica aceso; o que ninguém usa apaga devagar (meia-vida ~60 dias sem uso)"""
    usado = v.get("ultimo") or n["criado"]
    recencia = math.exp(-(agora - usado) / DIA / 87)
    uso = min(1, math.log1p(v.get("usos", 0)) / 2.5)
    novo = math.exp(-(agora - n["criado"]) / DIA / 30)
    nota = max(-.3, min(.3, .1 * v.get("util", 0)))
    return round(max(0.02, min(1, .45 * recencia + .3 * uso + .25 * novo + nota)), 3)


_RE_CAMINHO = r"(?<![A-Za-z])[A-Za-z]:[\\/][^\n`'\"<>|*?]+"


def _caminho_existe(bruto):
    """o trecho pode ter texto depois do caminho (pastas com espaço): vale se algum começo dele, com 2+ partes, existir"""
    c = bruto.strip().rstrip(".,;:)]")
    partes = c.split(" ")
    for k in range(len(partes), 0, -1):
        tent = " ".join(partes[:k]).rstrip(".,;:)]")
        if len(re.split(r"[\\/]", tent.strip("\\/"))) >= 2 and os.path.exists(tent):
            return True
    return False


def _caminhos_quebrados(texto):
    return [c.strip()[:120] for c in set(re.findall(_RE_CAMINHO, texto or "")) if not _caminho_existe(c)]


def _caminhos(texto):
    return set(re.findall(_RE_CAMINHO, texto or ""))


# ── montar ─────────────────────────────────────────────────────────────────────────────────────────────────────────
_MEM = {"vets": [], "idf": {}, "chave": None, "dados": None}


def _assinatura():
    partes = []
    for p in _pastas() + [os.path.join(DADOS, d) for d in ("licoes", "preferencias")]:
        try:
            partes.append((p, os.path.getmtime(p), len(os.listdir(p))))
        except OSError:
            pass
    for a in (ARQ_PROPRIOS, ARQ_VIDA, ARQ_ARQUIVO, os.path.join(PASTA, "classificacao.json"), os.path.join(DADOS, "perfil", "usuario.json"),
              os.path.join(os.path.dirname(__file__), "kani_modo.py"), os.path.join(os.path.dirname(__file__), "codigo_agente.py")):
        try:
            partes.append((a, os.path.getmtime(a)))
        except OSError:
            pass
    return tuple(partes) + (time.strftime("%Y-%m-%d"), tuple(_pc_pastas()))


def montar():
    classificacoes = _jler(os.path.join(PASTA, "classificacao.json"), {})
    vida = _jler(ARQ_VIDA, {})
    descartados = {d["chave"] for d in _jler(ARQ_ARQUIVO, []) if d.get("chave")}
    nos = []
    for fonte in (_fonte_perfil, _fonte_memorias, _fonte_licoes, _fonte_preferencias, _fonte_proprios, _fonte_pc, _fonte_ferramentas_kani):
        for n in fonte():
            if n["chave"] in descartados:
                continue
            n["id"] = len(nos)
            n["area"] = n.get("area") if n.get("area") in AREA_IDS else _area(n["tipo"], f"{n['titulo']} {n['desc']} {n['texto'][:400]}")
            n["grupo"] = GRUPO.get(n["tipo"], "saber")
            if n.get("ficha") and n["ficha"].get("status") in ("em andamento", "pausado"):
                n["grupo"] = "andamento"
            n.update(_classificacao(n, classificacoes))
            if "kani_local" in n["ambitos"] or n["agente"] == "kani":
                n["area"] = "kani"
                if n.get("ferramenta_kani"):
                    n["grupo"] = "ferramentas"
                elif n["finalidade"] == "aprendizado":
                    n["grupo"] = "aprendizados"
            if "pc" in n["ambitos"] and n["area"] != "kani":
                n["area"] = "pc"
                if n.get("pc"):
                    n["grupo"] = "caminhos"
                elif n["finalidade"] in ("regra", "aprendizado", "procedimento"):
                    n["grupo"] = "organizacao"
            nos.append(n)
    referencias = [n for n in nos if n.get("pc") and not n["pc"].get("mapa")]
    for n in nos:
        if "pc" in n["ambitos"] and not n.get("pc"):
            n["links"].append("pc:mapa_d")
        pasta = (n.get("ficha") or {}).get("pasta")
        if pasta and os.path.isdir(pasta):
            for ref in referencias:
                raiz = ref["pc"]["pasta"]
                try:
                    origem = os.path.normcase(os.path.abspath(pasta))
                    destino = os.path.normcase(os.path.abspath(raiz))
                    if os.path.commonpath([origem, destino]) == destino:
                        n["links"].append(ref["chave"])
                except ValueError:
                    pass
    por_nome = {}
    for n in nos:
        por_nome[n.get("nome") or n["chave"]] = n
        por_nome.setdefault(re.sub(r"^(feedback|project|reference|user)[_-]", "", n.get("nome") or ""), n)
        por_nome.setdefault(n["chave"], n)
        por_nome.setdefault(n["chave"].split(":", 1)[1], n)
    vets, idf = _vetores([f"{n['titulo']} {n['titulo']} {n['titulo']} {n['desc']} {n['desc']} {n['projeto']} {' '.join(n.get('tags') or [])} {n['texto'][:3000]}" for n in nos])
    ligas = {}
    for n in nos:
        for l in n.pop("links"):
            o = por_nome.get(l.strip()) or por_nome.get(l.strip().replace("-", "_"))
            if o and o is not n:
                ligas[(min(n["id"], o["id"]), max(n["id"], o["id"]))] = (1, 1.0)
        viz = sorted(((_cos(vets[n["id"]], vets[o["id"]]), o["id"]) for o in nos if o is not n and not n.get("pc") and
                      not o.get("pc") and _compativeis(n, o)), reverse=True)[:3]
        for c, oid in viz:
            chave = (min(n["id"], oid), max(n["id"], oid))
            if c >= 0.12 and chave not in ligas:
                ligas[chave] = (0, round(c, 3))
    agora = time.time()
    for n in nos:
        v = vida.get(n["chave"], {})
        n["usos"], n["ultimo"], n["util"] = v.get("usos", 0), v.get("ultimo"), v.get("util", 0)
        n["vida"] = 1 if n.get("pc") or n.get("ferramenta_kani") else _vitalidade(n, v, agora)
        n["texto"] = n["texto"][:3000 if n.get("ficha") else 1500]
    _MEM["vets"], _MEM["idf"] = vets, idf
    d = {"nos": nos, "ligas": sorted([a, b, k, w] for (a, b), (k, w) in ligas.items()),
         "areas": [{"id": a, "nome": r} for a, r, _ in AREAS], "tipos": TIPOS, "grupos": GRUPOS,
         "ambitos": AMBITOS, "finalidades": FINALIDADES}
    d["resumo"] = _resumo(d, agora)
    _historico(d)
    d["historico"] = _ler_historico()
    return d


def _resumo(d, agora):
    nos = d["nos"]
    return {"neuronios": len(nos), "ligacoes": len(d["ligas"]),
            "novos_semana": sum(1 for n in nos if agora - n["criado"] < 7 * DIA),
            "usados_semana": sum(1 for n in nos if n["ultimo"] and agora - n["ultimo"] < 7 * DIA),
            "apagando": sum(1 for n in nos if n["vida"] < .15), "proprios": sum(1 for n in nos if n["fonte"] == "cérebro"),
            "descartados": len(_jler(ARQ_ARQUIVO, [])), "fontes": dict(Counter(n["fonte"] for n in nos))}


def _historico(d):
    """uma fotografia por dia (para o Pailer ver o cérebro crescer)"""
    hoje = time.strftime("%Y-%m-%d")
    hist = _ler_historico()
    if hist and hist[-1].get("dia") == hoje:
        return
    r = d["resumo"]
    os.makedirs(PASTA, exist_ok=True)
    with open(ARQ_HIST, "a", encoding="utf-8") as f:
        f.write(json.dumps({"dia": hoje, "neuronios": r["neuronios"], "ligacoes": r["ligacoes"], "apagando": r["apagando"],
                            "proprios": r["proprios"]}, ensure_ascii=False) + "\n")


def _ler_historico():
    try:
        return [json.loads(l) for l in open(ARQ_HIST, encoding="utf-8").read().splitlines() if l.strip()][-120:]
    except (OSError, ValueError):
        return []


def ler():
    with _TRAVA:
        chave = _assinatura()
        if _MEM["chave"] != chave:
            _MEM["dados"], _MEM["chave"] = montar(), chave
        return _MEM["dados"]


def _marcar_uso(chaves, util=0):
    with _TRAVA:
        vida, agora = _jler(ARQ_VIDA, {}), time.time()
        for c in chaves:
            v = vida.setdefault(c, {})
            v["usos"] = v.get("usos", 0) + 1
            v["ultimo"] = agora
            if util:
                v["util"] = max(-3, min(5, v.get("util", 0) + util))
        _jgravar(ARQ_VIDA, vida)


def _achar(ref):
    """id numérico, chave (mem:…, pro:…) ou título"""
    d = ler()
    for n in d["nos"]:
        if str(ref) in (str(n["id"]), n["chave"], n["titulo"], n.get("nome")):
            return n
    raise ValueError(f"neurônio não encontrado: {ref}")


# ── ações (ferramenta do Claude) ───────────────────────────────────────────────────────────────────────────────────
MIN_DIRETO = .15    # abaixo disso o cérebro "não sabe" — volta vazio
MIN_PUXADO = .12    # vizinho só vem junto se a ligação for forte


def consultar(pergunta, n=4, marcar=True, quem="claude", completo=False, ambito=None):
    """só quando falta uma informação: acende os neurônios do assunto e, se a ligação for forte, o vizinho direto.
    Sem acerto forte volta [] — melhor nada do que contexto incerto."""
    d = ler()
    if ambito and ambito not in AMBITOS:
        raise ValueError("Âmbito inválido.")
    nos, vets, idf = d["nos"], _MEM["vets"], _MEM["idf"]
    q = _norm(Counter(_termos(pergunta)), idf)
    #     # cobertura: metade do peso da pergunta tem de estar no neurônio; palavra que o cérebro nem conhece pesa o máximo
    termos = set(_termos(pergunta))
    teto = max(idf.values()) if idf else 1
    peso = {w: idf.get(w, teto) for w in termos}
    total = sum(peso.values()) or 1
    direto = [_cos(q, v) * (.85 + .15 * nos[i]["vida"]) if _no_ambito(nos[i], ambito) and sum(p for w, p in peso.items() if w in v) / total >= .5 else 0
              for i, v in enumerate(vets)]
    if not nos or not q or max(direto) < MIN_DIRETO:
        return []
    viz = {i: [] for i in range(len(nos))}
    for a, b, k, w in d["ligas"]:
        viz[a].append((b, w)); viz[b].append((a, w))
    ativo, motivo = [v if v >= MIN_DIRETO else 0 for v in direto], {}
    for i, v in enumerate(list(ativo)):
        if v < MIN_DIRETO:
            continue
        for j, w in viz[i]:
            if not _no_ambito(nos[j], ambito):
                continue
            ganho = v * w * .6
            if ganho >= MIN_PUXADO and ganho > ativo[j]:   # a lembrança puxada nunca passa da que puxou
                ativo[j] = ganho
                motivo[j] = nos[i]["titulo"]
    saida = []
    for i in sorted(range(len(nos)), key=lambda i: -ativo[i])[:n]:
        if ativo[i] <= 0:
            break
        m = nos[i]
        saida.append({"id": i, "chave": m["chave"], "neuronio": m["titulo"], "area": m["area"], "tipo": m["tipo"], "fonte": m["fonte"],
                      "projeto": m["projeto"], "forca": round(ativo[i], 3), "vida": m["vida"],
                      "ambitos": m["ambitos"], "finalidade": m["finalidade"], "agente": m["agente"], "classificacao": m["classificacao"],
                      "veio_por": "assunto" if direto[i] >= ativo[i] else "ligado a: " + motivo.get(i, "?"),
                      "resumo": m["desc"], "texto": m["texto"] if completo else m["texto"][:700]})
    if marcar and pergunta.strip():
        _marcar_uso([s["chave"] for s in saida if s["veio_por"] == "assunto"][:3])
        _registro("consultou", (f"[{quem}] " if quem != "claude" else "") + pergunta[:120], [s["chave"] for s in saida[:3]])
    return saida


def mapa(area=None, ambito=None):
    """o "mapa do site" do cérebro: só títulos por lobo › grupo (barato), para saber SE existe antes de consultar"""
    d = ler()
    if ambito and ambito not in AMBITOS:
        raise ValueError("Âmbito inválido.")
    linhas = [f"CÉREBRO: {d['resumo']['neuronios']} neurônios. ref = chave para cerebro consultar/ler."]
    for a in d["areas"]:
        if area and a["id"] != area:
            continue
        nos = [n for n in d["nos"] if n["area"] == a["id"] and _no_ambito(n, ambito)]
        if not nos:
            continue
        linhas.append(f"\n## {a['nome']} ({a['id']})")
        for g, rotulo in d["grupos"].items():
            gs = sorted((n for n in nos if n["grupo"] == g), key=lambda n: -n["vida"])
            if gs:
                linhas.append(f"{rotulo}: " + "; ".join(f"{n['titulo']} [{n['chave']}; {','.join(n['ambitos'])}; {n['finalidade']}]" for n in gs))
    return "\n".join(linhas)


def ler_neuronio(ref):
    n = _achar(ref)
    _marcar_uso([n["chave"]])
    return {"chave": n["chave"], "neuronio": n["titulo"], "fonte": n["fonte"], "tipo": n["tipo"], "projeto": n["projeto"],
            "ambitos": n["ambitos"], "finalidade": n["finalidade"], "agente": n["agente"], "classificacao": n["classificacao"],
            "origem_classificacao": n.get("origem_classificacao"), "certeza_classificacao": n.get("certeza_classificacao"),
            "certeza": n.get("certeza", "confirmado"), "texto": n["texto"]}


CERTEZAS = ("pailer", "verificado")   # disse/confirmou o Pailer; ou conferido na fonte (arquivo, site, teste)


def projeto_em_andamento(projeto, ficha=None, origem=None, certeza=None, ref=None, area=None, ligar=None):
    """Ficha curta por trabalho; recebe só as mudanças confirmadas e conserva o que já era conhecido."""
    nome = (projeto or "").strip()
    if not nome or len(nome) > 90:
        raise ValueError("Informe o nome específico do trabalho (até 90 caracteres, não só o cliente).")
    if certeza not in CERTEZAS or not (origem or "").strip():
        return {"guardado": False, "motivo": "Projeto exige certeza='pailer' ou 'verificado' e origem. Palpite não entra."}
    campos = {"cliente": 120, "formato": 120, "tema": 240, "ferramentas": 240, "resumo": 700,
              "etapa": 240, "pasta": 500, "status": 30}
    if not isinstance(ficha, dict) or not ficha or set(ficha) - campos.keys():
        raise ValueError("Informe ficha com cliente, formato, tema, ferramentas, resumo, etapa, pasta ou status.")
    for c, v in ficha.items():
        if not isinstance(v, str) or len(v) > campos[c]:
            raise ValueError(f"{c}: use texto curto (até {campos[c]} caracteres).")
    if "status" in ficha and ficha["status"] not in ("em andamento", "pausado", "concluído", "cancelado"):
        raise ValueError("Status: em andamento, pausado, concluído ou cancelado.")
    if ligar is not None and (not isinstance(ligar, list) or any(not isinstance(c, str) for c in ligar)):
        raise ValueError("ligar deve ser uma lista de chaves de neurônios.")
    with _TRAVA:
        lista = _jler(ARQ_PROPRIOS, [])
        arquivados = {n["chave"] for n in _jler(ARQ_ARQUIVO, [])}
        candidatos = [p for p in lista if p.get("ficha") and (
            "pro:" + p["id"] == ref if ref else _sem_acento(p.get("projeto", "")) == _sem_acento(nome))]
        if ref and not candidatos:
            raise ValueError("Ficha não encontrada; use a chave devolvida ao registrar o projeto.")
        if len(candidatos) > 1:
            raise ValueError("Há mais de uma ficha com esse nome; informe ref.")
        p = candidatos[0] if candidatos else None
        if p and "pro:" + p["id"] in arquivados:
            return {"guardado": False, "motivo": "Projeto arquivado: restaure antes de atualizar.", "chave": "pro:" + p["id"]}
        nova = p is None
        if nova:
            p = {"id": hashlib.sha1(f"projeto:{nome}:{time.time_ns()}".encode()).hexdigest()[:12],
                 "titulo": nome, "projeto": nome, "tipo": "project", "criado": time.time(),
                 "ficha": {"status": "em andamento"}, "fontes_campos": {}, "ligar": []}
        antes = json.dumps(p, sort_keys=True, ensure_ascii=False)
        for c, v in ficha.items():
            v = v.strip()
            if p["ficha"].get(c) != v:
                p["ficha"][c] = v
                p["fontes_campos"][c] = {"origem": origem.strip(), "certeza": certeza}
        if area in AREA_IDS:
            p["area"] = area
        if ligar is not None:
            p["ligar"] = list(dict.fromkeys(p.get("ligar", []) + ligar))
        if not nova and json.dumps(p, sort_keys=True, ensure_ascii=False) == antes:
            return {"guardado": True, "alterado": False, "chave": "pro:" + p["id"]}
        rotulos = {"cliente": "Cliente", "formato": "Formato", "tema": "Tema", "ferramentas": "Ferramentas",
                   "resumo": "Resumo", "etapa": "Etapa atual", "pasta": "Pasta", "status": "Status"}
        p["texto"] = "\n".join(f"{r}: {p['ficha'][c]}" for c, r in rotulos.items() if p["ficha"].get(c))
        p["origem"], p["certeza"], p["atualizado"] = origem.strip(), certeza, time.time()
        if nova:
            lista.append(p)
        _jgravar(ARQ_PROPRIOS, lista)
        chave = "pro:" + p["id"]
        _marcar_uso([chave])
        _registro("guardou projeto" if nova else "atualizou projeto", nome, [chave])
    return {"guardado": True, "alterado": True, "chave": chave, "ficha": p["ficha"]}


def guardar(titulo, texto, tipo="fato", area=None, tags=None, projeto=None, origem=None, ligar=None, forcar=False, certeza=None):
    """neurônio novo, SÓ com certeza (certeza='pailer' ou 'verificado' + origem). Antes confere se já existe um parecido
    (≥ 0,55): aí devolve o parecido para atualizar em vez de duplicar."""
    titulo, texto = (titulo or "").strip(), (texto or "").strip()
    if not titulo or not texto:
        raise ValueError("Precisa de título e texto.")
    if certeza not in CERTEZAS or not (origem or "").strip():
        return {"guardado": False, "motivo": "o cérebro só guarda certeza: diga certeza='pailer' (ele disse/confirmou) ou "
                                             "'verificado' (conferi na fonte) e a origem. Palpite não entra."}
    if tipo not in TIPOS:
        tipo = "fato"
    d = ler()
    if not forcar and d["nos"]:
        v = _norm(Counter(_termos(f"{titulo} {titulo} {texto}")), _MEM["idf"])
        candidato = _classificacao({"chave": "novo", "titulo": titulo, "texto": texto, "tipo": tipo,
                                    "area": area or _area(tipo, titulo + " " + texto)}, {})
        parecidos = sorted(((_cos(v, _MEM["vets"][n["id"]]), n) for n in d["nos"] if not n.get("pc") and
                            (_compativeis(candidato, n) or "revisar" in candidato["ambitos"] + n["ambitos"])), key=lambda x: -x[0])[:3]
        if parecidos and parecidos[0][0] >= .55:
            return {"guardado": False, "motivo": "já existe parecido: atualize ou reforce esse (ou mande forcar=true)",
                    "parecidos": [{"chave": n["chave"], "neuronio": n["titulo"], "semelhanca": round(c, 2), "texto": n["texto"][:400]}
                                  for c, n in parecidos if c >= .4]}
    with _TRAVA:
        lista = _jler(ARQ_PROPRIOS, [])
        nid = hashlib.sha1(f"{titulo}{time.time()}".encode()).hexdigest()[:8]
        lista.append({"id": nid, "titulo": titulo[:90], "texto": texto[:4000], "tipo": tipo, "area": area if area in AREA_IDS else None,
                      "tags": tags or [], "projeto": projeto, "origem": origem, "ligar": ligar or [], "criado": time.time(),
                      "certeza": certeza})
        _jgravar(ARQ_PROPRIOS, lista)
    _registro("guardou", titulo, ["pro:" + nid])
    return {"guardado": True, "chave": "pro:" + nid}


def atualizar(ref, texto=None, titulo=None, tipo=None, area=None, tags=None):
    """só neurônios próprios (memórias se corrigem no arquivo da memória)"""
    n = _achar(ref)
    if n.get("ficha"):
        return {"ok": False, "motivo": "Use acao=projeto com ref e ficha (só os campos alterados), certeza e origem."}
    if not n["chave"].startswith("pro:"):
        return {"ok": False, "motivo": f"{n['fonte']}: corrija na origem" + (f" ({n['arquivo']})" if n.get("arquivo") else "")}
    with _TRAVA:
        lista = _jler(ARQ_PROPRIOS, [])
        for p in lista:
            if "pro:" + p["id"] == n["chave"]:
                if texto: p["texto"] = texto[:4000]
                if titulo: p["titulo"] = titulo[:90]
                if tipo in TIPOS: p["tipo"] = tipo
                if area in AREA_IDS: p["area"] = area
                if tags is not None: p["tags"] = tags
                p["atualizado"] = time.time()
        _jgravar(ARQ_PROPRIOS, lista)
    _marcar_uso([n["chave"]], util=1)
    _registro("atualizou", n["titulo"], [n["chave"]])
    return {"ok": True, "chave": n["chave"]}


def reforcar(ref, serviu=True):
    n = _achar(ref)
    _marcar_uso([n["chave"]], util=1 if serviu else -1)
    _registro("reforçou" if serviu else "enfraqueceu", n["titulo"], [n["chave"]])
    return {"ok": True, "chave": n["chave"], "neuronio": n["titulo"]}


def descartar(ref, motivo=""):
    """tira do cérebro sem apagar: vai para o arquivo com o motivo (dá para voltar)"""
    n = _achar(ref)
    with _TRAVA:
        arq = _jler(ARQ_ARQUIVO, [])
        arq.append({"chave": n["chave"], "titulo": n["titulo"], "texto": n["texto"], "fonte": n["fonte"], "motivo": motivo, "quando": time.time()})
        _jgravar(ARQ_ARQUIVO, arq)
    _registro("descartou", f"{n['titulo']} — {motivo}", [n["chave"]])
    aviso = f" A memória continua no arquivo {n['arquivo']}: apague lá também se estiver errada." if n.get("arquivo") and n["fonte"] == "memória" else ""
    return {"ok": True, "chave": n["chave"], "aviso": aviso.strip()}


def revisar(limite=12):
    """o que precisa de cuidado: parecidos demais (juntar), caminhos que não existem mais, apagando sem uso, projetos parados"""
    d = ler()
    nos, vets, agora = d["nos"], _MEM["vets"], time.time()
    dup = []
    for i, n in enumerate(nos):
        for j in range(i + 1, len(nos)):
            c = _cos(vets[i], vets[j])
            if not n.get("pc") and not nos[j].get("pc") and c >= .6 and _compativeis(n, nos[j]):
                dup.append({"a": n["titulo"], "b": nos[j]["titulo"], "chaves": [n["chave"], nos[j]["chave"]], "semelhanca": round(c, 2)})
    quebrados = [{"chave": n["chave"], "neuronio": n["titulo"], "caminhos": q[:3]} for n in nos if (q := _caminhos_quebrados(n["texto"]))]
    apagando = [{"chave": n["chave"], "neuronio": n["titulo"], "vida": n["vida"], "dias_sem_uso": int((agora - (n["ultimo"] or n["criado"])) / DIA)}
                for n in sorted(nos, key=lambda n: n["vida"]) if n["vida"] < .15]
    parados = [{"chave": n["chave"], "neuronio": n["titulo"], "dias": int((agora - (n["ultimo"] or n["criado"])) / DIA)}
               for n in nos if n["tipo"] == "project" and agora - (n["ultimo"] or n["criado"]) > 45 * DIA]
    return {"juntar": sorted(dup, key=lambda x: -x["semelhanca"])[:limite], "caminhos_quebrados": quebrados[:limite],
            "apagando": apagando[:limite], "projetos_parados": parados[:limite], "resumo": d["resumo"]}


def _registro(acao, texto, chaves):
    os.makedirs(PASTA, exist_ok=True)
    with open(os.path.join(PASTA, "atividade.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"t": time.time(), "acao": acao, "texto": texto, "chaves": chaves}, ensure_ascii=False) + "\n")


def atividade(n=30):
    try:
        linhas = open(os.path.join(PASTA, "atividade.jsonl"), encoding="utf-8").read().splitlines()[-n:]
        return [json.loads(l) for l in reversed(linhas)]
    except (OSError, ValueError):
        return []


def restaurar(ref):
    """volta um descartado do arquivo"""
    with _TRAVA:
        arq = _jler(ARQ_ARQUIVO, [])
        fica = [d for d in arq if str(ref) not in (d.get("chave"), d.get("titulo"))]
        if len(fica) == len(arq):
            raise ValueError(f"não está no arquivo: {ref}")
        _jgravar(ARQ_ARQUIVO, fica)
    _registro("restaurou", str(ref), [str(ref)])
    return {"ok": True}


# ── ponto de partida: o mesmo aviso para todas as IAs do portal (o conteúdo só sob demanda) ───────────────────────
def ponto_de_partida(tarefa="", limite=1200, quem="claude"):
    """Claude: uma linha dizendo que o cérebro existe (+ pendências da faxina, se houver). Outros agentes (que não têm a
    ferramenta): no máximo 2 neurônios com acerto FORTE para a tarefa; sem acerto, nada."""
    linhas = []
    if quem == "claude":
        linhas.append("Cérebro do Pailer (brain_search/brain_context; ou cerebro acao=mapa): use SÓ quando faltar uma "
                      "informação dele (cliente, estilo, processo, preferência). Sem acerto, siga sem ele. "
                      "Memória nova: brain_remember (com origem e certeza). "
                      "Trabalho em curso: acao=projeto guarda/atualiza ficha curta só com mudanças confirmadas já disponíveis.")
        pend = _jler(os.path.join(PASTA, "pendencias.json"), [])
        if pend:
            linhas.append("Faxina pede corrigir/apagar memórias .md suas (depois cerebro acao=resolvida): "
                          + "; ".join(f"{p['titulo']} ({p['motivo'][:80]})" for p in pend[:3]))
    elif tarefa.strip() and os.environ.get("CEREBRO_MOTOR") != "v1" and not quem.endswith("|v1"):
        try:   # motor universal: contexto compacto pelo perfil de quem pede (Kani/Pickle 600 tokens, Codex 1500)
            import cerebro_motor
            perfil = quem if quem in cerebro_motor.PERFIS else "kani"
            agente = quem if quem in cerebro_motor.agentes() else "kani"
            return cerebro_motor.usar("brain_context", {"pergunta": tarefa, "perfil": perfil}, agente)["texto"][:limite]
        except Exception:
            return ponto_de_partida(tarefa, limite, quem + "|v1")   # motor fora do ar: a busca antiga
    elif tarefa.strip():
        quem = quem.replace("|v1", "")
        rel = [r for r in consultar(tarefa, 2, marcar=True, quem=quem) if r["veio_por"] == "assunto" and r["forca"] >= .22]
        if rel:
            linhas.append("Do cérebro do Pailer (certeza; só o que bate com esta tarefa):")
            linhas += [f"- {r['neuronio']}: {(r['resumo'] or r['texto'])[:240]}" for r in rel]
    return "\n".join(linhas)[:limite]


# ── faxina: o cérebro se cuida sozinho ─────────────────────────────────────────────────────────────────────────────
ARQ_FAXINA = os.path.join(PASTA, "faxina.json")
ARQ_PEND = os.path.join(PASTA, "pendencias.json")
_JUIZ = """Você cuida do cérebro de trabalho do Pailer (memórias que as IAs usam). Decida se este neurônio deve SAIR por ser
ultrapassado/obsoleto, errado ou já coberto por outro, ou FICAR porque ainda ajuda o trabalho do dia a dia.
Na dúvida, FICA. Caminho que mudou de lugar não torna obsoleto o jeito de trabalhar descrito.
Responda só JSON: {"decisao": "descartar" ou "manter", "motivo": "frase curta em português"}"""


def _candidatos(d, agora):
    nos, vets, vida = d["nos"], _MEM["vets"], _jler(ARQ_VIDA, {})
    julgado = lambda n: agora - (vida.get(n["chave"], {}).get("mantido") or 0) < 30 * DIA
    cand = {}
    for n in nos:
        if n.get("pc") or n.get("ferramenta_kani") or julgado(n) or n["tipo"] in ("perfil", "user"):
            continue
        q = _caminhos_quebrados(n["texto"])
        todos = _caminhos(n["texto"])
        sem_uso = (agora - (n["ultimo"] or n["criado"])) / DIA
        if q and len(q) >= len(todos) and n["vida"] < .4:
            cand[n["chave"]] = (n, f"todos os caminhos citados sumiram: {', '.join(q[:3])}", None)
        elif n["tipo"] == "project" and sem_uso > 60 and n["vida"] < .2:
            cand[n["chave"]] = (n, f"projeto sem uso há {int(sem_uso)} dias", None)
        elif n["vida"] < .1 and sem_uso > 90 and n["grupo"] != "jeito":
            cand[n["chave"]] = (n, f"apagado: sem uso há {int(sem_uso)} dias", None)
    for i, a in enumerate(nos):
        for j in range(i + 1, len(nos)):
            if not a.get("pc") and not nos[j].get("pc") and not a.get("ferramenta_kani") and not nos[j].get("ferramenta_kani") and _compativeis(a, nos[j]) and _cos(vets[i], vets[j]) >= .6:
                velho, novo = (a, nos[j]) if a["criado"] <= nos[j]["criado"] else (nos[j], a)
                if not julgado(velho) and velho["tipo"] not in ("perfil", "user"):
                    cand.setdefault(velho["chave"], (velho, "muito parecido com um mais novo", novo))
    return list(cand.values())


def faxina(usar_kani=True, maximo=8, ao_evento=None):
    """acha os candidatos a obsoleto, pede o juízo da Kani (local, grátis) e descarta os que ela confirmar.
    Neurônios próprios e lições saem do cérebro; memórias .md do Claude saem do cérebro E viram pendência para o Claude
    corrigir o arquivo na próxima conversa. Tudo vai para o arquivo com o motivo (restaurar volta)."""
    agora = time.time()
    d = ler()
    cand = _candidatos(d, agora)[:maximo]
    rel = {"quando": agora, "analisados": len(cand), "descartados": [], "mantidos": [], "sem_juiz": 0}
    juiz = None
    if usar_kani and cand:
        try:
            import ajudantes
            juiz = ajudantes.kani if ajudantes.kani_disponivel() else None
        except Exception:
            juiz = None
    mantidos, pend = [], _jler(ARQ_PEND, [])
    for n, evid, novo in cand:
        decisao, motivo = "manter", "sem juiz: fica até a próxima faxina"
        if juiz:
            ctx = f"NEURÔNIO ({n['fonte']}, {TIPOS.get(n['tipo'], n['tipo'])}): {n['titulo']}\n{n['texto'][:1500]}\n\nEVIDÊNCIA: {evid}"
            if novo:
                ctx += f"\n\nO MAIS NOVO PARECIDO: {novo['titulo']}\n{novo['texto'][:1200]}"
            r = juiz(_JUIZ, ctx)
            m = re.search(r"\{.*\}", r.get("texto", ""), re.S)
            try:
                j = json.loads(m.group(0)) if m else {}
            except ValueError:
                j = {}
            decisao, motivo = j.get("decisao", "manter"), (j.get("motivo") or evid)[:200]
        elif novo and n["fonte"] == "cérebro" and _cos(_MEM["vets"][n["id"]], _MEM["vets"][novo["id"]]) >= .75:
            decisao, motivo = "descartar", f"coberto por '{novo['titulo']}'"
        else:
            rel["sem_juiz"] += 1
        if decisao == "descartar":
            descartar(n["chave"], "faxina: " + motivo)
            rel["descartados"].append({"chave": n["chave"], "titulo": n["titulo"], "motivo": motivo})
            if n["fonte"] == "memória":
                pend.append({"chave": n["chave"], "titulo": n["titulo"], "motivo": motivo, "arquivo": n.get("arquivo", ""), "quando": agora})
        else:
            mantidos.append(n["chave"])
            rel["mantidos"].append({"chave": n["chave"], "titulo": n["titulo"], "motivo": motivo})
        if ao_evento:
            ao_evento(f"{decisao}: {n['titulo']} — {motivo}")
    with _TRAVA:
        if juiz:   # só conta como julgado (30 dias de folga) quando houve juiz de verdade
            vida = _jler(ARQ_VIDA, {})
            for k in mantidos:
                vida.setdefault(k, {})["mantido"] = agora
            _jgravar(ARQ_VIDA, vida)
        _jgravar(ARQ_PEND, pend[-30:])
        _jgravar(ARQ_FAXINA, rel)
    _registro("faxina", f"{len(rel['descartados'])} descartados, {len(rel['mantidos'])} mantidos de {len(cand)}",
              [x["chave"] for x in rel["descartados"]])
    return rel


def pendencia_resolvida(ref):
    """o Claude corrigiu/apagou a memória: sai da lista"""
    with _TRAVA:
        pend = [p for p in _jler(ARQ_PEND, []) if str(ref) not in (p["chave"], p["titulo"])]
        _jgravar(ARQ_PEND, pend)
    return {"ok": True, "restam": len(pend)}


def faxina_diaria():
    """uma vez por dia (o KaniCode chama alguns minutos depois de abrir)"""
    if time.time() - (_jler(ARQ_FAXINA, {}).get("quando") or 0) < 20 * 3600:
        return None
    return faxina()


def _com_versao(acao_feita, r, depois):
    """toda escrita fica na linha do tempo do neurônio (cerebro/versoes.jsonl), venha da porta antiga ou da nova"""
    if isinstance(r, dict) and (r.get("guardado") or r.get("ok")) and r.get("chave") and r.get("alterado") is not False:
        try:
            import cerebro_motor
            cerebro_motor.versao(acao_feita, r["chave"], "claude", depois=depois)
        except Exception:
            pass
    return r


def acao(args):
    """porta única da ferramenta 'cerebro' (equipe)"""
    a = (args.get("acao") or "consultar").strip()
    if a == "consultar":
        r = None
        if os.environ.get("CEREBRO_MOTOR") != "v1":   # motor universal (palavra + sentido + grafo); v1 = TF-IDF antigo
            try:
                import cerebro_motor
                r = cerebro_motor.usar("brain_search", {"pergunta": args.get("tema", ""), "k": int(args.get("quantos") or 4),
                                                        "ambito": args.get("ambito")}, "claude")
            except Exception:
                r = None
        if r is None:
            r = consultar(args.get("tema", ""), int(args.get("quantos") or 4), ambito=args.get("ambito"))
        return r or {"nada": "o cérebro não tem isso com certeza — siga sem ele (ou pergunte ao Pailer)"}
    if a == "mapa":
        return mapa(args.get("area"), args.get("ambito"))
    if a == "classificar":
        return classificar(args.get("ref"), args.get("ambitos"), args.get("finalidade"), args.get("origem"),
                           args.get("certeza"), args.get("agente"))
    if a == "projeto":
        return _com_versao("projeto", projeto_em_andamento(args.get("projeto"), args.get("ficha"), args.get("origem"), args.get("certeza"),
                                    args.get("ref"), args.get("area"), args.get("ligar")),
                           {"ficha": args.get("ficha")} if (args.get("ficha") or {}) else {})
    if a == "ler":
        return ler_neuronio(args.get("ref"))
    if a == "guardar":
        return _com_versao("guardou", guardar(args.get("titulo"), args.get("texto"), args.get("tipo") or "fato", args.get("area"), args.get("tags"),
                       args.get("projeto"), args.get("origem"), args.get("ligar"), bool(args.get("forcar")), args.get("certeza")),
                           {"titulo": args.get("titulo"), "texto": (args.get("texto") or "")[:2000]})
    if a == "atualizar":
        return _com_versao("atualizou", atualizar(args.get("ref"), args.get("texto"), args.get("titulo"), args.get("tipo"),
                                                  args.get("area"), args.get("tags")), {"texto": (args.get("texto") or "")[:2000]})
    if a in ("reforcar", "enfraquecer"):
        return reforcar(args.get("ref"), a == "reforcar")
    if a == "descartar":
        return descartar(args.get("ref"), args.get("motivo", ""))
    if a == "revisar":
        return revisar()
    if a == "faxina":
        return faxina(maximo=int(args.get("quantos") or 8))
    if a == "restaurar":
        return restaurar(args.get("ref"))
    if a == "resolvida":
        return pendencia_resolvida(args.get("ref"))
    if a == "partida":
        return ponto_de_partida(args.get("tema", ""), quem=args.get("quem") or "claude")
    if a == "resumo":
        return ler()["resumo"]
    raise ValueError("ação do cérebro desconhecida: " + a)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1:2] == ["faxina"]:
        r = faxina_diaria() if "--diaria" in sys.argv else faxina(usar_kani="--sem-kani" not in sys.argv, ao_evento=print)
        print(json.dumps(r, ensure_ascii=False)[:3000])
        sys.exit(0)
    if sys.argv[1:2] == ["partida"]:
        print(ponto_de_partida(" ".join(sys.argv[2:]), quem="teste"))
        sys.exit(0)
    d = ler()
    print(json.dumps(d["resumo"], ensure_ascii=False))
    print(Counter(n["area"] for n in d["nos"]))
    for r in consultar(" ".join(sys.argv[1:]) or "legenda de reels", marcar=False):
        print(f"{r['forca']:.2f}  {r['neuronio']}  ({r['fonte']}, {r['veio_por']})")
    rv = revisar(4)
    print("juntar:", [(x["a"], x["b"], x["semelhanca"]) for x in rv["juntar"]])
    print("quebrados:", len(rv["caminhos_quebrados"]), "apagando:", len(rv["apagando"]), "parados:", len(rv["projetos_parados"]))
