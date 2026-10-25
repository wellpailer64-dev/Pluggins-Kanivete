"""Servidor MCP "kanicode-brain": só as ferramentas do cérebro (brain_*), para Codex e qualquer cliente MCP.

O Claude do KaniCode já recebe as mesmas ferramentas no servidor "equipe". Registrar em outro cliente:
  Codex (~/.codex/config.toml):
    [mcp_servers.kanicode-brain]
    command = "py"
    args = ["-3.13", "D:/Kanivete/Plugins/kanicode/mcp_cerebro.py", "--agente", "codex"]
  Claude Code avulso:  claude mcp add kanicode-brain -- py -3.13 D:/Kanivete/Plugins/kanicode/mcp_cerebro.py --agente claude
O agente (permissões em cerebro/agentes.json) é fixado na linha de comando, nunca pelo pedido.
"""
import json
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdin.reconfigure(encoding="utf-8", errors="replace")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import cerebro_motor as cm   # noqa: E402

AGENTE = sys.argv[sys.argv.index("--agente") + 1] if "--agente" in sys.argv else "visitante"
_SAIDA = threading.Lock()


def _responder(id_, resultado):
    with _SAIDA:
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": id_, "result": resultado}, ensure_ascii=False, default=str) + "\n")
        sys.stdout.flush()


def _chamar(id_, nome, args):
    try:
        texto, erro = json.dumps(cm.usar(nome, args, AGENTE), ensure_ascii=False, default=str), False
    except Exception as e:
        texto, erro = f"falhou: {e}", True
    _responder(id_, {"content": [{"type": "text", "text": texto}], "isError": erro})


def main():
    cm.permissao(AGENTE)   # agente desconhecido: falha já ao abrir
    pendentes = []
    for linha in sys.stdin:
        try:
            m = json.loads(linha)
        except ValueError:
            continue
        metodo, id_ = m.get("method"), m.get("id")
        if metodo == "initialize":
            _responder(id_, {"protocolVersion": (m.get("params") or {}).get("protocolVersion", "2025-06-18"),
                             "capabilities": {"tools": {}}, "serverInfo": {"name": "kanicode-brain", "version": "1"}})
        elif metodo == "tools/list":
            _responder(id_, {"tools": cm.FERRAMENTAS})
        elif metodo == "tools/call":
            p = m.get("params") or {}
            t = threading.Thread(target=_chamar, args=(id_, p.get("name"), p.get("arguments") or {}), daemon=True)
            t.start()
            pendentes.append(t)
        elif id_ is not None and metodo:
            _responder(id_, {})
    for t in pendentes:      # entrada fechou: responde o que ainda está em andamento antes de sair
        t.join(120)


if __name__ == "__main__":
    main()
