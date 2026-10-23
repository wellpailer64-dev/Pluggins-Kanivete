"""Navegador dentro do KaniCode (botão 🌐 / Ctrl+B): as janelas do KaniBrowser (Chrome do Kanivete, logins guardados)
ficam numa MOLDURA nossa colada sobre a área à direita da conversa (dona = KaniCode; ver a classe Painel);
a barra do Chrome fica fora da região visível. Abas, endereço, favoritos e botões são HTML do KaniCode (ui/navegador.js).
Só a janela ativa fica no lugar; as outras ficam fora dos monitores (continuam desenhando: a aba da Kani precisa de print).
Fechar o painel devolve as janelas ao esconderijo do KaniBrowser. O KaniBrowser não mexe nas encaixadas:
`kanibrowser._docadas` (ids das janelas do Chrome) é respeitado no `esconder`.
Cuidados (2026-10-23): achar a janela do Chrome SEMPRE pelo pid do KaniBrowser (pela classe pegou o Chrome do Pailer);
janela FILHA não serve: o KaniCode é "system aware" e no monitor de 125% o Windows estica tudo (faixas pretas).
"""
RECARREGAVEL = True   # kanicode._quente: recarrega este módulo sem reiniciar o KaniCode
import ctypes, re, sys, threading, time, urllib.parse
from contextlib import contextmanager
from ctypes import wintypes

# cópia própria das DLLs: argtypes em ctypes.windll.user32 vale para o processo todo e quebrou o move() do pywebview
# (SetWindowPos com None no tamanho) — o chat não abria mais pela bolinha (2026-10-23)
u32 = ctypes.WinDLL("user32")
u32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
u32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
u32.CreateWindowExW.restype = wintypes.HWND
u32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
u32.SetParent.restype = wintypes.HWND
u32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
u32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
u32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
u32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
u32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
u32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]

WS_CHILD, WS_POPUP, WS_VISIBLE, WS_CLIPCHILDREN, WS_CLIPSIBLINGS = 0x40000000, 0x80000000, 0x10000000, 0x2000000, 0x4000000
WS_CAPTION, WS_THICKFRAME, WS_SYSMENU, WS_MINMAX = 0xC00000, 0x40000, 0x80000, 0x30000
SWP_NOZORDER, SWP_NOACTIVATE, SWP_FRAMECHANGED, SWP_SHOWWINDOW = 0x4, 0x10, 0x20, 0x40
LOCAL = re.compile(r"^(localhost|127\.\d+\.\d+\.\d+|0\.0\.0\.0|\[::1\]|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+)(:\d+)?(/.*)?$", re.I)


def url_de(texto):
    """o que foi digitado na barra → endereço; localhost/IP da rede viram http:// (sem isso o Chrome pesquisaria)"""
    t = (texto or "").strip()
    if not t:
        return "about:blank"
    if re.match(r"^[a-z][a-z0-9+.-]*:", t, re.I) and not re.match(r"^[a-z0-9.-]+:\d+", t, re.I):
        return t   # http:, https:, file:, about:, chrome:
    if LOCAL.match(t) or re.match(r"^:\d+", t):
        return "http://" + (("localhost" + t) if t.startswith(":") else t)
    if re.match(r"^[A-Za-z]:[\\/]", t):
        return "file:///" + t.replace("\\", "/")
    if "." in t and " " not in t:
        return "https://" + t
    return "https://www.google.com/search?q=" + urllib.parse.quote(t)


def soltar_do_kanivete(porta=9222):
    """o KANIVETE (modo agente) está com o KaniBrowser aberto: pede para ele fechar (kb.py chamar_kanivete)"""
    import importlib.util, os
    pasta = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kanibrowser")
    if "kb_cli" not in sys.modules:
        spec = importlib.util.spec_from_file_location("kb_cli", os.path.join(pasta, "kb.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        sys.modules["kb_cli"] = mod
    try:
        return sys.modules["kb_cli"].chamar_kanivete(porta, "fechar_navegador", {}, 30)
    except Exception:
        return False


def _chrome_barra(n=4):
    """começo da barra de favoritos do Chrome do Pailer (perfil mais usado; favoritos da conta e do aparelho)"""
    import json, os
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "User Data")
    try:
        with open(os.path.join(base, "Local State"), encoding="utf-8") as f:
            perfil = json.load(f)["profile"].get("last_used") or "Default"
    except (OSError, ValueError, KeyError):
        perfil = "Default"
    itens = []
    for arq in ("AccountBookmarks", "Bookmarks"):
        try:
            with open(os.path.join(base, perfil, arq), encoding="utf-8") as f:
                barra = json.load(f)["roots"]["bookmark_bar"]["children"]
        except (OSError, ValueError, KeyError):
            continue
        itens += [{"nome": b["name"], "url": b["url"]} for b in barra if b.get("type") == "url" and b.get("url", "").startswith("http")]
    return itens[:n]


def favoritos(op="listar", a=None):
    """barra de favoritos do painel = a mesma do KaniBrowser (favoritos.json, também no KANIVETE). 1ª vez: traz o
    começo da barra do Chrome do Pailer. Ícones vão como data: (a página do KaniCode não vê o servidor da visão)."""
    import base64, os
    fav = sys.modules["favoritos"]
    a = a or {}
    marca = os.path.join(fav.kb.RAIZ, "favoritos_chrome.ok")
    if not os.path.exists(marca):
        try:
            atuais = {f["url"] for f in fav._ler()}
            novos = [f for f in _chrome_barra() if f["url"] not in atuais]
            with fav._trava:
                fav._gravar(fav._ler() + [{"nome": re.split(r" [—–|•·] ", f["nome"])[0].strip()[:40] or fav.dominio(f["url"]), "url": f["url"]} for f in novos])
            open(marca, "w").close()
        except Exception:
            pass
    if op == "salvar":
        lista = fav.salvar(a["url"], a.get("nome"))
    elif op == "remover":
        lista = fav.remover(a["url"])
    elif op == "renomear":
        lista = fav.renomear(a["url"], a["nome"])
    elif op == "ordenar":
        lista = fav.ordenar(a["urls"])
    else:
        lista = fav.listar()
    for f in lista:
        f["ic"] = ""
        if f.get("icone"):
            try:
                with open(os.path.join(fav.ICONES, f["icone"] + ".png"), "rb") as g:
                    f["ic"] = "data:image/png;base64," + base64.b64encode(g.read()).decode()
            except OSError:
                pass
    return lista


@contextmanager
def _por_monitor():
    """chamadas de posição na escala real de cada monitor (o KaniCode é 'system aware': sem isso o Windows converte as
    coordenadas pela escala do monitor principal e o Chrome sai do lugar no monitor de 125%)"""
    antes = u32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    try:
        yield
    finally:
        u32.SetThreadDpiAwarenessContext(ctypes.c_void_p(antes))


WINEVENT = ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND, wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD)
u32.SetWinEventHook.restype = wintypes.HANDLE
u32.SetWinEventHook.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.HMODULE, WINEVENT, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD]
gdi = ctypes.WinDLL("gdi32")
gdi.CreateRectRgn.restype = wintypes.HRGN
u32.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HRGN, wintypes.BOOL]


# modos de aparelho (como o "modo dispositivo" do Chrome): largura da página em px CSS e o que o site recebe
APARELHOS = {
    "celular": {"w": 390, "mobile": True, "ua": "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) "
                                               "Chrome/141.0.0.0 Mobile Safari/537.36", "plataforma": "Android"},
    "tablet": {"w": 820, "mobile": True, "ua": "Mozilla/5.0 (Linux; Android 14; SM-X710) AppleWebKit/537.36 (KHTML, like Gecko) "
                                             "Chrome/141.0.0.0 Safari/537.36", "plataforma": "Android"},
    "computador": {"w": 1280, "mobile": False, "ua": None, "plataforma": "Windows"},
}


def faixa(largura_css):
    """em que faixa um site responsivo põe essa largura (pontos de quebra mais comuns: 768 e 1024)"""
    return "celular" if largura_css < 768 else "tablet" if largura_css < 1024 else "computador"


class Painel:
    """2026-10-23 (3ª forma). 1ª: filhas da janela do KaniCode → no monitor de 125% o Windows estica a janela 'system
    aware' e o Chrome não acompanha (faixas pretas). 2ª: janelas soltas com região (SetWindowRgn) → o Chrome desenha por
    DirectComposition e ignora a região (a barra dele cobria a nossa). Agora: uma MOLDURA nossa (janela solta 'per monitor',
    DONO = KaniCode: fica por cima dele, some/minimiza junto) sobre a área do HTML, em coordenadas reais de tela; as janelas
    do Chrome são FILHAS da moldura, subidas a altura da barra (a moldura corta). Um gancho de eventos do Windows acompanha
    mover/redimensionar/esconder o KaniCode."""

    def __init__(self, kb, hwnd_dono, na_ui):
        """kb = módulo kanibrowser (já carregado); hwnd_dono = janela do KaniCode; na_ui(fn) roda fn na thread dela"""
        self.kb, self.dono, self.na_ui = kb, hwnd_dono, na_ui
        self.janelas = {}     # windowId do Chrome → hwnd encaixado
        self.ativa = None     # windowId mostrado
        self.aba = None       # targetId mostrado
        self.ret = (0.0, 0.0, 0.0, 0.0, 0.0)   # x, y, w, h da área + largura da página (CSS × devicePixelRatio)
        self.topo = {}        # windowId → altura da barra do Chrome (px reais) a esconder
        self.borda = {}       # windowId → (esquerda, direita, baixo): borda da janela do Chrome em volta da página
        self.aberto = False
        self.mexido = 0.0     # última vez que o Pailer trocou de aba (a Kani não puxa a vista logo em seguida)
        self._gancho = None
        self.moldura = None
        self.modo = "auto"    # auto | computador | tablet | celular
        self.emulado = {}     # targetId → modo já aplicado na aba
        self.icones = {}      # endereço → ícone da página (link rel=icon ou /favicon.ico)
        self._trava = threading.RLock()
        if not hasattr(kb, "_docadas"):
            kb._docadas = set()
        if self._ao_evento not in kb._ouvintes:
            kb._ouvintes.append(self._ao_evento)

    # ---------- onde fica a área, em pixels reais de tela ----------
    def area(self, x, y, w, h, largura=0):
        """retângulo da área do navegador no HTML (CSS × devicePixelRatio) + largura da página na mesma unidade"""
        self.ret = (float(x), float(y), float(w), float(h), float(largura or 0))
        if self.aberto:
            self._posicionar()
        return True

    def _tela(self):
        """área em pixels reais de tela: origem e tamanho da área útil do KaniCode medidos por monitor"""
        x, y, w, h, larg = self.ret
        with _por_monitor():
            c = wintypes.RECT()
            u32.GetClientRect(self.dono, ctypes.byref(c))
            p = wintypes.POINT(0, 0)
            u32.ClientToScreen(self.dono, ctypes.byref(p))
        k = (c.right / larg) if larg > 0 else 1.0
        return int(round(p.x + x * k)), int(round(p.y + y * k)), max(1, int(round(w * k))), max(1, int(round(h * k)))

    def _posicionar(self):
        if not self.janelas:
            return
        visivel = self.aberto and u32.IsWindowVisible(self.dono) and not u32.IsIconic(self.dono)
        X, Y, W, H = self._tela()
        ap = APARELHOS.get(self.modo)
        if ap and ap["mobile"]:
            Wd = min(W, int(round(ap["w"] * self._dpr())))
            X, W = X + (W - Wd) // 2, Wd
        with _por_monitor():
            if self.moldura:
                if visivel:
                    u32.SetWindowPos(self.moldura, 0, X, Y, W, H, SWP_NOACTIVATE | SWP_NOZORDER | SWP_SHOWWINDOW)
                else:
                    u32.ShowWindow(self.moldura, 0)
            for wid, hw in list(self.janelas.items()):
                t = self.topo.get(wid, 0)
                e, d, b = self.borda.get(wid, (0, 0, 0))
                # a ativa no lugar (barra e bordas do Chrome ficam fora do corte); as outras fora da moldura, ainda desenhando
                u32.SetWindowPos(hw, 0, -e if wid == self.ativa else 30000, -t, W + e + d, H + t + b, SWP_NOACTIVATE | SWP_NOZORDER)

    def _dpr(self):
        """escala da página no monitor da janela ativa"""
        hw = self.janelas.get(self.ativa)
        with _por_monitor():
            return (u32.GetDpiForWindow(hw) if hw else u32.GetDpiForSystem()) / 96 or 1

    # ---------- modo de aparelho ----------
    def aparelho(self, modo):
        """auto (segue a largura do painel) | computador | tablet | celular: muda a janela e o que o site recebe"""
        if modo not in ("auto", *APARELHOS):
            modo = "auto"
        self.modo = modo
        self._posicionar()
        time.sleep(0.05)
        if self.aba:
            self._emular(self.aba, forcar=True)
            try:
                self.kb._cdp(self.aba, "Page.reload", {"ignoreCache": False})   # o site escolhe a versão ao carregar
            except Exception:
                pass
        return self.estado()

    def _emular(self, tid, forcar=False):
        """aplica o modo na aba (CDP Emulation): celular/tablet = viewport móvel + toque + navegador de celular;
        computador = versão desktop (em painel estreito, página de 1280 encolhida para caber); auto = sem truque"""
        if not forcar and self.emulado.get(tid) == self.modo and self.modo != "computador":
            return
        kb, ap = self.kb, APARELHOS.get(self.modo)
        try:
            if not ap:
                kb._cdp(tid, "Emulation.clearDeviceMetricsOverride")
                kb._cdp(tid, "Emulation.setTouchEmulationEnabled", {"enabled": False})
                kb._cdp(tid, "Emulation.setEmitTouchEventsForMouse", {"enabled": False})
                kb._cdp(tid, "Emulation.setUserAgentOverride", {"userAgent": self._ua_original()})
            else:
                if ap["mobile"]:
                    kb._cdp(tid, "Emulation.setDeviceMetricsOverride", {"width": 0, "height": 0, "deviceScaleFactor": 0, "mobile": True})
                else:
                    _, _, W, H = self._tela()
                    css = W / self._dpr()
                    if css < ap["w"]:
                        esc = css / ap["w"]
                        kb._cdp(tid, "Emulation.setDeviceMetricsOverride", {"width": ap["w"], "height": int(H / self._dpr() / esc),
                                                                            "deviceScaleFactor": 0, "mobile": False, "scale": esc})
                    else:
                        kb._cdp(tid, "Emulation.clearDeviceMetricsOverride")
                kb._cdp(tid, "Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 5} if ap["mobile"] else {"enabled": False})
                kb._cdp(tid, "Emulation.setEmitTouchEventsForMouse", {"enabled": ap["mobile"], "configuration": "mobile"})
                kb._cdp(tid, "Emulation.setUserAgentOverride", {"userAgent": ap["ua"] or self._ua_original(), "platform": ap["plataforma"],
                        "userAgentMetadata": {"platform": ap["plataforma"], "platformVersion": "14.0.0" if ap["mobile"] else "10.0.0",
                                              "architecture": "" if ap["mobile"] else "x86", "model": "Pixel 8" if self.modo == "celular" else "",
                                              "mobile": self.modo == "celular",
                                              "brands": [{"brand": "Google Chrome", "version": "141"}, {"brand": "Chromium", "version": "141"}]}})
            self.emulado[tid] = self.modo
        except Exception:
            pass

    def _ua_original(self):
        if not getattr(self, "_ua", None):
            try:
                self._ua = self.kb._cmd("Browser.getVersion")["userAgent"].replace("HeadlessChrome", "Chrome")
            except Exception:
                self._ua = self.kb.UA
        return self._ua

    def _criar_moldura(self):
        """moldura: janela solta, sem borda, na escala real do monitor (criada com a thread em modo 'per monitor'),
        dona = KaniCode; criada na thread da interface (é ela que atende as mensagens). Nasce já sobre o KaniCode
        (a escala dela acompanha o monitor ao mover: medido em 2026-10-23)"""
        if self.moldura and u32.IsWindow(self.moldura):
            return
        X, Y, W, H = self._tela()

        def criar():
            with _por_monitor():
                self.moldura = u32.CreateWindowExW(0x80, "STATIC", "KaniCode navegador",   # janela de ferramenta (fora da barra de tarefas)
                                                   WS_POPUP | WS_CLIPCHILDREN | 0x4, X, Y, W, H, self.dono, None, None, None)
        self.na_ui(criar)

    def _ligar_gancho(self):
        """acompanha a janela do KaniCode: mover/redimensionar, esconder (bolinha) e minimizar"""
        if self._gancho:
            return
        pid = wintypes.DWORD()
        u32.GetWindowThreadProcessId(self.dono, ctypes.byref(pid))

        def ev(_h, evento, hwnd, obj, _f, _t, _ms):
            if hwnd == self.dono and obj == 0 and self.aberto:
                try:
                    self._posicionar()
                    if evento == 0x800B:   # mudou de lugar/tamanho (ampliar): confere de novo quando assentar
                        if getattr(self, "_assentar", None):
                            self._assentar.cancel()
                        self._assentar = threading.Timer(0.5, self._reajustar)
                        self._assentar.daemon = True
                        self._assentar.start()
                except Exception:
                    pass
        self._cb = WINEVENT(ev)   # guardado: o Windows chama enquanto o gancho existir

        def ligar():
            # 0x8002 mostrar … 0x800B mudou de lugar; 0x16/0x17 minimizar começou/terminou
            self._gancho = (u32.SetWinEventHook(0x8002, 0x800B, None, self._cb, pid.value, 0, 0),
                            u32.SetWinEventHook(0x16, 0x17, None, self._cb, pid.value, 0, 0))
        self.na_ui(ligar)

    def _reajustar(self):
        """a barra do Chrome mudou de altura (aviso amarelo, barra de favoritos) ou a borda dele mudou (janela ampliada:
        a página ficava deslocada para a esquerda, com faixa preta, porque só a ALTURA disparava o reposicionamento,
        2026-10-23): mede de novo e recoloca"""
        hw = self.janelas.get(self.ativa)
        if not (self.aberto and hw):
            return
        b0 = self.borda.get(self.ativa)
        t = self._medir_topo(hw, mover=False)
        mudou = self.borda.get(self.ativa) != b0
        if t is not None and t != self.topo.get(self.ativa):
            self.topo[self.ativa] = t
            mudou = True
        if mudou:
            self._posicionar()

    # ---------- abrir / fechar ----------
    def abrir(self):
        kb = self.kb
        with self._trava:
            if not kb.ativo():
                try:
                    kb.abrir()
                except kb.ErroKB as e:
                    if "fechou" not in str(e):
                        raise
                    soltar_do_kanivete()   # o mesmo perfil (logins) só abre num lugar: o KANIVETE fecha o dele
                    time.sleep(1.5)
                    kb.abrir()
            if not kb.abas_usuario():
                kb.nova("https://www.google.com/")
            self._criar_moldura()
            self._ligar_gancho()
            self.aberto = True
            for t in kb.abas():
                self._encaixar_aba(t["id"])
            if not self.aba or not any(t["id"] == self.aba for t in kb.abas()):
                sua = kb.abas_usuario()
                self.aba = (sua or kb.abas())[0]["id"]
            self.mostrar(self.aba, pailer=False)
        return self.estado()

    def fechar(self):
        """devolve as janelas ao esconderijo do KaniBrowser (fora da tela)"""
        kb = self.kb
        with self._trava:
            self.aberto = False
            for wid, hw in list(self.janelas.items()):
                self._soltar(hw)
                kb._docadas.discard(wid)
            self.janelas.clear()
            self.topo.clear()
            self.borda.clear()
            if self.moldura:
                u32.ShowWindow(self.moldura, 0)
            if kb.ativo():
                for t in kb.abas():
                    kb.esconder(t["id"])
        return True

    # ---------- encaixe de uma janela do Chrome ----------
    def _hwnd_da_janela(self, wid, tid):
        """acha o HWND da janela do Chrome: marca um tamanho único nela e procura, SÓ entre as janelas do KaniBrowser
        (2026-10-23: procurar pela classe pegou uma janela do Chrome do Pailer)"""
        kb = self.kb
        pid = kb._c["proc"].pid
        marca_w, marca_h = 1000 + (wid % 300), 700 + (wid % 97)
        f = kb._fora(marca_w, marca_h)
        kb._cmd("Browser.setWindowBounds", {"windowId": wid, "bounds": {"windowState": "normal"}})
        kb._cmd("Browser.setWindowBounds", {"windowId": wid, "bounds": f})
        for _ in range(20):
            achadas = []

            @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            def cada(h, _):
                p = wintypes.DWORD()
                u32.GetWindowThreadProcessId(h, ctypes.byref(p))
                if p.value == pid and u32.IsWindowVisible(h):
                    b = ctypes.create_unicode_buffer(64)
                    u32.GetClassNameW(h, b, 64)
                    r = wintypes.RECT()
                    u32.GetWindowRect(h, ctypes.byref(r))
                    esc = u32.GetDpiForWindow(h) / 96
                    if b.value == "Chrome_WidgetWin_1" and abs((r.right - r.left) - marca_w * esc) <= 3 and abs((r.bottom - r.top) - marca_h * esc) <= 3:
                        achadas.append(h)
                return True
            with _por_monitor():
                u32.EnumWindows(cada, 0)
            if len(achadas) == 1:
                return achadas[0]
            time.sleep(0.1)
        return None

    def _encaixar_aba(self, tid):
        kb = self.kb
        try:
            wid = kb._cmd("Browser.getWindowForTarget", {"targetId": tid})["windowId"]
        except kb.ErroKB:
            return None
        if wid in self.janelas:
            return wid
        hw = self._hwnd_da_janela(wid, tid)
        if not hw:
            return None
        kb._docadas.add(wid)
        moldura = self.moldura

        def prender():
            with _por_monitor():
                st = u32.GetWindowLongPtrW(hw, -16)
                # filha sem moldura; WS_MAXIMIZE faz o Chrome se desenhar sem a borda de janela solta
                u32.SetWindowLongPtrW(hw, -16, (st & ~(WS_CAPTION | WS_THICKFRAME | WS_SYSMENU | WS_MINMAX | WS_POPUP)) | WS_CHILD | WS_VISIBLE | 0x1000000)
                ex = u32.GetWindowLongPtrW(hw, -20)
                u32.SetWindowLongPtrW(hw, -20, ex & ~0x80)   # tira o "janela de ferramenta" que o KaniBrowser pôs
                u32.SetParent(hw, moldura)
                u32.SetWindowPos(hw, 0, 30000, 0, 100, 100, SWP_NOACTIVATE | SWP_NOZORDER | SWP_FRAMECHANGED)
        self.na_ui(prender)
        self.janelas[wid] = hw
        self.topo[wid] = self._medir_topo(hw)
        return wid

    def _medir_topo(self, hw, mover=True):
        """altura da barra do Chrome = onde começa a área da página (filha Chrome_RenderWidgetHostHWND)"""
        if mover:
            X, Y, W, H = self._tela()
            with _por_monitor():
                u32.SetWindowPos(hw, 0, 30000, 0, max(400, W), max(300, H) + 200, SWP_NOACTIVATE | SWP_NOZORDER)
            time.sleep(0.2)
        achou = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def cada(c, _):
            b = ctypes.create_unicode_buffer(64)
            u32.GetClassNameW(c, b, 64)
            if b.value == "Chrome_RenderWidgetHostHWND" and u32.IsWindowVisible(c):
                achou.append(c)
            return True
        r0, r1 = wintypes.RECT(), wintypes.RECT()
        topo = None
        with _por_monitor():
            u32.EnumChildWindows(hw, cada, 0)
            u32.GetWindowRect(hw, ctypes.byref(r0))
            for c in achou:
                u32.GetWindowRect(c, ctypes.byref(r1))
                if r1.right - r1.left > (r0.right - r0.left) * 0.6:   # a página (não a dos devtools/bolhas)
                    if topo is None or r1.top - r0.top < topo:
                        topo = r1.top - r0.top
                        borda = (max(0, r1.left - r0.left), max(0, r0.right - r1.right), max(0, r0.bottom - r1.bottom))
                        wid = next((k for k, v in self.janelas.items() if v == hw), None)
                        if wid is not None and 0 <= borda[0] < 40 and 0 <= borda[1] < 40 and 0 <= borda[2] < 40:
                            self.borda[wid] = borda
        if topo is None and not mover:
            return None
        if topo is None:   # sem a filha: pela página (barra = altura de fora - de dentro)
            try:
                v = self.kb.js("[outerHeight - innerHeight, devicePixelRatio]", self.aba)
                topo = int(v[0] * v[1])
            except Exception:
                topo = int(80 * u32.GetDpiForWindow(hw) / 96)
        return max(0, int(topo))

    def _soltar(self, hw):
        if not u32.IsWindow(hw):
            return

        def soltar():
            with _por_monitor():
                u32.ShowWindow(hw, 0)
                st = u32.GetWindowLongPtrW(hw, -16)
                u32.SetWindowLongPtrW(hw, -16, (st & ~(WS_CHILD | 0x1000000)) | WS_POPUP | WS_CAPTION | WS_THICKFRAME | WS_SYSMENU | WS_MINMAX)
                u32.SetParent(hw, None)
                u32.SetWindowPos(hw, 0, -32000, 0, 1280, 860, SWP_NOACTIVATE | SWP_NOZORDER | SWP_FRAMECHANGED)
                u32.ShowWindow(hw, 4)
        self.na_ui(soltar)

    # ---------- abas ----------
    def mostrar(self, tid, pailer=True):
        """mostra a aba na caixa (traz a janela dela para o lugar e ativa a aba nela)"""
        kb = self.kb
        with self._trava:
            for t in kb.abas():
                if t["id"].startswith(tid):
                    tid = t["id"]
                    break
            wid = self._encaixar_aba(tid)
            if wid is None:
                return self.estado()
            kb._cmd("Target.activateTarget", {"targetId": tid})
            self.aba, self.ativa = tid, wid
            if pailer:
                self.mexido = time.time()
            self._posicionar()
            if self.modo != "auto" or tid in self.emulado:
                self._emular(tid)
        return self.estado()

    def nova(self, url=None):
        kb = self.kb
        with self._trava:
            if self.aba:
                kb._cmd("Target.activateTarget", {"targetId": self.aba})
            tid = kb._cmd("Target.createTarget", {"url": url_de(url) if url else "https://www.google.com/"})["targetId"]
            time.sleep(0.2)
            return self.mostrar(tid)

    def fechar_aba(self, tid):
        kb = self.kb
        with self._trava:
            kb._cmd("Target.closeTarget", {"targetId": tid})
            time.sleep(0.25)
            vivas = kb.abas()
            if tid == self.aba:
                sua = [t for t in vivas if not t["kani"]] or vivas
                if not sua:
                    self.nova()
                else:
                    self.mostrar(sua[-1]["id"])
            return self.estado()

    def ir(self, texto):
        url = url_de(texto)
        if not self.aba:
            return self.nova(url)
        self.kb._cdp(self.aba, "Page.navigate", {"url": url})
        self.mexido = time.time()
        return self.estado()

    def acao(self, o):
        """voltar / avancar / recarregar / parar na aba mostrada"""
        if not self.aba:
            return self.estado()
        kb = self.kb
        if o in ("voltar", "avancar"):
            h = kb._cdp(self.aba, "Page.getNavigationHistory")
            i = h["currentIndex"] + (-1 if o == "voltar" else 1)
            if 0 <= i < len(h["entries"]):
                kb._cdp(self.aba, "Page.navigateToHistoryEntry", {"entryId": h["entries"][i]["id"]})
        elif o == "recarregar":
            kb._cdp(self.aba, "Page.reload", {"ignoreCache": False})
        elif o == "parar":
            kb._cdp(self.aba, "Page.stopLoading")
        return self.estado()

    def foco(self):
        """devolve o teclado à página (depois de digitar na barra do KaniCode)"""
        hw = self.janelas.get(self.ativa)
        if hw:
            self.na_ui(lambda: (u32.SetForegroundWindow(self.moldura), u32.SetFocus(hw)))
        return True

    def print_aba(self, pasta):
        """print (PNG) da aba mostrada → caminho, para anexar na conversa"""
        import base64, os
        if not self.aba:
            return None
        dados = self.kb._cdp(self.aba, "Page.captureScreenshot", {"format": "png"}, timeout=20)["data"]
        os.makedirs(pasta, exist_ok=True)
        cam = os.path.join(pasta, time.strftime("pagina_%Y%m%d_%H%M%S.png"))
        with open(cam, "wb") as f:
            f.write(base64.b64decode(dados))
        return cam

    # ---------- estado para o HTML ----------
    def estado(self):
        kb = self.kb
        if not kb.ativo():
            return {"aberto": False, "abas": [], "fazendo": []}
        abas = kb.abas()
        fazendo = list(kb._k.get("fazendo") or [])
        log = kb._k.get("log") or []
        # trabalhando = num trabalho agora ou num há < 8 s (entre um comando do kb.py e o próximo o brilho não pisca)
        trab = bool(fazendo) or bool(log and time.time() - log[-1]["t"] < 8)
        # a Kani está trabalhando e o Pailer não mexeu há 2 s: a vista vai para a aba dela (ele vê ao vivo)
        if self.aberto and trab and kb._k.get("aba") and self.aba != kb._k["aba"] and time.time() - self.mexido > 2:
            threading.Thread(target=self.mostrar, args=(kb._k["aba"], False), daemon=True).start()
        if self.aberto:
            self._reajustar()
        if not hasattr(self, "icones"):   # painel vivo de antes da recarga a quente (o __init__ não roda de novo)
            self.icones = {}
        ab = next((t for t in abas if t["id"] == self.aba), None)
        carregando = self._pagina(ab) if self.aberto else False
        for t in abas:
            t["icone"] = self.icones.get(t["url"], "")
        _, _, W, H = self._tela() if self.janelas else (0, 0, 0, 0)
        ap = APARELHOS.get(self.modo)
        css_w = round(min(W / self._dpr(), ap["w"]) if ap and ap["mobile"] else (ap["w"] if ap and W / self._dpr() < ap["w"] else W / self._dpr())) if W else 0
        return {"modo": self.modo, "faixa": faixa(css_w) if css_w else "", "tam": [css_w, round(H / self._dpr()) if H else 0],
                "aberto": self.aberto, "aba": self.aba, "carregando": carregando, "url": ab["url"] if ab else "", "titulo": ab["titulo"] if ab else "",
                "abas": abas, "fazendo": fazendo, "log": log[-1:],
                "trabalhando": trab and self.aba == kb._k.get("aba")}   # brilho verde-limão em volta da página

    def _pagina(self, ab):
        """a aba mostrada ainda carrega? e o ícone dela, tirado da própria página (o serviço do Google devolvia um globo
        genérico para localhost e sites pequenos). Uma consulta curta por segundo; o ícone fica guardado por endereço."""
        if not ab or not ab["url"].startswith(("http:", "https:", "file:")):
            return False
        try:
            r = self.kb._cdp(self.aba, "Runtime.evaluate", {"returnByValue": True, "expression":
                             "[document.readyState, ([...document.querySelectorAll('link[rel~=icon], link[rel=apple-touch-icon]')]"
                             ".map(l => l.href).find(Boolean) || (location.protocol.startsWith('http') ? location.origin + '/favicon.ico' : ''))]"},
                             timeout=0.8)["result"]["value"]
        except Exception:
            return True   # no meio da troca de página a consulta não responde: está carregando
        if r[1] and ab["url"] not in self.icones:
            if len(self.icones) > 300:
                self.icones.clear()
            self.icones[ab["url"]] = r[1]
        return r[0] != "complete"

    # ---------- eventos do Chrome ----------
    def _ao_evento(self, m):
        """janela nova (site abriu popup de login, Ctrl+N) com o painel aberto: encaixa e mostra"""
        if not self.aberto or m.get("method") != "Target.targetCreated":
            return
        info = m["params"]["targetInfo"]
        if info.get("type") != "page" or info.get("url", "").startswith("devtools://"):
            return
        tid = info["targetId"]

        def depois():
            time.sleep(0.45)   # depois do esconder do KaniBrowser (0,25 s)
            try:
                wid = self.kb._cmd("Browser.getWindowForTarget", {"targetId": tid})["windowId"]
            except Exception:
                return
            if tid == self.kb._k.get("aba"):
                self._encaixar_aba(tid)   # aba da Kani: encaixa, a vista vai para ela pelo estado()
            elif wid not in self.janelas or info.get("openerId"):
                self.mostrar(tid, pailer=False)
        threading.Thread(target=depois, daemon=True).start()
