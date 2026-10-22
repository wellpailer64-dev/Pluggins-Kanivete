"""Servidor MCP "equipe" do KaniCode: as ferramentas que o Claude usa para delegar ao Codex e à Kani.

O Claude Code abre este processo (--mcp-config da sessao.py) e conversa por stdio (JSON-RPC do MCP, linha a linha).
Cada chamada roda em ajudantes.py e avisa o andamento à janela do KaniCode pelo canal de controle (127.0.0.1:PORTA,
linha "evento <json>"), que mostra o avatar animado do ajudante no canto, com tempo e tokens.

Uso: python mcp_equipe.py <pasta do projeto>
"""
import json, os, socket, subprocess, sys, threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# o canal com o Claude Code é UTF-8; o padrão do Windows (cp1252) embaralhava os acentos do contrato e um caractere
# fora dele (→, ✓…) derrubava a resposta em silêncio — o Claude ficava esperando para sempre
sys.stdin.reconfigure(encoding="utf-8", errors="replace")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import ajudantes   # noqa: E402
import licoes      # noqa: E402

PORTA = 47613
PASTA = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
CONTINUIDADE = sys.argv[2] if len(sys.argv) > 2 else None
_missao_trava = threading.Lock()
_ULTIMA = {"codex": None}   # última sessão do Codex nesta conversa ("continuar")

FERRAMENTAS = [
    {"name": "missao",
     "description": ("Ler ou atualizar o ponto de retomada desta sessão, guardado em disco. Sem campos, consulta. "
                     "Em missão longa: guarde no início, após cada etapa relevante e antes de encerrar. Após compactação "
                     "ou interrupção, leia e confira o projeto real antes de repetir ações. Concluído deve conter "
                     "somente o que você verificou; referências devem usar IDs, caminhos, faixas e tempos, evitando pixels. "
                     "As listas enviadas substituem as anteriores. Não marque a missão concluída só porque uma ferramenta terminou."),
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
         "objetivo": {"type": "string"}, "concluido": {"type": "array", "items": {"type": "string"}},
         "proximo": {"type": "string"}, "referencias": {"type": "array", "items": {"type": "object"}},
         "observacoes": {"type": "string"}}}},
    {"name": "codex",
     "description": ("Delegar uma tarefa ao Codex (OpenAI, na conta ChatGPT Plus do Pailer: NÃO gasta a cota do Claude). "
                     "Use para trabalho médio e bem definido: escrever um teste, uma função, um script, refatorar um trecho, "
                     "investigar um bug num arquivo. Escreva um CONTRATO claro: objetivo, arquivos que pode mexer, o que não "
                     "pode, critério de pronto. As REGRAS do projeto e as LIÇÕES já aprendidas parecidas com a tarefa vão "
                     "junto sozinhas. Com editar=true, ao terminar o KaniCode confere sozinho: lista os arquivos mudados (com "
                     "o resumo do diff), checa a sintaxe de cada um e roda o comando de 'teste', se você der um. Leia o "
                     "relatório e só abra os arquivos se algo falhar ou parecer estranho. editar=false = só lê e responde. "
                     "Custo medido (2026-10-20): você sozinho ~96 s/US$ 0,84; com o Codex ~5-11 min/US$ 0,49. O Codex NÃO "
                     "roda Python nem o app (sandbox do Windows): quem testa é a revisão; se ela falhar, mande a correção "
                     "com continuar=true. Armadilha aprendida (sua ou dele): guarde com a ferramenta licao."),
     "inputSchema": {"type": "object", "properties": {
         "contrato": {"type": "string", "description": "a tarefa completa, em português"},
         "editar": {"type": "boolean", "description": "true = pode criar/editar arquivos na pasta do projeto", "default": False},
         "teste": {"type": "string", "description": "comando para conferir no fim (ex.: py -3.13 testes/teste_x.py); roda na pasta do projeto"},
         "continuar": {"type": "boolean", "description": "true = continua a ÚLTIMA sessão do Codex neste projeto (ele lembra do que fez; use para mandar correções depois da revisão)", "default": False},
         "prazo_min": {"type": "integer", "description": "minutos até o KaniCode encerrar o Codex (padrão 10)", "default": 10}},
         "required": ["contrato"]}},
    {"name": "licao",
     "description": ("Guardar uma LIÇÃO deste projeto (uma armadilha, um jeito certo de fazer) depois de revisar um trabalho "
                     "ou de errar e acertar. Ela entra sozinha nos próximos contratos do Codex parecidos. Uma frase, concreta, "
                     "com o como-fazer (ex.: 'Comparar monitor: desligue vePrSegEm e aqueça os dois estados')."),
     "inputSchema": {"type": "object", "properties": {
         "texto": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}}}, "required": ["texto"]}},
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


def _git(*args):
    try:
        return subprocess.run(["git", *args], cwd=PASTA, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=60, creationflags=0x08000000).stdout
    except Exception:
        return ""


def _mudados(extras=()):
    """arquivos já versionados que estão modificados (git diff: rápido) + os que o Codex disse que mexeu (os novos),
    cada um com o hash do conteúdo para comparar antes × depois. `git status -uall` levava ~1 min neste projeto (muito
    arquivo solto) e passava do limite: a revisão dizia "nenhum arquivo mudou" — medido 2026-10-20."""
    nomes = set(_git("diff", "--name-only").splitlines())
    for a in extras:
        try:
            nomes.add(os.path.relpath(os.path.join(PASTA, a), PASTA).replace("\\", "/"))
        except ValueError:
            pass
    out = {}
    for caminho in nomes:
        caminho = caminho.strip().strip('"')
        if not caminho:
            continue
        try:
            with open(os.path.join(PASTA, caminho), "rb") as f:
                out[caminho] = hash(f.read())
        except OSError:
            out[caminho] = None
    return out


def _sintaxe(caminho):
    """None = ok; texto = erro"""
    p = os.path.join(PASTA, caminho)
    ext = os.path.splitext(p)[1].lower()
    cmd = ([sys.executable.replace("pythonw.exe", "python.exe"), "-m", "py_compile", p] if ext == ".py"
           else ["node", "--check", p] if ext in (".js", ".mjs") else None)
    if ext == ".json":
        try:
            with open(p, encoding="utf-8") as f:
                json.load(f)
            return None
        except Exception as e:
            return str(e)[:300]
    if not cmd:
        return None
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=0x08000000)
    return None if r.returncode == 0 else (r.stderr or r.stdout)[-400:]


TESTE_PRAZO = 180   # s: teste da revisão que passa disso é dado como TRAVADO (não como falha do código)


def _revisar(antes, teste, arquivos_codex=()):
    """o que o Codex mudou + sintaxe + teste: o relatório que o Claude lê no lugar dos arquivos"""
    depois = _mudados(arquivos_codex)
    mexidos = sorted(k for k, h in depois.items() if antes.get(k, "∅") != h)
    linhas = ["REVISÃO AUTOMÁTICA DO KANICODE:"]
    if not mexidos:
        linhas.append("- nenhum arquivo mudou")
    else:
        stat = _git("diff", "--stat", "--", *mexidos).strip().splitlines()
        linhas.append(f"- {len(mexidos)} arquivo(s) mudado(s): " + ", ".join(mexidos))
        if stat:
            linhas.append("- diff: " + stat[-1].strip())
        _avisar({"t": "ajudante", "quem": "codex", "fase": "passo", "texto": f"conferindo a sintaxe de {len(mexidos)} arquivo(s)"})
        erros = [(m, e) for m in mexidos if os.path.isfile(os.path.join(PASTA, m)) for e in [_sintaxe(m)] if e]
        linhas.append("- sintaxe: ok" if not erros else "- sintaxe com ERRO: " + "; ".join(f"{m}: {e}" for m, e in erros))
    if teste:
        _avisar({"t": "ajudante", "quem": "codex", "fase": "passo", "texto": "rodando o teste: " + teste[:60]})
        p = subprocess.Popen(teste, cwd=PASTA, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             encoding="utf-8", errors="replace", creationflags=0x08000000)
        try:
            saida, _ = p.communicate(timeout=TESTE_PRAZO)
            saida = (saida or "").strip().splitlines()
            linhas.append(f"- teste ({teste}): {'PASSOU' if p.returncode == 0 else 'FALHOU (código ' + str(p.returncode) + ')'}")
            linhas += ["    " + l for l in saida[-15:]]
        except subprocess.TimeoutExpired:
            # shell=True: o teste é neto do cmd; taskkill /T derruba a árvore toda
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True, creationflags=0x08000000)
            linhas.append(f"- teste ({teste}): TRAVOU (passou de {TESTE_PRAZO // 60} min) — não é falha confirmada do código; "
                          "rode você mesmo para ver onde para")
    return "\n".join(linhas)


def _chamar(id_, nome, args):
    try:
        if nome == "codex":
            editar, teste = bool(args.get("editar")), (args.get("teste") or "").strip()
            contrato = args.get("contrato", "")
            extra = licoes.anexo(PASTA, contrato)
            if extra:
                contrato += "\n\n" + extra
            antes = _mudados() if editar else {}
            retomar = _ULTIMA["codex"] if args.get("continuar") else None
            if retomar:
                contrato = args.get("contrato", "")   # a sessão dele já tem as regras e lições
            r = ajudantes.codex(contrato, PASTA, editar, ao_evento=_avisar, retomar=retomar,
                                prazo=max(60, int(args.get("prazo_min") or 10) * 60))
            if r.get("sessao"):
                _ULTIMA["codex"] = r["sessao"]
            texto = r["texto"] + f"\n\n[Codex: {r['tokens']} tokens, {r['ms'] / 1000:.0f} s" + \
                (" — PASSOU DO PRAZO e foi encerrado" if r.get("estourou") else "") + "]"
            if editar:
                texto += "\n\n" + _revisar(antes, teste, r.get("arquivos") or ())
            if extra:
                texto += f"\n\n[foram junto: regras do projeto + {len(licoes.relevantes(PASTA, args.get('contrato', '')))} lição(ões)]"
        elif nome == "missao":
            if not CONTINUIDADE:
                raise ValueError("esta sessão não informou o registro de continuidade; reabra o KaniCode")
            from continuidade import missao
            with _missao_trava:
                registro = missao(CONTINUIDADE, args)
            r, texto = {"ok": True}, json.dumps(registro, ensure_ascii=False)
        elif nome == "licao":
            ok = licoes.gravar(PASTA, args.get("texto", ""), args.get("tags"))
            _avisar({"t": "licao", "texto": args.get("texto", ""), "nova": ok})
            r, texto = {"ok": True}, ("lição guardada" if ok else "essa lição já estava guardada")
        elif nome == "kani":
            r = ajudantes.kani(args.get("pedido", ""), args.get("contexto", ""), ao_evento=_avisar)
            texto = r["texto"] + f"\n[Kani (local): {r['tokens']} tokens, {r['ms'] / 1000:.0f} s]"
        else:
            raise ValueError(f"ferramenta desconhecida: {nome}")
        _responder(id_, {"content": [{"type": "text", "text": texto}], "isError": not r["ok"]})
    except Exception as e:
        try:
            _responder(id_, {"content": [{"type": "text", "text": f"falhou: {e}"}], "isError": True})
        except Exception:   # nunca deixar o Claude sem resposta
            _responder(id_, {"content": [{"type": "text", "text": "falhou (erro ao montar a resposta)"}], "isError": True})


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
