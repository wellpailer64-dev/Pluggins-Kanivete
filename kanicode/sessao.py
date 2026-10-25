"""Uma conversa com o Claude Code (o `claude` instalado, na assinatura do Pailer) pelo modo de conversa contínua.

`claude -p --input-format stream-json --output-format stream-json`: o processo fica aberto, cada mensagem é uma linha
JSON na entrada, e as respostas chegam aos pedaços na saída. Este módulo traduz essa saída em eventos simples para a
janela (ao_evento(dict)) e guarda a conversa em <DADOS>/conversas/<sessão>.jsonl para mostrar de novo ao reabrir.
Retomar = --resume <sessão> (o Claude lembra de tudo; a janela relê o arquivo).

Eventos: inicio{sessao, modelo} · comandos{lista} · texto{d} (pedaço) · texto_novo · pensando · ferr{id, nome, entrada} ·
ferr_fim{id, ok, saida} · uso{saida, contexto, novo} · limite{h5, h5_zera, sem, sem_zera} · permissao{id, ferr, entrada, motivo} ·
fim{custo, ms, tokens, erro} · saiu{erro}

Permissões (etapa 3): as mesmas do cmd — modo "auto" do Claude Code e as configurações dele, sem regras "ask" a mais
(REGRAS_PERGUNTAR vazia desde 2026-10-20). O pedido chega pelo próprio canal
(--permission-prompt-tool stdio + "initialize"): control_request can_use_tool → a janela mostra o cartão → responder().
Apagar só dentro da pasta do projeto é liberado aqui mesmo, sem cartão.
"""
import json, os, re, shlex, shutil, subprocess, sys, threading, time
from collections import deque
from continuidade import Registro

# o que vai a mais que no cmd em CADA passo (medido 2026-10-20: o texto antigo era +800 tokens/passo): só o essencial;
# o como-usar dos ajudantes mora na descrição das ferramentas (mcp_equipe.py), que só entra quando o Claude as abre
PROMPT_KANICODE = ("Você está no KaniCode: janela de ~500 px na área de trabalho do Pailer. Responda curto, em pt-BR, sem "
                   "tabelas largas. Pode editar e rodar comandos comuns na pasta do projeto sem perguntar.\n"
                   "Ajudantes que poupam a cota do Claude: mcp__equipe__codex (tarefa média bem delimitada, quando poupar cota "
                   "importa mais que tempo ou o Pailer pedir 'modo equipe') e mcp__equipe__kani (texto simples, local). "
                   "Com o Pailer esperando ou precisando do app rodando, faça você.\n"
                   "Em missões com várias etapas, use mcp__equipe__missao no início, após cada etapa relevante e antes de "
                   "encerrar: guarde objetivo, concluído, próximo passo e referências (IDs de clipes/timelines, faixas, "
                   "tempos e arquivos; prefira isso a coordenadas de mouse). Após compactação ou interrupção, leia o "
                   "registro e confira o projeto real antes de continuar. Registre só resultados que verificou; o fim "
                   "de uma ferramenta não comprova que a edição ou exportação ficou correta.\n"
                   "Web: use o navegador embutido do KaniCode (`py -3.13 D:/Kanivete/Plugins/kanibrowser/kb.py ...`; abre "
                   "sozinho no painel 🌐, ao vivo), nunca Chrome externo nem o do KANIVETE; trabalhe na aba da Kani, à vista.\n"
                   "Mexeu no próprio KaniCode (D:/Kanivete/Plugins/kanicode)? No fim rode "
                   "`py -3.13 D:/Kanivete/Plugins/kanicode/recarregar.py`.\n"
                   "Mensagem terminada em '(por voz)': o Pailer falou e pode estar só OUVINDO a resposta (lida em voz alta, "
                   "frase a frase). Comece com uma frase curta que já diga o essencial; frases curtas, sem caminho de "
                   "arquivo, código ou lista longa no texto (isso fica para depois, se ele abrir a janela).")


# o que sempre passa pelo Pailer (Bash e PowerShell): enviar/publicar, apagar, fechar programa, desligar
_RISCO = ["git push", "git commit", "git reset", "git rebase", "git clean", "git checkout --", "git restore", "git branch -D",
          "gh pr", "gh release", "gh repo", "gh api", "npm publish", "rm", "rmdir", "del", "rd", "Remove-Item", "taskkill",
          "Stop-Process", "kill", "shutdown", "Restart-Computer", "Stop-Computer", "format", "curl -X POST", "Invoke-RestMethod",
          "Invoke-WebRequest -Method Post"]
# vazia = as mesmas permissões do cmd (pedido do Pailer, 2026-10-20); _RISCO fica para o "Permitir sempre" quando o auto pergunta
REGRAS_PERGUNTAR = []   # antes: [f"{f}({c}:*)" for f in ("Bash", "PowerShell") for c in _RISCO]


def risco(cmd):
    """o item de _RISCO com que o comando começa ("git push", "rm"…) ou None (é o que "Permitir sempre" libera)"""
    c = (cmd or "").strip()
    for r in sorted(_RISCO, key=len, reverse=True):
        if c == r or c.startswith(r + " "):
            return r
    return None


def sempre(dados, add=None, tirar=None):
    """lista do "Permitir sempre" (dados/sempre.json); add/tirar = um item de _RISCO"""
    p = os.path.join(dados, "sempre.json")
    try:
        with open(p, encoding="utf-8") as f:
            lst = json.load(f)
    except (OSError, ValueError):
        lst = []
    if add in _RISCO and add not in lst:
        lst.append(add)
    if tirar in lst:
        lst.remove(tirar)
    if add or tirar:
        os.makedirs(dados, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(lst, f, ensure_ascii=False)
    return lst


_APAGAR = re.compile(r"^\s*(rm|rmdir|del|rd|Remove-Item)\b", re.I)


def _partida_cerebro():
    try:
        import perfil_cerebro
        return "\n\n" + perfil_cerebro.ponto_de_partida("", 2500, quem="claude")
    except Exception:
        return ""


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
        self.modo = "auto"         # "plan" = só planeja e pede aprovação antes de mexer (botão Planejar)
        self.registro = Registro(dados, pasta, sessao_id)
        self._falha_registro_avisada = False
        self._turno = 0

    def _registrar(self, tipo, dados=None):
        try:
            self.registro.evento(tipo, dados)
        except (OSError, ValueError) as e:
            if not self._falha_registro_avisada:
                self._falha_registro_avisada = True
                self.ao_evento({"t": "aviso", "texto": f"Não foi possível guardar a continuidade: {e}"})

    # ── processo ──
    def _abrir(self):
        """abre o claude -p; o cérebro do Pailer entra no prompt (o mesmo ponto de partida dos outros agentes)"""
        exe = shutil.which("claude")
        if not exe:
            raise RuntimeError("não achei o Claude Code (comando claude) neste PC")
        cmd = [exe, "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--include-partial-messages",
               "--verbose", "--permission-mode", self.modo, "--permission-prompt-tool", "stdio",
               *(["--settings", json.dumps({"permissions": {"ask": REGRAS_PERGUNTAR}})] if REGRAS_PERGUNTAR else []),
               "--append-system-prompt", PROMPT_KANICODE + _partida_cerebro(),
               # ajudantes (mcp_equipe.py): Codex e Kani como ferramentas, liberadas sem cartão
               "--mcp-config", json.dumps({"mcpServers": {"equipe": {
                   "command": sys.executable.replace("pythonw.exe", "python.exe"),
                   "args": [os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_equipe.py"), self.pasta,
                            str(self.registro.pasta)]}}}),
               "--allowedTools", "mcp__equipe__codex", "mcp__equipe__kani", "mcp__equipe__licao", "mcp__equipe__missao", "mcp__equipe__cerebro", "mcp__equipe__tarefa_agente", "mcp__equipe__chat",
               *("mcp__equipe__brain_" + f for f in ("search", "get", "expand", "timeline", "context", "remember", "update", "proposals", "status"))]
        if self.modelo:
            cmd += ["--model", self.modelo]
        if self.sessao_id:
            cmd += ["--resume", self.sessao_id]
        import contas
        self.proc = subprocess.Popen(cmd, cwd=self.pasta, env=contas.ambiente(self.conta),
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     encoding="utf-8", errors="replace", bufsize=1, creationflags=0x08000000)   # sem console
        self.proc._kanicode_erros = []
        self.proc._kanicode_leitor_erro = threading.Thread(target=self._ler_erro, args=(self.proc,), daemon=True)
        self.proc._kanicode_leitor_erro.start()
        threading.Thread(target=self._ler, args=(self.proc,), daemon=True).start()
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

    def enviar(self, texto, imagens=None, contexto=""):
        """imagens = [{tipo: "image/png"|"image/jpeg"..., dados: base64, mini: dataURL pequena (só para a conversa guardada)}]"""
        with self._trava:
            retomada = not self.vivo()
            continuidade = self.registro.contexto() if retomada and not texto.startswith('/') else ""
            if retomada:
                self._abrir()
            if self.ocupada:   # recado no meio da tarefa: o Claude Code lê no próximo passo (mesma volta, medido)
                self._fechar_texto()
            self.ocupada = True
            self._turno += 1
            self._texto = []
            imagens = imagens or []
            self._guardar({"t": "eu", "texto": texto, "minis": [i.get("mini") for i in imagens if i.get("mini")]})
            blocos = [{"type": "image", "source": {"type": "base64", "media_type": i.get("tipo") or "image/png", "data": i["dados"]}}
                      for i in imagens if i.get("dados")]
            blocos.append({"type": "text", "text": continuidade + contexto + (texto or "(veja a imagem)")})
            self._registrar("pedido", {"texto": texto})
            try:
                self._escrever({"type": "user", "message": {"role": "user", "content": blocos}})
            except (OSError, ValueError) as e:
                self.ocupada = False
                self._registrar("interrompida", {"erro": str(e), "fase": "envio"})
                raise

    def definir_modo(self, modo):
        """auto | plan, na sessão aberta (control_request) e nas próximas"""
        self.modo = modo
        if self.vivo():
            with self._trava:
                self._escrever({"type": "control_request", "request_id": f"modo{time.time():.0f}",
                                "request": {"subtype": "set_permission_mode", "mode": modo}})

    def responder_pergunta(self, pedido_id, entrada, respostas):
        """pergunta de múltipla escolha (AskUserQuestion): as escolhas voltam dentro da própria ferramenta (answers)"""
        if not self.vivo():
            return False
        ent = dict(entrada or {})
        ent["answers"] = respostas or {}
        with self._trava:
            self._escrever({"type": "control_response", "response": {"subtype": "success", "request_id": pedido_id,
                                                                     "response": {"behavior": "allow", "updatedInput": ent}}})
        self._guardar({"t": "pergunta_fim", "id": pedido_id, "respostas": respostas})
        return True

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
        p, turno = self.proc, self._turno

        def esperar():
            time.sleep(3)
            if self.ocupada and self.proc is p and self._turno == turno and p.poll() is None:
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
        for linha in proc.stderr:
            proc._kanicode_erros[:] = (proc._kanicode_erros + [linha.rstrip()])[-20:]
            self._registrar("stderr", {"texto": linha.rstrip()})

    def _ler(self, proc):
        for linha in proc.stdout:
            try:
                d = json.loads(linha)
            except ValueError:
                self._registrar("saida_invalida", {"texto": linha.rstrip()})
                continue
            try:
                self._traduzir(d)
            except Exception as e:   # um evento estranho não derruba a conversa
                self._registrar("evento_invalido", {"erro": str(e), "evento": d})
                self.ao_evento({"t": "aviso", "texto": f"evento não entendido: {e}"})
        if proc is self.proc:
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
            leitor = getattr(proc, "_kanicode_leitor_erro", None)
            if leitor:
                leitor.join(timeout=1)
            erro = "\n".join(getattr(proc, "_kanicode_erros", [])[-6:])[-1200:]
            interrompida = self.ocupada or proc.returncode not in (0, None)
            self._fechar_texto()
            self.ocupada = False
            if interrompida:
                erro = erro or f"A execução foi interrompida (código {proc.returncode}); confira o projeto antes de retomar."
                self._registrar("interrompida", {"erro": erro, "codigo": proc.returncode})
            self.ao_evento({"t": "saiu", "erro": erro if interrompida else "",
                           "diagnostico": str(self.registro.pasta / "eventos.jsonl") if interrompida else ""})

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
                if q.get("tool_name") == "AskUserQuestion":   # múltipla escolha: a janela mostra as opções
                    ev = {"t": "pergunta", "id": d["request_id"], "perguntas": ent.get("questions") or [], "entrada": ent}
                    self._guardar(ev)
                    self.ao_evento(ev)
                    return
                if q.get("tool_name") in ("Bash", "PowerShell") and self._apagar_dentro(ent.get("command", "")):
                    self.responder(d["request_id"], True, ent)
                    return
                rs = risco(ent.get("command")) if q.get("tool_name") in ("Bash", "PowerShell") else None
                # comando composto (&&, ;, |) não passa direto: o "sempre" vale só para o comando sozinho
                if rs and rs in sempre(self.dados) and not re.search(r"&&|\|\||[;|`]|\$\(", ent.get("command", "")):
                    self.responder(d["request_id"], True, ent)
                    ev = {"t": "auto_ok", "risco": rs, "cmd": ent.get("command", "")}
                    self._guardar(ev)
                    self.ao_evento(ev)
                    return
                ev = {"t": "permissao", "id": d["request_id"], "ferr": q.get("tool_name"), "entrada": ent,
                      "motivo": q.get("description") or "", "risco": rs}
                self._guardar(ev)
                self.ao_evento(ev)
            return
        if t == "system" and str(d.get("subtype") or "").startswith("task_"):
            # Tarefas em segundo plano também ficam no registro para conferir ao retomar.
            ev = {"t": "tarefa", "sub": d.get("subtype"), "id": d.get("task_id") or d.get("id"),
                  "status": d.get("status") or "", "resumo": d.get("summary") or d.get("description") or "",
                  "arquivo": d.get("output_file") or ""}
            self._registrar("tarefa", ev)
            self.ao_evento(dict(ev, resumo=ev["resumo"][:300]))
            return
        if t == "system" and d.get("subtype") == "init":
            novo = d.get("session_id")
            if novo and novo != self.sessao_id:
                self.sessao_id = novo
            if novo:
                self._registrar("inicio", {"sessao": novo})
            self.ao_evento({"t": "inicio", "sessao": self.sessao_id, "modelo": d.get("model", "")})
        elif t == "system" and d.get("subtype") == "compact_boundary":
            self._registrar("compactacao", {"metadados": d.get("compact_metadata") or {}})
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
                    self._registrar("ferr", ev)
                    self._guardar(ev)
                    self.ao_evento(ev)
        elif t == "user":
            for b in (d.get("message") or {}).get("content") or []:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    c = b.get("content")
                    if isinstance(c, list):
                        c = "\n".join(x.get("text", "") for x in c if isinstance(x, dict))
                    ev = {"t": "ferr_fim", "id": b.get("tool_use_id"), "ok": not b.get("is_error"), "saida": str(c or "")[:3000]}
                    self._registrar("ferr_fim", dict(ev, saida=c) if b.get("is_error") else ev)
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
            if ev["erro"]:
                erros = d.get("errors") or [d.get("result") or d.get("subtype")]
                ev["mensagem"] = ('\n'.join(str(x) for x in erros) if isinstance(erros, list) else str(erros))[:1200]
                ev["diagnostico"] = str(self.registro.pasta / "eventos.jsonl")
            self._registrar("resultado", d)
            self._registrar("fim", ev)
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
            linhas = deque(f, maxlen=limite)
        eventos = []
        for linha in linhas:
            try:
                ev = json.loads(linha)
                if isinstance(ev, dict):
                    eventos.append(ev)
            except ValueError:   # queda durante uma gravação não impede reabrir o restante da conversa
                continue
        return eventos
