"""Big Pickle como agente de código NATIVO (2026-10-21), do jeito que o Codex trabalha no KaniCode.

O OpenCode roda com as ferramentas PRÓPRIAS dele (ler, procurar, editar, conferir) numa CÓPIA do projeto: um git worktree
em D:\\kanivete_testes\\codigo_agentes\\sessao_*\\arvore, com as mudanças ainda não commitadas da origem copiadas por cima.
Arquivos ignorados pelo git (segredos, modelos) não vão para a cópia nem para o provedor. A origem só muda pelo botão
"Aplicar" da revisão (codigo_agente.Contexto, que confere se ninguém mexeu no original enquanto ele trabalhava).

Pedidos para MEXER NO APP (KANIVETE, KaniBrowser, abrir/clicar) continuam na ponte em etapas (bigpickle_modo).
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import unicodedata
from pathlib import Path

import codigo_agente
import opencode_mvp

PRAZO = 15 * 60             # s por pedido
MAX_COPIA = 5 * 1024 * 1024  # arquivo não commitado maior que isso não vai para a cópia
_SEM_JANELA = 0x08000000 if os.name == "nt" else 0

_CODIGO = re.compile(r"c[oó]digo|\bbug\b|fun[cç][aã]o|\bclasse\b|\.(?:py|js|html|css|json|java|md)\b|\bteste|"
                     r"programa|script|erro|traceback|refator|implement", re.I)
_EDITAR = re.compile(r"\b(?:corrij|corrig|consert|arrum|mud[ae]|alter|edit|adicion|acrescent|implement|cri[ae]|"
                     r"refator|remov|tir[ae]|troqu|troc|ajust|faz|fa[cç]a|melhor|otimiz|escrev|renome|resolv)", re.I)
_APP = re.compile(r"kanivete|canivete|kanibrowser|\bphoto\b|\bvetor\b|\bv[ií]deo\b|\bslider\b|\bsound\b|\blux\b|"
                  r"whats|instagram|\babr[ae]\b|\babrir\b|\bclic|\bfech[ae]|\bnavegador|\bsite\b|\bdisco\b|\bespa[cç]o\b|"
                  r"programas abertos|demanda|panda", re.I)

_RUIDO = re.compile(r"(?:^|/)__pycache__/|\.py[co]$")   # cache do Python: nem copia nem conta como mudança

_PROMPT = """Você é o Big Pickle, agente de código do Pailer no KaniCode. Trabalha em português do Brasil.
A pasta atual é uma CÓPIA ISOLADA do projeto: edite à vontade aqui; o Pailer revisa o diff e aplica no original pelo
botão Aplicar. Nunca diga que alterou o original.

COMO TRABALHAR (igual a um bom engenheiro):
1. Se houver AGENTS.md ou CLAUDE.md na pasta, leia antes de mexer: são as regras do projeto.
2. Ache o ponto exato com grep/glob e leia só o trecho necessário (arquivos grandes: leia por partes).
3. Faça a menor mudança que resolve, no estilo do código em volta (nomes, comentários, idioma). Nada de reescrever
   o que não foi pedido.
4. Confira: `py -3.13 -m py_compile <arquivo>` em cada .py alterado, `node --check <arquivo>` em cada .js; se existir
   teste unitário ligado ao que mudou e ele for rápido, rode (`py -3.13 -m unittest ...`). Falhou? Corrija e confira de novo.
5. Termine com uma resposta CURTA (até 5 linhas): o que mudou (arquivos), como conferiu e o que ficou faltando.
Escreva TUDO em português do Brasil, inclusive os recados do meio do trabalho ("Achei o problema em…").

LIMITES: sem commit, push, instalar pacotes, apagar arquivos, abrir apps, navegador ou portas de rede. Pergunta ou
conversa: responda direto, sem ferramentas. Se algo estiver fora do seu alcance, diga numa frase."""

_SO_LEITURA = """
MODO SÓ LEITURA: nesta conversa você NÃO edita arquivos; pesquise e responda (ou proponha a mudança em texto)."""

_VOZ = """
O Pailer está OUVINDO a resposta: no máximo 3 frases curtas, sem caminho de arquivo, código ou lista."""


def _sem_acento(t):
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if not unicodedata.combining(c))


def para_ponte(pedido):
    """pedido sobre o APP (KANIVETE, sites, disco, demandas) e não sobre código: vai para a ponte em etapas"""
    return bool(_APP.search(pedido)) and not _CODIGO.search(pedido)


def quer_editar(pedido):
    return bool(_EDITAR.search(pedido))


def _dentro(caminho, pasta):
    try:
        return Path(caminho).resolve().is_relative_to(Path(pasta).resolve())
    except (OSError, ValueError):
        return False


def _hash(dados):
    return hashlib.sha256(dados).hexdigest() if dados is not None else None


def _git(cwd, *args, binario=False, prazo=120):
    r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, timeout=prazo, creationflags=_SEM_JANELA)
    if r.returncode:
        raise ValueError("git " + args[0] + ": " + r.stderr.decode("utf-8", "replace").strip()[:300])
    return r.stdout if binario else r.stdout.decode("utf-8", "replace")


def _status(arvore):
    """[(XY, caminho)] do git status (-z: nomes com espaço e acento sem aspas); renomeado conta como os dois nomes"""
    partes = _git(arvore, "status", "--porcelain", "-z", "--untracked-files=all", binario=True).decode("utf-8", "replace").split("\0")
    saida, i = [], 0
    while i < len(partes):
        p = partes[i]
        if len(p) > 3 and not _RUIDO.search(p[3:]):
            saida.append((p[:2], p[3:]))
            if p[0] in "RC" and i + 1 < len(partes):   # o nome antigo vem no item seguinte
                saida.append(("D ", partes[i + 1]))
                i += 1
        i += 1
    return saida


def _permissoes(editar):
    leitura = {"*": "deny", "bash": {"*": "deny", "git status*": "allow", "git diff*": "allow", "git log*": "allow",
                                     "git show*": "allow", "py -3.13 -m py_compile *": "allow", "node --check *": "allow"},
               "read": "allow", "list": "allow", "glob": "allow", "grep": "allow", "todowrite": "allow",
               "todoread": "allow", "external_directory": "deny", "webfetch": "deny", "websearch": "deny", "task": "deny"}
    if editar:
        leitura["edit"] = "allow"
        leitura["bash"].update({"py -3.13 -m unittest *": "allow", "py -3.13 -m pytest *": "allow",
                                "python -m py_compile *": "allow", "python -m unittest *": "allow"})
    return leitura


class Sessao:
    """a cópia de trabalho do Big Pickle para uma pasta; vira um codigo_agente.Contexto para a revisão/Aplicar"""

    def __init__(self, origem):
        self.origem = Path(origem).resolve()
        self.ctx = codigo_agente.Contexto(self.origem, "pickle")
        self.topo = Path(_git(self.origem, "rev-parse", "--show-toplevel").strip()).resolve()
        self.rel = self.origem.relative_to(self.topo).as_posix() if self.origem != self.topo else ""

    def _indice(self):
        return codigo_agente.BASE / (self.ctx.chave + ".json")

    def atual(self):
        """a sessão anterior ainda serve (cópia viva, nada aplicado, mesma origem): continua nela"""
        try:
            ctx = codigo_agente.Contexto(self.origem, "pickle").carregar()
        except (ValueError, OSError, KeyError):
            return None
        meta = ctx.meta
        if meta.get("aplicada") or not meta.get("arvore") or not Path(meta["arvore"]).is_dir():
            return None
        for nome, h in (meta.get("foto") or {}).items():   # o original mudou desde a cópia: começa outra
            p = self.topo / nome
            if _hash(p.read_bytes() if p.is_file() else None) != h:
                return None
        if _git(self.topo, "rev-parse", "HEAD").strip() != meta.get("head"):
            return None
        self.pasta, self.meta = ctx.pasta, meta
        self.arvore = Path(meta["arvore"])
        return self

    def nova(self, objetivo):
        self.descartar_anterior()
        codigo_agente.BASE.mkdir(parents=True, exist_ok=True)
        self.pasta = Path(tempfile.mkdtemp(prefix="sessao_", dir=codigo_agente.BASE))
        self.arvore = self.pasta / "arvore"
        _git(self.topo, "worktree", "add", "--detach", str(self.arvore), "HEAD", prazo=600)
        foto = {}   # caminho (relativo ao topo) → hash do conteúdo que a cópia recebeu (None = não existe)
        pulados = []
        for xy, nome in _status(self.topo):
            src, dst = self.topo / nome, self.arvore / nome
            if src.is_file():
                if src.stat().st_size > MAX_COPIA:
                    pulados.append(nome)
                    continue
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                foto[nome] = _hash(src.read_bytes())
            elif not src.exists() and dst.is_file():
                dst.unlink()
                foto[nome] = None
        self.meta = {"origem": str(self.origem), "agente": "pickle", "objetivo": objetivo[:3000], "arquivos": {},
                     "aplicada": False, "testes": None, "arvore": str(self.arvore),
                     "trabalho": str(self.arvore / self.rel) if self.rel else str(self.arvore),
                     "foto": foto, "pulados": pulados, "head": _git(self.topo, "rev-parse", "HEAD").strip()}
        self._salvar()
        self._indice().write_text(json.dumps({"sessao": self.pasta.name}), encoding="utf-8")
        return self

    def descartar_anterior(self):
        try:
            sid = json.loads(self._indice().read_text(encoding="utf-8"))["sessao"]
            meta = json.loads((codigo_agente.BASE / sid / "contrato.json").read_text(encoding="utf-8"))
        except (OSError, ValueError, KeyError):
            return
        arv = meta.get("arvore")
        if arv and Path(arv).is_dir():
            try:
                _git(self.topo, "worktree", "remove", "--force", arv)
            except (ValueError, OSError, subprocess.TimeoutExpired):
                shutil.rmtree(arv, ignore_errors=True)
        try:
            _git(self.topo, "worktree", "prune")
        except (ValueError, OSError, subprocess.TimeoutExpired):
            pass

    def _salvar(self):
        (self.pasta / "contrato.json").write_text(json.dumps(self.meta, ensure_ascii=False, indent=2), encoding="utf-8")

    def _base_de(self, nome_topo):
        """o conteúdo que a cópia tinha antes do agente (o que a origem tinha ao começar)"""
        foto = self.meta["foto"]
        if nome_topo in foto:
            p = self.topo / nome_topo
            if foto[nome_topo] is None:
                return None
            # a origem ainda igual à foto: é ela; senão a revisão vai acusar "a origem mudou" (hash da foto)
            dados = p.read_bytes() if p.is_file() else None
            return dados if _hash(dados) == foto[nome_topo] else ("foto", foto[nome_topo])
        try:
            return _git(self.topo, "show", "HEAD:" + nome_topo, binario=True)
        except ValueError:
            return None

    def registrar_mudancas(self):
        """compara a cópia com a foto inicial e monta o contrato da revisão (arquivos + base/)"""
        foto = self.meta["foto"]
        mudou, apagados, fora = [], [], []
        for xy, nome in _status(self.arvore):
            p = self.arvore / nome
            dados = p.read_bytes() if p.is_file() else None
            if nome in foto and _hash(dados) == foto[nome]:
                continue   # é a mudança não commitada que veio da origem, intacta
            if self.rel and not (nome + "/").startswith(self.rel + "/"):
                fora.append(nome)
                continue
            if dados is None:
                apagados.append(nome)
                continue
            mudou.append(nome)
        base_dir = self.pasta / "base"
        arquivos, bloqueados = {}, []
        for nome in mudou:
            rel = nome[len(self.rel) + 1:] if self.rel else nome
            try:   # as mesmas travas do contrato: só texto (.py .js .html .css .json .md .txt), sem regras/dependências
                destino = codigo_agente.caminho(base_dir, rel)
            except ValueError:
                bloqueados.append(rel)
                continue
            base = self._base_de(nome)
            if isinstance(base, tuple):   # a origem mudou enquanto ele trabalhava: hash da foto (o Aplicar recusa)
                atual = self.topo / nome
                arquivos[rel] = {"hash": base[1], "tamanho": 0}
                base = atual.read_bytes() if atual.is_file() else None
            else:
                arquivos[rel] = {"hash": _hash(base), "tamanho": len(base or b"")}
            if base is not None:
                destino.parent.mkdir(parents=True, exist_ok=True)
                destino.write_bytes(base)
        self.meta["arquivos"] = arquivos
        self.meta["testes"] = None
        self._salvar()
        return {"arquivos": list(arquivos), "apagados": apagados, "fora": fora + bloqueados}


def _texto_prompt(pedido, historico, por_voz, editar):
    hist = ""
    trocas = [m for m in (historico or [])[-6:] if m.get("content")]
    if trocas:
        hist = "Conversa anterior (contexto; o pedido atual é o último):\n" + "\n".join(
            ("Pailer: " if m["role"] == "user" else "Big Pickle: ") + str(m["content"])[:600] for m in trocas) + "\n\n"
    return (hist + "Pedido do Pailer: " + re.sub(r"\s*\(por voz\)\s*$", "", pedido.strip())
            + (_VOZ if por_voz else "") + ("" if editar else _SO_LEITURA))


_NOMES = {"read": "Read", "edit": "Edit", "write": "Write", "patch": "Edit", "multiedit": "Edit", "bash": "Bash",
          "grep": "Grep", "glob": "Glob", "list": "Glob", "todowrite": "TodoWrite", "todoread": "TodoWrite"}


def _entrada(tool, inp):
    inp = inp if isinstance(inp, dict) else {}
    e = {}
    if inp.get("filePath"):
        e["file_path"] = inp["filePath"]
    for k in ("command", "pattern", "path"):
        if inp.get(k):
            e[k] = str(inp[k])[:400]
    return e


def rodar(pedido, pasta, ao_evento, historico=None, por_voz=False, parar=None, editar=True):
    """executa o pedido com o OpenCode nativo; devolve {ok, texto, tokens, ms, arquivos}"""
    t0 = time.monotonic()
    exe = opencode_mvp.executavel()
    if not exe:
        return {"ok": False, "texto": "Não achei o OpenCode instalado neste PC.", "tokens": 0, "ms": 0}

    def andamento(t):
        ao_evento({"t": "pickle_progresso", "texto": t})

    editar = bool(editar) and quer_editar(pedido)
    # SEMPRE na cópia (git worktree, ~0,6 s): até para ler, assim os arquivos ignorados pelo git (segredos, credenciais)
    # nunca ficam ao alcance dele nem do provedor
    try:
        sessao = Sessao(pasta)
        if not sessao.atual():
            if editar:
                andamento("Preparando uma cópia isolada do projeto…")
            sessao.nova(pedido)
        elif editar:
            andamento("Continuando na mesma cópia (as mudanças anteriores ainda não foram aplicadas).")
        cwd = sessao.meta["trabalho"]
    except (ValueError, OSError, subprocess.TimeoutExpired) as e:
        return {"ok": False, "texto": "Só trabalho em pastas com git (para ter a cópia isolada). Esta não deu: " + str(e)[:160],
                "tokens": 0, "ms": int((time.monotonic() - t0) * 1000)}

    env = opencode_mvp.ambiente()
    env["KANICODE_TESTE"] = "1"
    env["PWD"] = str(cwd)   # o OpenCode usa o PWD herdado como pasta do projeto (no Git Bash editou a ORIGEM; 2026-10-21)
    perm = _permissoes(editar)
    env["OPENCODE_CONFIG_CONTENT"] = json.dumps({
        "$schema": "https://opencode.ai/config.json", "model": opencode_mvp.MODELO, "autoupdate": False,
        "share": "disabled", "plugin": [], "permission": perm,
        "agent": {"kanicode-pickle": {"mode": "primary", "prompt": _PROMPT, "permission": perm}}})
    cmd = [exe, "run", "--pure", "--dir", str(cwd), "--model", opencode_mvp.MODELO, "--agent", "kanicode-pickle", "--format", "json"]
    textos, tokens, erros = [], 0, []
    try:
        proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                                creationflags=_SEM_JANELA)
    except OSError as e:
        return {"ok": False, "texto": "Não consegui iniciar o OpenCode: " + str(e)[:200], "tokens": 0, "ms": 0}
    proc.stdin.write(_texto_prompt(pedido, historico, por_voz, editar))
    proc.stdin.close()
    err = []
    threading.Thread(target=lambda: err.append(proc.stderr.read()), daemon=True).start()
    linhas = []
    leitor = threading.Thread(target=lambda: [linhas.append(l) for l in proc.stdout], daemon=True)
    leitor.start()
    lidas, motivo = 0, ""
    while True:
        while lidas < len(linhas):
            try:
                ev = json.loads(linhas[lidas])
            except ValueError:
                ev = None
            lidas += 1
            if not isinstance(ev, dict):
                continue
            parte = ev.get("part") if isinstance(ev.get("part"), dict) else {}
            tipo = ev.get("type")
            if tipo == "tool_use":
                est = parte.get("state") or {}
                nome = _NOMES.get(parte.get("tool"), str(parte.get("tool") or "ferramenta"))
                cid = parte.get("callID") or parte.get("id") or str(lidas)
                ao_evento({"t": "ferr", "id": cid, "nome": nome, "entrada": _entrada(parte.get("tool"), est.get("input"))})
                ok = est.get("status") == "completed"
                ao_evento({"t": "ferr_fim", "id": cid, "ok": ok,
                           "saida": str(est.get("output") if ok else est.get("error") or "")[:1500]})
                alvo = (est.get("input") or {}).get("filePath") if isinstance(est.get("input"), dict) else None
                if alvo and not _dentro(alvo, cwd):   # trava: nada fora da cópia (nem ler, nem editar)
                    motivo = "fora"
                    andamento("PAREI: ele tentou usar um arquivo fora da cópia isolada (" + str(alvo)[:200] + ", "
                              + ("o OpenCode já tinha bloqueado" if not ok else "chegou a usar") + ").")
                    proc.kill()
                    break
            elif tipo == "text" and isinstance(parte.get("text"), str) and parte["text"].strip():
                if textos:
                    andamento(textos[-1])   # o texto anterior era recado do meio; o último vira a resposta
                textos.append(parte["text"].strip())
            elif tipo == "step_finish":
                uso = parte.get("tokens") or {}
                tokens += sum(v for k, v in uso.items() if k in ("input", "output", "reasoning") and type(v) is int)
                ao_evento({"t": "agente_uso", "quem": "pickle", "tokens": tokens})
            elif tipo == "error":
                erros.append(json.dumps(ev.get("error") or ev, ensure_ascii=False)[:400])
        if motivo or (proc.poll() is not None and not leitor.is_alive() and lidas >= len(linhas)):
            break
        if parar is not None and parar.is_set():
            motivo = "parado"
        elif time.monotonic() - t0 > PRAZO:
            motivo = "prazo"
        if motivo:
            proc.kill()
            break
        time.sleep(0.15)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()

    resposta = textos[-1] if textos else ""
    mudancas = sessao.registrar_mudancas() if sessao else None
    ok = bool(resposta) and not motivo and not erros
    if motivo == "parado":
        resposta = "Parei."
    elif motivo == "fora":
        resposta = "Parei por segurança: ele tentou mexer num arquivo fora da cópia isolada. Nada foi aplicado; confira o andamento."
    elif motivo == "prazo":
        resposta = f"Passei de {PRAZO // 60} minutos e parei."
    elif not resposta:
        detalhe = " ".join(erros) or (err[0] if err else "")[-400:]
        if detalhe:
            andamento("Detalhe técnico: " + detalhe)
        cota = re.search(r"rate.?limit|quota|too many|429", detalhe, re.I)
        resposta = ("O serviço grátis do Big Pickle está no limite agora. Tente daqui a pouco ou passe para o Claude ou o Codex."
                    if cota else "Não consegui terminar: o OpenCode parou sem resposta. Quer passar para o Claude ou o Codex?")
    if mudancas and mudancas["arquivos"]:
        try:
            ctx = codigo_agente.Contexto(pasta, "pickle").carregar()
            sintaxe = ctx.verificar()
        except (ValueError, OSError) as e:
            sintaxe = {"ok": False, "arquivos": [{"arquivo": "?", "ok": False, "erro": str(e)}]}
        n = len(mudancas["arquivos"])
        if not por_voz:
            resposta += ("\n\n**Na cópia:** " + ", ".join(mudancas["arquivos"][:8]) + (" …" if n > 8 else "") + ". "
                         + ("Sintaxe conferida. " if sintaxe["ok"] else "⚠ A sintaxe falhou: corrija antes de aplicar. ")
                         + "Abra **Revisar e aplicar** para ver o diff e levar para o original.")
        else:
            resposta += f" Mudei {n} arquivo{'s' if n > 1 else ''} na cópia; revise na janela para aplicar."
        ao_evento({"t": "codigo_pronto", "quem": "pickle", "arquivos": mudancas["arquivos"], "sintaxe": sintaxe["ok"]})
    if mudancas and (mudancas["apagados"] or mudancas["fora"]):
        andamento("Não levo para o original: " + ", ".join(
            [f"apagar {a}" for a in mudancas["apagados"]] + [f"{a} (fora da pasta ou tipo protegido)" for a in mudancas["fora"]])[:600])
    return {"ok": ok, "texto": resposta, "tokens": tokens, "ms": int((time.monotonic() - t0) * 1000),
            "arquivos": (mudancas or {}).get("arquivos", [])}
