"""Servidor MCP "equipe" do KaniCode: as ferramentas que o Claude usa para delegar ao Codex e à Kani.

O Claude Code abre este processo (--mcp-config da sessao.py) e conversa por stdio (JSON-RPC do MCP, linha a linha).
Cada chamada roda em ajudantes.py e avisa o andamento à janela do KaniCode pelo canal de controle (127.0.0.1:PORTA,
linha "evento <json>"), que mostra o avatar animado do ajudante no canto, com tempo e tokens.

Uso: python mcp_equipe.py <pasta do projeto>
"""
import json, os, socket, sys, threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ajudantes   # noqa: E402

PORTA = 47613
PASTA = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()

FERRAMENTAS = [
    {"name": "codex",
     "description": ("Delegar uma tarefa ao Codex (OpenAI, na conta ChatGPT Plus do Pailer: NÃO gasta a cota do Claude). "
                     "Use para trabalho médio e bem definido: escrever um teste, uma função, um script, refatorar um trecho, "
                     "investigar um bug num arquivo. Escreva um CONTRATO claro: objetivo, arquivos que pode mexer, o que não "
                     "pode, critério de pronto, armadilhas conhecidas. Ele trabalha na pasta do projeto. Depois REVISE o que "
                     "ele fez (git diff / leia os arquivos) antes de dar por pronto. editar=false = só lê e responde."),
     "inputSchema": {"type": "object", "properties": {
         "contrato": {"type": "string", "description": "a tarefa completa, em português"},
         "editar": {"type": "boolean", "description": "true = pode criar/editar arquivos na pasta do projeto", "default": False}},
         "required": ["contrato"]}},
    {"name": "kani",
     "description": ("Pedir algo à Kani: modelo LOCAL pequeno (Qwen 3.5 4B), grátis e sem cota. Boa para tarefas simples "
                     "sobre um texto que você passa no contexto: resumir, classificar, extrair, reescrever curto, traduzir. "
                     "Não sabe nada do projeto além do que vier em 'contexto' e pode inventar: confira o que for fato."),
     "inputSchema": {"type": "object", "properties": {
         "pedido": {"type": "string"},
         "contexto": {"type": "string", "description": "o texto/material que ela precisa (até ~20 mil caracteres)"}},
         "required": ["pedido"]}},
]


def _avisar(ev):
    """manda o andamento para a janela do KaniCode (se ela estiver aberta; senão, segue em silêncio)"""
    try:
        with socket.create_connection(("127.0.0.1", PORTA), timeout=1) as s:
            s.sendall(("evento " + json.dumps(ev, ensure_ascii=False) + "\n").encode())
            s.recv(8)
    except OSError:
        pass


_saida = threading.Lock()


def _responder(id_, result=None, erro=None):
    msg = {"jsonrpc": "2.0", "id": id_}
    if erro:
        msg["error"] = {"code": -32000, "message": erro}
    else:
        msg["result"] = result
    with _saida:
        sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
        sys.stdout.flush()


def _chamar(id_, nome, args):
    try:
        if nome == "codex":
            r = ajudantes.codex(args.get("contrato", ""), PASTA, bool(args.get("editar")), ao_evento=_avisar)
            texto = r["texto"] + (f"\n\n[arquivos mexidos: {', '.join(map(str, r['arquivos']))}]" if r["arquivos"] else "") + \
                f"\n[Codex: {r['tokens']} tokens, {r['ms'] / 1000:.0f} s]"
        elif nome == "kani":
            r = ajudantes.kani(args.get("pedido", ""), args.get("contexto", ""), ao_evento=_avisar)
            texto = r["texto"] + f"\n[Kani (local): {r['tokens']} tokens, {r['ms'] / 1000:.0f} s]"
        else:
            raise ValueError(f"ferramenta desconhecida: {nome}")
        _responder(id_, {"content": [{"type": "text", "text": texto}], "isError": not r["ok"]})
    except Exception as e:
        _responder(id_, {"content": [{"type": "text", "text": f"falhou: {e}"}], "isError": True})


def main():
    for linha in sys.stdin:
        try:
            m = json.loads(linha)
        except ValueError:
            continue
        metodo, id_ = m.get("method"), m.get("id")
        if metodo == "initialize":
            _responder(id_, {"protocolVersion": (m.get("params") or {}).get("protocolVersion", "2025-06-18"),
                             "capabilities": {"tools": {}}, "serverInfo": {"name": "equipe-kanicode", "version": "1"}})
        elif metodo == "tools/list":
            _responder(id_, {"tools": FERRAMENTAS})
        elif metodo == "tools/call":
            p = m.get("params") or {}
            threading.Thread(target=_chamar, args=(id_, p.get("name"), p.get("arguments") or {}), daemon=True).start()
        elif metodo == "ping":
            _responder(id_, {})
        elif id_ is not None and metodo:   # pedido que não usamos: responde vazio para não travar o Claude Code
            _responder(id_, {})
    ajudantes.kani_parar()


if __name__ == "__main__":
    main()
