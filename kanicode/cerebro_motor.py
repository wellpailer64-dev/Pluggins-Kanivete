"""Motor do cérebro universal: a MESMA busca para qualquer IA (Kani local, Claude, Codex, a que vier).

O KaniCode é o dono do conhecimento; as IAs só consultam. As fontes continuam as de `perfil_cerebro` (memórias .md,
lições, preferências, perfil, neurônios próprios, mapa do disco, ferramentas da Kani). Este módulo monta por cima um
ÍNDICE DERIVADO (cerebro/indice.sqlite, apagável: refaz sozinho) com:
  - busca por palavra (SQLite FTS5 + BM25, título pesa mais, chave/arquivo exatos vão direto ao topo);
  - busca por sentido (multilingual-e5-small em ONNX, só no PROCESSADOR, 2 threads; o embedding é do motor, não da IA);
  - fusão das duas (RRF) + vizinhos pelo grafo de ligações + vida do neurônio + filtros e permissões por agente.
Contexto pronto por perfil (`contexto`): a seleção e a compactação acontecem aqui, sem LLM.
Escrita controlada (`propor`/`atualizar`): valida, deduplica, detecta conflito, guarda versão; quem não pode gravar só propõe.
Portas: Python (este módulo), MCP (`mcp_equipe.py` e `mcp_cerebro.py`) e HTTP (`cerebro_http.py`). Chave CEREBRO_MOTOR=v1
volta à busca antiga. Contratos e números da bancada em CEREBRO.md › "Motor universal"."""
import hashlib
import json
import os
import re
import secrets
import sqlite3
import threading
import time
import urllib.request

import perfil_cerebro as pc

VERSAO_INDICE = 2
MODELO = os.environ.get("CEREBRO_MODELO") or "multilingual-e5-base"   # bancada: base 94%/80% × small 86%
URL_MODELO = f"https://huggingface.co/Xenova/{MODELO}/resolve/main/"
# o modelo é cache compartilhado (inclusive com os testes); os dados seguem perfil_cerebro.PASTA, lida na hora
PASTA_MODELO = os.environ.get("CEREBRO_PASTA_MODELO") or os.path.join(
    os.path.splitdrive(os.path.abspath(__file__))[0] + os.sep, "Kanivete", "KaniCode", "modelos", MODELO)
_PASTA_REAL = pc.PASTA


def _arq(nome):
    return os.path.join(pc.PASTA, nome)
TRECHO = 900          # caracteres por trecho (o modelo lê até 256 tokens)
OCIOSO = 600          # descarrega o modelo depois de 10 min parado
NATUREZAS = {"fato": "Fato verificado", "hipotese": "Hipótese", "preferencia": "Preferência", "decisao": "Decisão",
             "temporario": "Temporário", "obsoleto": "Obsoleto"}
PERFIS = {"kani": {"orcamento_tokens": 600, "k": 3, "profundidade": 0, "detalhe": "curto", "citacoes": False},
          "pickle": {"orcamento_tokens": 600, "k": 3, "profundidade": 0, "detalhe": "curto", "citacoes": False},
          "agente": {"orcamento_tokens": 4000, "k": 12, "profundidade": 1, "detalhe": "normal", "citacoes": True},
          "codex": {"orcamento_tokens": 1500, "k": 5, "profundidade": 1, "detalhe": "normal", "citacoes": True}}
_TRAVA = threading.RLock()
SOU_SERVIDOR = False   # True no processo do KaniCode que serve o HTTP (lá o modelo fica carregado)


# ── modelo de embeddings (carrega sob demanda, solta quando fica parado) ─────────────────────────────────────────────
class _Modelo:
    def __init__(self):
        self.sessao = self.tok = None
        self.usado = 0
        self.baixando = False
        self.erro = None

    def pronto(self):
        return all(os.path.isfile(os.path.join(PASTA_MODELO, a)) for a in ("model_quantized.onnx", "tokenizer.json"))

    def baixar(self):
        """~135 MB uma vez, para a pasta de dados do KaniCode (nunca no C)"""
        if self.pronto() or self.baixando:
            return
        self.baixando = True
        try:
            os.makedirs(PASTA_MODELO, exist_ok=True)
            for rel in ("tokenizer.json", "onnx/model_quantized.onnx"):
                destino = os.path.join(PASTA_MODELO, os.path.basename(rel))
                if os.path.isfile(destino):
                    continue
                tmp = destino + ".parte"
                with urllib.request.urlopen(URL_MODELO + rel, timeout=60) as r, open(tmp, "wb") as f:
                    while bloco := r.read(1 << 20):
                        f.write(bloco)
                os.replace(tmp, destino)
        except Exception as e:      # sem internet: segue só com a busca por palavra
            self.erro = str(e)
        finally:
            self.baixando = False

    def _carregar(self):
        import onnxruntime as ort
        from tokenizers import Tokenizer
        op = ort.SessionOptions()
        op.intra_op_num_threads, op.inter_op_num_threads = 2, 1
        self.sessao = ort.InferenceSession(os.path.join(PASTA_MODELO, "model_quantized.onnx"), op, providers=["CPUExecutionProvider"])
        self.tok = Tokenizer.from_file(os.path.join(PASTA_MODELO, "tokenizer.json"))
        self.tok.enable_truncation(256)
        self.tok.enable_padding()
        threading.Thread(target=self._vigiar, daemon=True).start()

    def _vigiar(self):
        while self.sessao is not None:
            time.sleep(30)
            with _TRAVA:
                if time.time() - self.usado > OCIOSO:
                    self.sessao = self.tok = None

    def vetores(self, textos, lote=16):
        import numpy as np
        with _TRAVA:
            if self.sessao is None:
                self._carregar()
            self.usado = time.time()
            saida = []
            for i in range(0, len(textos), lote):
                cod = self.tok.encode_batch(textos[i:i + lote])
                ids = np.array([c.ids for c in cod], dtype=np.int64)
                m = np.array([c.attention_mask for c in cod], dtype=np.int64)
                feed = {"input_ids": ids, "attention_mask": m, "token_type_ids": np.zeros_like(ids)}
                h = self.sessao.run(None, {e.name: feed[e.name] for e in self.sessao.get_inputs()})[0]
                v = (h * m[..., None]).sum(1) / m.sum(1, keepdims=True)
                saida.append(v / np.linalg.norm(v, axis=1, keepdims=True))
            self.usado = time.time()
            return np.vstack(saida).astype(np.float32) if saida else np.zeros((0, 384), np.float32)


MOD = _Modelo()


# ── índice ───────────────────────────────────────────────────────────────────────────────────────────────────────────
_IDX = {"assinatura": None, "d": None, "trechos": [], "mat": None, "semantica": False, "viz": None, "fts": None}


def _db():
    os.makedirs(pc.PASTA, exist_ok=True)
    con = sqlite3.connect(_arq("indice.sqlite"), timeout=15)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS emb (hash TEXT PRIMARY KEY, vec BLOB)")
    v = dict(con.execute("SELECT k, v FROM meta").fetchall())
    if v.get("versao") != str(VERSAO_INDICE):   # trocou o esquema: refaz (o modelo entra no hash de cada vetor)
        con.execute("DELETE FROM emb")
        con.executemany("INSERT OR REPLACE INTO meta VALUES (?, ?)", [("versao", str(VERSAO_INDICE)), ("modelo", MODELO)])
        con.commit()
    return con


def _trechos(n):
    """cabeçalho (título, resumo, projeto, tags) + o texto em pedaços de ~900 caracteres cortados em fim de linha/frase"""
    cab = f"{n['titulo']}. {n.get('desc') or ''}".strip()
    extra = " ".join(x for x in (n.get("projeto") or "", " ".join(n.get("tags") or [])) if x)
    texto = re.sub(r"\n{3,}", "\n\n", (n.get("texto") or "").split("\nfonte:")[0]).strip()
    pedacos, atual = [], ""
    for parte in re.split(r"(?<=[.!?\n])\s+", texto):
        if len(atual) + len(parte) > TRECHO and atual:
            pedacos.append(atual.strip())
            atual = ""
        atual += parte + " "
    if atual.strip() or not pedacos:
        pedacos.append(atual.strip())
    saida = [(cab + (f" ({extra})" if extra else "") + "\n" + p).strip() for p in pedacos[:6]]
    if n.get("desc") and len(saida[0]) > len(cab) + 200:   # trecho curto só com o assunto: casa melhor com pergunta curta
        saida.append(cab)
    return saida


# Frases de assunto geral, fora do mundo do Pailer: entram só na régua da busca por sentido (média e desvio), para a
# régua não depender do tamanho do cérebro (com poucos neurônios, o desvio sozinho não diz nada).
ANCORAS = [
    "Receita de bolo de chocolate com cobertura.", "Resultado do jogo de futebol de domingo.", "Previsão de chuva para o fim de semana.",
    "Como plantar tomate em vaso na varanda.", "História da Revolução Francesa.", "Preço da gasolina subiu de novo.",
    "Dicas para dormir melhor à noite.", "Como trocar o óleo do carro.", "Regras do vôlei de praia.", "Capitais dos países da Europa.",
    "Benefícios de beber água durante o dia.", "Como cuidar de um cachorro filhote.", "Pacote de viagem para o Nordeste.",
    "Horário de funcionamento do banco.", "Como fazer pão caseiro.", "Temporada nova da série de televisão.",
    "Sintomas de gripe e resfriado.", "Como economizar na conta de luz.", "Exercícios de alongamento para as costas.",
    "Cotação do dólar hoje.", "Como montar um aquário.", "Música clássica para estudar.", "Dicas de jardinagem no inverno.",
    "Como passar roupa sem amassar.", "Campeonato de xadrez internacional.", "Como declarar o imposto de renda.",
    "Tabela de vitaminas das frutas.", "Planetas do sistema solar.", "Como aprender a nadar adulto.", "Promoção de supermercado.",
    "Receita de feijoada completa.", "Manutenção da bicicleta.", "Como limpar a geladeira.", "Livros de ficção científica.",
    "Escalação da seleção brasileira.", "Como fazer café coado.", "Clima seco e umidade do ar.", "Como organizar o guarda-roupa.",
    "Festa junina e comidas típicas.", "Animais da floresta amazônica.",
]
_FUNDO = {"rodando": False}
MAX_NA_HORA = 40    # mais vetores que isso faltando: calcula em segundo plano e responde só com a busca por palavra


def _no_fundo():
    if _FUNDO["rodando"]:
        return
    _FUNDO["rodando"] = True

    def rodar():
        try:
            _sincronizar(True, MAX_NA_HORA * 1000)
        finally:
            _FUNDO["rodando"] = False
    threading.Thread(target=rodar, daemon=True).start()


def _sincronizar(semantica=True, max_na_hora=MAX_NA_HORA):
    """refaz o índice só quando as fontes mudam (mesma assinatura do perfil_cerebro); vetores calculados só do que é novo.
    A busca por palavra mora na memória de cada processo (sem corrida entre processos); os vetores, no SQLite (cache)."""
    import numpy as np
    d = pc.ler()
    assinatura = (pc._MEM["chave"], semantica and MOD.pronto())
    if _IDX["assinatura"] == assinatura and _IDX["d"] is d:
        return _IDX
    with _TRAVA:
        if _IDX["assinatura"] == assinatura and _IDX["d"] is d:
            return _IDX
        trechos = [(n["id"], t) for n in d["nos"] for t in _trechos(n)]
        fts = sqlite3.connect(":memory:", check_same_thread=False)
        fts.execute("CREATE VIRTUAL TABLE fts USING fts5(nid UNINDEXED, titulo, ids, texto, tokenize='unicode61 remove_diacritics 2')")
        fts.executemany("INSERT INTO fts VALUES (?, ?, ?, ?)",
                        [(n["id"], n["titulo"] + " " + (n.get("desc") or ""),
                          " ".join([n["chave"], n.get("nome") or "", os.path.basename(n.get("arquivo") or ""), n.get("projeto") or ""]),
                          (n.get("texto") or "")[:4000]) for n in d["nos"]])
        fts.commit()
        con = _db()
        mat, ok, fundo = None, False, None
        if semantica and MOD.pronto():
            hashes = [hashlib.sha1((MODELO + "|" + t).encode()).hexdigest() for _, t in trechos]
            tem = {}
            for i in range(0, len(hashes), 500):
                parte = hashes[i:i + 500]
                tem.update(con.execute(f"SELECT hash, vec FROM emb WHERE hash IN ({','.join('?' * len(parte))})", parte).fetchall())
            falta = [i for i, h in enumerate(hashes) if h not in tem]
            if len(falta) > max_na_hora:      # 1ª vez ou muita coisa nova: não segura a resposta
                con.close()
                _IDX.update(assinatura=None, d=d, trechos=trechos, mat=None, semantica=False, fts=fts, viz=_vizinhos(d))
                _no_fundo()
                return _IDX
            if falta:
                vs = MOD.vetores(["passage: " + trechos[i][1] for i in falta])
                novos = [(hashes[i], vs[j].tobytes()) for j, i in enumerate(falta)]
                con.executemany("INSERT OR IGNORE INTO emb VALUES (?, ?)", novos)
                tem.update(novos)
            mat = np.vstack([np.frombuffer(tem[h], dtype=np.float32) for h in hashes]) if hashes else None
            ok = mat is not None
            fundo = _vetores_cache(con, ["passage: " + a for a in ANCORAS])
        con.commit()
        con.close()
        _IDX.update(assinatura=assinatura, d=d, trechos=trechos, mat=mat, semantica=ok, fts=fts, viz=_vizinhos(d), fundo=fundo)
    return _IDX


def _vetores_cache(con, textos):
    import numpy as np
    hs = [hashlib.sha1((MODELO + "|" + t).encode()).hexdigest() for t in textos]
    tem = dict(con.execute(f"SELECT hash, vec FROM emb WHERE hash IN ({','.join('?' * len(hs))})", hs).fetchall())
    falta = [i for i, h in enumerate(hs) if h not in tem]
    if falta:
        vs = MOD.vetores([textos[i] for i in falta])
        novos = [(hs[i], vs[j].tobytes()) for j, i in enumerate(falta)]
        con.executemany("INSERT OR IGNORE INTO emb VALUES (?, ?)", novos)
        tem.update(novos)
    return np.vstack([np.frombuffer(tem[h], dtype=np.float32) for h in hs])


def _vizinhos(d):
    viz = {i: [] for i in range(len(d["nos"]))}
    for a, b, k, w in d["ligas"]:
        viz[a].append((b, w, k)); viz[b].append((a, w, k))
    return viz


def indexar(esperar_modelo=False):
    """para o KaniCode chamar em segundo plano ao abrir: baixa o modelo se faltar e deixa o índice em dia"""
    if not MOD.pronto():
        if not esperar_modelo:
            threading.Thread(target=MOD.baixar, daemon=True).start()
            return _estado(_sincronizar(False))
        MOD.baixar()
    return _estado(_sincronizar(True, 10 ** 9))


def _estado(idx):
    return {"neuronios": len(idx["d"]["nos"]), "trechos": len(idx["trechos"]), "semantica": idx["semantica"],
            "modelo": MODELO if idx["semantica"] else None, "motor": "v2"}


def estado():
    return _estado(_sincronizar(MOD.pronto()))


# ── permissões ───────────────────────────────────────────────────────────────────────────────────────────────────────
def agentes():
    """cerebro/agentes.json: quem lê o quê e quem grava. Criado na 1ª vez com chaves aleatórias para o HTTP."""
    with _TRAVA:
        a = pc._jler(_arq("agentes.json"), None)
        if a is None:
            a = {"pailer": {"ler": "*", "gravar": True},
                 "claude": {"ler": "*", "gravar": True},
                 "codex": {"ler": "*", "areas_fora": ["eu"], "clientes": "por_projeto", "gravar": False},
                 "kani": {"ler": "*", "gravar": False},
                 "pickle": {"ler": "*", "gravar": False},
                 "visitante": {"ler": ["kanivete", "kanicode"], "areas_fora": ["eu", "clientes"], "gravar": False}}
            for nome, p in a.items():
                p["chave"] = secrets.token_urlsafe(24)
            pc._jgravar(_arq("agentes.json"), a)
        return a


def permissao(agente):
    a = agentes()
    if agente not in a:
        raise PermissionError(f"agente desconhecido: {agente} (cadastre em cerebro/agentes.json)")
    return a[agente]


def agente_por_chave(chave):
    for nome, p in agentes().items():
        if chave and secrets.compare_digest(str(p.get("chave", "")), str(chave)):
            return nome
    return None


# nomes de cliente (dos lobos do perfil_cerebro + cerebro/clientes.json): memória que cita um deles é "de cliente",
# esteja no lobo que estiver (o Carlinhos aparece em design, vídeo...), quando o ASSUNTO (título/resumo) cita o cliente.
# Palavras genéricas e a própria agência ficam fora.
_GENERICOS = {"cliente", "pandalab", "panda", "whatsapp"}


def _nomes_clientes():
    base = next(p for a, _, p in pc.AREAS if a == "clientes")
    extra = pc._jler(_arq("clientes.json"), [])
    return [pc._sem_acento(c) for c in list(base) + (extra if isinstance(extra, list) else []) if c not in _GENERICOS]


def _clientes_do(n):
    t = pc._sem_acento(f"{n['titulo']} {n.get('desc') or ''} {n.get('nome') or ''}")   # o ASSUNTO; exemplo no texto não conta
    achados = [c for c in _nomes_clientes() if re.search(r"\b" + re.escape(c), t)]
    return achados


def _visivel(n, perm, projeto=None):
    ler = perm.get("ler", "*")
    if ler != "*" and not set(n["ambitos"]) & set(ler):
        return False
    if n["area"] in (perm.get("areas_fora") or []):
        return False
    if perm.get("clientes") == "por_projeto" and (cs := _clientes_do(n)):   # cliente só aparece no trabalho dele
        if not projeto:
            return False
        pj = pc._sem_acento(projeto)
        return any(c in pj for c in cs if c != "?") or pj in pc._sem_acento(f"{n['titulo']} {n.get('projeto') or ''} {n['texto'][:600]}")
    return True


# ── busca ────────────────────────────────────────────────────────────────────────────────────────────────────────────
_RE_ID = re.compile(r"\b(?:mem|pro|lic|pref|pc|perfil):[\w\-.:À-ú ]{2,80}?(?=$|[\s,;])|\b[\w\-]+\.(?:md|py|js|json)\b")
PESO_TITULO, PESO_ID, PESO_TEXTO = 4.0, 6.0, 1.0
Z_SO_SENTIDO = 3.6
Z_SEM = 3.3        # quantos desvios acima da média o trecho precisa estar (busca por sentido: escala relativa, não absoluta)
Z_PAR, COB_PAR = 2.4, .4   # par sentido + palavra parcial
MIN_FORCA = .25    # abaixo disso o cérebro "não sabe" e volta vazio


# Sinônimos da casa (as memórias misturam português, inglês e jargão). Só abrem a busca por palavra; o Pailer pode
# acrescentar em cerebro/sinonimos.json → [["expressão", "alternativa 1", "alternativa 2"], ...]
SINONIMOS = [
    ["placa de video", "gpu", "placa", "nvidia", "directml"], ["processador", "cpu"],
    ["executavel", "exe", "build", "release"], ["e-mail", "email", "gmail"], ["email", "e-mail", "gmail"],
    ["deslizante", "slider", "barra", "barras"], ["slider", "barra", "deslizante"],
    ["inteligencia artificial", "ia", "gerador", "modelo"], ["ia", "gerador", "modelo"],
    ["voz sintetizada", "tts", "voz", "voice"], ["narracao", "voz", "tts", "fran"], ["pronuncia", "pronuncia", "accents", "sotaque"],
    ["acento", "accents", "acentos"], ["exemplos", "fewshot", "examples"], ["modelo pequeno", "small", "llm", "4b"],
    ["modelo de linguagem", "llm", "modelo"], ["tirar o fundo", "remover fundo", "recorte"], ["recortar", "recorte", "remover fundo"],
    ["animacao", "motion", "animar"], ["composicao", "comp", "comps"], ["composicoes", "comp", "comps"],
    ["legenda", "legendas", "caption"], ["imagem de apoio", "broll", "b-roll"], ["camera", "multicam", "multicamera"],
    ["musica", "trilha", "music"], ["video", "reels", "clipe"], ["tela", "monitor", "interface"],
]


# palavras de pedido ("vou fazer", "quero", "me ajuda"): não dizem o assunto, só atrapalham a cobertura
PEDIDO = set("vou vai vamos quero queria preciso precisa pode poderia ajuda ajudar ajude faz faca fiz ficar fica deixar "
             "agora hoje favor kani claude codex pailer ele ela dele dela meu minha seu sua isso aqui ali".split())


def _sinonimos():
    return SINONIMOS + [x for x in pc._jler(os.path.join(pc.PASTA, "sinonimos.json"), []) if isinstance(x, list) and len(x) > 1]


def _consulta_fts(pergunta):
    """termos da pergunta + alternativas; devolve também, por termo, os radicais que valem como ele na cobertura"""
    base = pc._sem_acento(pergunta)
    termos = [w for w in re.findall(r"[a-z0-9]{3,}", base) if w not in pc.PARADAS and w not in PEDIDO]
    alt = {w[:7]: {w[:7]} for w in termos}
    extras = []
    for grupo in _sinonimos():
        chave = pc._sem_acento(grupo[0])
        if re.search(r"\b" + re.escape(chave) + r"\b", base):
            raiz = [w[:7] for w in re.findall(r"[a-z0-9]{3,}", chave) if w not in pc.PARADAS]
            novos = [w[:7] for g in grupo[1:] for w in re.findall(r"[a-z0-9]{2,}", pc._sem_acento(g)) if w not in pc.PARADAS]
            extras += novos
            for r in raiz:
                alt.setdefault(r, {r}).update(novos)
    todos = list(dict.fromkeys([w[:7] for w in termos] + extras))
    return " OR ".join(f'"{w}"*' for w in todos), alt


def _lexical(pergunta, idx):
    q, alt = _consulta_fts(pergunta)
    if not q:
        return {}
    try:
        with _TRAVA:
            linhas = idx["fts"].execute(f"SELECT nid, bm25(fts, 0, {PESO_TITULO}, {PESO_ID}, {PESO_TEXTO}) FROM fts WHERE fts MATCH ? "
                                        "ORDER BY 2 LIMIT 40", (q,)).fetchall()
    except sqlite3.OperationalError:
        return {}
    if not linhas:
        return {}
    # cobertura como na v1: a maioria das palavras raras da pergunta tem de estar no neurônio
    d, idf = idx["d"], pc._MEM["idf"]
    teto = max(idf.values()) if idf else 1
    peso = {w: idf.get(w, teto) for w in alt}
    total = sum(peso.values()) or 1
    saida = {}
    for nid, nota in linhas:
        n = d["nos"][nid]
        texto = f"{n['titulo']} {n.get('desc') or ''} {n['chave']} {n.get('projeto') or ''} {n['texto'][:4000]}"
        alvo = set(pc._termos(texto)) | {w[:7] for w in re.findall(r"[a-z0-9]{2}\b", pc._sem_acento(texto))}
        cob = sum(p for w, p in peso.items() if alt[w] & alvo) / total
        saida[nid] = (-nota, cob)
    return saida


def _semantica(pergunta, idx):
    import numpy as np
    if not idx["semantica"]:
        return {}
    q = MOD.vetores(["query: " + pergunta])[0]
    cos = idx["mat"] @ q
    regua = np.concatenate([cos, idx["fundo"] @ q]) if idx.get("fundo") is not None else cos
    media, desvio = float(regua.mean()), float(regua.std()) or 1e-6
    melhor = {}
    for i in np.argsort(-cos)[:60]:
        nid = idx["trechos"][i][0]
        z = (float(cos[i]) - media) / desvio
        if nid not in melhor or z > melhor[nid][0]:
            melhor[nid] = (z, int(i))
    return melhor


def buscar(pergunta, k=5, modo="hibrido", agente="claude", projeto=None, area=None, ambito=None, fonte=None, tipo=None,
           natureza=None, desde=None, profundidade=1, marcar=True):
    """Busca híbrida. Devolve neurônios com força 0..1, o motivo do acerto e a procedência. Sem acerto forte → []."""
    if os.environ.get("CEREBRO_MOTOR") == "v1" and modo == "hibrido":
        return pc.consultar(pergunta, k, marcar=marcar, quem=agente, ambito=ambito)
    pergunta = (pergunta or "").strip()
    if not pergunta:
        return []
    perm = permissao(agente)
    idx = _sincronizar(modo != "lexical")
    d, nos = idx["d"], idx["d"]["nos"]

    def passa(n):
        return (_visivel(n, perm, projeto) and (not area or n["area"] == area) and (not ambito or ambito in n["ambitos"])
                and (not fonte or n["fonte"] == fonte) and (not tipo or n["tipo"] == tipo)
                and (n.get("natureza", "fato") == natureza if natureza else n.get("natureza") != "obsoleto") and (not desde or (n.get("atualizado") or n["criado"]) >= desde)
                and (not projeto or n["area"] != "clientes" or perm.get("clientes") == "por_projeto"
                     or pc._sem_acento(projeto) in pc._sem_acento(f"{n['titulo']} {n.get('projeto') or ''} {n['texto'][:600]}")))

    # 1) identificador exato (chave, nome do arquivo): vai direto ao topo
    exatos = {}
    for m in _RE_ID.findall(pergunta):
        m = m.strip().lower()
        for n in nos:
            if m in (n["chave"].lower(), (n.get("nome") or "").lower() + ".md", os.path.basename(n.get("arquivo") or "").lower()) \
                    or (len(m) > 6 and m == (n.get("nome") or "").lower()):
                exatos[n["id"]] = 1.0
    for w in re.findall(r"[\w\-]{6,}", pergunta):
        if "-" in w or "_" in w:
            for n in nos:
                if w.lower() in (n.get("nome") or "").lower():
                    exatos.setdefault(n["id"], .95)

    lex = _lexical(pergunta, idx) if modo in ("hibrido", "lexical") else {}
    sem = _semantica(pergunta, idx) if modo in ("hibrido", "semantica") else {}
    # 2) cada lista dá votos pela posição (RRF); 3) a força absoluta vem do sinal mais confiável de cada um
    pos_lex = {nid: r for r, nid in enumerate(sorted(lex, key=lambda i: -lex[i][0]))}
    pos_sem = {nid: r for r, nid in enumerate(sorted(sem, key=lambda i: -sem[i][0]))}
    melhor_lex = max((v[0] for v in lex.values()), default=1) or 1
    nota, motivo, trecho = {}, {}, {}
    for nid in set(lex) | set(sem) | set(exatos):
        n = nos[nid]
        if not passa(n):
            continue
        f_lex, cob = 0, 0
        if nid in lex:
            bm, cob = lex[nid]
            f_lex = (bm / melhor_lex) * min(1, cob / .5) * .9 if cob >= .5 else 0
        f_sem = 0
        if nid in sem:
            z = sem[nid][0]
            if z >= (Z_SEM if nid in lex else Z_SO_SENTIDO):   # sem nenhuma palavra em comum, exige mais
                f_sem = min(1, (z - Z_SEM) / 2.5 + .45)
            elif z >= Z_PAR and cob >= COB_PAR and pos_sem[nid] < 5:   # sentido mais fraco, mas a palavra confirma
                f_sem = .3 + (z - Z_PAR) * .1
            trecho[nid] = idx["trechos"][sem[nid][1]][1]
        rrf = (1 / (10 + pos_lex[nid]) if nid in pos_lex else 0) + (1 / (10 + pos_sem[nid]) if nid in pos_sem else 0)
        forca = max(exatos.get(nid, 0), f_lex, f_sem)
        if f_lex and f_sem:             # as duas buscas concordam: sobe
            forca = min(1, forca + .15 * min(f_lex, f_sem) / max(f_lex, f_sem) + .05)
        forca *= .85 + .15 * n["vida"]
        if forca >= MIN_FORCA:
            nota[nid] = forca + rrf * .05
            motivo[nid] = "exato" if nid in exatos else ("palavra + sentido" if f_lex and f_sem else "palavra" if f_lex else "sentido")
    if not nota:
        return []
    # 4) vizinhos pelo grafo (a lembrança puxada nunca passa da que puxou)
    for _ in range(max(0, int(profundidade))):
        for i, v in sorted(nota.items(), key=lambda x: -x[1])[:k]:
            for j, w, forte in idx["viz"][i]:
                ganho = v * w * (.7 if forte else .6)
                if ganho >= pc.MIN_PUXADO + .1 and ganho > nota.get(j, 0) and passa(nos[j]):
                    nota[j] = ganho
                    motivo[j] = "ligado a: " + nos[i]["titulo"]
    saida = []
    for nid in sorted(nota, key=lambda i: -nota[i])[:k]:
        n = nos[nid]
        saida.append({"id": nid, "chave": n["chave"], "neuronio": n["titulo"], "area": n["area"], "tipo": n["tipo"],
                      "natureza": n.get("natureza", "fato"), "fonte": n["fonte"], "projeto": n["projeto"],
                      "forca": round(min(1, nota[nid]), 3), "veio_por": motivo[nid], "ambitos": n["ambitos"],
                      "resumo": n.get("desc") or "", "trecho": (trecho.get(nid) or n["texto"])[:700],
                      "procedencia": {"fonte": n["fonte"], "arquivo": n.get("arquivo"), "origem": n.get("origem"),
                                      "certeza": n.get("certeza", "confirmado"), "criado": n.get("criado"),
                                      "atualizado": n.get("atualizado"), "agente": n.get("agente")}})
    if marcar:
        pc._marcar_uso([s["chave"] for s in saida if not s["veio_por"].startswith("ligado")][:3])
        pc._registro("consultou", (f"[{agente}] " if agente != "claude" else "") + pergunta[:120], [s["chave"] for s in saida[:3]])
    return saida


# ── leitura de um neurônio, ligações e linha do tempo ───────────────────────────────────────────────────────────────
def _no(ref, agente):
    n = pc._achar(ref)
    if not _visivel(n, permissao(agente), n.get("projeto")):
        raise PermissionError(f"{agente} não tem acesso a {n['chave']}")
    return n


def obter(ref, agente="claude"):
    _no(ref, agente)
    r = pc.ler_neuronio(ref)
    n = pc._achar(ref)
    r.update(natureza=n.get("natureza", "fato"), area=n["area"], resumo=n.get("desc") or "", arquivo=n.get("arquivo"),
             criado=n.get("criado"), atualizado=n.get("atualizado"))
    return r


def expandir(ref, profundidade=1, agente="claude", limite=12):
    """ligações do neurônio: fortes ([[links]], ligar, pasta do projeto) e por assunto parecido, até N passos"""
    n = _no(ref, agente)
    idx = _sincronizar(MOD.pronto())
    perm, nos = permissao(agente), idx["d"]["nos"]
    vistos, fila, saida = {n["id"]}, [(n["id"], 0)], []
    while fila:
        i, nivel = fila.pop(0)
        if nivel >= max(1, int(profundidade)):
            continue
        for j, w, forte in sorted(idx["viz"][i], key=lambda x: -x[1]):
            if j in vistos or not _visivel(nos[j], perm, nos[j].get("projeto")):
                continue
            vistos.add(j)
            o = nos[j]
            saida.append({"chave": o["chave"], "neuronio": o["titulo"], "area": o["area"], "passos": nivel + 1,
                          "ligacao": "forte" if forte else f"assunto {w:.2f}", "de": nos[i]["chave"], "resumo": (o.get("desc") or o["texto"])[:200]})
            fila.append((j, nivel + 1))
    return {"chave": n["chave"], "neuronio": n["titulo"], "ligacoes": saida[:limite]}


def linha_tempo(ref=None, tema=None, agente="claude", limite=30):
    """evolução: versões gravadas + atividade (consultas, guardas, descartes) de um neurônio ou de um tema"""
    chaves = None
    if ref:
        chaves = {_no(ref, agente)["chave"]}
    elif tema:
        chaves = {r["chave"] for r in buscar(tema, 8, agente=agente, marcar=False)}
    eventos = []
    try:
        for l in open(_arq("versoes.jsonl"), encoding="utf-8").read().splitlines():
            v = json.loads(l)
            if chaves is None or v.get("chave") in chaves:
                eventos.append({"t": v["t"], "acao": v["acao"], "chave": v.get("chave"), "agente": v.get("agente"),
                                "texto": (v.get("depois") or {}).get("texto", "")[:300] if isinstance(v.get("depois"), dict) else ""})
    except (OSError, ValueError):
        pass
    for a in pc.atividade(400):
        if a.get("acao") in ("consultou", "guardou", "atualizou", "guardou projeto", "atualizou projeto"):
            continue      # essas já estão nas versões (com o antes/depois)
        if chaves is None or set(a.get("chaves") or []) & chaves:
            eventos.append({"t": a["t"], "acao": a["acao"], "chave": (a.get("chaves") or [None])[0], "texto": a.get("texto", "")[:300]})
    eventos.sort(key=lambda e: -e["t"])
    for e in eventos:
        e["quando"] = time.strftime("%Y-%m-%d %H:%M", time.localtime(e["t"]))
    return eventos[:limite]


# ── contexto pronto por perfil (a Kani 4B recebe pouco e certeiro; o Claude, mais com fontes) ───────────────────────
def _frases_relevantes(texto, pergunta, limite_chars):
    termos = set(pc._termos(pergunta))
    frases = [f.strip() for f in re.split(r"(?<=[.!?])\s+|\n+", texto) if len(f.strip()) > 3]
    if sum(len(f) for f in frases) <= limite_chars:
        return " ".join(frases)
    nota = [(len(termos & set(pc._termos(f))) + (1.5 if i == 0 else 0) - i * .01, i) for i, f in enumerate(frases)]
    escolhidas, total = [], 0
    for _, i in sorted(nota, reverse=True):
        if total + len(frases[i]) > limite_chars:
            continue
        escolhidas.append(i)
        total += len(frases[i]) + 1
    return " … ".join(frases[i] for i in sorted(escolhidas))


def contexto(pergunta, perfil=None, agente=None, orcamento_tokens=None, k=None, profundidade=None, detalhe=None,
             citacoes=None, projeto=None, tarefa=None, area=None, marcar=True):
    """texto pronto para entrar no prompt, cortado pelo orçamento (≈4 caracteres por token). Sem acerto → texto vazio."""
    base = dict(PERFIS.get(perfil or agente or "agente", PERFIS["agente"]))
    for c, v in (("orcamento_tokens", orcamento_tokens), ("k", k), ("profundidade", profundidade), ("detalhe", detalhe), ("citacoes", citacoes)):
        if v is not None:
            base[c] = v
    agente = agente or (perfil if perfil in agentes() else "claude")
    consulta = f"{pergunta} {tarefa or ''}".strip()
    res = buscar(consulta, int(base["k"]), agente=agente, projeto=projeto, area=area, profundidade=base["profundidade"], marcar=marcar)
    if base["detalhe"] == "curto":
        res = [r for r in res if not r["veio_por"].startswith("ligado")]
    orc = int(base["orcamento_tokens"]) * 4
    por_item = {"curto": 260, "normal": 700, "completo": 2400}.get(base["detalhe"], 700)
    linhas, usados = [], 0
    for r in res:
        n = pc._achar(r["chave"])
        corpo = n["texto"] if base["detalhe"] == "completo" else _frases_relevantes(
            (r["resumo"] + ". " if r["resumo"] else "") + n["texto"], consulta, por_item)
        cab = f"- {r['neuronio']}"
        if base["citacoes"]:
            cab += f" [{r['chave']}; {r['fonte']}; {r['natureza']}; {r['veio_por']}; força {r['forca']}]"
        linha = f"{cab}: {corpo}"
        if usados + len(linha) > orc:
            linha = linha[:max(0, orc - usados)]
            if len(linha) < 80:
                break
        linhas.append(linha)
        usados += len(linha) + 1
    texto = ("Do cérebro do Pailer (só o que bate com o pedido):\n" + "\n".join(linhas)) if linhas else ""
    return {"texto": texto, "tokens": len(texto) // 4, "itens": [r["chave"] for r in res[:len(linhas)]], "perfil": base}


# ── escrita controlada ───────────────────────────────────────────────────────────────────────────────────────────────
def versao(acao, chave, agente, antes=None, depois=None):
    os.makedirs(pc.PASTA, exist_ok=True)
    with open(_arq("versoes.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"t": time.time(), "acao": acao, "chave": chave, "agente": agente, "antes": antes, "depois": depois},
                           ensure_ascii=False) + "\n")


def _parecidos(titulo, texto, agente):
    """mesmo tema pela busca híbrida (palavra + sentido), sem marcar uso"""
    return [r for r in buscar(f"{titulo}. {texto[:600]}", 3, agente=agente, profundidade=0, marcar=False)
            if not r["veio_por"].startswith("ligado")]


def propor(titulo, texto, agente="claude", natureza="fato", tipo="fato", area=None, tags=None, projeto=None,
           origem=None, certeza=None, ligar=None, validade_dias=None):
    """porta única de escrita para qualquer IA. Quem grava (agentes.json) e traz certeza+origem: entra no cérebro.
    Quem só propõe, hipótese ou conflito: vai para a fila (cerebro/propostas.json) até o Pailer/Claude aceitar."""
    titulo, texto = (titulo or "").strip(), (texto or "").strip()
    if not titulo or not texto:
        raise ValueError("Precisa de título e texto.")
    if natureza not in NATUREZAS:
        raise ValueError("natureza: " + ", ".join(NATUREZAS))
    if not (origem or "").strip():
        return {"guardado": False, "motivo": "Diga a origem (onde isso foi visto/dito). Sem origem não entra."}
    perm = permissao(agente)
    parecidos = _parecidos(titulo, texto, agente)
    igual = [p for p in parecidos if p["forca"] >= .8 and pc._sem_acento(p["neuronio"]) == pc._sem_acento(titulo)]
    if igual or (parecidos and parecidos[0]["forca"] >= .9):
        alvo = (igual or parecidos)[0]
        return {"guardado": False, "motivo": "já existe: atualize esse (brain_update) em vez de duplicar",
                "parecido": {"chave": alvo["chave"], "neuronio": alvo["neuronio"], "forca": alvo["forca"], "trecho": alvo["trecho"][:400]}}
    conflito = [p for p in parecidos if p["forca"] >= .6]
    vai_para_fila = not perm.get("gravar") or certeza not in pc.CERTEZAS or natureza in ("hipotese",) or conflito
    if vai_para_fila:
        with _TRAVA:
            fila = pc._jler(_arq("propostas.json"), [])
            pid = hashlib.sha1(f"{titulo}{time.time_ns()}".encode()).hexdigest()[:10]
            fila.append({"id": pid, "titulo": titulo[:90], "texto": texto[:4000], "agente": agente, "natureza": natureza, "tipo": tipo,
                         "area": area, "tags": tags or [], "projeto": projeto, "origem": origem, "certeza": certeza, "ligar": ligar or [],
                         "validade_dias": validade_dias, "quando": time.time(),
                         "conflita_com": [{"chave": p["chave"], "neuronio": p["neuronio"], "forca": p["forca"]} for p in conflito]})
            pc._jgravar(_arq("propostas.json"), fila[-200:])
        versao("propôs", "prop:" + pid, agente, depois={"titulo": titulo, "texto": texto[:600]})
        motivo = ("parece com o que já existe: confira se contradiz" if conflito else
                  "este agente só propõe" if not perm.get("gravar") else
                  "hipótese não entra direto" if natureza == "hipotese" else "sem certeza (pailer/verificado)")
        return {"guardado": False, "proposto": True, "id": "prop:" + pid, "motivo": motivo,
                "conflita_com": [p["chave"] for p in conflito]}
    r = pc.guardar(titulo, texto, tipo, area, tags, projeto, origem, ligar, True, certeza)
    if r.get("guardado"):
        extra = {"natureza": natureza, "agente": agente}
        if validade_dias:
            extra["expira"] = time.time() + float(validade_dias) * pc.DIA
        _marcar_proprio(r["chave"], extra)
        versao("guardou", r["chave"], agente, depois={"titulo": titulo, "texto": texto[:2000], **extra})
    return r


def _marcar_proprio(chave, campos):
    with pc._TRAVA:
        lista = pc._jler(pc.ARQ_PROPRIOS, [])
        for p in lista:
            if "pro:" + p["id"] == chave:
                p.update(campos)
        pc._jgravar(pc.ARQ_PROPRIOS, lista)


def atualizar(ref, agente="claude", texto=None, titulo=None, natureza=None, tipo=None, area=None, tags=None, origem=None):
    """só neurônios próprios; guarda o antes/depois em versoes.jsonl. Quem não grava: vira proposta de mudança."""
    n = _no(ref, agente)
    if natureza and natureza not in NATUREZAS:
        raise ValueError("natureza: " + ", ".join(NATUREZAS))
    if not permissao(agente).get("gravar"):
        return propor(titulo or n["titulo"], texto or n["texto"], agente, natureza or n.get("natureza", "fato"),
                      origem=origem or f"mudança proposta para {n['chave']}")
    antes = {"titulo": n["titulo"], "texto": n["texto"][:2000], "natureza": n.get("natureza", "fato")}
    r = pc.atualizar(ref, texto, titulo, tipo, area, tags)
    if r.get("ok"):
        if natureza:
            _marcar_proprio(n["chave"], {"natureza": natureza})
        versao("atualizou", n["chave"], agente, antes, {"titulo": titulo or n["titulo"], "texto": (texto or n["texto"])[:2000],
                                                       "natureza": natureza or antes["natureza"], "origem": origem})
    return r


def propostas():
    return pc._jler(_arq("propostas.json"), [])


def decidir_proposta(pid, aceitar, agente="claude", certeza="verificado"):
    """Pailer/Claude aceita (entra no cérebro) ou recusa (sai da fila, fica registrado nas versões)"""
    if not permissao(agente).get("gravar"):
        raise PermissionError("só quem grava decide propostas")
    pid = str(pid).replace("prop:", "")
    with _TRAVA:
        fila = pc._jler(_arq("propostas.json"), [])
        p = next((x for x in fila if x["id"] == pid), None)
        if not p:
            raise ValueError("proposta não encontrada")
        pc._jgravar(_arq("propostas.json"), [x for x in fila if x["id"] != pid])
    if not aceitar:
        versao("recusou", "prop:" + pid, agente)
        return {"ok": True, "recusada": True}
    r = pc.guardar(p["titulo"], p["texto"], p.get("tipo") or "fato", p.get("area"), p.get("tags"), p.get("projeto"),
                   f"{p['origem']} (proposto por {p['agente']})", p.get("ligar"), True, certeza)
    if r.get("guardado"):
        _marcar_proprio(r["chave"], {"natureza": "fato" if p["natureza"] == "hipotese" else p["natureza"], "agente": p["agente"]})
        versao("aceitou", r["chave"], agente, depois={"titulo": p["titulo"], "texto": p["texto"][:2000], "de": "prop:" + pid})
    return r


# ── porta única para MCP e HTTP (mesmos nomes e campos) ─────────────────────────────────────────────────────────────
def usar(nome, args, agente="claude"):
    """para os processos de fora (servidores MCP, Kani): com o KaniCode aberto vai pelo HTTP dele (um modelo só na
    memória); sem ele, roda aqui mesmo. O resultado é o mesmo nos dois caminhos."""
    if not SOU_SERVIDOR and os.environ.get("CEREBRO_LOCAL") != "1" and os.environ.get("KANICODE_TESTE") != "1"             and pc.PASTA == _PASTA_REAL:      # teste com dados isolados nunca pergunta ao KaniCode de verdade
        import cerebro_http
        r = cerebro_http.pedir(nome, args, agente)
        if r is not None:
            return r["r"]
    return chamar(nome, args, agente)


def chamar(nome, args, agente="claude"):
    a = dict(args or {})
    a.pop("agente", None)          # quem é vem da conexão (MCP/chave HTTP), nunca do pedido
    if nome == "brain_search":
        return buscar(a.get("pergunta") or a.get("tema") or "", int(a.get("k") or 5), a.get("modo") or "hibrido", agente,
                      a.get("projeto"), a.get("area"), a.get("ambito"), a.get("fonte"), a.get("tipo"), a.get("natureza"),
                      a.get("desde"), int(a.get("profundidade", 1)), a.get("marcar", True) is not False)
    if nome == "brain_get":
        return obter(a.get("ref"), agente)
    if nome == "brain_expand":
        return expandir(a.get("ref"), int(a.get("profundidade") or 1), agente)
    if nome == "brain_timeline":
        return linha_tempo(a.get("ref"), a.get("tema"), agente, int(a.get("limite") or 30))
    if nome == "brain_context":
        return contexto(a.get("pergunta") or "", a.get("perfil"), agente, a.get("orcamento_tokens"), a.get("k"),
                        a.get("profundidade"), a.get("detalhe"), a.get("citacoes"), a.get("projeto"), a.get("tarefa"), a.get("area"))
    if nome == "brain_remember":
        return propor(a.get("titulo"), a.get("texto"), agente, a.get("natureza") or "fato", a.get("tipo") or "fato", a.get("area"),
                      a.get("tags"), a.get("projeto"), a.get("origem"), a.get("certeza"), a.get("ligar"), a.get("validade_dias"))
    if nome == "brain_update":
        return atualizar(a.get("ref"), agente, a.get("texto"), a.get("titulo"), a.get("natureza"), a.get("tipo"), a.get("area"),
                         a.get("tags"), a.get("origem"))
    if nome == "brain_proposals":
        if a.get("id"):
            return decidir_proposta(a["id"], bool(a.get("aceitar")), agente, a.get("certeza") or "verificado")
        return propostas()
    if nome == "brain_status":
        return estado()
    raise ValueError("ferramenta do cérebro desconhecida: " + nome)


_P = {"type": "string"}
FERRAMENTAS = [
    {"name": "brain_search", "description": "Busca híbrida no cérebro do Pailer (palavra + sentido + ligações). Use quando faltar "
     "informação dele (cliente, estilo, processo, decisão). Devolve neurônios com força 0..1, motivo e procedência; vazio = não sabe.",
     "inputSchema": {"type": "object", "properties": {"pergunta": _P, "k": {"type": "integer"}, "modo": {"type": "string", "enum": ["hibrido", "lexical", "semantica"]},
                     "projeto": _P, "area": _P, "ambito": _P, "fonte": _P, "tipo": _P, "natureza": {"type": "string", "enum": list(NATUREZAS)},
                     "desde": {"type": "number"}, "profundidade": {"type": "integer"}}, "required": ["pergunta"]}},
    {"name": "brain_get", "description": "Neurônio completo pela chave (mem:…, pro:…, lic:…).",
     "inputSchema": {"type": "object", "properties": {"ref": _P}, "required": ["ref"]}},
    {"name": "brain_expand", "description": "Ligações de um neurônio (fortes e por assunto), até N passos.",
     "inputSchema": {"type": "object", "properties": {"ref": _P, "profundidade": {"type": "integer"}}, "required": ["ref"]}},
    {"name": "brain_timeline", "description": "Evolução e decisões: versões e atividade de um neurônio (ref) ou de um tema.",
     "inputSchema": {"type": "object", "properties": {"ref": _P, "tema": _P, "limite": {"type": "integer"}}}},
    {"name": "brain_context", "description": "Contexto pronto e compacto para um pedido, cortado pelo orçamento de tokens. "
     "Perfis: kani (600 tokens), codex (1500), agente (4000); ou declare orcamento_tokens/k/profundidade/detalhe/citacoes.",
     "inputSchema": {"type": "object", "properties": {"pergunta": _P, "perfil": _P, "orcamento_tokens": {"type": "integer"}, "k": {"type": "integer"},
                     "profundidade": {"type": "integer"}, "detalhe": {"type": "string", "enum": ["curto", "normal", "completo"]},
                     "citacoes": {"type": "boolean"}, "projeto": _P, "tarefa": _P, "area": _P}, "required": ["pergunta"]}},
    {"name": "brain_remember", "description": "Propõe memória nova. Entra direto só com certeza (pailer/verificado), origem e permissão "
     "de gravar; hipótese, conflito ou agente sem permissão vão para a fila de propostas. Duplicata é recusada.",
     "inputSchema": {"type": "object", "properties": {"titulo": _P, "texto": _P, "natureza": {"type": "string", "enum": list(NATUREZAS)},
                     "tipo": _P, "area": _P, "tags": {"type": "array", "items": _P}, "projeto": _P, "origem": _P,
                     "certeza": {"type": "string", "enum": list(pc.CERTEZAS)}, "ligar": {"type": "array", "items": _P},
                     "validade_dias": {"type": "number"}}, "required": ["titulo", "texto", "origem"]}},
    {"name": "brain_update", "description": "Atualiza um neurônio próprio (pro:…), guardando a versão anterior.",
     "inputSchema": {"type": "object", "properties": {"ref": _P, "texto": _P, "titulo": _P, "natureza": {"type": "string", "enum": list(NATUREZAS)},
                     "tipo": _P, "area": _P, "tags": {"type": "array", "items": _P}, "origem": _P}, "required": ["ref"]}},
    {"name": "brain_proposals", "description": "Lista a fila de propostas; com id + aceitar (true/false) decide uma.",
     "inputSchema": {"type": "object", "properties": {"id": _P, "aceitar": {"type": "boolean"}, "certeza": _P}}},
    {"name": "brain_status", "description": "Estado do índice (neurônios, trechos, busca por sentido ligada).",
     "inputSchema": {"type": "object", "properties": {}}},
]
