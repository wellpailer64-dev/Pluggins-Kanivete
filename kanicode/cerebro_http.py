"""API HTTP/JSON do cérebro (v1), para qualquer cliente que não fala MCP. Mesma porta única de `cerebro_motor.chamar`.

Sobe dentro do KaniCode (kanicode.py), só em 127.0.0.1. Quem é o agente vem da chave (cabeçalho Authorization: Bearer
<chave>, cadastrada em cerebro/agentes.json), nunca do corpo do pedido.

  GET  /v1/status                      estado do índice
  GET  /v1/tools                       as ferramentas (mesmos esquemas do MCP)
  POST /v1/brain_search  {"pergunta": "...", "k": 5}     (e brain_get, brain_expand, brain_timeline, brain_context,
                                                           brain_remember, brain_update, brain_proposals)
Resposta: {"ok": true, "resultado": ...} ou {"ok": false, "erro": "..."} (401 sem chave, 403 sem permissão).

Os servidores MCP (mcp_equipe.py, mcp_cerebro.py) também passam por aqui quando o KaniCode está aberto: o modelo de
embeddings fica carregado num processo só."""
import json
import os
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cerebro_motor as cm

PORTA = int(os.environ.get("CEREBRO_PORTA") or 47620)
_SERVIDOR = {"s": None}


class _Pedido(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _enviar(self, codigo, corpo):
        dados = json.dumps(corpo, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def _agente(self):
        auth = self.headers.get("Authorization", "")
        return cm.agente_por_chave(auth[7:].strip() if auth.lower().startswith("bearer ") else "")

    def _rodar(self, nome, args):
        agente = self._agente()
        if not agente:
            return self._enviar(401, {"ok": False, "erro": "chave ausente ou inválida (Authorization: Bearer <chave>)"})
        try:
            self._enviar(200, {"ok": True, "agente": agente, "resultado": cm.chamar(nome, args, agente)})
        except PermissionError as e:
            self._enviar(403, {"ok": False, "erro": str(e)})
        except (ValueError, TypeError) as e:
            self._enviar(400, {"ok": False, "erro": str(e)})
        except Exception as e:
            self._enviar(500, {"ok": False, "erro": f"{type(e).__name__}: {e}"})

    def do_GET(self):
        if self.path.rstrip("/") == "/v1/tools":
            return self._enviar(200, {"ok": True, "tools": cm.FERRAMENTAS})
        if self.path.rstrip("/") == "/v1/status":
            return self._rodar("brain_status", {})
        self._enviar(404, {"ok": False, "erro": "use /v1/status, /v1/tools ou POST /v1/<ferramenta>"})

    def do_POST(self):
        nome = self.path.strip("/").split("/")[-1]
        if not self.path.startswith("/v1/") or nome not in {f["name"] for f in cm.FERRAMENTAS}:
            return self._enviar(404, {"ok": False, "erro": "ferramenta desconhecida"})
        try:
            tam = int(self.headers.get("Content-Length") or 0)
            args = json.loads(self.rfile.read(tam).decode("utf-8") or "{}") if tam else {}
        except ValueError:
            return self._enviar(400, {"ok": False, "erro": "JSON inválido"})
        self._rodar(nome, args if isinstance(args, dict) else {})


def iniciar(porta=None):
    """sobe em segundo plano (uma vez por processo); porta ocupada = já há um KaniCode servindo"""
    if _SERVIDOR["s"]:
        return _SERVIDOR["s"].server_address[1]
    try:
        s = ThreadingHTTPServer(("127.0.0.1", porta or PORTA), _Pedido)
    except OSError:
        return None
    s.daemon_threads = True
    _SERVIDOR["s"] = s
    cm.SOU_SERVIDOR = True
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s.server_address[1]


def parar():
    if _SERVIDOR["s"]:
        _SERVIDOR["s"].shutdown()
        _SERVIDOR["s"] = None
        cm.SOU_SERVIDOR = False


def pedir(nome, args, agente, porta=None, timeout=60):
    """cliente: chama o KaniCode aberto com a chave do agente. Sem servidor → None (quem chamou usa o local)."""
    chave = cm.permissao(agente).get("chave")
    req = urllib.request.Request(f"http://127.0.0.1:{porta or PORTA}/v1/{nome}", data=json.dumps(args or {}).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {chave}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            corpo = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        corpo = json.loads(e.read().decode("utf-8") or "{}")
        raise (PermissionError if e.code in (401, 403) else ValueError)(corpo.get("erro") or str(e))
    except (OSError, ValueError):
        return None
    return {"r": corpo.get("resultado")}


if __name__ == "__main__":
    import sys
    import time
    sys.stdout.reconfigure(encoding="utf-8")
    print("cérebro HTTP em", iniciar(), "— índice:", cm.indexar())
    while True:
        time.sleep(3600)
