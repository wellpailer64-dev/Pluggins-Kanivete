"""Os ajudantes do KaniCode: Codex (na conta ChatGPT Plus do Pailer) e Kani (modelo local, grátis).

Usados de dois jeitos:
  - pelo Claude, como ferramentas (mcp_equipe.py → codex()/kani()): ele delega uma parte e revisa o resultado;
  - direto pelo Pailer ("Quem responde" na janela).
Cada chamada avisa o andamento por ao_evento({...}) → a janela mostra o avatar animado no canto, tempo e tokens.

Eventos: ajudante{quem, fase: "inicio"|"passo"|"fim", texto, tokens, cota, ms, ok}
  quem = "codex" | "kani"; cota (Codex) = {h5, h5_zera, sem, sem_zera} lida da sessão dele (~/.codex/sessions).
"""
import glob, json, os, shutil, socket, subprocess, threading, time, urllib.request

CODEX_MODELO = "gpt-6.1-sol"   # o que a conta Plus aceita no Codex (os outros dão "not supported with a ChatGPT account")
KANI_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                        "CANIVETE DO PAILER", "dist", "CaniveteDoPailer", "modelos_ia", "kani")
KANI_GGUF = "Qwen3.5-4B-Q5_K_M.gguf"
KANI_OCIOSA = 180   # s sem uso: a Kani sai da placa de vídeo
_SEM_JANELA = 0x08000000


def _nada(_ev):
    pass


# ─────────────────────────── Codex ───────────────────────────
def _codex_cota(thread_id):
    """cotas do Codex (5 h e semana) gravadas pelo próprio Codex no arquivo da sessão"""
    try:
        base = os.path.join(os.path.expanduser("~"), ".codex", "sessions")
        arqs = glob.glob(os.path.join(base, "*", "*", "*", f"*{thread_id}*.jsonl")) if thread_id else []
        if not arqs:
            arqs = sorted(glob.glob(os.path.join(base, "*", "*", "*", "*.jsonl")), key=os.path.getmtime)[-1:]
        cota = None
        with open(arqs[-1], encoding="utf-8") as f:
            for linha in f:
                if '"rate_limits"' in linha:
                    d = json.loads(linha)
                    rl = ((d.get("payload") or {}).get("rate_limits")) or d.get("rate_limits") or {}
                    p, s = rl.get("primary") or {}, rl.get("secondary") or {}
                    cota = {"h5": (p.get("used_percent") or 0) / 100, "h5_zera": p.get("resets_at"),
                            "sem": (s.get("used_percent") or 0) / 100, "sem_zera": s.get("resets_at")}
        return cota
    except Exception:
        return None


# O isolamento (sandbox) do Codex no Windows esconde o Python e o app (py e até o caminho completo "não existem"):
# medido 2026-10-20 — sem este aviso ele gastava minutos caçando um jeito de testar em vez de entregar.
AVISO_AMBIENTE = ("AMBIENTE: no seu terminal isolado NÃO existe Python nem o app (py, python e o caminho completo falham) e "
                  "não há acesso à porta 9333. NÃO tente rodar testes nem procure alternativas: escreva o código com cuidado, "
                  "confira lendo, e termine. O KaniCode roda a sintaxe e o teste logo depois e devolve o resultado.")
CODEX_PRAZO = 600   # s: passou disso, o KaniCode encerra o Codex e devolve o que tiver (nunca esperar sem fim)


def codex(tarefa, pasta, editar=False, ao_evento=_nada, parar=None, retomar=None, prazo=CODEX_PRAZO):
    """roda uma tarefa no Codex (codex exec) na pasta; retomar = id da sessão anterior (continua sem reler tudo).
    Devolve {ok, texto, tokens, arquivos, comandos, cota, ms, sessao, estourou}"""
    exe = shutil.which("codex")
    if not exe:
        raise RuntimeError("o Codex não está instalado (npm install -g @openai/codex)")
    t0 = time.time()
    ao_evento({"t": "ajudante", "quem": "codex", "fase": "inicio", "texto": ("continuando: " if retomar else "") + tarefa[:160]})
    sand = ["-s", "workspace-write" if editar else "read-only"]
    if retomar:
        cmd = [exe, "exec", "resume", "--json", "--skip-git-repo-check", "-m", CODEX_MODELO, *sand, retomar, "-"]
    else:
        cmd = [exe, "exec", "--json", "--skip-git-repo-check", "-m", CODEX_MODELO, *sand, "-"]
    p = subprocess.Popen(cmd, cwd=pasta, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         encoding="utf-8", errors="replace", creationflags=_SEM_JANELA)
    p.stdin.write(tarefa + "\n\n" + AVISO_AMBIENTE)
    p.stdin.close()
    estourou = threading.Event()

    def vigia():   # prazo: encerra o Codex (e o que ele abriu) e deixa a leitura terminar com o que já veio
        while p.poll() is None:
            if time.time() - t0 > prazo or (parar and parar.is_set()):
                estourou.set()
                subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True, creationflags=_SEM_JANELA)
                return
            time.sleep(1)
    threading.Thread(target=vigia, daemon=True).start()
    textos, arquivos, comandos, tokens, thread = [], [], [], 0, retomar
    for linha in p.stdout:
        try:
            d = json.loads(linha)
        except ValueError:
            continue
        if d.get("type") == "thread.started":
            thread = d.get("thread_id")
        it = d.get("item") or {}
        if d.get("type") == "item.completed":
            tipo = it.get("type")
            if tipo == "agent_message" and it.get("text"):
                textos.append(it["text"])
            elif tipo == "command_execution":
                comandos.append(it.get("command", ""))
                ao_evento({"t": "ajudante", "quem": "codex", "fase": "passo", "texto": "rodou " + str(it.get("command", ""))[:90]})
            elif tipo == "file_change":
                for ch in it.get("changes") or []:
                    arquivos.append(ch.get("path"))
                    ao_evento({"t": "ajudante", "quem": "codex", "fase": "passo", "texto": "editou " + os.path.basename(str(ch.get("path")))})
            elif tipo == "reasoning":
                ao_evento({"t": "ajudante", "quem": "codex", "fase": "passo", "texto": "pensando"})
        elif d.get("type") == "turn.completed":
            u = d.get("usage") or {}
            tokens += (u.get("input_tokens") or 0) - (u.get("cached_input_tokens") or 0) + (u.get("output_tokens") or 0)
            ao_evento({"t": "ajudante", "quem": "codex", "fase": "passo", "texto": "terminando", "tokens": tokens})
    p.wait()
    erro = "" if p.returncode == 0 else (p.stderr.read() or "")[-400:]
    if estourou.is_set():
        erro = f"o Codex passou do prazo de {prazo // 60} min e foi encerrado (o que ele já escreveu ficou nos arquivos)"
    res = {"ok": p.returncode == 0 and not estourou.is_set(), "texto": "\n\n".join(textos + ([erro] if estourou.is_set() else [])) or erro,
           "tokens": tokens, "arquivos": arquivos, "comandos": comandos, "cota": _codex_cota(thread),
           "ms": int((time.time() - t0) * 1000), "sessao": thread, "estourou": estourou.is_set()}
    ao_evento({"t": "ajudante", "quem": "codex", "fase": "fim", "ok": res["ok"], "tokens": tokens, "cota": res["cota"], "ms": res["ms"],
               "texto": (textos[-1] if textos else erro)[:200]})
    return res


# ─────────────────────────── Kani (llama.cpp local) ───────────────────────────
_kani = {"proc": None, "porta": None, "uso": 0.0}
_kani_trava = threading.Lock()


def kani_disponivel():
    return os.path.isfile(os.path.join(KANI_DIR, "bin", "llama-server.exe")) and os.path.isfile(os.path.join(KANI_DIR, KANI_GGUF))


def _porta_livre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _kani_subir(ao_evento):
    with _kani_trava:
        p = _kani["proc"]
        if p and p.poll() is None:
            return _kani["porta"]
        if not kani_disponivel():
            raise RuntimeError("a Kani não está instalada (abra a Kani uma vez no KANIVETE para baixar o modelo)")
        ao_evento({"t": "ajudante", "quem": "kani", "fase": "passo", "texto": "acordando (carregando o modelo)"})
        porta = _porta_livre()
        exe = os.path.join(KANI_DIR, "bin", "llama-server.exe")
        p = subprocess.Popen([exe, "-m", os.path.join(KANI_DIR, KANI_GGUF), "--host", "127.0.0.1", "--port", str(porta), "-c", "8192",
                              "-ngl", "99", "--jinja", "-np", "1"], cwd=os.path.dirname(exe), stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, creationflags=_SEM_JANELA)
        for _ in range(240):
            if p.poll() is not None:
                raise RuntimeError("o motor da Kani fechou ao carregar (memória da placa?)")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{porta}/health", timeout=2) as r:
                    if json.loads(r.read() or b"{}").get("status") == "ok":
                        break
            except Exception:
                pass
            time.sleep(0.5)
        _kani.update(proc=p, porta=porta)
        threading.Thread(target=_kani_vigiar, daemon=True).start()
        return porta


def _kani_vigiar():
    """sem uso por KANI_OCIOSA s: a Kani sai da placa (o KANIVETE e os renders precisam dela)"""
    while _kani["proc"] and _kani["proc"].poll() is None:
        time.sleep(15)
        if time.time() - _kani["uso"] > KANI_OCIOSA:
            kani_parar()


def kani_parar():
    p = _kani.get("proc")
    if p and p.poll() is None:
        p.terminate()
    _kani.update(proc=None, porta=None)


def kani(pedido, contexto="", ao_evento=_nada):
    """pergunta à Kani (Qwen local, sem custo); devolve {ok, texto, tokens, ms}"""
    t0 = time.time()
    _kani["uso"] = time.time()
    ao_evento({"t": "ajudante", "quem": "kani", "fase": "inicio", "texto": pedido[:160]})
    try:
        porta = _kani_subir(ao_evento)
        msgs = [{"role": "system", "content": "Você é a Kani, assistente do KANIVETE. Responda em português do Brasil, direto ao ponto."}]
        if contexto:
            msgs.append({"role": "user", "content": "Contexto:\n" + contexto[:20000]})
        msgs.append({"role": "user", "content": pedido})
        corpo = json.dumps({"messages": msgs, "temperature": 0.3, "chat_template_kwargs": {"enable_thinking": False}}).encode()
        ao_evento({"t": "ajudante", "quem": "kani", "fase": "passo", "texto": "escrevendo"})
        req = urllib.request.Request(f"http://127.0.0.1:{porta}/v1/chat/completions", corpo, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=600) as r:
            d = json.loads(r.read())
        texto = d["choices"][0]["message"]["content"].strip()
        tokens = (d.get("usage") or {}).get("total_tokens") or 0
        res = {"ok": True, "texto": texto, "tokens": tokens, "ms": int((time.time() - t0) * 1000)}
    except Exception as e:
        res = {"ok": False, "texto": str(e), "tokens": 0, "ms": int((time.time() - t0) * 1000)}
    _kani["uso"] = time.time()
    ao_evento({"t": "ajudante", "quem": "kani", "fase": "fim", "ok": res["ok"], "tokens": res["tokens"], "ms": res["ms"],
               "texto": res["texto"][:200]})
    return res
