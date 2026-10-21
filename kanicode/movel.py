"""KaniCode no celular: a MESMA conversa da janela (ui/janela.html) servida por HTTP, só para os aparelhos do Pailer.

O PC continua fazendo tudo; o celular é só a tela. A página é a da janela com ui/movel.js na frente: ele imita o
window.pywebview.api (cada chamada vira POST /api/<método>) e recebe os eventos da conversa por SSE (/eventos).
Escuta SÓ em 127.0.0.1:PORTA — de fora, só pelo Tailscale ("tailscale serve", HTTPS dentro da rede particular dele).
Mesmo assim pede a chave: o 1º acesso é pelo link com ?chave=… (vira cookie); sem ela, 403.

Ver o link: py -3.13 movel.py   (mostra o endereço com a chave e abre o QR na tela, se houver o pacote qrcode)
"""
import json, os, queue, secrets, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PASTA = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(PASTA, "ui")
PORTA = 47614

# o que o celular pode chamar (o resto da js_api mexe na janela do PC: no celular não faz nada)
LIBERADOS = {"info", "historico", "preparar", "enviar", "parar", "responder", "responder_pergunta", "sempre", "modo",
             "nova", "quem", "ajudante", "habilidades", "miniatura", "tarefas_ler", "contas_listar", "conta_atualizar",
             "conta_usar", "pendentes"}
NADA = {"esconder", "fixar", "expandir", "crescer", "tam_inicio", "tam_mudar", "tam_fim", "tam_padrao", "abrir_imagem",
        "escolher_pasta", "sair", "voz", "ouvir", "conta_adicionar", "conta_entrar_de_novo", "conta_renomear", "conta_remover"}
_TIPOS = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
          ".webp": "image/webp", ".png": "image/png", ".json": "application/json", ".webmanifest": "application/manifest+json"}

_app = None
_chave = None
_ouvintes = []            # filas dos celulares conectados (uma por página aberta)
_trava = threading.Lock()


def chave(dados):
    """a chave do pareamento (gerada uma vez, guardada em DADOS/movel.json)"""
    arq = os.path.join(dados, "movel.json")
    try:
        with open(arq, encoding="utf-8") as f:
            return json.load(f)["chave"]
    except Exception:
        c = secrets.token_urlsafe(18)
        os.makedirs(dados, exist_ok=True)
        with open(arq, "w", encoding="utf-8") as f:
            json.dump({"chave": c}, f)
        return c


def publicar(ev):
    """evento da conversa para todos os celulares abertos"""
    with _trava:
        for q in list(_ouvintes):
            try:
                q.put_nowait(ev)
            except queue.Full:
                pass


class _H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _enviar(self, cod, corpo=b"", tipo="text/plain; charset=utf-8", extra=None):
        self.send_response(cod)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(corpo)

    def _autorizado(self):
        for parte in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = parte.strip().partition("=")
            if k == "kc_chave" and secrets.compare_digest(v, _chave):
                return True
        return False

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if "chave" in q:   # pareamento: guarda a chave num cookie e volta para a página limpa
            if secrets.compare_digest(q["chave"][0], _chave):
                return self._enviar(302, extra={"Location": "/", "Set-Cookie":
                                    f"kc_chave={_chave}; Max-Age=31536000; Path=/; HttpOnly; SameSite=Lax; Secure"})
            return self._enviar(403, "Chave errada.".encode())
        if u.path in ("/manifest.webmanifest", "/icone.png"):   # o Chrome pede sem cookie em alguns casos
            return self._arquivo(u.path.lstrip("/"))
        if not self._autorizado():
            return self._enviar(403, "KaniCode: abra o link de pareamento (com ?chave=) no celular.".encode())
        if u.path == "/":
            return self._pagina()
        if u.path == "/eventos":
            return self._eventos()
        return self._arquivo(u.path.lstrip("/"))

    def _arquivo(self, nome):
        if nome == "manifest.webmanifest":
            m = {"name": "KaniCode", "short_name": "KaniCode", "start_url": "/", "display": "standalone",
                 "background_color": "#0E1110", "theme_color": "#151A18",
                 "icons": [{"src": "/icone.png", "sizes": "192x192", "type": "image/png"}]}
            return self._enviar(200, json.dumps(m).encode(), _TIPOS[".webmanifest"])
        cam = os.path.join(PASTA, "icone.png") if nome == "icone.png" else os.path.normpath(os.path.join(UI, nome.replace("ui/", "", 1)))
        if not (cam.startswith(UI + os.sep) or nome == "icone.png") or not os.path.isfile(cam):
            return self._enviar(404)
        with open(cam, "rb") as f:
            return self._enviar(200, f.read(), _TIPOS.get(os.path.splitext(cam)[1].lower(), "application/octet-stream"))

    def _pagina(self):
        with open(os.path.join(UI, "janela.html"), encoding="utf-8") as f:
            h = f.read()
        cab = ('<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover, interactive-widget=resizes-content">'
               '<meta name="theme-color" content="#151A18"><link rel="manifest" href="/manifest.webmanifest">'
               '<link rel="icon" href="/icone.png"><link rel="apple-touch-icon" href="/icone.png">'
               '<link rel="stylesheet" href="/movel.css"><script src="/movel.js"></script>')
        h = h.replace("<title>", cab + "<title>", 1)
        self._enviar(200, h.encode("utf-8"), _TIPOS[".html"])

    def _eventos(self):
        fila = queue.Queue(maxsize=5000)
        with _trava:
            _ouvintes.append(fila)
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            self.wfile.write(b": ok\n\n")
            self.wfile.flush()
            while True:
                try:
                    ev = fila.get(timeout=20)
                    linha = b"data: " + json.dumps(ev, ensure_ascii=False).encode("utf-8") + b"\n\n"
                except queue.Empty:
                    linha = b": ping\n\n"   # mantém a conexão viva (celular e Tailscale fecham conexão parada)
                self.wfile.write(linha)
                self.wfile.flush()
        except OSError:
            pass
        finally:
            with _trava:
                if fila in _ouvintes:
                    _ouvintes.remove(fila)
            self.close_connection = True

    def do_POST(self):
        if not self._autorizado():
            return self._enviar(403)
        u = urlparse(self.path)
        if not u.path.startswith("/api/"):
            return self._enviar(404)
        nome = u.path[5:]
        try:
            n = int(self.headers.get("Content-Length") or 0)
            args = json.loads(self.rfile.read(n) or b"[]") if n else []
            de = self.headers.get("X-KC-De") or "movel"
            if nome in NADA:
                r = None
            elif nome == "enviar":
                r = _app.enviar(*args[:2], _de=de)
            elif nome in ("responder", "responder_pergunta"):
                r = getattr(_app, nome)(*args)
                ok = args[1] if nome == "responder" else True
                _app._para_janela({"t": "eco_resp", "id": args[0], "ok": bool(ok), "de": de})
            elif nome in LIBERADOS:
                r = getattr(_app, nome)(*args)
            else:
                return self._enviar(404)
            return self._enviar(200, json.dumps({"r": r}, ensure_ascii=False).encode("utf-8"), _TIPOS[".json"])
        except Exception as e:
            return self._enviar(500, json.dumps({"erro": str(e)}, ensure_ascii=False).encode("utf-8"), _TIPOS[".json"])


def iniciar(app, dados):
    """liga o servidor do celular (127.0.0.1:PORTA) numa thread; devolve False se a porta estiver ocupada"""
    global _app, _chave
    _app, _chave = app, chave(dados)
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", PORTA), _H)
    except OSError:
        return False
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return True


if __name__ == "__main__":
    import shutil, subprocess
    dados = os.path.join(os.path.splitdrive(PASTA)[0] + os.sep, "Kanivete", "KaniCode")
    nome = ""
    try:
        st = json.loads(subprocess.run([shutil.which("tailscale") or r"C:\Program Files\Tailscale\tailscale.exe", "status", "--json"], capture_output=True, text=True, timeout=10).stdout)
        nome = st["Self"]["DNSName"].rstrip(".")
    except Exception:
        pass
    url = f"https://{nome or '<nome-do-pc>.ts.net'}/?chave={chave(dados)}"
    print(url)
    try:
        import qrcode
        # o QR na tela (o terminal do Windows não desenha os blocos); nome novo a cada vez: o visualizador trava o anterior
        png = os.path.join(dados, f"movel_qr_{int(time.time())}.png")
        for velho in os.listdir(dados):
            if velho.startswith("movel_qr"):
                try:
                    os.remove(os.path.join(dados, velho))
                except OSError:
                    pass
        qrcode.make(url, box_size=12, border=3).save(png)
        os.startfile(png)
    except ImportError:
        pass
