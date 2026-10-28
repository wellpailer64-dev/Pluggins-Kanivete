"""Plugin pessoal Pandalab (só do Pailer; fora do git e do release do KANIVETE).

Etapa 1 = SÓ LEITURA: login, demandas, detalhe, comentários do cliente, arquivos (baixar).
Conversa direto com o Supabase do sistema Pandalab, com o login do Pailer (as regras de acesso do banco valem).
A sessão fica em sessao.bin cifrada pelo Windows (DPAPI: só este usuário neste PC abre); a senha nunca é guardada.
"""
import base64, ctypes, ctypes.wintypes as wt, json, os, re, time, urllib.error, urllib.parse, urllib.request

PASTA = os.path.dirname(os.path.abspath(__file__))
SESSAO = os.path.join(PASTA, "sessao.bin")
CONFIG = os.path.join(PASTA, "config.json")
ENV_SISTEMA = r"D:\01 - ALL IN CLOUD - HD PAILER\01 - PANDA LAB\00 - Sistema Pandalab\.env"
DOWNLOADS = r"D:\Kanivete\Pandalab"

STATUS = {"todo": "A fazer", "in_progress": "Em andamento", "adjustment": "Ajuste", "done": "Feita"}
TIPOS = {"estatico": "Estático", "reels": "Reels", "stories": "Stories", "carrossel": "Carrossel", "mosaico": "Mosaico",
         "outro": "Outro", "estruturacao": "Estruturação", "sites_lp": "Site/LP", "impressos": "Impressos"}


class ErroPanda(Exception):
    pass


# ---------- configuração (URL e chave pública do sistema) ----------
def _config():
    cfg = {}
    if os.path.exists(CONFIG):
        with open(CONFIG, encoding="utf-8") as f:
            cfg = json.load(f)
    if not cfg.get("url") and os.path.exists(ENV_SISTEMA):
        with open(ENV_SISTEMA, encoding="utf-8") as f:
            for ln in f:
                m = re.match(r'\s*(VITE_SUPABASE_URL|VITE_SUPABASE_PUBLISHABLE_KEY)\s*=\s*"?([^"\s]+)', ln)
                if m:
                    cfg["url" if m.group(1).endswith("URL") else "chave"] = m.group(2)
        if cfg.get("url"):
            with open(CONFIG, "w", encoding="utf-8") as f:
                json.dump(cfg, f)
    if not cfg.get("url") or not cfg.get("chave"):
        raise ErroPanda("Não achei o endereço do Pandalab (config.json ou .env do sistema).")
    return cfg


# ---------- DPAPI ----------
class _Blob(ctypes.Structure):
    _fields_ = [("n", wt.DWORD), ("p", ctypes.POINTER(ctypes.c_char))]


def _dpapi(dados, cifrar):
    ent = _Blob(len(dados), ctypes.cast(ctypes.create_string_buffer(dados, len(dados)), ctypes.POINTER(ctypes.c_char)))
    sai = _Blob()
    fn = ctypes.windll.crypt32.CryptProtectData if cifrar else ctypes.windll.crypt32.CryptUnprotectData
    if not fn(ctypes.byref(ent), None, None, None, None, 0, ctypes.byref(sai)):
        raise ErroPanda("Não consegui abrir a sessão guardada (faça login de novo).")
    try:
        return ctypes.string_at(sai.p, sai.n)
    finally:
        ctypes.windll.kernel32.LocalFree(sai.p)


def _salvar_sessao(s):
    with open(SESSAO, "wb") as f:
        f.write(_dpapi(json.dumps(s).encode(), True))


def _ler_sessao():
    if not os.path.exists(SESSAO):
        raise ErroPanda("Sem login. Rode: panda.py login")
    with open(SESSAO, "rb") as f:
        return json.loads(_dpapi(f.read(), False))


# ---------- HTTP ----------
def _http(metodo, caminho, corpo=None, token=None, cru=False):
    cfg = _config()
    url = caminho if caminho.startswith("http") else cfg["url"].rstrip("/") + caminho
    cab = {"apikey": cfg["chave"], "Content-Type": "application/json"}
    if token:
        cab["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=json.dumps(corpo).encode() if corpo is not None else None,
                                 headers=cab, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            dados = r.read()
            return dados if cru else (json.loads(dados) if dados else None)
    except urllib.error.HTTPError as e:
        txt = e.read().decode("utf-8", "replace")[:300]
        raise ErroPanda(f"Pandalab respondeu {e.code}: {txt}")
    except urllib.error.URLError as e:
        raise ErroPanda(f"Sem conexão com o Pandalab: {e.reason}")


def login(identificador, senha):
    """E-mail = login normal do Supabase; @usuario (ou sem @ no meio) = login de funcionário do sistema."""
    ident = identificador.strip()
    if "@" in ident[1:]:
        r = _http("POST", "/auth/v1/token?grant_type=password", {"email": ident, "password": senha})
        sess, nome = r, (r.get("user") or {}).get("email")
    else:
        r = _http("POST", "/functions/v1/employee-login", {"username": ident.lstrip("@").lower(), "password": senha})
        sess, nome = r.get("session"), (r.get("employee") or {}).get("name")
        if not sess:
            # Como o site: funcionário sem usuário no Auth entra só com a chave pública (o que o banco deixa ler).
            _salvar_sessao({"nome": nome, "funcionario": r.get("employee"), "publico": True})
            return nome
    _salvar_sessao({"refresh": sess["refresh_token"], "access": sess["access_token"],
                    "expira": time.time() + int(sess.get("expires_in", 3600)) - 60, "nome": nome})
    return nome


def sair():
    if os.path.exists(SESSAO):
        os.remove(SESSAO)


def _token():
    s = _ler_sessao()
    if s.get("publico"):
        return None
    if time.time() < s.get("expira", 0):
        return s["access"]
    try:
        r = _http("POST", "/auth/v1/token?grant_type=refresh_token", {"refresh_token": s["refresh"]})
    except ErroPanda:
        raise ErroPanda("A sessão do Pandalab venceu. Rode: panda.py login")
    s.update(refresh=r["refresh_token"], access=r["access_token"], expira=time.time() + int(r.get("expires_in", 3600)) - 60)
    _salvar_sessao(s)
    return s["access"]


def _ler(tabela, **params):
    """GET no PostgREST. SÓ LEITURA nesta etapa: não existe função de escrita no plugin."""
    q = urllib.parse.urlencode(params, safe="(),*:!.")
    return _http("GET", f"/rest/v1/{tabela}?{q}", token=_token())


# ---------- consultas ----------
_SEL = ("id,title,status,content_type,custom_creative_type_name,is_urgent,needs_revision,created_at,updated_at,"
        "description,delivery_link,is_from_lab,client:client_tags(id,name)")


def quem():
    s = _ler_sessao()
    if s.get("publico"):
        return {"nome": s.get("nome"), "modo": "funcionário (chave pública)", "papel": (s.get("funcionario") or {}).get("role")}
    u = _http("GET", "/auth/v1/user", token=_token())
    return {"nome": s.get("nome"), "email": u.get("email"), "id": u.get("id")}


def demandas(status=None, cliente=None, busca=None, limite=200, arquivadas=False):
    p = {"select": _SEL, "deleted_at": "is.null", "order": "is_urgent.desc.nullslast,position.asc,created_at.desc", "limit": str(limite)}
    if not arquivadas:
        p["archived_at"] = "is.null"
    if status == "abertas":
        p["status"] = "neq.done"
    elif status:
        p["status"] = "eq." + status
    if busca:
        p["title"] = f"ilike.*{busca}*"
    rows = _ler("demands", **p)
    if cliente:
        c = cliente.lower()
        rows = [r for r in rows if c in ((r.get("client") or {}).get("name") or "").lower()]
    return rows


def _achar_id(ref):
    if re.fullmatch(r"[0-9a-f-]{36}", ref):
        return ref
    rows = [r for r in demandas(limite=1000, arquivadas=True) if r["id"].startswith(ref)]
    if len(rows) != 1:
        raise ErroPanda(f"'{ref}' achou {len(rows)} demandas; use mais letras do id.")
    return rows[0]["id"]


def demanda(ref):
    did = _achar_id(ref)
    d = _ler("demands", select=_SEL + ",audio_path,archived_at", id="eq." + did)
    if not d:
        raise ErroPanda("Demanda não encontrada (ou sem acesso).")
    d = d[0]
    d["arquivos"] = _ler("demand_files", select="id,file_name,file_path,file_size,created_at",
                         demand_id="eq." + did, order="created_at.asc")
    d["comentarios"] = _ler("demand_client_comments",
                            select="comment_text,created_at,cliente:client_tags(name),equipe:employee_tags(name)",
                            demand_id="eq." + did, order="created_at.asc")
    return d


def clientes():
    return _ler("client_tags", select="id,name,service_type,parent_tag_id", order="name.asc")


def _url_assinada(bucket, caminho, segundos=120):
    r = _http("POST", f"/storage/v1/object/sign/{bucket}/{urllib.parse.quote(caminho)}", {"expiresIn": segundos},
              token=_token())
    u = r.get("signedURL") or r.get("signedUrl")
    return _config()["url"].rstrip("/") + "/storage/v1" + u


def _limpo(t):
    return re.sub(r'[<>:"/\\|?*\n\r\t]+', " ", t or "").strip()[:80] or "sem nome"


KANIVETE = os.path.join("D:" + os.sep, "01 - ALL IN CLOUD - HD PAILER", "DESENVOLVIMENTOS EM PYTHON", "CANIVETE DO PAILER")


def _drive():
    """o baixador de link público do Drive do próprio KANIVETE (Functions/drive_publico.py)"""
    import sys
    try:   # dentro do KANIVETE (código ou exe)
        from Functions import drive_publico
        return drive_publico
    except ImportError:
        pass
    for p in (os.path.join(KANIVETE, "Functions"), KANIVETE):
        if p not in sys.path:
            sys.path.insert(0, p)
    import drive_publico
    return drive_publico


def onde(ref, mes=None):
    """Pasta onde a demanda vai morar no PC (sem criar nada). mes = 'AAAA-MM' (padrão: mês de hoje)."""
    import pastas
    d = demanda(ref)
    return d, pastas.pasta_demanda(d, _mes(mes))


def _mes(mes):
    import datetime
    if not mes:
        return None
    a, m = mes.split("-")
    return datetime.date(int(a), int(m), 1)


def baixar(ref, pasta=None, mes=None):
    """Baixa o material da demanda para a pasta certa do cliente (mapa_clientes.json): monta a pasta da demanda,
    material em 01 - BRUTO (vídeo) ou 02 - ASSETS, BRIEFING.txt e demanda.json na raiz dela.
    Cliente sem pasta no mapa: D:/Kanivete/Pandalab/<cliente>/<título>."""
    import pastas
    d = demanda(ref)
    raiz = pasta or pastas.pasta_demanda(d, _mes(mes), criar=True)
    if not raiz:
        raiz = os.path.join(DOWNLOADS, _limpo((d.get("client") or {}).get("name") or "Sem cliente"), _limpo(d["title"]))
    os.makedirs(raiz, exist_ok=True)
    destino_pasta = pastas.pasta_material(d, raiz) if not pasta else raiz
    os.makedirs(destino_pasta, exist_ok=True)
    feitos = []
    for a in d["arquivos"]:
        caminho = a["file_path"]
        m = re.search(r"drive\.google\.com/.*?(?:/d/|id=)([\w-]{20,})", caminho)
        if m:
            if not _drive().baixar(m.group(1), destino_pasta, url=caminho):
                raise ErroPanda(f"O Drive não liberou '{a['file_name']}' (arquivo privado?): {caminho}")
            feitos.append(os.path.join(destino_pasta, a["file_name"]))
            continue
        destino = os.path.join(destino_pasta, _limpo(a["file_name"]))
        dados = _http("GET", caminho, cru=True) if caminho.startswith("http") else \
            _http("GET", _url_assinada("demand-files", caminho), cru=True)
        with open(destino, "wb") as f:
            f.write(dados)
        feitos.append(destino)
    with open(os.path.join(raiz, "demanda.json"), "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    pastas.briefing(d, raiz)
    return raiz, feitos


# ---------- escrita (só por comando explícito; o Claude pede o ok do Pailer antes) ----------
def _multipart(campos):
    limite = "----kanivete" + os.urandom(8).hex()
    partes = []
    for k, v in campos.items():
        partes.append(f'--{limite}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n')
    return ("".join(partes) + f"--{limite}--\r\n").encode("utf-8"), "multipart/form-data; boundary=" + limite


def criar(titulo, cliente_id, tipo="estatico", descricao="", responsavel_id=None):
    """Cria a demanda pelo mesmo caminho do site (função receive-demand), em nome do funcionário logado.
    Arquivos ainda não: anexar pelo site (o site sobe para o Drive do cliente)."""
    if tipo not in TIPOS:
        raise ErroPanda(f"Tipo inválido: {tipo}. Use: {', '.join(TIPOS)}")
    s = _ler_sessao()
    campos = {"title": titulo, "description": descricao, "contentType": tipo, "clientTagId": cliente_id,
              "fileData": "[]", "audioData": "[]"}
    if (s.get("funcionario") or {}).get("tagId"):
        campos["createdByEmployeeId"] = s["funcionario"]["tagId"]
    if responsavel_id:
        campos["assignedEmployeeId"] = responsavel_id
    corpo, ctipo = _multipart(campos)
    cfg = _config()
    req = urllib.request.Request(cfg["url"].rstrip("/") + "/functions/v1/receive-demand", data=corpo, method="POST",
                                 headers={"apikey": cfg["chave"], "Authorization": "Bearer " + (_token() or cfg["chave"]),
                                          "Content-Type": ctipo})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raise ErroPanda(f"Pandalab recusou: {e.code} {e.read().decode('utf-8', 'replace')[:300]}")


def achar_cliente(nome):
    n = nome.lower()
    cs = [c for c in clientes() if n in c["name"].lower() or c["id"].startswith(nome)]
    if len(cs) != 1:
        raise ErroPanda(f"'{nome}' achou {len(cs)} clientes: {', '.join(c['name'] for c in cs) or '-'}")
    return cs[0]


# ---------- volta para o sistema: status e comentário (como o site faz; liberado pelo Pailer em 2026-10-19,
# o Claude confirma com ele antes de mexer em card real) ----------
def _gravar(metodo, tabela, corpo, filtro=""):
    cfg = _config()
    tok = _token() or cfg["chave"]
    req = urllib.request.Request(f"{cfg['url'].rstrip('/')}/rest/v1/{tabela}{filtro}", method=metodo,
                                 data=json.dumps(corpo).encode() if corpo is not None else None,
                                 headers={"apikey": cfg["chave"], "Authorization": "Bearer " + tok,
                                          "Content-Type": "application/json", "Prefer": "return=representation"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        raise ErroPanda(f"Pandalab recusou: {e.code} {e.read().decode('utf-8', 'replace')[:300]}")


def _eu():
    s = _ler_sessao()
    f = s.get("funcionario") or {}
    return {"tag": f.get("tagId"), "nome": f.get("name") or s.get("nome") or "Kanivete", "foto": f.get("profileImageUrl")}


def mudar_status(ref, status):
    """A fazer / Em andamento / Ajuste. 'Feita' é pela entrega (no site), que sobe os arquivos e fecha o card."""
    if status not in ("todo", "in_progress", "adjustment"):
        raise ErroPanda("Status: todo, in_progress ou adjustment ('done' só pela entrega, no site).")
    d = demanda(ref)
    # como o site: o card vai para o topo da coluna e os outros descem uma posição
    for o in _ler("demands", select="id,position", status="eq." + status, deleted_at="is.null"):
        _gravar("PATCH", "demands", {"position": (o.get("position") or 0) + 1}, "?id=eq." + o["id"])
    _gravar("PATCH", "demands", {"status": status, "position": 0}, "?id=eq." + d["id"])
    if status == "in_progress":
        eu = _eu()
        tipo = TIPOS.get(d["content_type"], d["content_type"])
        cli = (d.get("client") or {}).get("name")
        _gravar("POST", "delivery_notifications", {
            "notification_type": "demand_in_progress", "is_read": False,
            "delivery_title": f"{tipo} de {cli} está Em Andamento!" if cli else f"{tipo} está Em Andamento!",
            "actor_name": eu["nome"], "actor_image_path": eu["foto"]})
    return {"id": d["id"], "status": status}


def comentar(ref, texto):
    d = demanda(ref)
    eu = _eu()
    texto = (texto or "").strip()
    if not texto:
        raise ErroPanda("Comentário vazio.")
    _gravar("POST", "demand_client_comments", {"demand_id": d["id"], "comment_text": texto, "employee_tag_id": eu["tag"]})
    try:   # como no site: se o banco recusar a notificação, o comentário fica assim mesmo
        _gravar("POST", "demand_notifications", {
            "demand_id": d["id"], "notification_type": "comment", "demand_title": d["title"], "actor_name": eu["nome"],
            "actor_image_path": eu["foto"], "comment_text": texto[:100], "message": texto[:100]})
    except ErroPanda:
        return {"ok": True, "aviso": "comentário salvo; a notificação foi recusada pelo banco (igual acontece no site)"}
    return {"ok": True}


EXT_FINAIS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".mov", ".pdf")


def finais(ref, limite_mb=400):
    """Arquivos finais para a entrega: pasta RENDERS/EXPORT da demanda; senão as imagens/vídeos soltos na raiz dela
    (o padrão das pautas: '01 - CARROSSEL 1.png')."""
    import pastas
    d = demanda(ref)
    raiz = pastas.pasta_demanda(d) or os.path.join(DOWNLOADS, _limpo((d.get("client") or {}).get("name") or "Sem cliente"),
                                                   _limpo(d["title"]))
    if not os.path.isdir(raiz):
        raise ErroPanda("A demanda ainda não tem pasta no PC.")
    cands = [os.path.join(raiz, n) for n in sorted(os.listdir(raiz)) if os.path.isdir(os.path.join(raiz, n))
             and re.search(r"RENDER|EXPORT", n, re.I)] + [raiz]
    for p in cands:
        arqs = sorted(os.path.join(p, f) for f in os.listdir(p)
                      if f.lower().endswith(EXT_FINAIS) and os.path.isfile(os.path.join(p, f)))
        if arqs:
            if sum(os.path.getsize(a) for a in arqs) > limite_mb * 1024 * 1024:
                raise ErroPanda(f"Os finais passam de {limite_mb} MB: envie pelo botão normal do site.")
            return {"pasta": p, "arquivos": arqs}
    raise ErroPanda("Nenhum arquivo final na pasta (RENDERS, EXPORT ou imagens na raiz da demanda).")


# ---------- cliente novo (tag): nome, cor e foto de perfil, como o site (bucket meeting-files/client-profiles) ----------
SERVICOS = ("caixa_rapido", "gerenciamento", "pacote_artes")


def subir_foto_perfil(caminho):
    """Sobe a foto para meeting-files/client-profiles/<aleatório>.<ext> e devolve a URL pública (igual ao site)."""
    import mimetypes, random
    ext = os.path.splitext(caminho)[1].lower() or ".jpg"
    destino = f"client-profiles/{random.random()}{ext}"
    cfg = _config()
    req = urllib.request.Request(f"{cfg['url'].rstrip('/')}/storage/v1/object/meeting-files/{destino}", method="POST",
                                 data=open(caminho, "rb").read(),
                                 headers={"apikey": cfg["chave"], "Authorization": "Bearer " + (_token() or cfg["chave"]),
                                          "Content-Type": mimetypes.guess_type(caminho)[0] or "image/jpeg", "x-upsert": "false"})
    try:
        urllib.request.urlopen(req, timeout=60).read()
    except urllib.error.HTTPError as e:
        raise ErroPanda(f"Pandalab recusou a foto: {e.code} {e.read().decode('utf-8', 'replace')[:300]}")
    return f"{cfg['url'].rstrip('/')}/storage/v1/object/public/meeting-files/{destino}"


def criar_cliente(nome, cor, foto=None, servico="caixa_rapido"):
    """Cria a tag de cliente (aparece no site com nome, cor e foto). Recusa nome repetido."""
    if servico not in SERVICOS:
        raise ErroPanda(f"Serviço inválido: {servico}. Use: {', '.join(SERVICOS)}")
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", cor or ""):
        raise ErroPanda(f"Cor inválida: {cor} (use #rrggbb)")
    if any(c["name"].strip().lower() == nome.strip().lower() for c in clientes()):
        raise ErroPanda(f"Já existe um cliente chamado '{nome}'")
    url = subir_foto_perfil(foto) if foto else None
    r = _gravar("POST", "client_tags", {"name": nome.strip(), "color": cor.lower(), "profile_image_path": url,
                                        "service_type": servico, "is_multi_company": False, "parent_tag_id": None})
    return r[0] if isinstance(r, list) else r


def editar_cliente(ref, nome=None, cor=None, foto=None):
    c = achar_cliente(ref)
    corpo = {}
    if nome: corpo["name"] = nome
    if cor: corpo["color"] = cor.lower()
    if foto: corpo["profile_image_path"] = subir_foto_perfil(foto)
    r = _gravar("PATCH", "client_tags", corpo, f"?id=eq.{c['id']}")
    return r[0] if isinstance(r, list) and r else r


def pasta_drive_cliente(nome, foto_url=None, tag_id=None):
    """Pasta do cliente no Drive da agência, igual ao botão 'Pasta no Drive' do site (função create-client-drive-folder).
    Com tag_id grava o link em client_drive_folders (aba Drive do cliente no site; o botão do site NÃO grava)."""
    cfg = _config()
    req = urllib.request.Request(cfg["url"].rstrip("/") + "/functions/v1/create-client-drive-folder", method="POST",
                                 data=json.dumps({"clientName": nome.strip(), "profileImageUrl": foto_url}).encode(),
                                 headers={"apikey": cfg["chave"], "Authorization": "Bearer " + (_token() or cfg["chave"]),
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raise ErroPanda(f"Drive recusou: {e.code} {e.read().decode('utf-8', 'replace')[:300]}")
    if not d.get("success"):
        raise ErroPanda(f"Drive: {d.get('error') or d}")
    if tag_id:
        ligar_drive(tag_id, d.get("folderUrl"), nome)
    return d.get("folderUrl")


def ligar_drive(tag_id, url, nome=None):
    """link da pasta do Drive na aba Drive do cliente (client_drive_folders), sem repetir"""
    if not _ler("client_drive_folders", select="id", client_tag_id="eq." + tag_id, drive_url="eq." + url):
        _gravar("POST", "client_drive_folders", {"client_tag_id": tag_id, "drive_url": url, "folder_name": nome})


TIPOS_TS = os.path.join(os.path.splitdrive(os.path.abspath(__file__))[0] + os.sep, "01 - ALL IN CLOUD - HD PAILER",
                        "01 - PANDA LAB", "00 - Sistema Pandalab", "src", "integrations", "supabase", "types.ts")


def esquema(tabela=None):
    """tabelas e colunas do banco pelo types.ts do repositório do site (o export-schema não está publicado).
    Sem tabela: nomes; com parte do nome: colunas (nome: tipo) das que batem."""
    txt = open(TIPOS_TS, encoding="utf-8").read()
    txt = txt[txt.index("Tables: {"):txt.index("Views: {")]
    tabs = {}
    for m in re.finditer(r"\n      (\w+): \{\n        Row: \{\n(.*?)\n        \}", txt, re.S):
        tabs[m.group(1)] = [l.strip() for l in m.group(2).splitlines() if l.strip()]
    if not tabela:
        return sorted(tabs)
    return {k: v for k, v in tabs.items() if tabela.lower() in k.lower()}


def area_cliente(tag_id, login, pin):
    """Login da Área do Cliente (como o site: client_areas, PIN de 4 dígitos guardado em base64). Cria ou atualiza."""
    if not re.fullmatch(r"\d{4}", pin or ""):
        raise ErroPanda("O PIN deve ter exatamente 4 dígitos")
    if any(a["login"].lower() == login.strip().lower() and a["tag_id"] != tag_id
           for a in _ler("client_areas", select="tag_id,login")):
        raise ErroPanda(f"O login '{login}' já é de outro cliente")
    corpo = {"tag_id": tag_id, "login": login.strip(), "pin_hash": base64.b64encode(pin.encode()).decode(), "active": True}
    if _ler("client_areas", select="tag_id", tag_id="eq." + tag_id):
        return _gravar("PATCH", "client_areas", corpo, f"?tag_id=eq.{tag_id}")
    return _gravar("POST", "client_areas", corpo)


def marcar_reuniao(cliente, data, hora, titulo=None, link=None, gerar_link=True, participantes=None):
    """Igual ao 'Marcar Reunião' do site: (opcional) create-meet-link gera o Meet + evento na Agenda do Google; grava em
    meeting_reminders, na coluna de reuniões do cliente (meeting_columns, criada se faltar). cliente = tag ou nome livre."""
    try:
        tag = achar_cliente(cliente)
    except ErroPanda:
        tag = None
    nome = tag["name"] if tag else cliente.strip()
    titulo = titulo or f"Reunião com {nome}"
    evento = None
    if not link and gerar_link:
        cfg = _config()
        req = urllib.request.Request(cfg["url"].rstrip("/") + "/functions/v1/create-meet-link", method="POST",
                                     data=json.dumps({"title": titulo, "meetingDate": data, "meetingTime": hora}).encode(),
                                     headers={"apikey": cfg["chave"], "Authorization": "Bearer " + (_token() or cfg["chave"]),
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            raise ErroPanda(f"Meet recusou: {e.code} {e.read().decode('utf-8', 'replace')[:300]}")
        if d.get("needsAuth"):
            raise ErroPanda(f"O Google Agenda do sistema pede autorização: abra {d.get('authUrl')}")
        link, evento = d.get("meetLink"), d.get("eventId")
        if not link:
            raise ErroPanda(f"Não veio link do Meet: {d}")
    if tag:
        col = _ler("meeting_columns", select="id", client_tag_id="eq." + tag["id"])
        col = col[0]["id"] if col else _gravar("POST", "meeting_columns", {
            "title": nome, "client_tag_id": tag["id"], "position": 0,
            "profile_image_path": (_ler("client_tags", select="profile_image_path", id="eq." + tag["id"]) or [{}])[0].get("profile_image_path")})[0]["id"]
    else:
        col = _gravar("POST", "meeting_columns", {"title": nome, "position": 0})[0]["id"]
    corpo_extra = {}
    if participantes:   # nomes (parte) da equipe → employee_tags.id (coluna participant_ids, bolinhas no card)
        equipe = _ler("employee_tags", select="id,name")
        ids = []
        for n in participantes:
            achou = [e for e in equipe if n.strip().lower() in e["name"].lower()]
            if len(achou) != 1:
                raise ErroPanda(f"participante '{n}' achou {len(achou)}: {', '.join(e['name'] for e in achou) or '-'}")
            ids.append(achou[0]["id"])
        corpo_extra["participant_ids"] = ids
    r = _gravar("POST", "meeting_reminders", {**corpo_extra, "title": titulo, "meeting_date": data, "meeting_time": hora, "meet_link": link,
                                              "google_event_id": evento, "client_tag_id": tag["id"] if tag else None,
                                              "client_name": nome, "column_id": col})
    return (r[0] if isinstance(r, list) else r)


# ---------- entrega (como o DeliveryUploadDialog do site; liberado pelo Pailer em 2026-10-28) ----------
def _pacote_da_entrega(cliente_id):
    """getPackageNumberForNextDelivery do site: só cliente 'pacote_artes' tem número de pacote."""
    if not cliente_id:
        return None
    c = _ler("client_tags", select="service_type", id="eq." + cliente_id)
    if not c or c[0].get("service_type") != "pacote_artes":
        return None
    pacotes = _ler("client_packages", select="id,package_number,package_quantity,package_type,package_value,is_completed",
                   client_tag_id="eq." + cliente_id, order="package_number.asc")
    if not pacotes:
        return 1
    usados = {}
    for e in _ler("deliveries", select="id,package_number", client_tag_id="eq." + cliente_id):
        n = int(e.get("package_number") or 0)
        if n:
            usados[n] = usados.get(n, 0) + 1
    for p in pacotes:
        if not p.get("is_completed") and usados.get(p["package_number"], 0) < p["package_quantity"]:
            return p["package_number"]
    ult = pacotes[-1]
    prox = (ult.get("package_number") or 1) + 1
    agora = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if not ult.get("is_completed"):
        _gravar("PATCH", "client_packages", {"is_completed": True, "completed_at": agora, "updated_at": agora}, "?id=eq." + ult["id"])
    if _ler("client_packages", select="package_number", client_tag_id="eq." + cliente_id, package_number=f"eq.{prox}"):
        return prox
    _gravar("POST", "client_packages", {"client_tag_id": cliente_id, "package_type": ult.get("package_type"),
                                        "package_quantity": ult["package_quantity"], "package_value": ult.get("package_value"),
                                        "package_number": prox, "activated_at": agora, "is_completed": False,
                                        "completed_at": None, "updated_at": agora})
    return prox


def _cab(t):
    """cabeçalho como o navegador manda (Latin-1 cru; o Deno lê assim); fora do Latin-1, sem acento"""
    try:
        t.encode("latin-1"); return t
    except UnicodeEncodeError:
        import unicodedata
        return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()


def _subir_drive(caminho, cliente, titulo):
    """upload-to-drive do site (x-upload-type delivery): vai para a pasta de entrega do cliente no Drive da agência."""
    import mimetypes
    cfg = _config()
    tipo = mimetypes.guess_type(caminho)[0] or "application/octet-stream"
    nome = os.path.basename(caminho)
    req = urllib.request.Request(cfg["url"].rstrip("/") + "/functions/v1/upload-to-drive", method="POST",
                                 data=open(caminho, "rb").read(),
                                 headers={"apikey": cfg["chave"], "Authorization": "Bearer " + cfg["chave"], "Content-Type": tipo,
                                          "x-file-name": _cab(nome),
                                          "x-client-name": _cab(cliente),
                                          "x-demand-title": _cab(titulo),
                                          "x-upload-type": "delivery"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            res = json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raise ErroPanda(f"Drive recusou {nome}: {e.code} {e.read().decode('utf-8', 'replace')[:300]}")
    if not res.get("webViewLink"):
        raise ErroPanda(f"Drive não devolveu o link de {nome}: {res}")
    return {"nome": nome, "tipo": tipo, "link": res["webViewLink"]}


def entregar(ref, arquivos):
    """Sobe os finais para o Drive, cria a entrega (deliveries + delivery_items), põe o card em Feitas e apaga a
    demanda — os mesmos passos do botão Entregar do site. Site/LP, Identidade visual e demanda com áudio: pelo site."""
    d = _ler("demands", select="id,title,description,content_type,client_tag_id,audio_path,"
             "client_tags(name,profile_image_path)", id="eq." + _achar_id(ref))
    if not d:
        raise ErroPanda("Demanda não encontrada.")
    d = d[0]
    if d["content_type"] in ("sites_lp", "identidade_visual"):
        raise ErroPanda("Site/LP e Identidade visual: entregar pelo site (têm etapas próprias).")
    if d.get("audio_path"):
        raise ErroPanda("A demanda tem áudio anexado: entregar pelo site (ele apaga os áudios do armazenamento).")
    if not arquivos:
        raise ErroPanda("Nenhum arquivo para entregar.")
    ct = d.get("client_tags") or {}
    cliente, titulo = ct.get("name") or "Cliente", d.get("title") or "Demanda"
    feitos = [_subir_drive(a, cliente, titulo) for a in arquivos]
    ent = _ler("deliveries", select="id", demand_id="eq." + d["id"])
    if ent:
        eid = ent[0]["id"]
    else:
        eid = _gravar("POST", "deliveries", {
            "title": titulo, "demand_id": d["id"], "content_type": d["content_type"], "client_tag_id": d.get("client_tag_id"),
            "description": d.get("description") or None, "instagram_username": ct.get("name"),
            "instagram_profile_image": ct.get("profile_image_path"),
            "package_number": _pacote_da_entrega(d.get("client_tag_id"))})[0]["id"]
    _gravar("DELETE", "delivery_revisions", None, "?delivery_id=eq." + eid)
    for f in _ler("demand_files", select="id,file_path", demand_id="eq." + d["id"]):
        if f.get("file_path") and not f["file_path"].startswith("http"):
            try:
                _http("DELETE", "/storage/v1/object/demand-files", {"prefixes": [f["file_path"]]}, token=_token())
            except ErroPanda:
                pass
        _gravar("DELETE", "demand_files", None, "?id=eq." + f["id"])
    for o in _ler("demands", select="id,position", status="eq.done", deleted_at="is.null"):
        _gravar("PATCH", "demands", {"position": (o.get("position") or 0) + 1}, "?id=eq." + o["id"])
    _gravar("PATCH", "demands", {"status": "done", "delivery_link": feitos[0]["link"], "needs_revision": False, "position": 0},
            "?id=eq." + d["id"])
    _gravar("POST", "delivery_items", [{"delivery_id": eid, "file_path": f["link"], "file_type": f["tipo"], "position": i}
                                       for i, f in enumerate(feitos)])
    _gravar("DELETE", "demands", None, "?id=eq." + d["id"])
    return {"entrega": eid, "arquivos": [f["nome"] for f in feitos], "link": feitos[0]["link"]}
