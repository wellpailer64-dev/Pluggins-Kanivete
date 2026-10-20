"""Uma conversa com o Claude Code (o `claude` instalado, na assinatura do Pailer) pelo modo de conversa contínua.

`claude -p --input-format stream-json --output-format stream-json`: o processo fica aberto, cada mensagem é uma linha
JSON na entrada, e as respostas chegam aos pedaços na saída. Este módulo traduz essa saída em eventos simples para a
janela (ao_evento(dict)) e guarda a conversa em <DADOS>/conversas/<sessão>.jsonl para mostrar de novo ao reabrir.
Retomar = --resume <sessão> (o Claude lembra de tudo; a janela relê o arquivo).

Eventos: inicio{sessao, modelo} · texto{d} (pedaço) · texto_novo · ferr{id, nome, entrada} · ferr_fim{id, ok, saida} ·
limite{uso, reinicia} · fim{custo, ms, tokens, erro} · saiu{erro}
"""
import json, os, shutil, subprocess, threading, time

PROMPT_KANICODE = ("Você está respondendo pelo KaniCode: uma janela pequena de conversa na área de trabalho do Pailer. "
                   "Responda curto e em português do Brasil; evite tabelas largas (a janela tem ~440 px). "
                   "Pode editar arquivos e rodar comandos comuns dentro da pasta do projeto sem perguntar.")


class Sessao:
    def __init__(self, pasta, dados, ao_evento, sessao_id=None):
        self.pasta, self.dados, self.ao_evento = pasta, dados, ao_evento
        self.sessao_id = sessao_id
        self.proc = None
        self.ocupada = False
        self._trava = threading.Lock()
        self._texto = []           # pedaços do texto da resposta em andamento (para guardar inteiro no fim)

    # ── processo ──
    def _abrir(self):
        exe = shutil.which("claude")
        if not exe:
            raise RuntimeError("não achei o Claude Code (comando claude) neste PC")
        cmd = [exe, "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--include-partial-messages",
               "--verbose", "--permission-mode", "acceptEdits", "--permission-prompts", "none",
               "--append-system-prompt", PROMPT_KANICODE]
        if self.sessao_id:
            cmd += ["--resume", self.sessao_id]
        self.proc = subprocess.Popen(cmd, cwd=self.pasta, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     encoding="utf-8", errors="replace", bufsize=1, creationflags=0x08000000)   # sem console
        threading.Thread(target=self._ler, args=(self.proc,), daemon=True).start()
        threading.Thread(target=self._ler_erro, args=(self.proc,), daemon=True).start()

    def vivo(self):
        return self.proc is not None and self.proc.poll() is None

    def enviar(self, texto):
        with self._trava:
            if not self.vivo():
                self._abrir()
            self.ocupada = True
            self._texto = []
            self._guardar({"t": "eu", "texto": texto})
            msg = {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": texto}]}}
            self.proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()

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
        if t == "system" and d.get("subtype") == "init":
            novo = d.get("session_id")
            if novo and novo != self.sessao_id:
                self.sessao_id = novo
            self.ao_evento({"t": "inicio", "sessao": self.sessao_id, "modelo": d.get("model", "")})
        elif t == "stream_event":
            e = d.get("event") or {}
            if e.get("type") == "content_block_start" and (e.get("content_block") or {}).get("type") == "text":
                self._fechar_texto()
                self.ao_evento({"t": "texto_novo"})
            elif e.get("type") == "content_block_delta" and (e.get("delta") or {}).get("type") == "text_delta":
                pedaco = e["delta"].get("text", "")
                self._texto.append(pedaco)
                self.ao_evento({"t": "texto", "d": pedaco})
        elif t == "assistant":
            for b in (d.get("message") or {}).get("content") or []:
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
            j = (info.get("unifiedWindows") or {}).get("five_hour") or {}
            self.ao_evento({"t": "limite", "uso": j.get("utilization"), "reinicia": j.get("resetsAt") or info.get("resetsAt")})
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
