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

ICONES = ("icone.png", "icone-192.png", "icone-512.png", "icone-mascara-512.png", "icone-badge.png")   # icone_oculos.py

_app = None
_asr = None               # voz.Voz só para transcrever (o mesmo Parakeet do "Ei Kani"; carrega no 1º uso)
_tts = threading.Lock()   # um Kokoro só (fala.py) para a janela e o celular
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
    """evento da conversa para todos os celulares abertos (e o aviso no celular, aviso_movel.py)"""
    try:
        import aviso_movel
        aviso_movel.ver(ev)
    except Exception:
        pass
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
        if u.path == "/sw.js":   # o "carteiro" do aviso no celular (precisa morar na raiz)
            with open(os.path.join(UI, "movel-sw.js"), "rb") as f:
                return self._enviar(200, f.read(), _TIPOS[".js"], {"Service-Worker-Allowed": "/"})
        if u.path == "/manifest.webmanifest" or u.path.lstrip("/") in ICONES:   # o Chrome pede sem cookie em alguns casos
            return self._arquivo(u.path.lstrip("/"))
        if not self._autorizado():
            return self._enviar(403, "KaniCode: abra o link de pareamento (com ?chave=) no celular.".encode())
        if u.path == "/":
            return self._pagina()
        if u.path == "/eventos":
            return self._eventos(q.get("de", [""])[0])
        return self._arquivo(u.path.lstrip("/"))

    def _arquivo(self, nome):
        if nome == "manifest.webmanifest":
            m = {"name": "KaniCode", "short_name": "KaniCode", "start_url": "/", "display": "standalone",
                 "background_color": "#0E1110", "theme_color": "#151A18",
                 "icons": [{"src": "/icone-192.png", "sizes": "192x192", "type": "image/png"},
                           {"src": "/icone-512.png", "sizes": "512x512", "type": "image/png"},
                           {"src": "/icone-mascara-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}]}
            return self._enviar(200, json.dumps(m).encode(), _TIPOS[".webmanifest"])
        cam = os.path.join(PASTA, nome) if nome in ICONES else os.path.normpath(os.path.join(UI, nome.replace("ui/", "", 1)))
        if not (cam.startswith(UI + os.sep) or nome in ICONES) or not os.path.isfile(cam):
            return self._enviar(404)
        with open(cam, "rb") as f:
            return self._enviar(200, f.read(), _TIPOS.get(os.path.splitext(cam)[1].lower(), "application/octet-stream"))

    def _pagina(self):
        with open(os.path.join(UI, "janela.html"), encoding="utf-8") as f:
            h = f.read()
        cab = ('<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover, interactive-widget=resizes-content">'
               '<meta name="theme-color" content="#151A18"><link rel="manifest" href="/manifest.webmanifest">'
               '<link rel="icon" href="/icone-192.png"><link rel="apple-touch-icon" href="/icone-192.png">'
               '<link rel="stylesheet" href="/movel.css"><script src="/movel.js"></script>')
        h = h.replace("<title>", cab + "<title>", 1)
        self._enviar(200, h.encode("utf-8"), _TIPOS[".html"])

    def _eventos(self, de=""):
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
            if de:   # a página fechou ou caiu: não está mais à vista
                import aviso_movel
                aviso_movel.visto(de, False)
            self.close_connection = True

    def do_POST(self):
        if not self._autorizado():
            return self._enviar(403)
        u = urlparse(self.path)
        if u.path in ("/voz/ouvir", "/voz/falar"):
            return self._voz(u.path[5:])
        if u.path.startswith("/push/"):
            return self._push(u.path[6:])
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


    def _push(self, o_que):
        """chave | assinar {sub} | sair {endpoint} | visto {de, on} | teste"""
        import aviso_movel
        n = int(self.headers.get("Content-Length") or 0)
        d = json.loads(self.rfile.read(n) or b"{}") if n else {}
        try:
            if o_que == "chave":
                r = aviso_movel.chave_publica()
            elif o_que == "assinar":
                r = aviso_movel.assinar(d["sub"])
            elif o_que == "sair":
                r = aviso_movel.sair(d.get("endpoint"))
            elif o_que == "visto":
                r = aviso_movel.visto(str(d.get("de") or ""), bool(d.get("on")))
            elif o_que == "teste":
                r = aviso_movel.avisar("KaniCode", "Pronto: os avisos chegam aqui quando eu terminar ou precisar de você.", "kc-teste")
            else:
                return self._enviar(404)
            return self._enviar(200, json.dumps({"r": r}).encode(), _TIPOS[".json"])
        except Exception as e:
            return self._enviar(500, json.dumps({"erro": str(e)}, ensure_ascii=False).encode("utf-8"), _TIPOS[".json"])

    def _voz(self, o_que):
        """ouvir: corpo = PCM 16 bits mono 16 kHz do microfone do celular → {"texto"}; falar: {"texto"} → WAV (Kokoro)"""
        global _asr
        n = int(self.headers.get("Content-Length") or 0)
        corpo = self.rfile.read(n) if n else b""
        try:
            import numpy as np
            if o_que == "ouvir":
                audio = np.frombuffer(corpo[: len(corpo) // 2 * 2], np.int16).astype(np.float32) / 32768
                if len(audio) < 16000 * 0.3:
                    texto = ""
                else:
                    voz = getattr(_app, "_voz", None)
                    if voz is None:
                        if _asr is None:
                            from voz import Voz
                            _asr = Voz()
                        voz = _asr
                    texto = voz._transcrever(audio)
                return self._enviar(200, json.dumps({"texto": texto}, ensure_ascii=False).encode("utf-8"), _TIPOS[".json"])
            import io, wave
            from fala import VELOCIDADE, VOZ, limpar
            frase = limpar(json.loads(corpo or b"{}").get("texto") or "")
            if len(frase) < 2:
                return self._enviar(204)
            with _tts:
                a, sr = _app._fala_obj().carregar().create(frase, voice=VOZ, speed=VELOCIDADE, lang="pt-br")
            buf = io.BytesIO()
            with wave.open(buf, "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
                w.writeframes((np.clip(np.asarray(a, np.float32), -1, 1) * 32767).astype(np.int16).tobytes())
            return self._enviar(200, buf.getvalue(), "audio/wav")
        except Exception as e:
            return self._enviar(500, json.dumps({"erro": str(e)}, ensure_ascii=False).encode("utf-8"), _TIPOS[".json"])


def iniciar(app, dados):
    """liga o servidor do celular (127.0.0.1:PORTA) numa thread; devolve False se a porta estiver ocupada"""
    global _app, _chave
    _app, _chave = app, chave(dados)
    import aviso_movel
    aviso_movel.iniciar(dados)
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
