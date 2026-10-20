"""Uma conversa com o Claude Code (o `claude` instalado, na assinatura do Pailer) pelo modo de conversa contínua.

`claude -p --input-format stream-json --output-format stream-json`: o processo fica aberto, cada mensagem é uma linha
JSON na entrada, e as respostas chegam aos pedaços na saída. Este módulo traduz essa saída em eventos simples para a
janela (ao_evento(dict)) e guarda a conversa em <DADOS>/conversas/<sessão>.jsonl para mostrar de novo ao reabrir.
Retomar = --resume <sessão> (o Claude lembra de tudo; a janela relê o arquivo).

Eventos: inicio{sessao, modelo} · comandos{lista} · texto{d} (pedaço) · texto_novo · pensando · ferr{id, nome, entrada} ·
ferr_fim{id, ok, saida} · uso{saida, contexto, novo} · limite{h5, h5_zera, sem, sem_zera} · permissao{id, ferr, entrada, motivo} ·
fim{custo, ms, tokens, erro} · saiu{erro}

Permissões (etapa 3): modo "auto" do Claude Code (o classificador dele libera o que é seguro dentro do projeto) + regras
"ask" do KaniCode para o que o Pailer quer decidir (REGRAS_PERGUNTAR). O pedido chega pelo próprio canal
(--permission-prompt-tool stdio + "initialize"): control_request can_use_tool → a janela mostra o cartão → responder().
Apagar só dentro da pasta do projeto é liberado aqui mesmo, sem cartão.
"""
import json, os, re, shlex, shutil, subprocess, sys, threading, time

PROMPT_KANICODE = ("Você está respondendo pelo KaniCode: uma janela pequena de conversa na área de trabalho do Pailer. "
                   "Responda curto e em português do Brasil; evite tabelas largas (a janela tem ~500 px). "
                   "Pode editar arquivos e rodar comandos comuns dentro da pasta do projeto sem perguntar.\n"
                   "EQUIPE: você tem dois ajudantes para economizar a cota do Claude do Pailer — mcp__equipe__codex (Codex, "
                   "conta ChatGPT Plus dele: tarefas médias e bem definidas, com contrato claro; revise o que ele fizer) e "
                   "mcp__equipe__kani (modelo local grátis: resumir, classificar, reescrever um texto que você passa). "
                   "QUANDO DELEGAR (medido 2026-10-20: mesma tarefa, você sozinho 96 s / US$ 0,84; com o Codex ~5-11 min / "
                   "US$ 0,49): faça VOCÊ quando o Pailer está esperando ou a tarefa precisa do app rodando para conferir; "
                   "delegue ao Codex quando poupar cota importa mais que tempo (conta perto do limite, fila de tarefas, ou o "
                   "Pailer pedir 'modo equipe') e a tarefa é bem delimitada. "
                   "MODO EQUIPE: no contrato do Codex vão sozinhas as regras do projeto e as lições parecidas; passe "
                   "'teste' (um comando) quando houver como conferir — a revisão automática volta com arquivos mudados, "
                   "sintaxe e teste, e você só abre arquivo se algo falhar. Quando aprender uma armadilha (sua ou do Codex), "
                   "guarde com mcp__equipe__licao, em uma frase com o como-fazer. O Codex não consegue rodar Python nem o app "
                   "(o sandbox dele no Windows esconde): quem testa é a revisão; se ela falhar, mande a correção com "
                   "continuar=true (mesma sessão dele, sem reler o projeto).")


# o que sempre passa pelo Pailer (Bash e PowerShell): enviar/publicar, apagar, fechar programa, desligar
_RISCO = ["git push", "git commit", "git reset", "git rebase", "git clean", "git checkout --", "git restore", "git branch -D",
          "gh pr", "gh release", "gh repo", "gh api", "npm publish", "rm", "rmdir", "del", "rd", "Remove-Item", "taskkill",
          "Stop-Process", "kill", "shutdown", "Restart-Computer", "Stop-Computer", "format", "curl -X POST", "Invoke-RestMethod",
          "Invoke-WebRequest -Method Post"]
REGRAS_PERGUNTAR = [f"{f}({c}:*)" for f in ("Bash", "PowerShell") for c in _RISCO]
_APAGAR = re.compile(r"^\s*(rm|rmdir|del|rd|Remove-Item)\b", re.I)


class Sessao:
    def __init__(self, pasta, dados, ao_evento, sessao_id=None):
        self.pasta, self.dados, self.ao_evento = pasta, dados, ao_evento
        self.sessao_id = sessao_id
        self.proc = None
        self.ocupada = False
        self._trava = threading.Lock()
        self._texto = []           # pedaços do texto da resposta em andamento (para guardar inteiro no fim)
        self.comandos = []         # comandos "/" (nome, descrição) que esta instalação do Claude Code tem
        self.modelo = None         # --model (None = o padrão do Claude Code)
        self.conta = None          # conta do Claude (contas.py; None = a principal)

    # ── processo ──
    def _abrir(self):
        exe = shutil.which("claude")
        if not exe:
            raise RuntimeError("não achei o Claude Code (comando claude) neste PC")
        cmd = [exe, "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--include-partial-messages",
               "--verbose", "--permission-mode", "auto", "--permission-prompt-tool", "stdio",
               "--settings", json.dumps({"permissions": {"ask": REGRAS_PERGUNTAR}}),
               "--append-system-prompt", PROMPT_KANICODE,
               # ajudantes (mcp_equipe.py): Codex e Kani como ferramentas, liberadas sem cartão
               "--mcp-config", json.dumps({"mcpServers": {"equipe": {
                   "command": sys.executable.replace("pythonw.exe", "python.exe"),
                   "args": [os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_equipe.py"), self.pasta]}}}),
               "--allowedTools", "mcp__equipe__codex", "mcp__equipe__kani", "mcp__equipe__licao"]
        if self.modelo:
            cmd += ["--model", self.modelo]
        if self.sessao_id:
            cmd += ["--resume", self.sessao_id]
        import contas
        self.proc = subprocess.Popen(cmd, cwd=self.pasta, env=contas.ambiente(self.conta),
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     encoding="utf-8", errors="replace", bufsize=1, creationflags=0x08000000)   # sem console
        threading.Thread(target=self._ler, args=(self.proc,), daemon=True).start()
        threading.Thread(target=self._ler_erro, args=(self.proc,), daemon=True).start()
        self._escrever({"type": "control_request", "request_id": "kc_ini", "request": {"subtype": "initialize"}})

    def _escrever(self, obj):
        self.proc.stdin.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def responder(self, pedido_id, permitir, entrada=None, motivo=""):
        """resposta do Pailer a um cartão de permissão"""
        if not self.vivo():
            return False
        r = {"behavior": "allow", "updatedInput": entrada or {}} if permitir else \
            {"behavior": "deny", "message": motivo or "O Pailer recusou pelo KaniCode."}
        with self._trava:
            self._escrever({"type": "control_response", "response": {"subtype": "success", "request_id": pedido_id, "response": r}})
        self._guardar({"t": "permissao_fim", "id": pedido_id, "ok": bool(permitir)})
        return True

    def _apagar_dentro(self, cmd):
        """comando de apagar cujos alvos estão TODOS dentro da pasta do projeto (esse passa sem cartão)"""
        if not _APAGAR.match(cmd or "") or re.search(r"[;&|`$*?]", cmd):
            return False
        try:
            partes = shlex.split(cmd, posix=False)[1:]
        except ValueError:
            return False
        alvos = [x.strip("\"'") for x in partes if not x.startswith("-") and not x.startswith("/")]
        raiz = os.path.normcase(os.path.abspath(self.pasta)) + os.sep
        return bool(alvos) and all(os.path.normcase(os.path.abspath(os.path.join(self.pasta, a))).startswith(raiz) for a in alvos)

    def vivo(self):
        return self.proc is not None and self.proc.poll() is None

    def enviar(self, texto):
        with self._trava:
            if not self.vivo():
                self._abrir()
            self.ocupada = True
            self._texto = []
            self._guardar({"t": "eu", "texto": texto})
            self._escrever({"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": texto}]}})

    def parar(self):
        """interrompe a resposta em andamento (pede com jeito; se não parar em 3 s, encerra o processo)"""
        if not self.vivo():
            return
        try:
            req = {"type": "control_request", "request_id": f"parar{time.time():.0f}", "request": {"subtype": "interrupt"}}
            self.proc.stdin.write(json.dumps(req) + "\n")
            self.proc.stdin.flush()
        except OSError:
            pass
        p = self.proc

        def esperar():
            time.sleep(3)
            if self.ocupada and p.poll() is None:
                p.kill()
        threading.Thread(target=esperar, daemon=True).start()

    def fechar(self):
        if self.vivo():
            try:
                self.proc.stdin.close()
                self.proc.wait(5)
            except Exception:
                self.proc.kill()

    # ── saída do claude → eventos ──
    def _ler_erro(self, proc):
        self._erro = []
        for linha in proc.stderr:
            self._erro = (self._erro + [linha.rstrip()])[-20:]

    def _ler(self, proc):
        for linha in proc.stdout:
            try:
                d = json.loads(linha)
            except ValueError:
                continue
            try:
                self._traduzir(d)
            except Exception as e:   # um evento estranho não derruba a conversa
                self.ao_evento({"t": "aviso", "texto": f"evento não entendido: {e}"})
        if proc is self.proc:
            erro = "\n".join(getattr(self, "_erro", [])[-6:])
            self.ocupada = False
            self.ao_evento({"t": "saiu", "erro": erro if proc.returncode not in (0, None) else ""})

    def _traduzir(self, d):
        t = d.get("type")
        if t == "control_response":
            r = ((d.get("response") or {}).get("response")) or {}
            if r.get("commands"):
                self.comandos = [{"nome": c.get("name"), "desc": (c.get("description") or "")[:160], "arg": c.get("argumentHint") or ""}
                                 for c in r["commands"] if c.get("name") and not c["name"].startswith("__")]
                self.ao_evento({"t": "comandos", "lista": self.comandos})
            return
        if t == "control_request":
            q = d.get("request") or {}
            if q.get("subtype") == "can_use_tool":
                ent = q.get("input") or {}
                if q.get("tool_name") in ("Bash", "PowerShell") and self._apagar_dentro(ent.get("command", "")):
                    self.responder(d["request_id"], True, ent)
                    return
                ev = {"t": "permissao", "id": d["request_id"], "ferr": q.get("tool_name"), "entrada": ent,
                      "motivo": q.get("description") or ""}
                self._guardar(ev)
                self.ao_evento(ev)
            return
        if t == "system" and d.get("subtype") == "init":
            novo = d.get("session_id")
            if novo and novo != self.sessao_id:
                self.sessao_id = novo
            self.ao_evento({"t": "inicio", "sessao": self.sessao_id, "modelo": d.get("model", "")})
        elif t == "stream_event":
            e = d.get("event") or {}
            bloco = (e.get("content_block") or {}).get("type")
            if e.get("type") == "message_start":
                self._streamou = False
            if e.get("type") in ("message_start", "message_delta"):
                u = e.get("usage") or (e.get("message") or {}).get("usage") or {}
                if u:
                    self.ao_evento({"t": "uso", "saida": u.get("output_tokens") or 0, "novo": e.get("type") == "message_start",
                                    "contexto": (u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0)
                                    + (u.get("cache_creation_input_tokens") or 0)})
            elif e.get("type") == "content_block_start" and bloco == "thinking":
                self.ao_evento({"t": "pensando"})
            elif e.get("type") == "content_block_start" and bloco == "text":
                self._fechar_texto()
                self.ao_evento({"t": "texto_novo"})
            elif e.get("type") == "content_block_delta" and (e.get("delta") or {}).get("type") == "text_delta":
                self._streamou = True
                pedaco = e["delta"].get("text", "")
                self._texto.append(pedaco)
                self.ao_evento({"t": "texto", "d": pedaco})
        elif t == "assistant":
            # comando interno ("/context", "/usage"...): a resposta vem inteira, sem os pedaços (modelo "<synthetic>")
            sintetica = (d.get("message") or {}).get("model") == "<synthetic>" or not getattr(self, "_streamou", True)
            for b in (d.get("message") or {}).get("content") or []:
                if b.get("type") == "text" and sintetica and b.get("text"):
                    self._fechar_texto()
                    self.ao_evento({"t": "texto_novo"})
                    self._texto.append(b["text"])
                    self.ao_evento({"t": "texto", "d": b["text"]})
                if b.get("type") == "tool_use":
                    ev = {"t": "ferr", "id": b.get("id"), "nome": b.get("name"), "entrada": b.get("input") or {}}
                    self._guardar(ev)
                    self.ao_evento(ev)
        elif t == "user":
            for b in (d.get("message") or {}).get("content") or []:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    c = b.get("content")
                    if isinstance(c, list):
                        c = "\n".join(x.get("text", "") for x in c if isinstance(x, dict))
                    ev = {"t": "ferr_fim", "id": b.get("tool_use_id"), "ok": not b.get("is_error"), "saida": str(c or "")[:3000]}
                    self._guardar(ev)
                    self.ao_evento(ev)
        elif t == "rate_limit_event":
            info = d.get("rate_limit_info") or {}
            w = info.get("unifiedWindows") or {}
            h5, sem = w.get("five_hour") or {}, w.get("seven_day") or {}
            self.ao_evento({"t": "limite", "h5": h5.get("utilization"), "h5_zera": h5.get("resetsAt"),
                            "sem": sem.get("utilization"), "sem_zera": sem.get("resetsAt"), "estado": info.get("status")})
        elif t == "result":
            self._fechar_texto()
            self.ocupada = False
            u = d.get("usage") or {}
            ev = {"t": "fim", "custo": d.get("total_cost_usd"), "ms": d.get("duration_ms"), "erro": d.get("subtype") != "success",
                  "tokens": (u.get("input_tokens") or 0) + (u.get("output_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0)}
            self._guardar(ev)
            self.ao_evento(ev)

    def _fechar_texto(self):
        if self._texto:
            self._guardar({"t": "kc", "texto": "".join(self._texto)})
            self._texto = []

    # ── conversa guardada ──
    def _arquivo(self):
        return os.path.join(self.dados, "conversas", f"{self.sessao_id}.jsonl") if self.sessao_id else None

    def _guardar(self, ev):
        if not self.sessao_id:   # a 1ª mensagem chega antes do id: guarda quando ele vier
            self._pendentes = getattr(self, "_pendentes", []) + [ev]
            return
        os.makedirs(os.path.join(self.dados, "conversas"), exist_ok=True)
        with open(self._arquivo(), "a", encoding="utf-8") as f:
            for x in getattr(self, "_pendentes", []) + [ev]:
                f.write(json.dumps(x, ensure_ascii=False) + "\n")
        self._pendentes = []

    def historico(self, limite=400):
        a = self._arquivo()
        if not a or not os.path.isfile(a):
            return []
        with open(a, encoding="utf-8") as f:
            linhas = f.readlines()[-limite:]
        return [json.loads(l) for l in linhas if l.strip()]
