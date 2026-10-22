"""Google Calendar somente leitura. OAuth desktop/PKCE; segredos no DPAPI do usuário Windows.

Sem SDK ou dependências novas. Não faz login nem acessa rede ao importar o módulo.
"""
import base64
import contextlib
import ctypes
from ctypes import wintypes
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

DADOS = Path("D:/Kanivete/KaniCode/conexoes")
SCOPES = ("https://www.googleapis.com/auth/calendar.calendarlist.readonly",
          "https://www.googleapis.com/auth/calendar.events.readonly")
TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/calendar/v3/"


class FalhaCalendar(RuntimeError):
    pass


def _json(path, default):
    # no Windows, ler enquanto outro processo troca o arquivo dá PermissionError: tenta de novo
    for i in range(5):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return default
        except (PermissionError, ValueError):
            if i == 4:
                return default
            time.sleep(0.05)


def _salvar(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + secrets.token_hex(6) + ".tmp")
    try:
        temp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        for i in range(10):
            try:
                os.replace(temp, path)
                break
            except PermissionError:
                if i == 9:
                    raise
                time.sleep(0.05)
    finally:
        temp.unlink(missing_ok=True)


def _dpapi(data, proteger=True):
    """DPAPI sem chave no disco; vinculado ao login Windows atual."""
    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]
    buf = ctypes.create_string_buffer(data)
    entrada = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))
    saida = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    func = crypt.CryptProtectData if proteger else crypt.CryptUnprotectData
    func.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                     ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    func.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not func(ctypes.byref(entrada), None, None, None, None, 1, ctypes.byref(saida)):
        raise FalhaCalendar("Não foi possível acessar as credenciais protegidas deste usuário Windows.")
    try:
        return ctypes.string_at(saida.pbData, saida.cbData)
    finally:
        kernel.LocalFree(saida.pbData)


def _http(url, form=None, token=None):
    headers = {"Accept": "application/json"}
    data = None
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if token:
        headers["Authorization"] = "Bearer " + token
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        # Não devolver corpo HTTP: pode conter código OAuth ou outros dados privados.
        if e.code == 400 and url == TOKEN_URL:
            raise FalhaCalendar("O Google recusou a credencial. Conecte a conta novamente.") from None
        if e.code == 401:
            raise FalhaCalendar("A autorização expirou ou foi revogada. Conecte a conta novamente.") from None
        if e.code == 403:
            raise FalhaCalendar("Acesso recusado. Confira as permissões e se a Calendar API está ativada no projeto Google.") from None
        raise FalhaCalendar(f"Google Calendar indisponível (HTTP {e.code}). Tente sincronizar depois.") from None
    except (OSError, ValueError):
        raise FalhaCalendar("Sem conexão com o Google Calendar. A última agenda continua disponível.") from None


def _evento(event, calendar):
    if event.get("status") == "cancelled":
        return None
    start = event.get("start", {})
    raw = start.get("dateTime") or start.get("date")
    if not raw:
        return None
    all_day = "dateTime" not in start
    if all_day:
        inicio = raw
    else:
        data = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if data.tzinfo is None:
            # Nunca adivinhar o fuso de um horário do Google.
            raise FalhaCalendar("O Google retornou um evento sem fuso horário.")
        inicio = data.isoformat()
    return {"id": "google:" + calendar["id"] + ":" + event["id"],
            "titulo": event.get("summary") or "Compromisso sem título", "inicio": inicio,
            "dia_inteiro": all_day, "calendario": calendar["nome"], "origem": "google",
            "obs": event.get("location", "")}


class Calendar:
    escopos = SCOPES
    permissao_erro = "Autorize a leitura dos calendários e dos eventos para conectar."

    def __init__(self, dados=DADOS):
        self.dados = Path(dados)
        self._mutex = threading.RLock()
        self._auth_mutex = threading.Lock()
        self._cancelar = threading.Event()
        self._conectando = False
        self._mensagem = ""

    @contextlib.contextmanager
    def _lock(self):
        # Janela e Agendador do Windows compartilham os mesmos arquivos.
        import msvcrt
        with self._mutex:
            self.dados.mkdir(parents=True, exist_ok=True)
            with (self.dados / "google.lock").open("a+b") as f:
                f.seek(0, 2)
                if not f.tell():
                    f.write(b"0")
                    f.flush()
                limite = time.monotonic() + 120
                while True:
                    f.seek(0)
                    try:
                        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        if time.monotonic() > limite:
                            raise FalhaCalendar("Outra sincronização está em andamento. Tente novamente.")
                        time.sleep(.1)
                try:
                    yield
                finally:
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)

    def _estado(self):
        return _json(self.dados / "google.json", {"selecionados": None, "calendarios": [], "eventos": [], "antes": 10})

    def _privado(self):
        value = _json(self.dados / "google.dpapi.json", None)
        if not value:
            return {}
        try:
            return json.loads(_dpapi(base64.b64decode(value["blob"]), proteger=False))
        except (ValueError, KeyError):
            raise FalhaCalendar("Credencial local inválida. Importe o JSON OAuth novamente.") from None

    def _guardar_privado(self, value):
        blob = _dpapi(json.dumps(value).encode())
        _salvar(self.dados / "google.dpapi.json", {"blob": base64.b64encode(blob).decode()})

    def _status(self):
        e, p = self._estado(), self._privado()
        return {"configurado": bool(p.get("client")), "conectado": bool(p.get("token")),
                "conectando": self._conectando, "mensagem": self._mensagem or e.get("erro", ""),
                "conta": e.get("conta", ""), "ultima_sync": e.get("ultima_sync"),
                "calendarios": e.get("calendarios", []), "selecionados": e.get("selecionados") or [],
                "eventos": e.get("eventos", []), "antes": e.get("antes", 10),
                "permissao": "Somente leitura",
                "avisos": _json(self.dados.parent / 'avisos' / 'preparar_estado.json', {})}

    def status(self):
        with self._lock():
            return self._status()

    def importar(self, caminho):
        try:
            c = json.loads(Path(caminho).read_text(encoding="utf-8-sig"))["installed"]
            if not (c["client_id"].endswith(".apps.googleusercontent.com") and c["client_secret"]):
                raise ValueError()
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            raise FalhaCalendar("Selecione o JSON OAuth de um aplicativo para computador (Desktop app), baixado do Google Cloud.") from None
        with self._lock():
            if self._conectando or self._privado().get("token"):
                raise FalhaCalendar("Desconecte a conta antes de trocar o aplicativo OAuth.")
            self._guardar_privado({"client": {"client_id": c["client_id"], "client_secret": c["client_secret"]}})
            self._mensagem = "Aplicativo configurado. Agora conecte sua conta Google."
            return self._status()

    def conectar(self, apos_conectar=None):
        with self._auth_mutex:
            with self._lock():
                if self._conectando:
                    return self._status()
                c = self._privado().get("client")
                if not c:
                    raise FalhaCalendar("Importe primeiro o JSON OAuth do aplicativo Google.")
                self._cancelar = threading.Event()
                self._conectando = True
                self._mensagem = "Conclua a autorização no navegador (até 3 minutos)."
                threading.Thread(target=self._autorizar, args=(c, self._cancelar, apos_conectar), daemon=True).start()
                return self._status()

    def _autorizar(self, client, cancelar, apos_conectar=None):
        try:
            token = self._login(client, cancelar)
            with self._lock():
                if cancelar.is_set():
                    return
                self._guardar_privado({"client": client, "token": token})
                self._mensagem = ""
            self.sincronizar()
            if apos_conectar and not cancelar.is_set():
                apos_conectar()
        except Exception as e:
            self._mensagem = str(e) if isinstance(e, FalhaCalendar) else "Não foi possível conectar. Tente novamente."
        finally:
            self._conectando = False

    def _login(self, client, cancelar):
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        resposta = {}

        class Callback(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                u = urllib.parse.urlsplit(self.path)
                q = urllib.parse.parse_qs(u.query)
                valido = u.path == "/oauth" and secrets.compare_digest(q.get("state", [""])[0], state)
                if valido:
                    resposta.update({"code": q.get("code", [""])[0], "erro": bool(q.get("error"))})
                self.send_response(200 if valido else 400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Security-Policy", "default-src 'none'")
                self.end_headers()
                self.wfile.write(("Autorização recebida. Volte ao KaniCode para conferir a conexão."
                                  if valido else "Solicitação inválida.").encode())

        with HTTPServer(("127.0.0.1", 0), Callback) as server:
            server.timeout = 1
            redirect = f"http://127.0.0.1:{server.server_port}/oauth"
            params = {"client_id": client["client_id"], "redirect_uri": redirect, "response_type": "code",
                      "scope": " ".join(self.escopos), "access_type": "offline", "prompt": "consent select_account",
                      "state": state, "code_challenge": challenge, "code_challenge_method": "S256"}
            if not webbrowser.open("https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)):
                raise FalhaCalendar("Não foi possível abrir o navegador padrão para entrar no Google.")
            limite = time.monotonic() + 180
            while not resposta and not cancelar.is_set() and time.monotonic() < limite:
                server.handle_request()
        if cancelar.is_set():
            raise FalhaCalendar("Conexão cancelada.")
        if not resposta:
            raise FalhaCalendar("O prazo do login terminou. Clique em Conectar novamente.")
        if resposta.get("erro") or not resposta.get("code"):
            raise FalhaCalendar("A autorização foi cancelada no Google.")
        token = _http(TOKEN_URL, {**client, "code": resposta["code"], "code_verifier": verifier,
                                 "redirect_uri": redirect, "grant_type": "authorization_code"})
        if not set(self.escopos).issubset(set(token.get("scope", "").split())) or not token.get("refresh_token"):
            raise FalhaCalendar(self.permissao_erro)
        token["expires_at"] = time.time() + token.get("expires_in", 3600)
        return token

    def _access(self, p):
        token = p.get("token")
        if not token:
            raise FalhaCalendar("Conecte uma conta Google em Configurações → Conexões.")
        if token.get("expires_at", 0) < time.time() + 60:
            novo = _http(TOKEN_URL, {**p["client"], "refresh_token": token["refresh_token"], "grant_type": "refresh_token"})
            token.update(novo)
            token["expires_at"] = time.time() + novo.get("expires_in", 3600)
            self._guardar_privado(p)
        return token["access_token"]

    def _paginas(self, path, params, access):
        itens, page = [], None
        while True:
            query = dict(params)
            if page:
                query["pageToken"] = page
            result = _http(API + path + "?" + urllib.parse.urlencode(query), token=access)
            itens.extend(result.get("items", []))
            page = result.get("nextPageToken")
            if not page:
                return itens

    def sincronizar(self):
        with self._lock():
            e = self._estado()
            try:
                access = self._access(self._privado())
                calendars = self._paginas("users/me/calendarList", {"maxResults": 250}, access)
                lista = [{"id": c["id"], "nome": c.get("summaryOverride") or c.get("summary", c["id"]),
                          "principal": bool(c.get("primary"))} for c in calendars if not c.get("deleted")]
                selecionados = e.get("selecionados")
                if selecionados is None:
                    selecionados = [c["id"] for c in lista if c["principal"]]
                agora = dt.datetime.now(dt.timezone.utc)
                params = {"timeMin": agora.isoformat(), "timeMax": (agora + dt.timedelta(days=7)).isoformat(),
                          "singleEvents": "true", "orderBy": "startTime", "maxResults": 2500}
                eventos = []
                for c in lista:
                    if c["id"] in selecionados:
                        path = "calendars/" + urllib.parse.quote(c["id"], safe="") + "/events"
                        for item in self._paginas(path, params, access):
                            evento = _evento(item, c)
                            if evento:
                                eventos.append(evento)
                e.update(calendarios=lista, selecionados=selecionados, eventos=sorted(eventos, key=lambda x: x["inicio"]),
                         conta=next((c["id"] for c in lista if c["principal"]), "Conta Google"),
                         ultima_sync=agora.isoformat(), erro="")
                self._mensagem = ""
            except FalhaCalendar as error:
                e["erro"] = str(error)
                self._mensagem = ""
                _salvar(self.dados / "google.json", e)
                raise
            _salvar(self.dados / "google.json", e)
            return self._status()

    def selecionar(self, ids, antes=10):
        with self._lock():
            e = self._estado()
            permitidos = {c["id"] for c in e.get("calendarios", [])}
            if not isinstance(ids, list) or any(not isinstance(i, str) or i not in permitidos for i in ids):
                raise FalhaCalendar("Selecione apenas calendários da conta conectada.")
            if isinstance(antes, bool) or not isinstance(antes, int) or not 1 <= antes <= 1440:
                raise FalhaCalendar("A antecedência deve estar entre 1 e 1440 minutos.")
            e.update(selecionados=list(dict.fromkeys(ids)), antes=antes, eventos=[])
            _salvar(self.dados / "google.json", e)
        return self.sincronizar()

    def desconectar(self):
        self._cancelar.set()
        with self._lock():
            p = self._privado()
            # Esquece a autorização local; não revoga outros usos do mesmo projeto Google.
            self._guardar_privado({"client": p["client"]} if p.get("client") else {})
            _salvar(self.dados / "google.json", {"selecionados": None, "calendarios": [], "eventos": [], "antes": 10})
            self._mensagem = "Conta desconectada deste computador."
            return self._status()

    def ocorrencias(self, agora, fim):
        with self._lock():
            if not self._privado().get("token"):
                return []
            e = self._estado()
            ultima = e.get('ultima_sync')
            if not ultima or (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(ultima)).total_seconds() > 7200:
                return []  # Não disparar eventos de uma agenda que parou de sincronizar há horas.
            saida = []
            for item in e.get("eventos", []):
                if item["dia_inteiro"]:
                    continue
                inicio = dt.datetime.fromisoformat(item["inicio"]).astimezone().replace(tzinfo=None)
                if agora < inicio <= fim:
                    saida.append({**item, "inicio": inicio, "antes": e.get("antes", 10)})
            return saida


calendar = Calendar()
