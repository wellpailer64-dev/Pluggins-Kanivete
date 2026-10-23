"""Contas do Claude salvas no KaniCode (troca MANUAL, com um clique — decisão do Pailer, 2026-10-20: nada de trocar
sozinho quando uma acaba; os termos da Anthropic proíbem contornar restrições do produto).

Cada conta = uma pasta de configuração do Claude Code (variável CLAUDE_CONFIG_DIR), cada uma com o seu login.
A principal é a de sempre (~/.claude). As outras ficam em <DADOS>/contas/<id> e enxergam as MESMAS conversas, memória,
skills e plugins da principal (junções de pasta para projects/, skills/, plugins/, agents/, commands/; settings.json e
CLAUDE.md copiados a cada uso) — trocar de conta continua a mesma conversa (--resume acha o arquivo).
Só o login (.credentials.json, .claude.json) é de cada uma.

E-mail e plano: `claude auth status`. Cotas sem gastar nada: `claude -p /usage` (resposta interna, custo 0).
"""
import json, os, re, shutil, subprocess, time

from dados_app import pasta_dados
DADOS = str(pasta_dados())
PRINCIPAL = (os.environ.get("CLAUDE_CONFIG_DIR") or str(pasta_dados() / "claude")) if os.environ.get("KANICODE_TESTE") == "1" else os.path.join(os.path.expanduser("~"), ".claude")
_PASTAS_COMUNS = ("projects", "skills", "plugins", "agents", "commands")
_ARQUIVOS_COMUNS = ("settings.json", "CLAUDE.md", "keybindings.json")
_SEM_JANELA = 0x08000000


def pasta_da(conta_id):
    return PRINCIPAL if conta_id in (None, "", "principal") else os.path.join(DADOS, "contas", conta_id)


def ambiente(conta_id):
    """variáveis de ambiente para rodar o claude nesta conta (None = o ambiente normal)"""
    if conta_id in (None, "", "principal"):
        return None
    preparar(conta_id)
    env = dict(os.environ)
    env["CLAUDE_CONFIG_DIR"] = pasta_da(conta_id)
    return env


def preparar(conta_id):
    """pasta da conta com as partes comuns ligadas à principal (conversas, memória, skills...)"""
    d = pasta_da(conta_id)
    os.makedirs(d, exist_ok=True)
    for nome in _PASTAS_COMUNS:
        alvo, link = os.path.join(PRINCIPAL, nome), os.path.join(d, nome)
        if os.path.isdir(alvo) and not os.path.exists(link):
            subprocess.run(["cmd", "/c", "mklink", "/J", link, alvo], capture_output=True, creationflags=_SEM_JANELA)
    for nome in _ARQUIVOS_COMUNS:
        de = os.path.join(PRINCIPAL, nome)
        if os.path.isfile(de):
            try:
                shutil.copy2(de, os.path.join(d, nome))
            except OSError:
                pass
    return d


def _claude(conta_id, *args, cwd=None, timeout=60):
    exe = shutil.which("claude")
    if not exe:
        raise RuntimeError("não achei o Claude Code (comando claude)")
    return subprocess.run([exe, *args], cwd=cwd or DADOS, env=ambiente(conta_id), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout, creationflags=_SEM_JANELA)


def status(conta_id):
    """{logado, email, plano}"""
    try:
        r = _claude(conta_id, "auth", "status", timeout=30)
        d = json.loads(r.stdout or "{}")
        return {"logado": bool(d.get("loggedIn")), "email": d.get("email") or "", "plano": d.get("subscriptionType") or ""}
    except Exception as e:
        return {"logado": False, "email": "", "plano": "", "erro": str(e)}


_MESES = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def _quando(txt):
    """'Oct 20, 4:29pm' → timestamp (hora local)"""
    m = re.search(r"([A-Za-z]{3})\s+(\d{1,2}),?\s+(\d{1,2})(?::(\d{2}))?\s*([ap]m)", txt or "", re.I)
    if not m:
        return None
    mes, dia, h, mi, ap = _MESES.get(m.group(1).lower()), int(m.group(2)), int(m.group(3)) % 12, int(m.group(4) or 0), m.group(5).lower()
    if not mes:
        return None
    h += 12 if ap == "pm" else 0
    agora = time.localtime()
    ano = agora.tm_year + (1 if mes < agora.tm_mon - 6 else 0)
    return int(time.mktime((ano, mes, dia, h, mi, 0, 0, 0, -1)))


def cotas(conta_id):
    """{h5, h5_zera, sem, sem_zera} pelo /usage (resposta interna do Claude Code: não gasta tokens)"""
    os.makedirs(os.path.join(DADOS, "sonda"), exist_ok=True)
    try:
        r = _claude(conta_id, "-p", "/usage", "--output-format", "json", cwd=os.path.join(DADOS, "sonda"), timeout=90)
        txt = json.loads(r.stdout or "{}").get("result") or ""
    except Exception as e:
        return {"erro": str(e)}
    out = {}
    s = re.search(r"Current session:\s*(\d+)%\s*used(?:\s*·\s*resets\s*([^\n(]+))?", txt)
    w = re.search(r"Current week[^:]*:\s*(\d+)%\s*used(?:\s*·\s*resets\s*([^\n(]+))?", txt)
    if s:
        out.update(h5=int(s.group(1)) / 100, h5_zera=_quando(s.group(2)))
    if w:
        out.update(sem=int(w.group(1)) / 100, sem_zera=_quando(w.group(2)))
    if not out:
        out["erro"] = (txt or r.stderr or "sem resposta")[:200]
    out["lido"] = int(time.time())
    return out


def abrir_login(conta_id, apelido):
    """abre uma janela de terminal com o login oficial do Claude Code nesta conta (o navegador abre para entrar)"""
    preparar(conta_id)
    d = pasta_da(conta_id)
    titulo = f"KaniCode - entrar na conta {apelido}"
    script = os.path.join(d, "entrar.cmd")
    with open(script, "w", encoding="utf-8") as f:
        f.write("@echo off\r\nchcp 65001 >nul\r\n"
                f'set "CLAUDE_CONFIG_DIR={d}"\r\n'
                f"echo Entrando na conta \"{apelido}\" do Claude. O navegador vai abrir: escolha a conta e autorize.\r\n"
                "echo.\r\nclaude auth login\r\necho.\r\n"
                "echo Pronto! Pode fechar esta janela e voltar ao KaniCode.\r\npause >nul\r\n")
    subprocess.Popen(["cmd", "/c", "start", titulo, "cmd", "/c", script], creationflags=_SEM_JANELA)
    return True


def remover(conta_id):
    """apaga a pasta da conta (as junções saem sem tocar nas pastas da principal)"""
    if conta_id in (None, "", "principal"):
        return False
    d = pasta_da(conta_id)
    if not os.path.isdir(d):
        return True
    for nome in _PASTAS_COMUNS:   # junção: rmdir tira só o atalho
        link = os.path.join(d, nome)
        if os.path.isdir(link):
            subprocess.run(["cmd", "/c", "rmdir", link], capture_output=True, creationflags=_SEM_JANELA)
    if any(os.path.exists(os.path.join(d, n)) for n in _PASTAS_COMUNS):
        raise RuntimeError("não consegui soltar as pastas comuns; nada foi apagado")
    shutil.rmtree(d)
    return True
