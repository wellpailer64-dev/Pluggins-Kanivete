"""Gmail: leitura e rascunhos, com OAuth independente e proteção DPAPI."""
import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage
from html.parser import HTMLParser
import google_calendar as gc

API = "https://gmail.googleapis.com/gmail/v1/users/me/"
FalhaGmail = gc.FalhaCalendar

def _http(caminho, token, dados=None):
    cab = {"Authorization": "Bearer " + token, "Accept": "application/json"}
    corpo = None
    if dados is not None:
        cab["Content-Type"] = "application/json"
        corpo = json.dumps(dados).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(API + caminho, data=corpo, headers=cab), timeout=25) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise FalhaGmail(f"Gmail recusou a operação (HTTP {e.code}). Confira a Gmail API, as permissões e a conexão da conta.") from None
    except (OSError, ValueError):
        raise FalhaGmail("Não foi possível acessar o Gmail. Confira a conexão e tente novamente.") from None

def _id(valor):
    if not isinstance(valor, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", valor):
        raise FalhaGmail("Identificador de mensagem inválido.")
    return valor

class _Texto(HTMLParser):
    def __init__(self):
        super().__init__(); self.partes = []; self.ignorar = 0
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"): self.ignorar += 1
        if tag in ("br", "p", "div"): self.partes.append("\n")
    def handle_endtag(self, tag):
        if tag in ("script", "style"): self.ignorar = max(0, self.ignorar - 1)
    def handle_data(self, data):
        if not self.ignorar: self.partes.append(data)

def _mensagem(m):
    payload = m.get("payload", {})
    cab = {h["name"].lower(): h.get("value", "") for h in payload.get("headers", [])}
    textos, html = [], []
    def visitar(parte):
        if parte.get("filename"): return
        data = parte.get("body", {}).get("data")
        if data and parte.get("mimeType") in ("text/plain", "text/html"):
            try:
                texto = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")
            except (ValueError, TypeError):
                texto = "[Conteúdo indisponível]"
            (textos if parte["mimeType"] == "text/plain" else html).append(texto)
        for filho in parte.get("parts", []): visitar(filho)
    visitar(payload)
    if not textos and html:
        parser = _Texto(); parser.feed("\n".join(html)); textos = ["".join(parser.partes)]
    return {"id": m["id"], "assunto": cab.get("subject", "Sem assunto"), "de": cab.get("from", ""),
            "para": cab.get("to", ""), "data": cab.get("date", ""), "resumo": m.get("snippet", ""),
            "texto": "\n".join(textos)[:200000]}

class Gmail(gc.Calendar):
    escopos = ("https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.compose")
    permissao_erro = "Autorize a leitura e os rascunhos do Gmail para conectar."
    def __init__(self, dados=gc.DADOS / "gmail", origem=None):
        super().__init__(dados)
        self.origem = origem if origem is not None else gc.calendar
    def _status(self):
        p = self._privado()
        with self.origem._lock():
            reutilizavel = bool(self.origem._privado().get("client"))
        return {"configurado": bool(p.get("client")), "conectado": bool(p.get("token")),
                "conectando": self._conectando, "mensagem": self._mensagem, "reutilizavel": reutilizavel}
    def usar_calendar(self):
        with self.origem._lock(): client = self.origem._privado().get("client")
        if not client: raise FalhaGmail("Configure o OAuth do Calendar ou importe um JSON OAuth Desktop.")
        with self._lock():
            if self._conectando or self._privado().get("token"):
                raise FalhaGmail("Desconecte o Gmail antes de trocar a configuração.")
            self._guardar_privado({"client": dict(client)})
            self._mensagem = "Configuração pronta. Conecte sua conta Gmail."
            return self._status()
    def sincronizar(self):
        with self._lock():
            perfil = _http("profile", self._access(self._privado()))
            self._mensagem = "Conectado: " + perfil.get("emailAddress", "Gmail")
            return self._status()
    def buscar(self, busca="", proxima=""):
        if not isinstance(busca, str) or len(busca) > 500 or not isinstance(proxima, str) or len(proxima) > 4096:
            raise FalhaGmail("Busca ou página inválida.")
        with self._lock():
            token = self._access(self._privado())
            params = {"q": busca, "maxResults": 20}
            if proxima: params["pageToken"] = proxima
            r = _http("messages?" + urllib.parse.urlencode(params), token)
            mensagens = [_mensagem(_http("messages/" + _id(m["id"]) + "?format=metadata&metadataHeaders=Subject&metadataHeaders=From&metadataHeaders=Date", token)) for m in r.get("messages", [])]
            return {"mensagens": mensagens, "proxima": r.get("nextPageToken", "")}
    def ler(self, id):
        caminho = "messages/" + _id(id) + "?format=full"
        with self._lock(): return _mensagem(_http(caminho, self._access(self._privado())))
    def rascunho(self, para, assunto, texto):
        if any(not isinstance(v, str) for v in (para, assunto, texto)):
            raise FalhaGmail("Preencha destinatário, assunto e mensagem.")
        if not para.strip() or len(para) > 2000 or len(assunto) > 1000 or len(texto) > 200000 or any(c in para + assunto for c in "\r\n"):
            raise FalhaGmail("Destinatário, assunto ou tamanho da mensagem inválido.")
        m = EmailMessage(); m["To"] = para; m["Subject"] = assunto; m.set_content(texto)
        dados = {"message": {"raw": base64.urlsafe_b64encode(m.as_bytes()).decode()}}
        with self._lock():
            r = _http("drafts", self._access(self._privado()), dados)
        return {"id": r["id"], "mensagem": "Rascunho criado no Gmail. Nenhum e-mail foi enviado."}
    def desconectar(self):
        self._cancelar.set()
        with self._lock():
            p = self._privado()
            self._guardar_privado({"client": p["client"]} if p.get("client") else {})
            self._mensagem = "Gmail desconectado deste computador."
            return self._status()

gmail = Gmail()
