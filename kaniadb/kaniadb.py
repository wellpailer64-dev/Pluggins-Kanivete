"""KaniADB — o celular Android do Pailer no KaniCode, pelo cabo USB com a Depuração USB ligada.

Etapa 1 (2026-10-29): achar o adb e o aparelho, transmitir a tela numa página local, tocar, arrastar, digitar,
teclas e volume. O SOM ainda NÃO sai: o adb sozinho não captura áudio (ver `audio`). Nada é instalado; nada escuta
fora deste PC (servidor só em 127.0.0.1), e nenhuma porta é publicada.

  py -3.13 kaniadb.py estado [--json]
  py -3.13 kaniadb.py dispositivos
  py -3.13 kaniadb.py tamanho
  py -3.13 kaniadb.py tela [--salvar tela.png] [--largura 720]
  py -3.13 kaniadb.py tocar 540 1200
  py -3.13 kaniadb.py deslizar 540 1800 540 600 [--ms 300]
  py -3.13 kaniadb.py texto "boa noite"       (acentos são removidos: o input text do Android não aceita)
  py -3.13 kaniadb.py tecla voltar|home|recentes|ligar|volume+|volume-|KEYCODE_...
  py -3.13 kaniadb.py audio
  py -3.13 kaniadb.py servir [--porta 47615] [--largura 720]    (página do celular; Ctrl+C para parar)
"""
import argparse, base64, http.server, io, json, os, re, shutil, socketserver, subprocess, sys, threading, time
import unicodedata, urllib.parse

PORTA = 47615                 # só 127.0.0.1: a página do celular não sai deste PC
AQUI = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(AQUI, "ui")

# o SDK do Android: build-tools 34 + platform-tools em D:/dev/android (README do repositório)
CANDIDATOS_ADB = (
    r"D:\dev\android\platform-tools\adb.exe",
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk", "platform-tools", "adb.exe"),
    r"C:\Android\platform-tools\adb.exe",
)

_ADB = {"caminho": None}


class ErroADB(Exception):
    pass


# ---------- o programa adb ----------
def caminho_adb():
    """O adb deste PC (nunca baixa nem instala nada)."""
    if _ADB["caminho"] and os.path.isfile(_ADB["caminho"]):
        return _ADB["caminho"]
    for c in (os.environ.get("KANIADB_ADB"), os.environ.get("ADB"), *CANDIDATOS_ADB):
        if c and os.path.isfile(c):
            _ADB["caminho"] = c
            return c
    achado = shutil.which("adb")
    if achado:
        _ADB["caminho"] = achado
        return achado
    raise ErroADB("Não achei o adb neste PC. Ele vem com o Android SDK (platform-tools); aponte com a variável "
                  "KANIADB_ADB. Nada será baixado sem o ok do Pailer.")


def _run(*args, serial=None, timeout=30, binario=False):
    """Roda o adb e devolve a saída (bytes se binario=True). Erro do aparelho vira ErroADB."""
    cmd = [caminho_adb()] + (["-s", serial] if serial else []) + [str(a) for a in args]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except FileNotFoundError:
        raise ErroADB("O adb sumiu do caminho " + cmd[0] + ".")
    except subprocess.TimeoutExpired:
        raise ErroADB("O celular demorou demais para responder (adb " + " ".join(cmd[1:]) + ").")
    if r.returncode != 0:
        erro = (r.stderr or r.stdout or b"").decode("utf-8", "replace").strip()
        raise ErroADB(erro[:400] or "adb saiu com código " + str(r.returncode))
    return r.stdout if binario else r.stdout.decode("utf-8", "replace")


# ---------- aparelhos ----------
def dispositivos():
    """[{serial, estado, modelo, transporte}] da saída de `adb devices -l`."""
    saida = _run("devices", "-l", timeout=20)
    lista = []
    for linha in saida.splitlines():
        linha = linha.strip()
        if not linha or linha.startswith(("List of devices", "*")):
            continue
        partes = linha.split()
        meta = {}
        for p in partes[2:]:
            if ":" in p:
                k, v = p.split(":", 1)
                meta[k] = v
        lista.append({"serial": partes[0],
                      "estado": partes[1] if len(partes) > 1 else "desconhecido",
                      "modelo": meta.get("model", "").replace("_", " "),
                      "transporte": meta.get("transport_id", "")})
    return lista


def serial_padrao():
    devs = dispositivos()
    for d in devs:
        if d["estado"] == "device":
            return d["serial"]
    if any(d["estado"] == "unauthorized" for d in devs):
        raise ErroADB("Depuração USB não autorizada: aceite o aviso no celular e marque \"sempre permitir\".")
    if any(d["estado"] == "offline" for d in devs):
        raise ErroADB("O celular aparece offline no adb: reconecte o cabo USB.")
    raise ErroADB("Nenhum celular conectado. Ligue o cabo USB e a Depuração USB nas opções de desenvolvedor.")


def _serial(serial=None):
    return serial or serial_padrao()


def _prop(nome, serial=None):
    return _run("shell", "getprop", nome, serial=_serial(serial), timeout=20).strip()


def tamanho(serial=None):
    """Tamanho usado na tela (Override quando o celular tem resolução trocada)."""
    txt = _run("shell", "wm", "size", serial=_serial(serial), timeout=20)
    for padrao in (r"Override size:\s*(\d+)x(\d+)", r"Physical size:\s*(\d+)x(\d+)"):
        m = re.search(padrao, txt)
        if m:
            return {"largura": int(m.group(1)), "altura": int(m.group(2))}
    raise ErroADB("Não consegui ler o tamanho da tela: " + txt.strip()[:120])


def estado():
    """O retrato completo: adb, aparelhos, tela, áudio e o motivo quando não está pronto."""
    r = {"adb": None, "pronto": False, "erro": "", "dispositivos": [], "aparelho": {}, "audio": {}}
    try:
        r["adb"] = caminho_adb()
    except ErroADB as e:
        r["erro"] = str(e)
        return r
    try:
        r["dispositivos"] = dispositivos()
    except ErroADB as e:
        r["erro"] = str(e)
        return r
    prontos = [d for d in r["dispositivos"] if d["estado"] == "device"]
    if not prontos:
        if any(d["estado"] == "unauthorized" for d in r["dispositivos"]):
            r["erro"] = "Depuração USB não autorizada: aceite o aviso no celular e marque \"sempre permitir\"."
        elif any(d["estado"] == "offline" for d in r["dispositivos"]):
            r["erro"] = "O celular aparece offline no adb: reconecte o cabo USB."
        else:
            r["erro"] = ("Nenhum celular conectado. Ligue o cabo USB e a Depuração USB nas opções de desenvolvedor "
                         "do Android.")
        return r
    d = prontos[0]
    r["pronto"] = True
    try:
        r["aparelho"] = {"serial": d["serial"], "modelo": d["modelo"], "tela": tamanho(d["serial"]),
                         "android": _prop("ro.build.version.release", d["serial"]),
                         "sdk": _prop("ro.build.version.sdk", d["serial"])}
    except ErroADB as e:
        r["aparelho"] = {"serial": d["serial"], "modelo": d["modelo"], "erro": str(e)}
    r["audio"] = audio_estado(d["serial"])
    return r


# ---------- tela ----------
def _reduzir(png, largura):
    """Encolhe o quadro quando o PIL está disponível (sem ele, entrega o PNG original)."""
    try:
        from PIL import Image
    except ImportError:
        return png
    try:
        img = Image.open(io.BytesIO(png))
        if img.width <= largura:
            return png
        alt = max(1, int(img.height * largura / img.width))
        img = img.convert("RGB").resize((largura, alt), Image.LANCZOS)
        b = io.BytesIO()
        img.save(b, "PNG")
        return b.getvalue()
    except Exception:
        return png


def quadro(serial=None, largura=None):
    """Um quadro da tela em PNG (bytes)."""
    dados = _run("exec-out", "screencap", "-p", serial=_serial(serial), timeout=40, binario=True)
    if not dados.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ErroADB("O celular devolveu uma imagem inválida (a tela pode estar bloqueada).")
    return _reduzir(dados, largura) if largura else dados


# ---------- controle ----------
def tocar(x, y, serial=None):
    px, py = max(0, int(x)), max(0, int(y))
    _run("shell", "input", "tap", str(px), str(py), serial=_serial(serial))
    return {"x": px, "y": py}


def deslizar(x1, y1, x2, y2, ms=300, serial=None):
    a = [max(0, int(v)) for v in (x1, y1, x2, y2)]
    dur = max(50, int(ms))
    _run("shell", "input", "swipe", *(str(v) for v in a), str(dur), serial=_serial(serial), timeout=60)
    return {"de": a[:2], "ate": a[2:], "ms": dur}


def _sem_acento(t):
    return "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))


def _aspas(t):
    """Texto entre aspas simples para o shell do celular (apóstrofo vira '\\'')."""
    return "'" + t.replace("'", "'\\''") + "'"


def texto(t, serial=None):
    original = t or ""
    limpo = _sem_acento(original).replace("\n", " ").strip()
    if not limpo:
        raise ErroADB("Nada para digitar.")
    _run("shell", "input", "text", _aspas(limpo), serial=_serial(serial), timeout=60)
    aviso = ""
    if limpo != original.strip():
        aviso = "Acentos removidos: o `input text` do Android não os aceita (digitado: " + limpo + ")."
    return {"digitado": limpo, "aviso": aviso}


TECLAS = {
    "voltar": "KEYCODE_BACK", "home": "KEYCODE_HOME", "recentes": "KEYCODE_APP_SWITCH",
    "enter": "KEYCODE_ENTER", "espaco": "KEYCODE_SPACE", "apagar": "KEYCODE_DEL",
    "ligar": "KEYCODE_POWER", "tela": "KEYCODE_POWER", "menu": "KEYCODE_MENU",
    "volume+": "KEYCODE_VOLUME_UP", "volume-": "KEYCODE_VOLUME_DOWN", "mudo": "KEYCODE_VOLUME_MUTE",
    "play": "KEYCODE_MEDIA_PLAY_PAUSE", "camera": "KEYCODE_CAMERA", "captura": "KEYCODE_SYSRQ",
    "despertar": "KEYCODE_WAKEUP", "suspender": "KEYCODE_SLEEP",
}


def tecla(nome, serial=None):
    chave = (nome or "").strip()
    codigo = TECLAS.get(chave.lower())
    if not codigo:
        bruto = chave.upper()
        if re.fullmatch(r"(KEYCODE_)?[A-Z0-9_]+", bruto):
            codigo = bruto if bruto.startswith("KEYCODE_") else "KEYCODE_" + bruto
    if not codigo:
        raise ErroADB("Tecla desconhecida: " + chave + ". Use " + ", ".join(sorted(TECLAS)) + " ou KEYCODE_...")
    _run("shell", "input", "keyevent", codigo, serial=_serial(serial))
    return codigo


# ---------- áudio (etapa seguinte) ----------
def audio_estado(serial=None):
    """Estado honesto do som: o adb sozinho NÃO captura áudio do celular."""
    sdk = 0
    try:
        sdk = int(_prop("ro.build.version.sdk", serial) or 0)
    except (ErroADB, ValueError):
        pass
    auxiliar = os.path.join(AQUI, "auxiliar", "audio.jar")
    if os.path.isfile(auxiliar):
        return {"pronto": False, "sdk": sdk, "android_ok": sdk >= 30, "auxiliar": auxiliar,
                "motivo": "O auxiliar está na pasta, mas a captura de som ainda não foi ligada nesta etapa."}
    return {"pronto": False, "sdk": sdk, "android_ok": sdk >= 30,
            "motivo": ("O adb sozinho não captura o som do celular: é preciso um auxiliar rodando pelo shell "
                       "(Android 11+, SDK " + str(sdk or "?") + ") ou o app do KaniCode no celular. Nada foi "
                       "instalado; a tela e o controle já funcionam.")}


# ---------- página local (127.0.0.1) ----------
class _Captura:
    """Um único capturador para a página: pedidos seguidos aproveitam o mesmo quadro (a captura é cara)."""

    def __init__(self, largura=None):
        self.largura = largura
        self.trava = threading.Lock()
        self.png = None
        self.carimbo = 0.0

    def pegar(self, idade=0.12):
        with self.trava:
            if self.png and time.time() - self.carimbo < idade:
                return self.png
            png = quadro(largura=self.largura)
            self.png, self.carimbo = png, time.time()
            return png


class _Transmissao:
    """Vídeo contínuo compartilhado; encerra a captura quando a última página sai."""

    def __init__(self, largura=720):
        self.largura = largura
        self.video = None
        self.clientes = 0
        self.trava = threading.Lock()
        self.encerrar = None

    def entrar(self):
        with self.trava:
            self.clientes += 1
            if self.encerrar:
                self.encerrar.cancel()
                self.encerrar = None

    def sair(self):
        with self.trava:
            self.clientes = max(0, self.clientes - 1)
            if not self.clientes:
                self.encerrar = threading.Timer(2, self._ociosa)
                self.encerrar.daemon = True
                self.encerrar.start()

    def _ociosa(self):
        with self.trava:
            if not self.clientes and self.video:
                self.video.fechar()
                self.video = None

    def _obter(self):
        with self.trava:
            if not self.video:
                from video_continuo import VideoContinuo
                serial = serial_padrao()
                tam = tamanho(serial)
                largura = max(2, min(int(self.largura or 720), tam['largura'])) // 2 * 2
                altura = max(2, round(tam['altura'] * largura / tam['largura']) // 2 * 2)
                ffmpeg = (os.environ.get('KANIADB_FFMPEG') or shutil.which('ffmpeg') or
                          (r'C:\Program Files\FFmpeg\ffmpeg.exe' if os.path.isfile(r'C:\Program Files\FFmpeg\ffmpeg.exe') else None))
                if not ffmpeg:
                    raise ErroADB('FFmpeg não encontrado. Aponte KANIADB_FFMPEG para o executável existente.')
                self.video = VideoContinuo(caminho_adb(), serial, largura=largura, altura=altura, ffmpeg=ffmpeg)
                self.serial, self.resolucao = serial, tam
            return self.video

    def alvo(self):
        self._obter()
        return self.serial, dict(self.resolucao)

    def comando(self, acao, **dados):
        try:
            return self._obter().controlar(acao, self.resolucao, **dados)
        except (OSError, RuntimeError, ValueError) as e:
            raise ErroADB('Controle direto: ' + str(e)) from e

    def iniciar(self):
        try:
            self._obter().iniciar()
        except (OSError, RuntimeError, ValueError) as e:
            raise ErroADB('Vídeo contínuo: ' + str(e)) from e

    def espiar(self):
        try:
            return self._obter().ultimo()
        except (OSError, RuntimeError, ValueError) as e:
            raise ErroADB('Vídeo contínuo: ' + str(e)) from e

    def pegar(self):
        video = self._obter()
        try:
            return video.pegar(timeout=10)
        except (OSError, RuntimeError, TimeoutError, ValueError) as e:
            raise ErroADB('Vídeo contínuo: ' + str(e)) from e

    def estado(self):
        with self.trava:
            return self.video.estado() if self.video else {'pronto': False, 'erro': '', 'quadros': 0, 'idade_ms': None}

    def fechar(self):
        with self.trava:
            if self.encerrar:
                self.encerrar.cancel()
            if self.video:
                self.video.fechar()
                self.video = None


def _ponto(par, tam):
    """Coordenada 0..1 vira pixel do celular; número maior que 1 é pixel mesmo."""
    try:
        x, y = float(par[0]), float(par[1])
    except (TypeError, ValueError, IndexError):
        raise ErroADB("Coordenada inválida: " + repr(par))
    if 0 <= x <= 1 and 0 <= y <= 1:
        return int(min(x, 0.999) * tam["largura"]), int(min(y, 0.999) * tam["altura"])
    return int(x), int(y)


_TIPOS = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
          ".js": "application/javascript; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png"}

LIMITE_CORPO = 16 * 1024   # nenhum POST precisa de mais que isso para tocar/digitar


class _Servidor(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class _Casa(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    captura = None
    video = None

    def log_message(self, *a):
        pass

    # ---- quem pode falar com a página: só ela mesma, no loopback e na porta certa ----
    def _porta_real(self):
        """A porta em que este servidor está de fato (protege o Host contra DNS rebinding)."""
        try:
            return int(self.server.server_address[1])
        except (AttributeError, IndexError, TypeError, ValueError):
            return PORTA

    def _hosts_locais(self):
        porta = str(self._porta_real())
        return {"127.0.0.1:" + porta, "localhost:" + porta, "[::1]:" + porta}

    def _host_ok(self):
        host = (self.headers.get("Host") or "").strip().lower()
        return host in self._hosts_locais()

    def _origem_ok(self):
        origem = (self.headers.get("Origin") or "").strip().lower()
        if not origem:
            return True
        return origem in {"http://" + h for h in self._hosts_locais()}

    def _site_ok(self):
        """Sec-Fetch-Site: mesma origem (ou pedido digitado) pode; cross-site/same-site não."""
        site = (self.headers.get("Sec-Fetch-Site") or "").strip().lower()
        return not site or site in ("same-origin", "none")

    def _filtro_get(self):
        """False (já respondeu o erro) quando o pedido não vem desta página."""
        if not self._host_ok():
            self._json(403, {"erro": "Host não é o loopback deste servidor."})
            return False
        if not self._site_ok():
            self._json(403, {"erro": "Pedido de outra origem recusado."})
            return False
        return True

    def _filtro_post(self):
        """Host, Origin, Sec-Fetch-Site, Content-Type e Content-Length — antes de qualquer adb."""
        if not self._filtro_get():
            return False
        if not self._origem_ok():
            self._json(403, {"erro": "Origin externo recusado."})
            return False
        tipo = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if tipo != "application/json":
            self._json(415, {"erro": "envie Content-Type: application/json"})
            return False
        bruto = (self.headers.get("Content-Length") or "").strip()
        if not bruto.isdigit():
            self._json(411, {"erro": "Content-Length obrigatório e numérico"})
            return False
        n = int(bruto)
        if n > LIMITE_CORPO:
            self._json(413, {"erro": "corpo maior que " + str(LIMITE_CORPO) + " bytes"})
            return False
        return True

    def _json(self, codigo, obj):
        dados = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(dados)

    def _arquivo(self, nome):
        caminho = os.path.join(UI, os.path.basename(nome))
        if not os.path.isfile(caminho):
            return self._json(404, {"erro": "arquivo não encontrado: " + nome})
        with open(caminho, "rb") as f:
            dados = f.read()
        self.send_response(200)
        self.send_header("Content-Type", _TIPOS.get(os.path.splitext(caminho)[1].lower(), "application/octet-stream"))
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(dados)

    def _fluxo(self):
        """H264 contínuo do celular, convertido para JPEG sem fila de quadros antigos."""
        if not self.video:
            raise ErroADB('Transmissão não iniciada.')
        self.video.entrar()
        enviou = False
        try:
            self.video.iniciar()
            imagem = self.captura.pegar(idade=0) if self.captura else quadro()
            tipo = b'image/png'   # prévia imediata enquanto o Android prepara o primeiro vídeo
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=quadro")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            enviou = True
            while True:
                inicio = time.monotonic()
                self.wfile.write(b"--quadro\r\nContent-Type: " + tipo + b"\r\nContent-Length: "
                                 + str(len(imagem)).encode() + b"\r\n\r\n" + imagem + b"\r\n")
                self.wfile.flush()
                time.sleep(max(0, 1 / 30 - (time.monotonic() - inicio)))
                jpeg = self.video.espiar()
                if jpeg:
                    imagem, tipo = jpeg, b'image/jpeg'
        except (BrokenPipeError, ConnectionResetError, OSError):
            return
        except ErroADB:
            if not enviou:
                raise
            return
        finally:
            self.video.sair()

    def do_GET(self):
        if not self._filtro_get():
            return
        rota = urllib.parse.urlparse(self.path).path
        try:
            if rota in ("/", "/ui/telefone.html"):
                return self._arquivo("telefone.html")
            if rota.startswith("/ui/"):
                return self._arquivo(rota[len("/ui/"):])
            if rota == "/estado":
                dados = estado()
                if self.video:
                    dados['video'] = self.video.estado()
                return self._json(200, dados)
            if rota == "/audio":
                return self._json(200, audio_estado())
            if rota == "/quadro":
                png = self.captura.pegar() if self.captura else quadro()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(png)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "close")
                self.end_headers()
                return self.wfile.write(png)
            if rota == "/fluxo":
                return self._fluxo()
            return self._json(404, {"erro": "não existe: " + rota})
        except ErroADB as e:
            return self._json(409, {"erro": str(e)})

    def do_POST(self):
        if not self._filtro_post():
            return
        rota = urllib.parse.urlparse(self.path).path
        try:
            n = int(self.headers.get("Content-Length") or 0)
            dados = json.loads(self.rfile.read(n).decode("utf-8") or "{}") if n else {}
            if rota == "/tocar":
                serial, tam = self._alvo()
                x, y = _ponto((dados.get("x"), dados.get("y")), tam)
                direto = self.video.comando('tocar', x=x, y=y) if self.video else None
                if direto is not None:
                    return self._json(200, direto)
                return self._json(200, tocar(x, y, serial=serial))
            if rota == "/deslizar":
                serial, tam = self._alvo()
                x1, y1 = _ponto(dados.get("de") or (0, 0), tam)
                x2, y2 = _ponto(dados.get("ate") or (0, 0), tam)
                direto = self.video.comando('deslizar', x1=x1, y1=y1, x2=x2, y2=y2, ms=dados.get('ms') or 300) if self.video else None
                if direto is not None:
                    return self._json(200, direto)
                return self._json(200, deslizar(x1, y1, x2, y2, dados.get("ms") or 300, serial=serial))
            if rota == '/ponteiro':
                _, tam = self._alvo()
                x, y = _ponto((dados.get('x'), dados.get('y')), tam)
                direto = self.video.comando('ponteiro', x=x, y=y, tipo=dados.get('tipo')) if self.video else None
                if direto is None:
                    raise ErroADB('Controle direto do ponteiro indisponível.')
                return self._json(200, direto)
            if rota == "/texto":
                serial, _ = self._alvo()
                return self._json(200, texto(dados.get("texto") or "", serial=serial))
            if rota == "/tecla":
                serial, _ = self._alvo()
                nome = str(dados.get('tecla') or '')
                codigo = TECLAS.get(nome.lower()) or (nome.upper() if nome.upper().startswith('KEYCODE_') else 'KEYCODE_' + nome.upper())
                direto = self.video.comando('tecla', codigo=codigo) if self.video else None
                if direto is not None:
                    return self._json(200, direto)
                return self._json(200, {"tecla": tecla(dados.get("tecla") or "", serial=serial)})
            return self._json(404, {"erro": "não existe: " + rota})
        except ErroADB as e:
            return self._json(409, {"erro": str(e)})
        except ValueError:
            return self._json(400, {"erro": "corpo JSON inválido"})

    def _alvo(self):
        if self.video:
            return self.video.alvo()
        serial = serial_padrao()
        return serial, tamanho(serial)


def servir(porta=PORTA, largura=720):
    caminho_adb()   # falha cedo, com a explicação certa
    _Casa.captura = _Captura(largura)
    _Casa.video = _Transmissao(largura)
    srv = _Servidor(("127.0.0.1", porta), _Casa)
    print(f"KaniADB: celular em http://127.0.0.1:{porta}/   (Ctrl+C para parar)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        _Casa.video.fechar()
        srv.server_close()
    return True


# ---------- linha de comando ----------
def _mostrar_estado(e):
    if e["erro"]:
        print("celular: " + e["erro"])
    else:
        a = e["aparelho"]
        tam = a.get("tela") or {}
        print(f"celular: {a.get('modelo') or a.get('serial')} · Android {a.get('android', '?')} (SDK {a.get('sdk', '?')})"
              f" · tela {tam.get('largura', '?')}x{tam.get('altura', '?')}")
    if e.get("audio"):
        print("som: " + e["audio"].get("motivo", "pendente"))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kaniadb.py", description="KaniADB: o celular Android no KaniCode pelo cabo USB.",
                                 epilog=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", help="estado | dispositivos | tamanho | tela | tocar | deslizar | texto | tecla | audio | servir")
    ap.add_argument("valores", nargs="*", help="coordenadas, texto ou nome da tecla")
    ap.add_argument("--serial", help="aparelho, quando há mais de um conectado")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--salvar", help="tela: onde gravar o PNG")
    ap.add_argument("--largura", type=int, default=720, help="tela/servir: largura do quadro (padrão 720)")
    ap.add_argument("--porta", type=int, default=PORTA)
    ap.add_argument("--ms", type=int, default=300, help="deslizar: duração do gesto em milissegundos")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    a = ap.parse_args(argv)
    cmd = a.cmd.lower()
    try:
        if cmd == "estado":
            e = estado()
            print(json.dumps(e, ensure_ascii=False, indent=2) if a.json else "", end="")
            if not a.json:
                _mostrar_estado(e)
            return 0 if e["pronto"] else 2
        if cmd == "dispositivos":
            devs = dispositivos()
            if a.json:
                print(json.dumps(devs, ensure_ascii=False, indent=2))
            else:
                for d in devs:
                    print(f"{d['serial']}  {d['estado']:<13} {d['modelo']}")
                if not devs:
                    print("(nenhum aparelho no adb)")
            return 0
        if cmd == "tamanho":
            tam = tamanho(a.serial)
            print(json.dumps(tam) if a.json else f"{tam['largura']}x{tam['altura']}")
            return 0
        if cmd in ("tela", "quadro"):
            png = quadro(a.serial, a.largura)
            if a.salvar:
                os.makedirs(os.path.dirname(os.path.abspath(a.salvar)), exist_ok=True)
                with open(a.salvar, "wb") as f:
                    f.write(png)
                print(a.salvar)
            elif a.json:
                print(json.dumps({"bytes": len(png), "png_base64": base64.b64encode(png).decode("ascii")}))
            else:
                print(f"quadro de {len(png)} bytes (use --salvar para gravar ou --json para o base64)")
            return 0
        if cmd == "tocar":
            if len(a.valores) < 2:
                raise ErroADB("tocar precisa de x e y (pixels do celular).")
            print(json.dumps(tocar(a.valores[0], a.valores[1], a.serial)))
            return 0
        if cmd == "deslizar":
            if len(a.valores) < 4:
                raise ErroADB("deslizar precisa de x1 y1 x2 y2.")
            print(json.dumps(deslizar(*a.valores[:4], ms=a.ms, serial=a.serial)))
            return 0
        if cmd == "texto":
            t = " ".join(a.valores)
            if not t:
                raise ErroADB("texto precisa do que digitar.")
            r = texto(t, a.serial)
            print(json.dumps(r, ensure_ascii=False) if a.json else "digitado: " + r["digitado"])
            if r["aviso"] and not a.json:
                print(r["aviso"])
            return 0
        if cmd == "tecla":
            if not a.valores:
                raise ErroADB("tecla precisa do nome (voltar, home, recentes...).")
            print(tecla(a.valores[0], a.serial))
            return 0
        if cmd == "audio":
            r = audio_estado(a.serial)
            print(json.dumps(r, ensure_ascii=False, indent=2) if a.json else r["motivo"])
            return 0 if r["pronto"] else 3
        if cmd == "servir":
            servir(a.porta, a.largura)
            return 0
        raise ErroADB("comando desconhecido: " + a.cmd)
    except ErroADB as e:
        print("erro: " + str(e))
        return 2


if __name__ == "__main__":
    sys.exit(main())
