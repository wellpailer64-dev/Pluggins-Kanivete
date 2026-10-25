"""Os ajudantes do KaniCode: Codex (na conta ChatGPT Plus do Pailer) e Kani (modelo local, grátis).

Usados de dois jeitos:
  - pelo Claude, como ferramentas (mcp_equipe.py → codex()/kani()): ele delega uma parte e revisa o resultado;
  - direto pelo Pailer ("Quem responde" na janela).
Cada chamada avisa o andamento por ao_evento({...}) → a janela mostra o avatar animado no canto, tempo e tokens.

Eventos: ajudante{quem, fase: "inicio"|"passo"|"fim", texto, tokens, cota, ms, ok}
  quem = "codex" | "kani"; cota (Codex) = {h5, h5_zera, sem, sem_zera} lida da sessão dele (~/.codex/sessions).
"""
import glob, json, os, re, shutil, socket, subprocess, threading, time, urllib.request

import codex_alteracoes
import codex_contexto
import codex_processo

CODEX_MODELO = "gpt-6.1-sol"   # o que a conta Plus aceita no Codex (os outros dão "not supported with a ChatGPT account")
KANI_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))),
                        "CANIVETE DO PAILER", "dist", "CaniveteDoPailer", "modelos_ia", "kani")
KANI_GGUF = "Qwen3.5-4B-Q5_K_M.gguf"
KANI_OCIOSA = 180   # s sem uso: a Kani sai da placa de vídeo
_SEM_JANELA = 0x08000000


def _nada(_ev):
    pass


# ─────────────────────────── Codex ───────────────────────────
def _codex_cauda(thread_id):
    try:
        if not thread_id:
            return []
        base = os.path.join(os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex"), "sessions")
        arqs = glob.glob(os.path.join(base, "*", "*", "*", f"*{thread_id}*.jsonl"))
        if not arqs:
            return []
        with open(arqs[-1], "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - 262144))
            return f.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return []


def _codex_uso(thread_id):
    """Último acumulado da sessão; permite medir só o turno atual no exec resume."""
    for linha in reversed(_codex_cauda(thread_id)):
        if '"token_count"' not in linha:
            continue
        try:
            d = json.loads(linha)
            uso = ((d.get("payload") or {}).get("info") or {}).get("total_token_usage")
            if uso is not None:
                return uso
        except ValueError:
            continue
    return None


def _codex_cota(thread_id):
    """cotas do Codex (5 h e semana) gravadas pelo próprio Codex no arquivo da sessão"""
    try:
        for linha in reversed(_codex_cauda(thread_id)):
            if '"rate_limits"' in linha:
                try:
                    d = json.loads(linha)
                except ValueError:
                    continue
                rl = ((d.get("payload") or {}).get("rate_limits")) or d.get("rate_limits") or {}
                p, s = rl.get("primary") or {}, rl.get("secondary") or {}
                if p or s:
                    return {"h5": (p.get("used_percent") or 0) / 100, "h5_zera": p.get("resets_at"),
                            "sem": (s.get("used_percent") or 0) / 100, "sem_zera": s.get("resets_at")}
        return None
    except Exception:
        return None


CODEX_PRAZO = 3600  # s (1 h): permite fluxos longos; Parar continua interrompendo a qualquer momento


def _conversa(tarefa):
    return codex_contexto.conversa(tarefa)


def codex(tarefa, pasta, editar=False, ao_evento=_nada, parar=None, retomar=None, prazo=CODEX_PRAZO, esforco=None):
    """roda uma tarefa no Codex (codex exec) na pasta; retomar = id da sessão anterior (continua sem reler tudo).
    Devolve {ok, texto, tokens, uso, arquivos, comandos, cota, ms, sessao, estourou, cancelado}.
    tokens mantém a medida antiga (entrada não cacheada + saída), não um preço em dinheiro."""
    exe = shutil.which("codex")
    if not exe:
        raise RuntimeError("o Codex não está instalado (npm install -g @openai/codex)")
    esforco = esforco or codex_contexto.esforco(tarefa)
    if esforco not in ("low", "medium", "high"):
        raise ValueError("esforço do Codex deve ser low, medium ou high")
    def avisar(fase, texto, **extra):
        ao_evento({"t": "ajudante", "quem": "codex", "fase": fase, "texto": texto, **extra})
    avisar("inicio", ("continuando: " if retomar else "") + tarefa[:160], esforco=esforco)
    # Opções de exec vêm ANTES de resume. Configuração só desta chamada, sem mudar ~/.codex.
    cmd = [exe, "exec", "-s", "danger-full-access" if editar else "read-only",
           "-c", f'model_reasoning_effort="{esforco}"', "-c", 'model_verbosity="low"',
           "-c", "tool_output_token_limit=2500"]
    if retomar:
        cmd += ["resume"]
    cmd += ["--json", "--skip-git-repo-check", "-m", CODEX_MODELO]
    cmd += [retomar, "-"] if retomar else ["-"]
    entrada = codex_contexto.preparar(tarefa, pasta, editar, retomar)
    textos, arquivos, comandos, erros = [], [], [], []
    anterior = _codex_uso(retomar) if retomar else {}
    campos_uso = {"entrada": "input_tokens", "cache": "cached_input_tokens",
                  "saida": "output_tokens", "raciocinio": "reasoning_output_tokens"}
    uso = {"entrada": 0, "cache": 0, "saida": 0, "raciocinio": 0}
    thread, completo, falhou = retomar, False, False
    ultima_medicao = None
    captura = codex_alteracoes.Captura(pasta) if editar else None

    def medir():
        nonlocal ultima_medicao
        acumulado = _codex_uso(thread) if thread else None
        if acumulado is None or anterior is None:
            return
        parcial = {chave: max(0, (acumulado.get(campo) or 0) - ((anterior or {}).get(campo) or 0))
                   for chave, campo in campos_uso.items()}
        if parcial == ultima_medicao:
            return
        ultima_medicao = dict(parcial)
        parcial["novos"] = max(0, parcial["entrada"] - parcial["cache"])
        parcial["total"] = parcial["entrada"] + parcial["saida"]
        ao_evento({"t": "codex_uso", "quem": "codex", "uso": parcial,
                   "tokens": parcial["novos"] + parcial["saida"], "cota": _codex_cota(thread)})

    def receber(linha):
        nonlocal thread, completo, falhou
        try:
            d = json.loads(linha)
        except ValueError:
            return
        if not isinstance(d, dict):
            return
        if d.get("type") == "thread.started":
            thread = d.get("thread_id") or thread
            avisar("passo", "conectado", sessao=thread)
        elif d.get("type") == "turn.started":
            avisar("passo", "pensando")
        elif d.get("type") in ("error", "turn.failed"):
            erro = d.get("error") or d.get("message") or "o turno do Codex falhou"
            mensagem = str(erro.get("message", erro) if isinstance(erro, dict) else erro)
            erros.append(mensagem)
            if re.search(r"usage.?limit|hit your.*limit|rate.?limit.*(?:reach|exceed)|insufficient_quota|cota.*esgot", json.dumps(d), re.I):
                ao_evento({"t": "codex_limite", "mensagem": mensagem, "cota": _codex_cota(thread)})
            falhou = falhou or d.get("type") == "turn.failed"
        it = d.get("item") or {}
        tipo = it.get("type")
        if d.get("type") in ("item.started", "item.updated"):
            if tipo == "agent_message" and it.get("text"):
                ao_evento({"t": "codex_progresso", "id": it.get("id"), "texto": it["text"]})
            atividade = {"command_execution": "executando " + str(it.get("command", ""))[:120],
                         "mcp_tool_call": "usando " + str(it.get("tool", "ferramenta")),
                         "web_search": "pesquisando", "file_change": "editando arquivos", "reasoning": "pensando"}
            if tipo in atividade:
                avisar("passo", atividade[tipo], id=it.get("id"), operacao="inicio",
                       entrada={"command": str(it.get("command", ""))[:12000], "changes": it.get("changes") or [],
                                **(it.get("arguments") if isinstance(it.get("arguments"), dict) else {})})
        if d.get("type") == "item.completed":
            if tipo == "agent_message" and it.get("text"):
                textos.append(it["text"])
                avisar("passo", it["text"][:160])
                ao_evento({"t": "codex_progresso", "id": it.get("id"), "texto": it["text"], "concluido": True})
            elif tipo == "command_execution":
                comandos.append(it.get("command", ""))
                avisar("passo", "rodou " + str(it.get("command", ""))[:120])
            elif tipo == "file_change":
                for ch in it.get("changes") or []:
                    if captura:
                        alteracao = captura.registrar(ch)
                        if alteracao:
                            ao_evento(alteracao)
                    caminho = ch.get("path")
                    if caminho and caminho not in arquivos:
                        arquivos.append(caminho)
                        avisar("passo", "editou " + os.path.basename(caminho))
            if tipo != "agent_message":
                avisar("passo", "pensando", id=it.get("id"), operacao="fim",
                       ok=it.get("exit_code") in (None, 0) and it.get("status") != "failed",
                       saida=str(it.get("aggregated_output") or "")[-3000:] if tipo == "command_execution" else "")
        elif d.get("type") == "turn.completed":
            completo = True
            u = d.get("usage") or {}
            for chave, campo in campos_uso.items():
                uso[chave] = max(0, (u.get(campo) or 0) - ((anterior or {}).get(campo) or 0))
            avisar("passo", "terminando", tokens=max(0, uso["entrada"] - uso["cache"]) + uso["saida"])
    processo = codex_processo.executar(cmd, pasta, entrada, receber,
                                      lambda: avisar("passo", "aguardando o Codex; Parar continua disponível"),
                                      parar=parar, prazo=prazo, ao_pulso=medir)
    acumulado = _codex_uso(thread)
    if acumulado is not None and anterior is not None:
        # O CLI 0.163 emite usage acumulado ao retomar; a diferença do log evita contar turnos antigos outra vez.
        for chave, campo in campos_uso.items():
            uso[chave] = max(0, (acumulado.get(campo) or 0) - (anterior.get(campo) or 0))
    ok = processo["codigo"] == 0 and completo and not falhou and not processo["cancelado"] and not processo["estourou"]
    erro = ""
    if processo["cancelado"]:
        erro = "Codex interrompido pelo usuário. Alterações já feitas continuam nos arquivos."
    elif processo["estourou"]:
        erro = f"O Codex passou do prazo de {prazo:g} s e foi encerrado. Alterações já feitas continuam nos arquivos."
    elif not ok:
        erro = "\n".join(erros[-3:]) or processo["erro"] or "O Codex encerrou sem confirmar o fim da resposta."
    uso["novos"] = max(0, uso["entrada"] - uso["cache"])
    uso["total"] = uso["entrada"] + uso["saida"]
    res = {"ok": ok, "texto": "\n\n".join(t for t in [textos[-1] if textos else "", erro] if t),
           "tokens": uso["novos"] + uso["saida"], "uso": uso, "arquivos": arquivos, "comandos": comandos,
           "progresso": textos[:-1], "alteracoes": list(captura.alteracoes.values()) if captura else [],
           "cota": _codex_cota(thread), "ms": processo["ms"], "sessao": thread, "esforco": esforco,
           "primeiro_evento_ms": processo["primeiro_evento_ms"],
           "estourou": processo["estourou"], "cancelado": processo["cancelado"]}
    avisar("fim", res["texto"][:200], ok=ok, tokens=res["tokens"], uso=uso, cota=res["cota"], ms=res["ms"])
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


_job = [None]


def _amarrar(p):
    """o motor morre junto com quem o abriu (Job do Windows com KILL_ON_JOB_CLOSE): sem isso, KaniCode recarregado ou
    teste encerrado deixava llama-server órfão na placa, e o próximo ficava 10× mais lento (2026-10-21: 90 s por pedido)"""
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    if not _job[0]:
        class _LIM(ctypes.Structure):
            _fields_ = [("a", ctypes.c_int64), ("b", ctypes.c_int64), ("LimitFlags", wintypes.DWORD), ("c", ctypes.c_size_t),
                        ("d", ctypes.c_size_t), ("e", wintypes.DWORD), ("f", ctypes.c_size_t), ("g", wintypes.DWORD), ("h", wintypes.DWORD)]

        class _EXT(ctypes.Structure):
            _fields_ = [("basico", _LIM), ("io", ctypes.c_uint64 * 6), ("m1", ctypes.c_size_t), ("m2", ctypes.c_size_t),
                        ("m3", ctypes.c_size_t), ("m4", ctypes.c_size_t)]
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        j = k32.CreateJobObjectW(None, None)
        info = _EXT()
        info.basico.LimitFlags = 0x2000   # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        k32.SetInformationJobObject(wintypes.HANDLE(j), 9, ctypes.byref(info), ctypes.sizeof(info))
        _job[0] = j
    k32.AssignProcessToJobObject(wintypes.HANDLE(_job[0]), wintypes.HANDLE(int(p._handle)))


def _limpar_orfaos():
    """llama-server da Kani cujo dono já morreu (o do KANIVETE tem dono vivo e fica)"""
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "Get-CimInstance Win32_Process -Filter \"Name='llama-server.exe'\" | ForEach-Object { "
                              "if (-not (Get-Process -Id $_.ParentProcessId -ErrorAction SilentlyContinue)) { $_.ProcessId } }"],
                             capture_output=True, text=True, timeout=20, creationflags=_SEM_JANELA).stdout
        for pid in out.split():
            subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True, timeout=10, creationflags=_SEM_JANELA)
    except Exception:
        pass


def _kani_subir(ao_evento):
    with _kani_trava:
        p = _kani["proc"]
        if p and p.poll() is None:
            return _kani["porta"]
        if not kani_disponivel():
            raise RuntimeError("a Kani não está instalada (abra a Kani uma vez no KANIVETE para baixar o modelo)")
        _limpar_orfaos()
        ao_evento({"t": "ajudante", "quem": "kani", "fase": "passo", "texto": "acordando (carregando o modelo)"})
        porta = _porta_livre()
        exe = os.path.join(KANI_DIR, "bin", "llama-server.exe")
        p = subprocess.Popen([exe, "-m", os.path.join(KANI_DIR, KANI_GGUF), "--host", "127.0.0.1", "--port", str(porta), "-c", "8192",
                              "-ngl", "99", "--jinja", "-np", "1"], cwd=os.path.dirname(exe), stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, creationflags=_SEM_JANELA)
        try:
            _amarrar(p)
        except Exception:
            pass
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
