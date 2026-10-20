"""Onde cada demanda mora no PC: <cliente>/<produção>/<ano>/<mês>/<nn - TIPO - TÍTULO>/.

Vídeo (reels/stories) ganha 01 - BRUTO, 02 - ASSETS, 03 - PROJETO - <nome>, 04 - RENDERS (padrão das pastas do Pailer);
o resto ganha só 02 - ASSETS. O material do cliente vai para 01 - BRUTO (vídeo) ou 02 - ASSETS.
Uma vez criada, a pasta fica ligada à demanda em vinculos.json (baixar de novo cai no mesmo lugar, mesmo que o mês vire).
"""
import datetime, json, os, re, unicodedata

PASTA = os.path.dirname(os.path.abspath(__file__))
MAPA = os.path.join(PASTA, "mapa_clientes.json")
VINCULOS = os.path.join(PASTA, "vinculos.json")
MESES = ["JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO", "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO",
         "NOVEMBRO", "DEZEMBRO"]
TIPO_PASTA = {"estatico": "ESTATICO", "reels": "REELS", "stories": "STORIES", "carrossel": "CARROSSEL",
              "mosaico": "MOSAICO", "outro": "PECA", "estruturacao": "ESTRUTURACAO", "sites_lp": "SITE",
              "impressos": "IMPRESSO"}
VIDEO = {"reels", "stories"}


def _json(p, padrao):
    if not os.path.exists(p):
        return padrao
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def mapa():
    return _json(MAPA, {})


def _norm(t):
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9]+", " ", t).strip()


def _limpo(t, n=60):
    t = re.sub(r'[<>:"/\\|?*\n\r\t]+', " ", t or "").strip().rstrip(".")
    return re.sub(r"\s+", " ", t)[:n].strip() or "SEM TITULO"


def pasta_cliente(client_id):
    m = mapa()
    c = m.get("clientes", {}).get((client_id or "")[:8])
    if not c or not c.get("pasta"):
        return None, c
    return os.path.join(m["raiz"], c["pasta"]), c


def _mes_existente(base, rel):
    """'2026\\10 - OUTUBRO': se já existe uma pasta '10 - ...' no mesmo lugar, usa ela (nomes variam: '06 - JUN')."""
    partes = rel.split("\\")
    atual = base
    for p in partes:
        m = re.match(r"(\d{2}) - ", p)
        if m and os.path.isdir(atual):
            ach = [d for d in os.listdir(atual) if d.startswith(m.group(1) + " -") and os.path.isdir(os.path.join(atual, d))]
            if ach:
                p = sorted(ach)[0]
        atual = os.path.join(atual, p)
    return atual


def pasta_demanda(d, quando=None, criar=False):
    """Caminho da pasta da demanda `d` (dict do pandalab.demanda). criar=True monta as subpastas."""
    vinc = _json(VINCULOS, {})
    if d["id"] in vinc and os.path.isdir(vinc[d["id"]]):
        return vinc[d["id"]]
    base, c = pasta_cliente((d.get("client") or {}).get("id"))
    if not base:
        return None
    quando = quando or datetime.date.today()
    rel = c.get("modelo", "{ano}\\{mm} - {MES}").format(ano=quando.year, mm=f"{quando.month:02d}",
                                                         MES=MESES[quando.month - 1], pacote=quando.month)
    mes = _mes_existente(os.path.join(base, c.get("producao", "")), rel)
    titulo = _limpo(d["title"]).upper()
    tipo = TIPO_PASTA.get(d.get("content_type"), "PECA")
    # já existe uma pasta com esse título no mês? (feita à mão antes) -> usa
    if os.path.isdir(mes):
        alvo = _norm(titulo)
        for nome in os.listdir(mes):
            if os.path.isdir(os.path.join(mes, nome)) and alvo and alvo in _norm(nome):
                return _vincular(d["id"], os.path.join(mes, nome)) if criar else os.path.join(mes, nome)
    nums = [int(m.group(1)) for n in (os.listdir(mes) if os.path.isdir(mes) else [])
            if (m := re.match(r"(\d{2})\s*-", n))]
    nn = f"{(max(nums) + 1) if nums else 1:02d}"
    nome = c.get("demanda", "{nn} - {TIPO} - {TITULO}").format(nn=nn, TIPO=tipo, TITULO=titulo)
    caminho = os.path.join(mes, _limpo(nome, 90))
    if criar:
        subs = (["01 - BRUTO", "02 - ASSETS", f"03 - PROJETO - {_limpo(nome, 90)}", "04 - RENDERS"]
                if d.get("content_type") in VIDEO else ["02 - ASSETS"])
        for s in subs:
            os.makedirs(os.path.join(caminho, s), exist_ok=True)
        _vincular(d["id"], caminho)
    return caminho


def pasta_material(d, caminho):
    return os.path.join(caminho, "01 - BRUTO" if d.get("content_type") in VIDEO else "02 - ASSETS")


def _vincular(did, caminho):
    v = _json(VINCULOS, {})
    v[did] = caminho
    with open(VINCULOS, "w", encoding="utf-8") as f:
        json.dump(v, f, ensure_ascii=False, indent=1)
    return caminho


def briefing(d, caminho):
    """BRIEFING.txt na pasta: o que o cliente pediu, para ler sem abrir o sistema."""
    linhas = [d["title"], "", f"Cliente: {(d.get('client') or {}).get('name')}", f"Tipo: {d.get('content_type')}",
              f"Status: {d.get('status')}", f"Id: {d['id']}", "", "DESCRIÇÃO", d.get("description") or "(vazia)"]
    if d.get("comentarios"):
        linhas += ["", "COMENTÁRIOS"] + [f"[{c['created_at'][:16]}] {c['comment_text']}" for c in d["comentarios"]]
    with open(os.path.join(caminho, "BRIEFING.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(linhas))
