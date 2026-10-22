"""Drive com leitura e escrita autorizadas; OAuth/PKCE e DPAPI separados do Calendar."""
import datetime as dt
import urllib.parse

import google_calendar as gc
from google_drive_arquivos import OperacoesDrive, ESCOPO_TOTAL, _id

FalhaDrive = gc.FalhaCalendar
API = "https://www.googleapis.com/drive/v3/"


def _http(url, token):
    try:
        return gc._http(url, token=token)
    except gc.FalhaCalendar as e:
        raise FalhaDrive(str(e).replace("Google Calendar", "Google Drive").replace("Calendar API", "Drive API")) from None


class Drive(OperacoesDrive, gc.Calendar):
    escopos = (ESCOPO_TOTAL,)
    permissao_erro = "Autorize o controle dos arquivos do Google Drive para conectar."

    def __init__(self, dados=gc.DADOS / "drive", origem=None):
        super().__init__(dados)
        self.origem = origem if origem is not None else gc.calendar

    def _guardar_privado(self, value):
        anterior = self._privado().get("token", {})
        super()._guardar_privado(value)
        token = value.get("token", {})
        if token and token.get("refresh_token") != anterior.get("refresh_token"):
            # Uma nova autorização pode ser de outra conta: nunca mostrar a listagem anterior.
            gc._salvar(self.dados / "google.json", {})

    def _estado(self):
        return gc._json(self.dados / "google.json", {})

    def _status(self):
        e, p = self._estado(), self._privado()
        with self.origem._lock():
            reutilizavel = bool(self.origem._privado().get("client"))
        return {"configurado": bool(p.get("client")), "conectado": bool(p.get("token")),
                "conectando": self._conectando, "mensagem": self._mensagem or e.get("erro", ""),
                "conta": e.get("conta", ""), "ultima_sync": e.get("ultima_sync"),
                "reutilizavel": reutilizavel, "controle_total": self._total(p), "permissao": "Controle total" if self._total(p) else "Somente leitura",
                "arquivos": e.get("arquivos", []), "proxima": e.get("proxima", "")}

    def usar_calendar(self):
        with self.origem._lock():
            client = self.origem._privado().get("client")
        if not client:
            raise FalhaDrive("Configure primeiro o aplicativo OAuth do Calendar ou importe outro JSON.")
        with self._lock():
            if self._conectando or self._privado().get("token"):
                raise FalhaDrive("Desconecte o Drive antes de trocar o aplicativo OAuth.")
            self._guardar_privado({"client": dict(client)})
            self._mensagem = "Aplicativo configurado. Agora conecte sua conta Google Drive."
            return self._status()

    def buscar(self, busca="", proxima="", pasta="", lixeira=False):
        with self._lock():
            return self._buscar(busca, proxima, self._access(self._privado()), pasta, lixeira)

    def _buscar(self, busca, proxima, access, pasta="", lixeira=False):
        if not isinstance(busca, str) or len(busca) > 200 or not isinstance(proxima, str) or len(proxima) > 4096:
            raise FalhaDrive("Use uma busca de até 200 caracteres e uma página válida.")
        termo = busca.strip().replace("\\", "\\\\").replace("'", "\\'")
        if not isinstance(lixeira, bool):
            raise FalhaDrive("Informe se deseja consultar a lixeira.")
        query = "trashed = " + ("true" if lixeira else "false") + (" and name contains '" + termo + "'" if termo else "")
        if pasta:
            query += " and '" + _id(pasta) + "' in parents"
        params = {"q": query, "pageSize": 50, "orderBy": "folder,name_natural",
                  "fields": "nextPageToken,incompleteSearch,files(id,name,mimeType,modifiedTime,webViewLink,size,trashed,parents)",
                  "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"}
        if proxima:
            params["pageToken"] = proxima
        resultado = _http(API + "files?" + urllib.parse.urlencode(params), access)
        arquivos = [{"id": f["id"], "nome": f.get("name", "Sem nome"),
                     "pasta": f.get("mimeType") == "application/vnd.google-apps.folder",
                     "tipo": f.get("mimeType", ""), "modificado": f.get("modifiedTime", ""), "lixeira": bool(f.get("trashed")), "pais": f.get("parents", []),
                     "url": "https://drive.google.com/" + ("drive/folders/" if f.get("mimeType") == "application/vnd.google-apps.folder" else "file/d/") + urllib.parse.quote(f["id"], safe="")}
                    for f in resultado.get("files", [])]
        return {"arquivos": arquivos, "proxima": resultado.get("nextPageToken", ""),
                "incompleta": bool(resultado.get("incompleteSearch"))}

    def sincronizar(self):
        with self._lock():
            e = self._estado()
            try:
                access = self._access(self._privado())
                usuario = _http(API + "about?fields=user(emailAddress,displayName)", access).get("user", {})
                resultado = self._buscar("", "", access)
                e.update(conta=usuario.get("emailAddress") or usuario.get("displayName", "Conta Google"),
                         ultima_sync=dt.datetime.now(dt.timezone.utc).isoformat(), erro="",
                         arquivos=resultado["arquivos"], proxima=resultado["proxima"])
                self._mensagem = ""
            except gc.FalhaCalendar as exc:
                e["erro"] = str(exc).replace("Google Calendar", "Google Drive").replace("Calendar API", "Drive API")
                self._mensagem = e["erro"]
                gc._salvar(self.dados / "google.json", e)
                raise FalhaDrive(e["erro"]) from None
            gc._salvar(self.dados / "google.json", e)
            return self._status()

    def desconectar(self):
        self._cancelar.set()
        with self._lock():
            p = self._privado()
            self._guardar_privado({"client": p["client"]} if p.get("client") else {})
            gc._salvar(self.dados / "google.json", {})
            self._mensagem = "Google Drive desconectado deste computador."
            return self._status()


drive = Drive()
