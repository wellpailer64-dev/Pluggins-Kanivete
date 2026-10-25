"""Energia do PC pela Kani: suspender, hibernar, desligar ou reiniciar agora ou numa hora ("daqui 30 min", "às 23h").

Agenda numa tarefa do Windows "Kani Energia ..." (vale com o KaniCode fechado) e CONFERE que ela ficou registrada antes de
dizer que marcou (2026-10-25: a Kani respondia "será às 03:09" sem agendar nada). Desligar/reiniciar dão 2 min de aviso do
Windows (shutdown /a cancela). Registro em <dados>/energia_log.txt.
  py -3.13 energia.py agendar suspender "daqui 30 min" | listar | cancelar [acao] | executar <acao> <tarefa>   (JSON)
"""
RECARREGAVEL = True
import datetime as dt, json, os, re, subprocess, sys

AQUI = os.path.dirname(os.path.abspath(__file__))
PREFIXO = "Kani Energia"
ACOES = {"suspender": "suspensão", "hibernar": "hibernação", "desligar": "desligamento", "reiniciar": "reinício"}
_SEM_JANELA = 0x08000000


def _log(txt):
    try:
        import casa
        with open(os.path.join(casa.DADOS, "energia_log.txt"), "a", encoding="utf-8") as f:
            f.write(dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S ") + txt + "\n")
    except Exception:
        pass


def _ps(cmd, prazo=30):
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                        "[Console]::OutputEncoding=[Text.Encoding]::UTF8; $ErrorActionPreference='Stop'; " + cmd],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=prazo, creationflags=_SEM_JANELA)
    if r.returncode:
        raise RuntimeError((r.stderr or r.stdout).strip().splitlines()[0] if (r.stderr or r.stdout).strip() else "PowerShell falhou")
    return r.stdout.strip()


def _q(s):
    return "'" + str(s).replace("'", "''") + "'"


# ── a hora sai do pedido do Pailer, nunca do modelo ──
_N = r"(\d+|uma?|duas|dois|tr[eê]s|meia)"
_NUM = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "três": 3, "meia": .5}


def _n(s):
    s = s.lower()
    return _NUM[s] if s in _NUM else int(s)


def quando(pedido, agora=None):
    """'daqui 30 min' / 'em 1h30' / 'daqui uma hora e meia' / 'às 23h' / 'agora' → datetime (None = sem hora no pedido)"""
    agora = (agora or dt.datetime.now()).replace(microsecond=0)
    p = re.sub(r"\(por voz\)", "", str(pedido or ""), flags=re.I).lower()
    m = re.search(r"\b(?:daqui|dentro de|em)\s+(?:a\s+|uns?\s+|umas?\s+)?" + _N + r"\s*(horas?|h|min\w*)(?![a-zà-ú])"
                  r"(?:\s*(?:e\s*)?(meia|\d+)\s*(?:min\w*)?)?", p)
    if m:
        n, un, resto = _n(m.group(1)), m.group(2), m.group(3)
        minutos = n * 60 if un.startswith("h") else n
        if resto and un.startswith("h"):
            minutos += 30 if resto == "meia" else int(resto)
        return agora + dt.timedelta(minutes=minutos)
    if re.search(r"\b(?:daqui|em)\s+meia\s+hora\b", p):
        return agora + dt.timedelta(minutes=30)
    if re.search(r"\b(?:agora|j[aá])\b", p) and not re.search(r"\d", p):
        return agora
    import tarefas
    iso = tarefas.hora_do_pedido(p, None, agora)
    return dt.datetime.fromisoformat(iso) if iso else None


def _hiberna_ligado():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Power") as k:
            return bool(winreg.QueryValueEx(k, "HibernateEnabled")[0])
    except OSError:
        return True


def listar():
    """tarefas de energia marcadas (as que já passaram são apagadas)"""
    bruto = _ps(f"Get-ScheduledTask -TaskName {_q(PREFIXO + '*')} -ErrorAction SilentlyContinue | ForEach-Object "
                "{ [pscustomobject]@{nome=$_.TaskName; quando=($_.Triggers | Select-Object -First 1).StartBoundary} } | ConvertTo-Json -Compress")
    itens = json.loads(bruto) if bruto else []
    itens = [itens] if isinstance(itens, dict) else itens
    agora, saida = dt.datetime.now(), []
    for it in itens:
        try: q = dt.datetime.fromisoformat(str(it["quando"])[:19])
        except (ValueError, TypeError, KeyError): continue
        acao = next((a for a in ACOES if a in it["nome"]), "?")
        if q < agora - dt.timedelta(minutes=5):
            _ps(f"Unregister-ScheduledTask -TaskName {_q(it['nome'])} -Confirm:$false -ErrorAction SilentlyContinue")
            continue
        saida.append({"tarefa": it["nome"], "acao": acao, "quando": q.strftime("%Y-%m-%dT%H:%M"),
                      "legivel": q.strftime("%d/%m às %H:%M")})
    return sorted(saida, key=lambda x: x["quando"])


def agendar(acao, pedido, agora=None):
    """marca a ação na hora do pedido e confere no Agendador do Windows"""
    acao = str(acao or "").lower().strip()
    if acao not in ACOES:
        raise ValueError("Ação de energia desconhecida: use suspender, hibernar, desligar ou reiniciar.")
    if acao == "hibernar" and not _hiberna_ligado():
        raise ValueError("A hibernação está desligada neste PC (powercfg /h on, como administrador, liga). Posso suspender no lugar.")
    q = quando(pedido, agora)
    if q is None:
        raise ValueError(f"Faltou dizer quando (ex.: daqui 30 min, às 23h ou agora).")
    agora = (agora or dt.datetime.now())
    if q <= agora + dt.timedelta(seconds=20):   # agora: roda já (desligar/reiniciar ainda dão 2 min de aviso)
        executar(acao)
        return {"id": "agora", "acao": acao, "feito": f"{ACOES[acao]} iniciada agora" if acao in ("suspender", "hibernar")
                else f"{ACOES[acao]} em 2 minutos (aviso do Windows; 'cancela o {ACOES[acao]}' para parar)"}
    nome = f"{PREFIXO} {acao} {q.strftime('%Y-%m-%d %H%M')}"
    w = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    py = w if os.path.isfile(w) else sys.executable
    arg = f'"{os.path.join(AQUI, "energia.py")}" executar {acao} "{nome}"'
    _ps(f"$a = New-ScheduledTaskAction -Execute {_q(py)} -Argument {_q(arg)} -WorkingDirectory {_q(AQUI)}; "
        f"$t = New-ScheduledTaskTrigger -Once -At ([datetime]::ParseExact({_q(q.strftime('%Y-%m-%d %H:%M:%S'))}, 'yyyy-MM-dd HH:mm:ss', $null)); "
        "$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 5); "
        f"Register-ScheduledTask -TaskName {_q(nome)} -Action $a -Trigger $t -Settings $s -Description 'Marcado pela Kani' -Force | Out-Null")
    marcada = next((x for x in listar() if x["tarefa"] == nome), None)
    if not marcada:
        raise RuntimeError("O Windows não confirmou a tarefa; nada foi marcado.")
    _log(f"agendado {acao} para {marcada['quando']} ({nome})")
    falta = int(round((q - agora).total_seconds() / 60))
    return {"id": nome, "acao": acao, "quando": marcada["quando"], "legivel": marcada["legivel"], "em_minutos": falta,
            "conferido": "tarefa registrada no Agendador do Windows"}


def cancelar(acao=""):
    """apaga as marcadas (todas ou só de uma ação) e para um desligamento em contagem"""
    acao = str(acao or "").lower().strip()
    apagadas = []
    for x in listar():
        if acao in ACOES and x["acao"] != acao: continue
        _ps(f"Unregister-ScheduledTask -TaskName {_q(x['tarefa'])} -Confirm:$false")
        apagadas.append(x["legivel"] + " " + x["acao"])
    contagem = subprocess.run(["shutdown", "/a"], capture_output=True, creationflags=_SEM_JANELA).returncode == 0
    _log(f"cancelado: {apagadas or 'nada'}{' + contagem parada' if contagem else ''}")
    return {"cancelados": apagadas, "contagem_parada": contagem, "restam": listar()}


def executar(acao, tarefa=""):
    _log(f"executando {acao}")
    if tarefa:
        try: _ps(f"Unregister-ScheduledTask -TaskName {_q(tarefa)} -Confirm:$false -ErrorAction SilentlyContinue")
        except Exception: pass
    if acao in ("suspender", "hibernar"):
        import ctypes
        if not ctypes.windll.powrprof.SetSuspendState(acao == "hibernar", True, False):
            raise RuntimeError("O Windows recusou a " + ACOES[acao])
    elif acao in ("desligar", "reiniciar"):
        msg = f"Kani: {ACOES[acao]} em 2 minutos. Para cancelar: shutdown /a ou peça à Kani."
        subprocess.run(["shutdown", "/s" if acao == "desligar" else "/r", "/t", "120", "/c", msg], check=True, creationflags=_SEM_JANELA)
    else:
        raise ValueError("ação desconhecida")


# ── frase direta (atalho do KaniCode, sem IA): "suspende o pc daqui 30 min", "cancela o desligamento" ──
_VERBO = {"suspend": "suspender", "dorm": "suspender", "hibern": "hibernar", "deslig": "desligar", "reinici": "reiniciar"}
_FRASE = re.compile(r"^(?:kani[,!]?\s+)?(?:(?:pode|por favor|favor)\s+)?(suspend|hibern|deslig|reinici)\w*\s+(?:o\s+|a\s+|meu\s+)?"
                    r"(?:pc|computador|m[aá]quina|note(?:book)?)\b(.*)$", re.I)
_CANCELA = re.compile(r"^(?:kani[,!]?\s+)?(?:cancel\w*|desmarc\w*|tira|para)\s+(?:a\s+|o\s+)?(suspens|hiberna|desligamento|rein[ií]cio)\w*", re.I)
_PERGUNTA = re.compile(r"\?|\b(?:como|por ?qu[eê]|quando|pode me explicar|consegue)\b", re.I)


def rapido(texto):
    """resposta pronta (já conferida) ou None se a frase não é um comando de energia"""
    t = re.sub(r"\s*\(por voz\)\s*$", "", str(texto or "").strip(), flags=re.I).strip(" .!")
    if len(t) > 90 or _PERGUNTA.search(t):
        return None
    m = _CANCELA.match(t)
    if m:
        alvo = {"suspens": "suspender", "hiberna": "hibernar", "desligamento": "desligar"}.get(m.group(1).lower(), "reiniciar")
        r = cancelar(alvo)
        return (f"Cancelei: {', '.join(r['cancelados'])}." if r["cancelados"] else "Não havia nada marcado.") + \
               (" Parei a contagem do Windows." if r["contagem_parada"] else "")
    m = _FRASE.match(t)
    if not m:
        return None
    acao = _VERBO[next(k for k in _VERBO if m.group(1).lower().startswith(k))]
    if quando(m.group(2)) is None:
        return None   # sem hora: deixa a Kani perguntar
    try:
        r = agendar(acao, m.group(2))
    except (ValueError, RuntimeError, subprocess.SubprocessError) as e:
        return f"Não marquei: {e}"
    if r["id"] == "agora":
        return r["feito"][0].upper() + r["feito"][1:] + "."
    art = "a" if acao in ("suspender", "hibernar") else "o"
    h, mi = divmod(r["em_minutos"], 60)
    falta = f"{mi} min" if not h else f"{h} h" + (f" {mi:02d}" if mi else "")
    return f"Marquei {art} {ACOES[acao]} do PC para {r['legivel']} (daqui {falta}). Para desmarcar: \"cancela {art} {ACOES[acao]}\"."


if __name__ == "__main__":
    sys.path.insert(0, AQUI)
    c = sys.argv[1:] or ["listar"]
    if c[0] == "executar":
        executar(c[1], c[2] if len(c) > 2 else "")
        sys.exit(0)
    f = {"listar": lambda: listar(), "cancelar": lambda: cancelar(c[1] if len(c) > 1 else ""),
         "agendar": lambda: agendar(c[1], " ".join(c[2:])), "rapido": lambda: rapido(" ".join(c[1:]))}[c[0]]
    print(json.dumps(f(), ensure_ascii=False))
