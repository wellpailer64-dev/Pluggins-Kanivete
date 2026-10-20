"""Visão ao vivo das abas do KaniBrowser DENTRO do KANIVETE (nenhuma janela do Chrome aparece: ficam fora da tela).

Imagem: cada aba à vista no painel vira um MJPEG (Page.startScreencast) servido em 127.0.0.1, porta aleatória, caminho com
token secreto, SÓ imagem (nenhum comando entra por ali). Mouse e teclado do painel voltam pelo canal privado
(KPLUG.chamar → entrada()). O que o Chrome desenha fora da página (lista de opções, avisos do site, escolher arquivo)
é refeito no painel: um script na página guarda o cursor e a lista aberta (lidos no fim de cada entrada(); evento de
binding exigiria Runtime.enable, que inunda o canal) e os avisos/arquivo vêm pelos eventos do Page. Tamanho da área =
Emulation.setDeviceMetricsOverride (a janela escondida fica 1280×860). A transmissão só roda enquanto o painel olha.
"""
import base64, http.server, json, os, secrets, socketserver, threading, time

import kanibrowser as kb

TOKEN = secrets.token_urlsafe(18)
_telas = {}          # id da aba -> Tela
_por_sessao = {}     # sessionId -> Tela
_srv = {"porta": None}
_baixados = []       # downloads do navegador (para o aviso no painel)

_JS_PAGINA = r"""
(() => { if (window.__kb) return; window.__kb = 1; window.__kbCur = 'default';
  const ed = el => el.closest && el.closest('input:not([type=button]):not([type=submit]):not([type=checkbox]):not([type=radio]),textarea,[contenteditable=""],[contenteditable=true]');
  addEventListener('mousemove', e => {
    const el = e.target; if (!el || el.nodeType !== 1) return;
    let c = getComputedStyle(el).cursor;
    if (c === 'auto') c = el.closest('a[href],button,[role=button],label,summary,select') ? 'pointer' : ed(el) ? 'text' : 'default';
    window.__kbCur = c;
  }, { capture: true, passive: true });
  addEventListener('mousedown', e => {
    const s = e.target.closest && e.target.closest('select');
    if (!s || s.multiple || s.size > 1 || e.button || s.disabled) return;
    e.preventDefault(); window.__kbSel = s;
    const r = s.getBoundingClientRect();
    window.__kbSelPend = { x: r.left / innerWidth, y: r.bottom / innerHeight, w: r.width / innerWidth, i: s.selectedIndex,
      o: [...s.options].map(o => [o.text, o.disabled, o.parentNode.tagName === 'OPTGROUP' ? o.parentNode.label : '']) };
  }, true);
})()
"""


class Tela:
    def __init__(self, tid):
        self.tid, self.sessao, self.jpg, self.n, self.meta = tid, None, None, 0, {}
        self.cond = threading.Condition()
        self.vendo, self.ligado, self.tam = 0, False, None
        self.cursor, self.select, self.dialogo, self.arquivo, self.carregando = "default", None, None, None, False


def _tela(tid):
    t = _telas.get(tid)
    if not t:
        t = _telas[tid] = Tela(tid)
    return t


def _preparar(t):
    """sessão da aba + script da página + avisos (uma vez por sessão)"""
    _, s = kb._sessao(t.tid)
    if t.sessao == s:
        return s
    kb._cmd("Page.enable", None, s)
    kb._cmd("Page.addScriptToEvaluateOnNewDocument", {"source": _JS_PAGINA}, s)
    kb._cmd("Page.setInterceptFileChooserDialog", {"enabled": True}, s)
    try:
        kb._cmd("Runtime.evaluate", {"expression": _JS_PAGINA}, s, timeout=5)
    except kb.ErroKB:
        pass
    t.sessao = s   # só depois de tudo pronto (se algo falhar, tenta de novo na próxima)
    _por_sessao[s] = t
    if t.tam:
        _tamanho(t)
    return s


def _tamanho(t):
    """a página "acha" que a tela tem o tamanho da área do painel (a janela escondida pode ser menor: o Chrome
    encolhe janelas maiores que o monitor, a simulação não)"""
    w, h, dpr = t.tam
    kb._cmd("Emulation.setDeviceMetricsOverride", {"width": w, "height": h, "deviceScaleFactor": dpr, "mobile": False,
                                                   "screenWidth": w, "screenHeight": h}, t.sessao)


def _ligar(t):
    s = _preparar(t)
    if t.ligado:   # novo tamanho: recomeça a transmissão
        try:
            kb._cmd("Page.stopScreencast", None, s, timeout=5)
        except kb.ErroKB:
            pass
    w, h, dpr = t.tam or (1280, 860, 1)
    kb._cmd("Page.startScreencast", {"format": "jpeg", "quality": 74, "maxWidth": int(w * dpr), "maxHeight": int(h * dpr)}, s)
    t.ligado = True


def _desligar(t):
    if t.ligado and t.sessao and kb.ativo():
        try:
            kb._cmd("Page.stopScreencast", None, t.sessao, timeout=5)
        except kb.ErroKB:
            pass
    t.ligado = False


def _evento(m):
    met = m["method"]
    if met.startswith("Browser.download"):
        p = m["params"]
        if met == "Browser.downloadWillBegin":
            _baixados.append({"id": p["guid"], "nome": p.get("suggestedFilename", ""), "estado": "baixando", "t": time.time()})
        elif met == "Browser.downloadProgress" and p.get("state") in ("completed", "canceled"):
            for d in _baixados:
                if d["id"] == p["guid"]:
                    d.update(estado="pronto" if p["state"] == "completed" else "cancelado", t=time.time())
        del _baixados[:-10]
        return
    if met == "Target.targetDestroyed":
        t = _telas.pop(m["params"]["targetId"], None)
        if t:
            _por_sessao.pop(t.sessao, None)
            with t.cond:
                t.cond.notify_all()
        return
    t = _por_sessao.get(m.get("sessionId"))
    if not t:
        return
    p = m.get("params", {})
    if met == "Page.screencastFrame":
        with t.cond:
            t.jpg, t.meta, t.n = base64.b64decode(p["data"]), p.get("metadata", {}), t.n + 1
            t.cond.notify_all()
        try:
            kb._enviar("Page.screencastFrameAck", {"sessionId": p["sessionId"]}, t.sessao)
        except OSError:
            pass
    elif met == "Page.javascriptDialogOpening":
        t.dialogo = {"tipo": p.get("type"), "texto": p.get("message", ""), "padrao": p.get("defaultPrompt", "")}
    elif met == "Page.javascriptDialogClosed":
        t.dialogo = None
    elif met == "Page.fileChooserOpened":
        t.arquivo = {"no": p.get("backendNodeId"), "varios": p.get("mode") == "selectMultiple"}
    elif met == "Page.frameStartedLoading":
        t.carregando = True
    elif met == "Page.frameStoppedLoading":
        t.carregando = False


class _MJPEG(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        partes = self.path.split("?")[0].strip("/").split("/")
        if len(partes) == 3 and partes[0] == TOKEN and partes[1] == "i":   # ícone de favorito
            import favoritos
            arq = os.path.join(favoritos.ICONES, os.path.basename(partes[2]))
            if not os.path.isfile(arq):
                self.send_error(404)
                return
            with open(arq, "rb") as f:
                dados = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Cache-Control", "max-age=86400")
            self.end_headers()
            self.wfile.write(dados)
            return
        if len(partes) != 3 or partes[0] != TOKEN or partes[1] != "v" or not kb.ativo():
            self.send_error(404)
            return
        tid = partes[2].removesuffix(".mjpg")
        if not any(a["id"] == tid for a in kb.abas()):
            self.send_error(404)
            return
        t = _tela(tid)
        t.vendo += 1
        try:
            if not t.ligado:
                _ligar(t)
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=kbq")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            n = -1
            while kb.ativo() and _telas.get(tid) is t:
                with t.cond:
                    t.cond.wait_for(lambda: t.n != n or _telas.get(tid) is not t, timeout=4)
                if t.jpg is None:
                    continue
                n, jpg = t.n, t.jpg   # sem quadro novo em 4 s: manda o mesmo (descobre se o painel fechou)
                self.wfile.write(b"--kbq\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(jpg) + jpg + b"\r\n")
                self.wfile.flush()
        except (OSError, kb.ErroKB):
            pass
        finally:
            t.vendo -= 1
            if t.vendo <= 0:
                _desligar(t)

    def log_message(self, *a):
        pass


class _Servidor(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


def base():
    """endereço das transmissões (o servidor sobe na 1ª vez)"""
    if not _srv["porta"]:
        s = _Servidor(("127.0.0.1", 0), _MJPEG)
        _srv["porta"] = s.server_address[1]
        threading.Thread(target=s.serve_forever, daemon=True).start()
    if _evento not in kb._ouvintes:
        kb._ouvintes.append(_evento)
    return f"http://127.0.0.1:{_srv['porta']}/{TOKEN}/v/"


def ajustar(aba, w, h, dpr=1.0):
    """a janela escondida da aba fica do tamanho da área do painel (imagem nítida, 1 para 1)"""
    w, h = max(400, int(w)), max(300, int(h))
    t = _tela(aba)
    if t.tam and abs(t.tam[0] - w) < 4 and abs(t.tam[1] - h) < 4 and t.tam[2] == dpr:
        return True
    t.tam = (w, h, dpr)
    if t.sessao:
        _tamanho(t)
    else:
        _preparar(t)
    if t.ligado:   # novo tamanho de quadro
        _ligar(t)
    return True


_BOTOES = {0: "left", 1: "middle", 2: "right"}
_MASCARA = {"left": 1, "right": 2, "middle": 4}


def entrada(aba, eventos):
    """mouse e teclado do painel, em ordem. x, y = fração (0..1) da imagem. Devolve cursor e lista de opções aberta."""
    t = _tela(aba)
    s = _preparar(t)
    W, H = t.meta.get("deviceWidth") or 1280, t.meta.get("deviceHeight") or 860
    for e in eventos:
        tipo = e.get("t")
        mods = e.get("m", 0)
        if tipo in ("move", "down", "up", "wheel"):
            p = {"x": e["x"] * W, "y": e["y"] * H, "modifiers": mods}
            if tipo == "wheel":
                kb._cmd("Input.dispatchMouseEvent", {"type": "mouseWheel", **p, "deltaX": e.get("dx", 0), "deltaY": e.get("dy", 0)}, s)
                continue
            b = _BOTOES.get(e.get("b", 0), "none")
            p["buttons"] = e.get("bs", 0)
            if tipo == "move":
                kb._cmd("Input.dispatchMouseEvent", {"type": "mouseMoved", **p, "button": "left" if p["buttons"] & 1 else "none"}, s)
            else:
                kb._cmd("Input.dispatchMouseEvent", {"type": "mousePressed" if tipo == "down" else "mouseReleased", **p,
                                                     "button": b, "clickCount": e.get("c", 1)}, s)
        elif tipo in ("kd", "ku"):
            k = {"key": e["key"], "code": e.get("code", ""), "windowsVirtualKeyCode": e.get("vk", 0),
                 "nativeVirtualKeyCode": e.get("vk", 0), "modifiers": mods, "autoRepeat": bool(e.get("rep"))}
            if tipo == "ku":
                kb._cmd("Input.dispatchKeyEvent", {"type": "keyUp", **k}, s)
            elif e.get("txt") and not mods & 2:
                kb._cmd("Input.dispatchKeyEvent", {"type": "keyDown", **k, "text": e["txt"], "unmodifiedText": e["txt"]}, s)
            else:
                kb._cmd("Input.dispatchKeyEvent", {"type": "rawKeyDown", **k}, s)
        elif tipo == "txt":
            kb._cmd("Input.insertText", {"text": e["txt"]}, s)
    try:   # cursor da página e a lista de opções que o clique abriu
        c, sel = kb._cmd("Runtime.evaluate", {"expression": "(() => { const r = [window.__kbCur || 'default', window.__kbSelPend || null];"
                                                             " window.__kbSelPend = null; return r; })()", "returnByValue": True},
                         s, timeout=3)["result"].get("value") or ("default", None)
    except (kb.ErroKB, ValueError, TypeError):
        c, sel = t.cursor, None
    t.cursor = c
    return {"cursor": c, "select": sel} if sel else {"cursor": c}


def escolher(aba, indice):
    """a opção escolhida na lista refeita pelo painel vai para o <select> da página"""
    return kb.js(f"""(() => {{ const s = window.__kbSel; if (!s) return false; s.selectedIndex = {int(indice)};
        s.dispatchEvent(new Event('input', {{ bubbles: true }})); s.dispatchEvent(new Event('change', {{ bubbles: true }}));
        return true; }})()""", aba)


def dialogo(aba, aceitar=True, texto=None):
    t = _tela(aba)
    p = {"accept": bool(aceitar)}
    if texto is not None:
        p["promptText"] = texto
    kb._cmd("Page.handleJavaScriptDialog", p, _preparar(t))
    t.dialogo = None
    return True


def arquivo(aba, caminhos):
    """resposta ao "escolher arquivo" do site (o painel abre o seletor do Kanivete)"""
    t = _tela(aba)
    a, t.arquivo = t.arquivo, None
    if a and caminhos:
        kb._cmd("DOM.setFileInputFiles", {"files": list(caminhos), "backendNodeId": a["no"]}, _preparar(t))
    return True


def navegar(aba, acao):
    s = _preparar(_tela(aba))
    if acao == "recarregar":
        kb._cmd("Page.reload", None, s)
    elif acao == "parar":
        kb._cmd("Page.stopLoading", None, s)
    else:
        h = kb._cmd("Page.getNavigationHistory", None, s)
        i = h["currentIndex"] + (-1 if acao == "voltar" else 1)
        if 0 <= i < len(h["entries"]):
            kb._cmd("Page.navigateToHistoryEntry", {"entryId": h["entries"][i]["id"]}, s)
    return True


def ponto(aba, x, y):
    """o que há embaixo do botão direito: link, imagem, texto selecionado"""
    return kb.js(f"""(() => {{ const el = document.elementFromPoint({float(x)} * innerWidth, {float(y)} * innerHeight);
        const a = el && el.closest('a[href]'), im = el && (el.closest('img') || (el.querySelector && el.querySelector('img')));
        return {{ link: a ? a.href : '', img: im ? (im.currentSrc || im.src) : '', sel: String(getSelection()) }}; }})()""", aba)


def estado(abas_vistas=()):
    """para o painel (~2×/s): abas, e de cada aba à vista o endereço, título, cursor, avisos e carregando"""
    if not kb.ativo():
        return {"aberto": False, "base": base()}
    if time.time() - _srv.get("varrida", 0) > 1.5:   # janelinha que escapou para a tela (popup nativo, aviso do Chrome)
        _srv["varrida"] = time.time()
        kb._sem_barra()
    infos = {x["targetId"]: x for x in kb._cmd("Target.getTargets")["targetInfos"] if x.get("type") == "page"}
    vistas = {}
    for tid in abas_vistas:
        if tid not in infos:
            continue
        t = _tela(tid)
        vistas[tid] = {"url": infos[tid].get("url", ""), "titulo": infos[tid].get("title", ""), "carregando": t.carregando,
                       "dialogo": t.dialogo, "arquivo": t.arquivo}
    kani = kb._k["aba"] if kb._k["aba"] in infos else None
    return {"aberto": True, "base": base(), "kani": kani, "fazendo": kb._k["fazendo"][-1] if kb._k["fazendo"] else "",
            "log": kb._k["log"][-8:], "vistas": vistas,
            "abas": [{"id": i, "titulo": x.get("title", ""), "url": x.get("url", ""), "abriu": x.get("openerId", "")}
                     for i, x in infos.items() if i != kani and not x.get("url", "").startswith(("devtools://", "chrome-extension://"))],
            "baixados": [d for d in _baixados if time.time() - d["t"] < 12]}


# o estado (servidor, transmissões) sobrevive a "recarregar o plugin"; o ouvinte de eventos passa a ser o desta versão
kb._persistir("visao", ("TOKEN", "_telas", "_por_sessao", "_srv", "_baixados"), globals())
kb._ouvintes[:] = [f for f in kb._ouvintes if f.__name__ != "_evento"] + ([_evento] if _srv.get("porta") else [])
