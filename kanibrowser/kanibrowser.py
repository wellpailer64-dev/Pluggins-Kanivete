"""KaniBrowser: um Chrome próprio do KANIVETE (perfil separado, logins guardados), controlado por CANAL PRIVADO.

Segurança: o Chrome abre com --remote-debugging-pipe (dois pipes herdados só por ele), SEM porta de rede. Só o
processo do Kanivete que o abriu consegue comandá-lo; nenhum outro programa do PC entra. Fechou o app, o canal some
(o navegador fecha junto). O agente usa o KaniBrowser pelo próprio app (kb.py → modo agente → KPLUG.chamar).
Ler e baixar: livres. Clicar/digitar/postar em site de terceiros: só por pedido explícito do Pailer.
"""
import base64, ctypes, json, mimetypes, msvcrt, os, re, subprocess, sys, threading, time, urllib.parse, urllib.request
from ctypes import wintypes
from contextlib import contextmanager

RAIZ = r"D:\Kanivete\KaniBrowser"
PERFIL = os.path.join(RAIZ, "perfil")
SAIDA = os.path.join(RAIZ, "downloads")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/141.0.0.0 Safari/537.36")


class ErroKB(Exception):
    pass


# ---------- perfis (várias contas, como a tela "Quem está usando o Chrome?") ----------
# cada perfil = uma pasta de dados própria do Chrome (logins separados); "principal" = a pasta antiga (PERFIL)
PERFIS = os.path.join(RAIZ, "perfis")
PERFIS_JSON = os.path.join(RAIZ, "perfis.json")


def _perfis_ler():
    try:
        with open(PERFIS_JSON, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    lista = [p for p in d.get("lista") or [] if isinstance(p, dict) and p.get("id")]
    if not any(p["id"] == "principal" for p in lista):
        lista.insert(0, {"id": "principal", "nome": "Principal"})
    return {"atual": d.get("atual") or "principal", "lista": lista}


def _perfis_gravar(d):
    os.makedirs(RAIZ, exist_ok=True)
    with open(PERFIS_JSON + ".tmp", "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(PERFIS_JSON + ".tmp", PERFIS_JSON)


def pasta_perfil(pid=None):
    pid = pid or _perfis_ler()["atual"]
    return PERFIL if pid == "principal" else os.path.join(PERFIS, pid)


def _conta(pasta):
    """e-mail e foto da conta Google logada no perfil (Local State do Chrome); foto em data URL"""
    try:
        with open(os.path.join(pasta, "Local State"), encoding="utf-8") as f:
            info = ((json.load(f).get("profile") or {}).get("info_cache") or {}).get("Default") or {}
    except (OSError, ValueError):
        return "", ""
    foto = ""
    arq = info.get("gaia_picture_file_name")
    if arq:
        c = os.path.join(pasta, "Default", arq)
        try:
            with open(c, "rb") as f:
                foto = "data:image/png;base64," + base64.b64encode(f.read()).decode()
        except OSError:
            pass
    return str(info.get("user_name") or ""), foto


def perfis():
    """lista dos perfis {id, nome, email, foto, atual} + qual está aberto"""
    d = _perfis_ler()
    atual = _c.get("perfil") if ativo() else d["atual"]
    out = []
    for p in d["lista"]:
        email, foto = _conta(pasta_perfil(p["id"]))
        out.append({"id": p["id"], "nome": p.get("nome") or p["id"], "email": email, "foto": foto, "atual": p["id"] == atual})
    return {"atual": atual, "lista": out}


def perfil_criar(nome):
    nome = str(nome or "").strip()[:40]
    if not nome:
        raise ErroKB("Dê um nome ao perfil.")
    d = _perfis_ler()
    base = re.sub(r"[^a-z0-9]+", "-", nome.lower()).strip("-") or "perfil"
    pid, n = base, 2
    while any(p["id"] == pid for p in d["lista"]) or pid == "principal":
        pid, n = f"{base}-{n}", n + 1
    d["lista"].append({"id": pid, "nome": nome})
    _perfis_gravar(d)
    return pid


def perfil_renomear(pid, nome):
    d = _perfis_ler()
    for p in d["lista"]:
        if p["id"] == pid:
            p["nome"] = str(nome or "").strip()[:40] or p["nome"]
    _perfis_gravar(d)
    return True


def perfil_trocar(pid):
    """fecha o navegador e marca o perfil novo; quem chamou abre de novo (o painel 🌐 reencaixa as janelas)"""
    d = _perfis_ler()
    if not any(p["id"] == pid for p in d["lista"]):
        raise ErroKB("Perfil não existe: " + str(pid))
    if ativo() and _c.get("perfil") == pid:
        return pid
    if ativo():
        fechar_navegador()
        proc = _c["proc"]
        try:
            proc.wait(10)
        except Exception:
            proc.kill()
    d["atual"] = pid
    _perfis_gravar(d)
    return pid


def _chrome():
    for v in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        for p in (("Google", "Chrome", "Application", "chrome.exe"), ("Microsoft", "Edge", "Application", "msedge.exe")):
            c = os.path.join(os.environ.get(v, ""), *p)
            if os.path.isfile(c):
                return c
    return None


# ---------- o canal (um navegador por processo do Kanivete) ----------
_c = {"proc": None, "w": None, "r": None, "id": 0, "resp": {}, "sessoes": {}, "vivo": False}
_trava = threading.Lock()
_ouvintes = []   # funções chamadas com cada evento do navegador (visao.py: quadros, cursor, listas, avisos)


def _ler():
    buf = b""
    fd = _c["r"]
    while True:
        try:
            pedaco = os.read(fd, 1 << 16)
        except OSError:
            pedaco = b""
        if not pedaco:
            break
        buf += pedaco
        while b"\0" in buf:
            msg, buf = buf.split(b"\0", 1)
            try:
                m = json.loads(msg)
            except ValueError:
                continue
            if "id" in m and m["id"] in _c["resp"]:
                ev = _c["resp"][m["id"]]
                _c["resp"][m["id"]] = m
                ev.set()
            elif "method" in m:
                if m["method"] == "Target.detachedFromTarget":
                    tid = next((k for k, v in _c["sessoes"].items() if v == m["params"].get("sessionId")), None)
                    _c["sessoes"].pop(tid, None)
                for f in _ouvintes:
                    try:
                        f(m)
                    except Exception:
                        pass
    _c["vivo"] = False
    _c["sessoes"].clear()
    for k, v in list(_c["resp"].items()):   # acorda quem estava esperando
        if isinstance(v, threading.Event):
            _c["resp"][k] = {"error": {"message": "o navegador fechou"}}
            v.set()


def ativo():
    return bool(_c["vivo"] and _c["proc"] and _c["proc"].poll() is None)


def _cmd(metodo, params=None, sessao=None, timeout=30):
    if not ativo():
        raise ErroKB("O KaniBrowser está fechado. Abra primeiro.")
    with _trava:
        _c["id"] += 1
        i = _c["id"]
        ev = threading.Event()
        _c["resp"][i] = ev
        m = {"id": i, "method": metodo, "params": params or {}}
        if sessao:
            m["sessionId"] = sessao
        os.write(_c["w"], json.dumps(m).encode() + b"\0")
    if not ev.wait(timeout):
        _c["resp"].pop(i, None)
        raise ErroKB("O navegador demorou para responder.")
    r = _c["resp"].pop(i)
    if "error" in r:
        raise ErroKB(r["error"].get("message", "erro do navegador"))
    return r.get("result", {})


def abrir(url=None):
    """Abre o navegador (se fechado). Com url, abre numa aba nova. Devolve as abas."""
    if not ativo():
        u32 = ctypes.windll.user32
        frente_antes = u32.GetForegroundWindow()
        fora = _fora()
        exe = _chrome()
        if not exe:
            raise ErroKB("Não achei o Google Chrome nem o Edge neste PC.")
        pid = _perfis_ler()["atual"]
        pasta = pasta_perfil(pid)
        os.makedirs(pasta, exist_ok=True)
        r1, w1 = os.pipe()   # nós -> Chrome
        r2, w2 = os.pipe()   # Chrome -> nós
        h_in, h_out = msvcrt.get_osfhandle(r1), msvcrt.get_osfhandle(w2)
        os.set_handle_inheritable(h_in, True)
        os.set_handle_inheritable(h_out, True)
        si = subprocess.STARTUPINFO()
        si.lpAttributeList = {"handle_list": [h_in, h_out]}   # só esses dois vão para o Chrome
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            _c["proc"] = subprocess.Popen(
                [exe, "--remote-debugging-pipe", f"--remote-debugging-io-pipes={h_in},{h_out}", f"--user-data-dir={pasta}",
                 "--no-first-run", "--no-default-browser-check", f"--window-size={fora['width']},{fora['height']}",
                 f"--window-position={fora['left']},{fora['top']}",
                 # a janela da Kani fica escondida atrás/fora da tela e precisa continuar desenhando (visão ao vivo)
                 "--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding",
                 "--disable-background-timer-throttling",
                 # sem a marca de "navegador de teste automático" (navigator.webdriver): é o navegador do Pailer, com os
                 # logins dele; com a marca, o login do Google/Microsoft recusa ("este navegador pode não ser seguro")
                 "--disable-blink-features=AutomationControlled", url or "https://www.google.com/"],
                startupinfo=si, close_fds=False)
        os.close(r1)
        os.close(w2)
        _c.update(w=w1, r=r2, vivo=True, resp={}, sessoes={}, perfil=pid)
        _k.update(aba=None, fazendo=[])
        if _ao_criar not in _ouvintes:
            _ouvintes.append(_ao_criar)
        threading.Thread(target=_ler, daemon=True).start()
        _cmd("Browser.getVersion", timeout=20)
        _cmd("Target.setDiscoverTargets", {"discover": True})
        os.makedirs(SAIDA, exist_ok=True)
        _cmd("Browser.setDownloadBehavior", {"behavior": "allow", "downloadPath": SAIDA, "eventsEnabled": True})
        time.sleep(0.6)
        for t in abas():
            esconder(t["id"])
        if frente_antes:   # o Chrome pega o foco ao abrir: devolve para o Kanivete
            u32.SetForegroundWindow(frente_antes)
    elif url:
        nova(url)
    return abas()


def fechar_navegador():
    if ativo():
        try:
            _cmd("Browser.close", timeout=5)
        except ErroKB:
            pass
    return True


def abas():
    if not ativo():
        return []
    t = _cmd("Target.getTargets")["targetInfos"]
    return [{"id": x["targetId"], "titulo": x.get("title", ""), "url": x.get("url", ""), "kani": x["targetId"] == _k["aba"]}
            for x in t if x.get("type") == "page" and not x.get("url", "").startswith(("devtools://", "chrome-extension://"))]


def abas_usuario():
    return [t for t in abas() if not t["kani"]]


def _aba(aba=None):
    """aba pelo id (ou começo dele); sem aba = a aba da Kani (o agente trabalha nela, à vista no painel)."""
    if not ativo():
        abrir()   # quem pede uma aba com o navegador fechado (agente, Instagram, pesquisa) abre ele
    if not aba:
        return aba_kani()
    for t in abas():
        if t["id"].startswith(aba):
            return t["id"]
    raise ErroKB(f"Aba '{aba}' não encontrada.")


def _sessao(aba=None):
    tid = _aba(aba)
    if tid not in _c["sessoes"]:
        _c["sessoes"][tid] = _cmd("Target.attachToTarget", {"targetId": tid, "flatten": True})["sessionId"]
    return tid, _c["sessoes"][tid]


def _cdp(aba, metodo, params=None, timeout=30):
    _, s = _sessao(aba)
    return _cmd(metodo, params, s, timeout)


def nova(url):
    """aba nova na janela do Pailer (nunca na da Kani)"""
    if not ativo():
        abrir(_url(url))
        return {"id": abas_usuario()[0]["id"], "url": url}
    sua = abas_usuario()
    if sua:   # o Chrome abre a aba na última janela ativa: ativa uma aba dele antes
        _cmd("Target.activateTarget", {"targetId": sua[0]["id"]})
    return {"id": _cmd("Target.createTarget", {"url": _url(url), **({} if sua else {"newWindow": True, **_fora()})})["targetId"], "url": url}


def fechar(aba):
    _cmd("Target.closeTarget", {"targetId": _aba(aba)})
    return True


def js(codigo, aba=None):
    r = _cdp(aba, "Runtime.evaluate", {"expression": codigo, "returnByValue": True, "awaitPromise": True})
    if r.get("exceptionDetails"):
        raise ErroKB("Erro no script: " + str(r["exceptionDetails"].get("text", ""))[:200])
    return r.get("result", {}).get("value")


def _url(url):
    url = (url or "").strip()
    if not re.match(r"^[a-z]+://", url):
        url = "https://" + url if "." in url and " " not in url else "https://www.google.com/search?q=" + urllib.parse.quote(url)
    return url


def ir(url, aba=None):
    url = _url(url)
    if not aba:
        _nota("Abrindo " + (urllib.parse.urlparse(url).netloc or url))
    _cdp(aba, "Page.navigate", {"url": url})
    return url


def frente(aba=None):
    """mostra a aba no painel (ativa na janela dela; as janelas ficam escondidas, nada vem para a frente)"""
    _cmd("Target.activateTarget", {"targetId": _aba(aba)})
    return True


# ---------- janelas escondidas: fora de todos os monitores, fora da barra de tarefas e do Alt+Tab ----------
def _fora(w=1280, h=860):
    """posição (em pixels lógicos do Chrome) à esquerda de todos os monitores"""
    u32 = ctypes.windll.user32
    esc = (u32.GetDpiForSystem() or 96) / 96
    return {"left": int(u32.GetSystemMetrics(76) / esc) - w - 600, "top": int(u32.GetSystemMetrics(77) / esc), "width": w, "height": h}


def _janela(tid, bounds):
    w = _cmd("Browser.getWindowForTarget", {"targetId": tid})["windowId"]
    _cmd("Browser.setWindowBounds", {"windowId": w, "bounds": {"windowState": "normal"}})
    _cmd("Browser.setWindowBounds", {"windowId": w, "bounds": bounds})
    return w


def _sem_barra():
    """tira as janelas do Chrome da barra de tarefas e do Alt+Tab (janela de ferramenta)"""
    if not _c["proc"]:
        return
    u32, pid, hs = ctypes.windll.user32, _c["proc"].pid, []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cada(h, _):
        p = wintypes.DWORD()
        u32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and u32.IsWindowVisible(h):
            hs.append(h)
        return True
    u32.EnumWindows(cada, 0)
    vx = u32.GetSystemMetrics(76)
    for h in hs:
        ex = u32.GetWindowLongW(h, -20)
        if not (ex & 0x80 and not ex & 0x40000):
            u32.ShowWindow(h, 0)
            u32.SetWindowLongW(h, -20, (ex | 0x80) & ~0x40000)
            u32.ShowWindow(h, 4)   # SW_SHOWNOACTIVATE: continua desenhando, sem pegar o foco
        r = wintypes.RECT()
        u32.GetWindowRect(h, ctypes.byref(r))
        if u32.MonitorFromRect(ctypes.byref(r), 0):   # caiu num monitor: empurra para fora (sem mudar o tamanho)
            u32.SetWindowPos(h, 0, vx - (r.right - r.left) - 3000, r.top, 0, 0, 0x0001 | 0x0004 | 0x0010)


_docadas = set()   # janelas (windowId) encaixadas no KaniCode: o esconder não mexe


def esconder(tid):
    """leva a janela da aba para fora da tela (aba nova aberta por site, janelinha de login...)"""
    try:
        jw = _cmd("Browser.getWindowForTarget", {"targetId": tid})
        if jw["windowId"] in _docadas:   # encaixada no painel do KaniCode (navegador_painel.py): fica onde está
            return
        b = jw["bounds"]
        f = _fora(b.get("width", 1280), b.get("height", 860))
        if b.get("windowState") != "normal" or b.get("left", 0) > f["left"] + 200:
            _janela(tid, f)
        _sem_barra()
    except ErroKB:
        pass


def _ao_criar(m):
    """aba/janela nova (inclusive as que o site abre): esconde já"""
    if m.get("method") == "Target.targetCreated" and m["params"]["targetInfo"].get("type") == "page":
        tid = m["params"]["targetInfo"]["targetId"]
        threading.Thread(target=lambda: (time.sleep(0.25), esconder(tid)), daemon=True).start()


# ---------- a aba da Kani: o agente trabalha numa janela só dele; o painel mostra ao vivo (visao.py) ----------
_k = {"aba": None, "fazendo": [], "log": []}
_k_trava = threading.RLock()   # um trabalho por vez na aba da Kani


def aba_kani():
    """a aba da Kani (cria a janela dela, escondida, na 1ª vez)"""
    if _k["aba"] and any(t["id"] == _k["aba"] for t in abas()):
        return _k["aba"]
    _k["aba"] = None
    tid = _cmd("Target.createTarget", {"url": "about:blank", "newWindow": True, "background": True, **_fora()})["targetId"]
    _k["aba"] = tid
    esconder(tid)
    return tid


def _nota(texto):
    _k["log"].append({"t": time.time(), "o": texto})
    del _k["log"][:-30]


@contextmanager
def trabalho(texto):
    """um trabalho do agente na aba da Kani: aparece no painel ("Kani: pesquisando…") e no histórico"""
    with _k_trava:
        _nota(texto)
        _k["fazendo"].append(texto)
        try:
            yield aba_kani()
        finally:
            _k["fazendo"].remove(texto)


def _enviar(metodo, params, sessao):
    """manda sem esperar resposta (o confirmador de quadro roda na linha que lê o canal)"""
    with _trava:
        _c["id"] += 1
        os.write(_c["w"], json.dumps({"id": _c["id"], "method": metodo, "params": params, "sessionId": sessao}).encode() + b"\0")


def texto(aba=None, limite=60000):
    t = js("document.title + '\\n' + location.href + '\\n\\n' + (document.body ? document.body.innerText : '')", aba) or ""
    return t[:limite]


def foto(aba=None, caminho=None, inteira=False):
    """Print da aba (PNG). Sem caminho, devolve data URL (prévia no painel)."""
    p = {"format": "png"}
    if inteira:
        m = _cdp(aba, "Page.getLayoutMetrics")
        cs = m.get("cssContentSize") or m.get("contentSize")
        p.update(captureBeyondViewport=True,
                 clip={"x": 0, "y": 0, "width": cs["width"], "height": min(cs["height"], 12000), "scale": 1})
    dados = _cdp(aba, "Page.captureScreenshot", p, timeout=60)["data"]
    if not caminho:
        return "data:image/png;base64," + dados
    os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)
    with open(caminho, "wb") as f:
        f.write(base64.b64decode(dados))
    return caminho


_JS_IMAGENS = r"""
(() => {
  const out = new Map();
  const add = (u, w, h, alt) => {
    if (!u || u.startsWith('data:') || u.startsWith('blob:')) return;
    try { u = new URL(u, location.href).href; } catch (e) { return; }
    const v = out.get(u); if (!v || w * h > v.w * v.h) out.set(u, { url: u, w, h, alt: alt || '' });
  };
  const maior = srcset => (srcset || '').split(',').map(s => s.trim().split(/\s+/))
      .map(([u, d]) => [u, parseFloat(d) || 1]).sort((a, b) => b[1] - a[1])[0]?.[0];
  document.querySelectorAll('img').forEach(i => add(maior(i.srcset) || i.currentSrc || i.src, i.naturalWidth, i.naturalHeight, i.alt));
  document.querySelectorAll('meta[property="og:image"]').forEach(m => add(m.content, 9999, 9999, 'og:image'));
  return [...out.values()];
})()
"""


def _melhor_url(u):
    """troca a miniatura pela versão grande nos sites conhecidos (Pinterest)"""
    return re.sub(r"(i\.pinimg\.com)/\d+x(\d+)?/", r"\1/originals/", u)


def imagens(aba=None, minimo=250):
    out = []
    for i in js(_JS_IMAGENS, aba) or []:
        if i["w"] and i["h"] and min(i["w"], i["h"]) < minimo:
            continue
        i["grande"] = _melhor_url(i["url"])
        out.append(i)
    og = [i for i in out if i["alt"] == "og:image"]
    out = [i for i in out if i["alt"] != "og:image"] or og
    out.sort(key=lambda i: -(i["w"] * i["h"]))
    return out


def _ext(dados, tipo):
    """extensão pelo conteúdo (o site pode mandar WebP com nome .jpg)"""
    if dados[:4] == b"RIFF" and dados[8:12] == b"WEBP":
        return ".webp"
    if dados[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if dados[:2] == b"\xff\xd8":
        return ".jpg"
    if dados[:4] == b"GIF8":
        return ".gif"
    if dados[4:12] in (b"ftypavif", b"ftypavis"):
        return ".avif"
    return mimetypes.guess_extension((tipo or "").split(";")[0]) or ".jpg"


def _nome(url, dados, tipo, n):
    base = os.path.basename(urllib.parse.urlparse(url).path) or f"imagem_{n}"
    base = re.sub(r'[<>:"/\\|?*]+', "_", urllib.parse.unquote(base))[:80]
    raiz, ext = os.path.splitext(base)
    if ext.lower() in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"):
        base = raiz
    return base + _ext(dados, tipo)


def baixar(urls, pasta=None, referer=None):
    """Baixa as imagens (tenta a versão grande e cai na original). Devolve os arquivos salvos e as falhas."""
    pasta = pasta or SAIDA
    os.makedirs(pasta, exist_ok=True)
    feitos, falhas = [], []
    for n, u in enumerate(urls, 1):
        erro = ""
        for tentativa in dict.fromkeys([_melhor_url(u), u]):
            try:
                req = urllib.request.Request(tentativa, headers={"User-Agent": UA, **({"Referer": referer} if referer else {})})
                with urllib.request.urlopen(req, timeout=60) as r:
                    dados, tipo = r.read(), r.headers.get("Content-Type", "")
                if not tipo.startswith("image/"):
                    raise ErroKB("não é imagem")
                destino = os.path.join(pasta, _nome(tentativa, dados, tipo, n))
                b, e = os.path.splitext(destino)
                k = 2
                while os.path.exists(destino):
                    destino = f"{b}_{k}{e}"
                    k += 1
                with open(destino, "wb") as f:
                    f.write(dados)
                feitos.append(destino)
                break
            except Exception as e:
                erro = str(e)
        else:
            falhas.append({"url": u, "erro": erro})
    return {"pasta": pasta, "arquivos": feitos, "falhas": falhas}


# ---------- destinos: as pastas das demandas do Pandalab (plugin pandalab, vinculos.json) ----------
def destinos():
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pandalab", "vinculos.json")
    if not os.path.isfile(p):
        return []
    with open(p, encoding="utf-8") as f:
        v = json.load(f)
    out = []
    for k, c in v.items():
        if os.path.isdir(c):
            partes = c.split(os.sep)
            cli = partes[partes.index("01 - CLIENTES") + 1] if "01 - CLIENTES" in partes else ""
            out.append({"id": k, "pasta": c, "nome": os.path.basename(c), "cliente": cli})
    out.sort(key=lambda d: -os.path.getmtime(d["pasta"]))
    return out


def pasta_referencias(pasta_demanda):
    return os.path.join(pasta_demanda, "02 - ASSETS", "REFERENCIAS")


# ---------- etapa 2: Instagram, links de arquivo, pesquisa ----------
def _esperar(cond_js, aba=None, seg=20):
    fim = time.time() + seg
    while time.time() < fim:
        try:
            if js(cond_js, aba):
                return True
        except ErroKB:
            pass
        time.sleep(0.7)
    return False


def instagram(usuario, aba=None):
    """Abre o perfil (precisa do login no KaniBrowser) e lista os posts visíveis: link, imagem e texto alternativo."""
    usuario = usuario.strip().lstrip("@").split("/")[-1] or usuario
    if not aba:
        with trabalho(f"Lendo o Instagram de @{usuario}") as aba:
            return instagram(usuario, aba)
    ir(f"https://www.instagram.com/{usuario}/", aba)
    _esperar("document.querySelectorAll('a[href*=\"/p/\"],a[href*=\"/reel/\"]').length > 2", aba, 25)
    js("window.scrollBy(0, 1600)", aba)
    time.sleep(2)
    posts = js(r"""[...document.querySelectorAll('a[href*="/p/"],a[href*="/reel/"]')].map(a => {
        const i = a.querySelector('img'); return { link: a.href, imagem: i ? (i.currentSrc || i.src) : '', alt: i ? i.alt : '' };
      }).filter((p, k, t) => t.findIndex(x => x.link === p.link) === k)""", aba) or []
    cab = js("(document.querySelector('header') || {}).innerText || ''", aba) or ""
    logado = not js("!!document.querySelector('a[href*=\"/accounts/login\"]')", aba)
    return {"usuario": usuario, "cabecalho": cab[:600], "posts": posts, "logado": logado}


def _pasta_estavel(pasta, antes, seg=300):
    """espera aparecer arquivo novo e terminar de baixar (.crdownload some, tamanho para de mudar)"""
    fim, ultimo = time.time() + seg, None
    while time.time() < fim:
        novos = [f for f in os.listdir(pasta) if f not in antes]
        if novos and not any(f.endswith((".crdownload", ".tmp")) for f in novos):
            tam = sum(os.path.getsize(os.path.join(pasta, f)) for f in novos)
            if tam == ultimo:
                return [os.path.join(pasta, f) for f in novos]
            ultimo = tam
        time.sleep(1.5)
    raise ErroKB("O download não terminou a tempo.")


def baixar_link(url, pasta):
    """Link de arquivo para a pasta: Drive público pelo baixador do Kanivete; o resto (WeTransfer...) pelo navegador,
    clicando no botão de baixar da página."""
    os.makedirs(pasta, exist_ok=True)
    m = re.search(r"drive\.google\.com/.*?(?:/d/|id=|folders/)([\w-]{20,})", url)
    if m:
        try:
            from Functions import drive_publico
            antes = set(os.listdir(pasta))
            if drive_publico.baixar(m.group(1), pasta, url=url):
                return {"pasta": pasta, "arquivos": [os.path.join(pasta, f) for f in os.listdir(pasta) if f not in antes]}
        except Exception:
            pass   # privado: tenta pelo navegador (login do KaniBrowser)
    with trabalho("Baixando material de " + urllib.parse.urlparse(url).netloc) as aba:
        antes = set(os.listdir(pasta))
        _cmd("Browser.setDownloadBehavior", {"behavior": "allow", "downloadPath": pasta, "eventsEnabled": False})
        _cdp(aba, "Page.navigate", {"url": _url(url)})
        _esperar("document.readyState === 'complete'", aba, 30)
        time.sleep(3)
        js(r"""(() => {
            const alvo = [...document.querySelectorAll('button,a,[role=button]')].find(b =>
                /^(baixar|download|transferir|fazer download)/i.test((b.innerText || b.getAttribute('aria-label') || '').trim()));
            if (alvo) alvo.click(); return !!alvo; })()""", aba)
        try:
            return {"pasta": pasta, "arquivos": _pasta_estavel(pasta, antes)}
        finally:   # os downloads do Pailer voltam para a pasta de sempre
            _cmd("Browser.setDownloadBehavior", {"behavior": "allow", "downloadPath": SAIDA, "eventsEnabled": True})


def pesquisar(termo, n=3, limite=6000):
    """Busca (DuckDuckGo: o Google pede captcha a navegador controlado) e lê os primeiros resultados (texto cortado)."""
    with trabalho(f"Pesquisando “{termo}”") as aba:
        _cdp(aba, "Page.navigate", {"url": "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(termo)})
        _esperar("document.querySelectorAll('a.result__a').length > 0", aba, 20)
        links = js(r"""[...document.querySelectorAll('a.result__a')].map(a => {
            let u = a.href; try { const q = new URL(u).searchParams.get('uddg'); if (q) u = q; } catch (e) {}
            return { titulo: a.innerText, url: u }; }).filter(r => r.url.startsWith('http') && !r.url.includes('duckduckgo.com/y.js'))""", aba) or []
        out = []
        for r in links[:n]:
            try:
                _nota("Lendo " + urllib.parse.urlparse(r["url"]).netloc)
                ir(r["url"], aba)
                _esperar("document.readyState === 'complete'", aba, 20)
                r["texto"] = texto(aba, limite)
            except ErroKB as e:
                r["texto"] = f"(não abriu: {e})"
            out.append(r)
        return out


def ler_pagina(url, limite=6000):
    """Para a Kani: abre a página na aba dela, espera montar e lê o texto (só leitura)."""
    with trabalho("Lendo " + (urllib.parse.urlparse(_url(url)).netloc or url)) as aba:
        _cdp(aba, "Page.navigate", {"url": _url(url)})
        _esperar("document.readyState === 'complete'", aba, 25)
        time.sleep(2.5)   # sites em JS terminam de montar depois do load
        return texto(aba, limite)


# ---------- ChatGPT na conta do Pailer (aba da Kani): pergunta, espera terminar, traz o texto e as imagens ----------
_JS_GPT = r"""(() => {
  // layout de 2026-10: cada resposta é um bloco data-talvt-turn-state ("complete" = terminou); texto em
  // [data-markdown-text-style=assistant-message], imagem em [data-testid=generated-image-gallery]. O layout antigo
  // (article / data-message-author-role) fica de reserva.
  const login = !!document.querySelector('[data-testid="login-button"]');
  const parar = !!document.querySelector('[data-testid="stop-button"],button[aria-label*="Parar"],button[aria-label*="Stop"]');
  let turnos = [...document.querySelectorAll('[data-talvt-turn-state]')], novo = true;
  if (!turnos.length) { novo = false; turnos = [...document.querySelectorAll('[data-message-author-role="assistant"]')].map(e => e.closest('article') || e); }
  const ult = turnos[turnos.length - 1];
  if (!ult) return { ocupado: parar, login, n: 0, autor: '', texto: '', imgs: [] };
  const estado = novo ? ult.getAttribute('data-talvt-turn-state') : '';
  const md = ult.querySelector('[data-markdown-text-style="assistant-message"]') || ult.querySelector('[data-message-author-role="assistant"]');
  const imgs = [...ult.querySelectorAll('[data-testid="generated-image-gallery"] img, img')].filter(i => i.naturalWidth >= 256).map(i => i.currentSrc || i.src);
  return { ocupado: parar || (novo && estado !== 'complete'), login, n: turnos.length, estado, autor: 'assistant',
           texto: md ? md.innerText : '', imgs: [...new Set(imgs)] };
})()"""

_CAIXA = ("#prompt-textarea, [data-testid=\"prompt-textarea\"], div.ProseMirror[contenteditable=\"true\"], "
          "textarea[name=\"prompt-textarea\"], form [contenteditable=\"true\"], form textarea")
_JS_BLOB = r"""fetch(%s).then(r => r.blob()).then(b => new Promise(ok => { const f = new FileReader(); f.onload = () => ok(f.result); f.readAsDataURL(b); }))"""


_JS_GPT_DIAG = r"""(() => { const q = s => document.querySelectorAll(s).length;
  const r = [...document.querySelectorAll('[data-message-author-role]')];
  const u = r[r.length - 1];
  let cad = []; for (let e = u; e && cad.length < 8; e = e.parentElement) cad.push(e.tagName + (e.dataset.testid ? '[' + e.dataset.testid + ']' : '') + (e.className ? '.' + e.className.toString().split(' ')[0] : ''));
  return { article: q('article'), turn: q('[data-testid^="conversation-turn"]'), papel: r.length, ultimo: u ? u.getAttribute('data-message-author-role') : '',
           stop: q('[data-testid="stop-button"]'), cadeia: cad.join(' < ') }; })()"""


def diagnostico_chatgpt():
    return js(_JS_GPT_DIAG, aba_kani())


def chatgpt(pergunta, nova=True, pasta=None, timeout=300):
    """Pergunta ao ChatGPT (o login é o do KaniBrowser) na aba da Kani, à vista no painel. Espera a resposta terminar
    (texto parado e sem o botão de parar) e salva as imagens que ele criar. Devolve {texto, imagens, url}."""
    pergunta = (pergunta or "").strip()
    if not pergunta:
        raise ErroKB("Falta a pergunta.")
    with trabalho("Perguntando ao ChatGPT") as aba:
        url = _cmd("Target.getTargetInfo", {"targetId": aba})["targetInfo"].get("url", "")
        if nova or "chatgpt.com" not in url:
            _cdp(aba, "Page.navigate", {"url": "https://chatgpt.com/"})
            time.sleep(1.5)
        if not _esperar(f"!!document.querySelector('{_CAIXA}')", aba, 30):
            achou = js("[...document.querySelectorAll('textarea,[contenteditable]')].map(e => e.tagName + '#' + e.id + '.' + "
                       "e.className.toString().slice(0, 30)).join(' ; ') + ' | ' + location.href", aba)
            raise ErroKB(f"O ChatGPT não abriu (sem a caixa de mensagem): {achou}")
        e = js(_JS_GPT, aba)
        if e["login"]:
            raise ErroKB("Entre no ChatGPT pelo KaniBrowser primeiro (o login fica guardado).")
        n0 = e["n"]
        js(f"document.querySelector('{_CAIXA}').focus()", aba)
        _cdp(aba, "Input.insertText", {"text": pergunta})
        time.sleep(0.5)
        if not js("(() => { const b = document.querySelector('[data-testid=\"send-button\"]'); if (b && !b.disabled) { b.click(); return true; } return false; })()", aba):
            for t in ("rawKeyDown", "keyUp"):
                _cdp(aba, "Input.dispatchKeyEvent", {"type": t, "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13, **({"text": "\r"} if t == "rawKeyDown" else {})})
        fim, ult, parado, avisou, img_parada = time.time() + timeout, None, 0, False, 0
        _k["cancelar"] = False
        while time.time() < fim:
            time.sleep(2)
            if _k.get("cancelar"):
                raise ErroKB("Cancelado.")
            e = js(_JS_GPT, aba)
            if e["n"] <= n0 or e["autor"] != "assistant":
                continue
            if e["imgs"] and not avisou:
                _nota("ChatGPT: imagem pronta")
                avisou = True
            sinal = (e["texto"], tuple(e["imgs"]))
            parado = parado + 1 if (sinal == ult and not e["ocupado"]) else 0
            # imagem pronta e igual por ~8 s: entrega mesmo com o turno ainda "em andamento" (o ChatGPT às vezes
            # segue ocupado depois da imagem e a espera estourava o tempo com a imagem já na tela)
            img_parada = img_parada + 1 if (e["imgs"] and ult and tuple(e["imgs"]) == ult[1]) else 0
            ult = sinal
            if (parado >= 2 and (e["texto"].strip() or e["imgs"])) or img_parada >= 4:
                break
        else:
            raise ErroKB("O ChatGPT demorou demais para responder.")
        imagens = []
        if e["imgs"]:
            pasta = pasta or os.path.join(SAIDA, "chatgpt")
            os.makedirs(pasta, exist_ok=True)
            carimbo = time.strftime("%Y%m%d_%H%M%S")
            for k, src in enumerate(e["imgs"], 1):
                du = js(_JS_BLOB % json.dumps(src), aba) or ""
                if "," not in du:
                    continue
                dados = base64.b64decode(du.split(",", 1)[1])
                caminho = os.path.join(pasta, f"chatgpt_{carimbo}_{k}{_ext(dados, du[5:du.find(';')])}")
                with open(caminho, "wb") as f:
                    f.write(dados)
                imagens.append(caminho)
        texto = re.sub(r"^\s*ChatGPT (?:disse|said):\s*", "", e["texto"]).strip()
        url = _cmd("Target.getTargetInfo", {"targetId": aba})["targetInfo"].get("url", "")
        return {"texto": texto, "imagens": imagens, "url": url}


# ---------- o estado sobrevive a "recarregar o plugin": o navegador aberto e o canal continuam ----------
def _persistir(modulo, nomes, g):
    """guarda as variáveis de estado fora do módulo. Na 1ª vez, adota as de uma versão antiga ainda viva (sem isto,
    recarregar o plugin perdia o canal e deixava o Chrome órfão, com o perfil preso)"""
    E = sys.__dict__.setdefault("_kanivete_" + modulo, {})
    if not E:
        import gc
        for o in gc.get_objects():
            if type(o) is dict and o is not g and o.get("__name__") == modulo and all(n in o for n in nomes):
                if modulo != "kanibrowser" or o["_c"].get("vivo"):
                    E.update({n: o[n] for n in nomes})
                    break
    for n in nomes:
        g[n] = E.setdefault(n, g[n])


_persistir("kanibrowser", ("_c", "_trava", "_ouvintes", "_k", "_k_trava"), globals())
_ouvintes[:] = [f for f in _ouvintes if f.__name__ != "_ao_criar"] + ([_ao_criar] if _c.get("vivo") else [])
