"""Cenas da Casa (aba Casa › Cenas): automações montadas pelo Pailer = gatilhos + ações em sequência.

Gatilhos: horário (HH:MM + dias da semana), frase de voz/chat ("modo cinema") e ao abrir o KaniCode.
Ações: aparelho (ligar/desligar/alternar/brilho; alvo = aparelho, cômodo ou "luzes"), alimentar os gatos, esperar,
PC (bloquear, apagar tela, suspender, desligar/reiniciar em 60 s), alerta (aviso + voz), som (volume, mudo, mídia)
e abrir (programa, arquivo, pasta ou site). Guardadas em <casa>/cenas.json, com o registro em cenas_log.txt.

  py -3.13 cenas.py lista
  py -3.13 cenas.py rodar "<nome ou id>"
"""
import datetime, json, os, re, subprocess, sys, threading, time, uuid

import casa

ARQ = os.path.join(casa.DADOS, "cenas.json")
LOG = os.path.join(casa.DADOS, "cenas_log.txt")
_trava = threading.Lock()
_ganchos = {"avisar": None, "falar": None}
_rodando = set()


def _ler():
    try:
        with open(ARQ, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    d.setdefault("cenas", [])
    d.setdefault("ultimas", {})
    return d


def _gravar(d):
    os.makedirs(casa.DADOS, exist_ok=True)
    tmp = ARQ + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, ARQ)


def _log(txt):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {txt}\n")
    except OSError:
        pass


def listar():
    d = _ler()
    for c in d["cenas"]:
        c["ultima"] = d["ultimas"].get(c["id"], "")
    return d["cenas"]


def salvar(cena):
    with _trava:
        d = _ler()
        cena = dict(cena)
        cena.pop("ultima", None)
        cena["id"] = cena.get("id") or uuid.uuid4().hex[:8]
        cena["nome"] = (cena.get("nome") or "Cena").strip()[:60]
        cena.setdefault("ativa", True)
        cena["gatilhos"] = list(cena.get("gatilhos") or [])
        cena["acoes"] = list(cena.get("acoes") or [])
        i = next((k for k, c in enumerate(d["cenas"]) if c["id"] == cena["id"]), None)
        if i is None:
            d["cenas"].append(cena)
        else:
            d["cenas"][i] = cena
        _gravar(d)
    despertadores_fundo()
    return cena


def apagar(id_):
    with _trava:
        d = _ler()
        d["cenas"] = [c for c in d["cenas"] if c["id"] != id_]
        d["ultimas"].pop(id_, None)
        _gravar(d)
    despertadores_fundo()


def achar(ref):
    r = casa._sem(ref)
    cs = _ler()["cenas"]
    return next((c for c in cs if c["id"] == ref), None) or next((c for c in cs if casa._sem(c["nome"]) == r), None)


# ── ações ──
def _volume():
    from pycaw.pycaw import AudioUtilities
    alto = AudioUtilities.GetSpeakers()
    if hasattr(alto, "EndpointVolume"):
        return alto.EndpointVolume
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import IAudioEndpointVolume
    return cast(alto.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None), POINTER(IAudioEndpointVolume))


def _tecla(vk):
    import ctypes
    u = ctypes.windll.user32
    u.keybd_event(vk, 0, 1, 0)
    u.keybd_event(vk, 0, 3, 0)


def _som(op, valor):
    if op in ("tocar_pausar", "proxima", "anterior", "parar"):
        _tecla({"tocar_pausar": 0xB3, "proxima": 0xB0, "anterior": 0xB1, "parar": 0xB2}[op])
        return {"tocar_pausar": "tocar/pausar", "proxima": "próxima faixa", "anterior": "faixa anterior", "parar": "parar mídia"}[op]
    import comtypes
    comtypes.CoInitialize()
    try:
        v = _volume()
        if op == "volume":
            pct = max(0, min(100, int(valor or 0)))
            v.SetMute(0, None)
            v.SetMasterVolumeLevelScalar(pct / 100, None)
            return f"volume {pct}%"
        v.SetMute(1 if op == "mudo" else 0, None)
        return "sem som" if op == "mudo" else "som ligado"
    finally:
        comtypes.CoUninitialize()


def _pc(op):
    import ctypes
    if op == "acordar":   # acende a tela e sai do "acordou sozinho" (senão o Windows volta a dormir em ~2 min)
        u = ctypes.windll.user32
        ctypes.windll.kernel32.SetThreadExecutionState(0x00000001 | 0x00000002)
        u.mouse_event(0x0001, 1, 0, 0, 0)
        u.mouse_event(0x0001, -1 & 0xFFFFFFFF, 0, 0, 0)
        return "PC acordado, tela acesa"
    if op == "bloquear":
        ctypes.windll.user32.LockWorkStation()
        return "PC bloqueado"
    if op == "tela_off":
        ctypes.windll.user32.PostMessageW(0xFFFF, 0x0112, 0xF170, 2)
        return "tela apagada"
    if op == "suspender":
        ctypes.windll.powrprof.SetSuspendState(False, True, False)
        return "PC suspenso"
    if op in ("desligar", "reiniciar"):
        subprocess.Popen(["shutdown", "/s" if op == "desligar" else "/r", "/t", "60", "/c",
                          f"Cena da Casa: o PC vai {'desligar' if op == 'desligar' else 'reiniciar'} em 1 minuto. Cancelar: shutdown /a"],
                         creationflags=0x08000000)
        return f"PC vai {'desligar' if op == 'desligar' else 'reiniciar'} em 60 s"
    raise ValueError(f"ação de PC desconhecida: {op}")


def _abrir(alvo):
    alvo = (alvo or "").strip().strip('"')
    if not alvo:
        return "abrir: vazio, pulei"
    if re.match(r"^[a-z]+://|^www\.", alvo, re.I):
        os.startfile(alvo if "://" in alvo else "https://" + alvo)
    elif os.path.exists(alvo):
        os.startfile(alvo)
    else:   # nome de programa no PATH/registro ("notepad", "spotify")
        subprocess.Popen(["cmd", "/c", "start", "", alvo], creationflags=0x08000000)
    return f"abri {os.path.basename(alvo.rstrip('/\\')) or alvo}"


def _quieto(f, *a):
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = f(*a)
    txt = buf.getvalue().strip().replace("\n", "; ")
    if rc:
        raise RuntimeError(txt or "falhou")
    return txt


def acao(a):
    t = a.get("tipo")
    if t == "aparelho":
        op, alvo = a.get("op", "ligar"), a.get("alvo") or "luzes"
        if op == "brilho":
            if any(d.get("category") == "dj" for d in casa.alvos(alvo)):
                return _quieto(casa.brilho, alvo, a.get("valor") or 100)
            return _quieto(casa.ligar, alvo, True) + " (tomada não tem brilho: só liguei)"
        if op == "alternar":
            ds = [d for d in casa.alvos(alvo) if d.get("category") != "cwwsq"]
            return "; ".join(f"{d['name']}: {'ligado' if casa.alternar(d['name']).get('ligado') else 'desligado'}" for d in ds) or f"não achei {alvo}"
        return _quieto(casa.ligar, alvo, op == "ligar")
    if t == "alimentar":
        return _quieto(casa.alimentar, int(a.get("porcoes") or 1), True)
    if t == "esperar":
        s = max(0, min(3600, float(a.get("seg") or 0)))
        time.sleep(s)
        return f"esperei {s:g} s"
    if t == "pc":
        return _pc(a.get("op"))
    if t == "som":
        return _som(a.get("op", "volume"), a.get("valor"))
    if t == "abrir":
        return _abrir(a.get("alvo"))
    if t == "falar":
        txt = (a.get("texto") or "").strip()
        if not txt:
            return "falar: vazio, pulei"
        if not _ganchos["falar"]:
            raise RuntimeError("a voz da Kani só fala com o KaniCode aberto")
        _ganchos["falar"](txt)
        return f"falei: {txt}"
    if t == "alerta":
        txt = (a.get("texto") or "").strip() or "Alerta da cena"
        if _ganchos["avisar"]:
            _ganchos["avisar"]("🔔 " + txt)
        if a.get("falar", True) and _ganchos["falar"]:
            _ganchos["falar"](txt)
        return f"alerta: {txt}"
    raise ValueError(f"ação desconhecida: {t}")


def rodar(cena, origem="manual"):
    """executa as ações em ordem; uma falha não para as outras. → {ok, linhas}"""
    if cena["id"] in _rodando:
        return {"ok": False, "linhas": ["essa cena já está rodando"]}
    _rodando.add(cena["id"])
    linhas, ok = [], True
    try:
        for a in cena.get("acoes") or []:
            try:
                linhas.append(acao(a) or "ok")
            except Exception as e:
                ok = False
                linhas.append(f"erro ({a.get('tipo')}): {e}")
    finally:
        _rodando.discard(cena["id"])
    with _trava:
        d = _ler()
        d["ultimas"][cena["id"]] = datetime.datetime.now().isoformat(timespec="minutes")
        _gravar(d)
    _log(f"[{origem}] {cena['nome']}: " + " | ".join(linhas))
    return {"ok": ok, "linhas": linhas}


def rodar_fundo(cena, origem):
    def ir():
        r = rodar(cena, origem)
        if _ganchos["avisar"] and origem != "manual":
            _ganchos["avisar"](f"🏠 Cena “{cena['nome']}”" + (" feita." if r["ok"] else ": " + "; ".join(l for l in r["linhas"] if l.startswith("erro"))))
    threading.Thread(target=ir, daemon=True).start()


# ── despertador: tarefa do Windows com "despertar o computador" 2 min antes de cada horário (PC hibernado/suspenso;
# a tarefa só acorda, quem roda a cena é o KaniCode). Pasta \KaniCode\Cenas no Agendador de Tarefas. ──
PASTA_TAREFAS = "\\KaniCode\\Cenas\\"
ANTES = 2
_DIAS_XML = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _xml_tarefa(hora, dias):
    h, m = map(int, hora.split(":"))
    antes = datetime.datetime(2026, 1, 1, h, m) - datetime.timedelta(minutes=ANTES)
    t = antes.strftime("%H:%M")
    if antes.day != 1:   # 00:01 → acorda 23:59 do dia anterior
        dias = [(k - 1) % 7 for k in dias or []]
    if dias and len(dias) < 7:
        agenda = ("<ScheduleByWeek><DaysOfWeek>" + "".join(f"<{_DIAS_XML[k]} />" for k in sorted(set(dias)))
                  + "</DaysOfWeek><WeeksInterval>1</WeeksInterval></ScheduleByWeek>")
    else:
        agenda = "<ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>"
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>KaniCode: acorda o PC para uma cena da Casa</Description></RegistrationInfo>
  <Triggers><CalendarTrigger><StartBoundary>2026-01-01T{t}:00</StartBoundary><Enabled>true</Enabled>{agenda}</CalendarTrigger></Triggers>
  <Principals><Principal id="Autor"><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings><WakeToRun>true</WakeToRun><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><StartWhenAvailable>false</StartWhenAvailable>
    <ExecutionTimeLimit>PT1M</ExecutionTimeLimit><Enabled>true</Enabled></Settings>
  <Actions Context="Autor"><Exec><Command>C:\\Windows\\System32\\conhost.exe</Command><Arguments>--headless cmd.exe /c exit</Arguments></Exec></Actions>
</Task>"""


def _schtasks(*a):
    return subprocess.run(["schtasks", *a], capture_output=True, text=True, encoding="mbcs", errors="replace",
                          creationflags=0x08000000, timeout=30)


def despertadores():
    """recria as tarefas: uma por horário de cena ativa; apaga as que sobraram. → quantas ficaram"""
    with _trava_desp:
        quero = {}
        for c in _ler()["cenas"]:
            if not c.get("ativa", True):
                continue
            for i, g in enumerate(c.get("gatilhos") or []):
                if g.get("tipo") == "horario" and re.match(r"^\d{1,2}:\d{2}$", g.get("hora") or ""):
                    quero[f"{c['id']}_{i}"] = _xml_tarefa(g["hora"], g.get("dias") or [])
        r = _schtasks("/Query", "/FO", "CSV", "/NH")
        tem = set(re.findall(r'"\\KaniCode\\Cenas\\([^"]+)"', r.stdout or ""))
        for n in tem - set(quero):
            _schtasks("/Delete", "/TN", PASTA_TAREFAS + n, "/F")
        import tempfile
        for n, xml in quero.items():
            arq = os.path.join(tempfile.gettempdir(), f"kanicode_cena_{n}.xml")
            with open(arq, "w", encoding="utf-16") as f:
                f.write(xml)
            r = _schtasks("/Create", "/TN", PASTA_TAREFAS + n, "/XML", arq, "/F")
            os.remove(arq)
            if r.returncode:
                _log(f"despertador {n}: {(r.stderr or r.stdout).strip()}")
        return len(quero)


_trava_desp = threading.Lock()


def despertadores_fundo():
    threading.Thread(target=lambda: _tentar(despertadores), daemon=True).start()


def _tentar(f):
    try:
        return f()
    except Exception as e:
        _log(f"despertador: {e}")


def _manter_acordado(tela=False):
    """o Windows volta a dormir ~2 min depois de acordar sozinho: avisa que há trabalho (e acende a tela ao rodar)"""
    try:
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x00000001 | (0x00000002 if tela else 0))
    except Exception:
        pass


# ── gatilhos ──
def por_frase(texto):
    """frase curta que bate com o gatilho de voz de uma cena ativa → a cena (ou None)"""
    t = re.sub(r"[^a-z0-9 ]", " ", casa._sem(re.sub(r"\(por voz\)", " ", texto or "")))
    t = " " + re.sub(r"\s+", " ", t).strip() + " "
    if len(t.split()) > 10:
        return None
    for c in _ler()["cenas"]:
        if not c.get("ativa", True):
            continue
        for g in c.get("gatilhos") or []:
            f = re.sub(r"[^a-z0-9 ]", " ", casa._sem(g.get("frase") or "")).strip()
            if g.get("tipo") == "voz" and f and " " + f + " " in t:
                return c
    return None


def _proxima(d, agora):
    """próximo horário de cena ativa a partir de agora (datetime) ou None"""
    melhor = None
    for c in d["cenas"]:
        if not c.get("ativa", True):
            continue
        for g in c.get("gatilhos") or []:
            if g.get("tipo") != "horario" or not re.match(r"^\d{1,2}:\d{2}$", g.get("hora") or ""):
                continue
            h, m = map(int, g["hora"].split(":"))
            for k in range(8):
                t = (agora + datetime.timedelta(days=k)).replace(hour=h, minute=m, second=0, microsecond=0)
                if t > agora and (not g.get("dias") or t.weekday() in g["dias"]):
                    melhor = t if not melhor or t < melhor else melhor
                    break
    return melhor


_timer = {"h": None, "alvo": None}


def _armar_despertador(d, agora):
    """despertador do próprio KaniCode (SetWaitableTimer que acorda o PC) 40 s antes da próxima cena; vale mesmo se a
    cena foi criada em cima da hora (a tarefa do Windows acorda 2 min antes e só serve se o PC dormiu antes disso)"""
    import ctypes
    from ctypes import wintypes
    k = ctypes.windll.kernel32
    prox = _proxima(d, agora)
    alvo = prox - datetime.timedelta(seconds=40) if prox else None
    if alvo == _timer["alvo"]:
        return
    if _timer["h"] is None:
        k.CreateWaitableTimerW.restype = wintypes.HANDLE
        _timer["h"] = k.CreateWaitableTimerW(None, True, None)
    if not alvo or alvo <= agora:
        k.CancelWaitableTimer(wintypes.HANDLE(_timer["h"]))
        _timer["alvo"] = alvo
        return
    utc = alvo.astimezone(datetime.timezone.utc).replace(tzinfo=None)   # hora absoluta (FILETIME): conta o tempo dormindo
    vence = ctypes.c_longlong(int((utc - datetime.datetime(1601, 1, 1)).total_seconds() * 10_000_000))
    k.SetWaitableTimer.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_longlong), wintypes.LONG, ctypes.c_void_p,
                                   ctypes.c_void_p, wintypes.BOOL]
    if k.SetWaitableTimer(_timer["h"], ctypes.byref(vence), 0, None, None, True):
        _timer["alvo"] = alvo
    else:
        _log(f"despertador interno falhou: {ctypes.GetLastError()}")


def _vigiar():
    while True:
        try:
            agora = datetime.datetime.now()
            d = _ler()
            _armar_despertador(d, agora)
            for c in d["cenas"]:
                if not c.get("ativa", True):
                    continue
                for g in c.get("gatilhos") or []:
                    if g.get("tipo") != "horario" or not re.match(r"^\d{1,2}:\d{2}$", g.get("hora") or ""):
                        continue
                    dias = g.get("dias")
                    if dias and agora.weekday() not in dias:
                        continue
                    h, m = map(int, g["hora"].split(":"))
                    alvo = agora.replace(hour=h, minute=m, second=0, microsecond=0)
                    marca = alvo.isoformat(timespec="minutes")
                    falta = (alvo - agora).total_seconds()
                    if 0 < falta <= (ANTES + 1) * 60:
                        _manter_acordado()   # acordou pelo despertador: segura até a hora da cena
                    if 0 <= -falta < 180 and d["ultimas"].get(c["id"], "") < marca:
                        _manter_acordado()
                        rodar_fundo(c, "horário")
                        d["ultimas"][c["id"]] = marca   # não repete no próximo giro
        except Exception as e:
            _log(f"vigia: {e}")
        time.sleep(10)


def iniciar(avisar=None, falar=None):
    """chamado pelo KaniCode ao abrir: liga a agenda e roda as cenas "ao abrir o KaniCode" """
    _ganchos.update(avisar=avisar, falar=falar)
    threading.Thread(target=_vigiar, daemon=True).start()
    despertadores_fundo()

    def ao_abrir():
        time.sleep(8)
        for c in _ler()["cenas"]:
            if c.get("ativa", True) and any(g.get("tipo") == "inicio" for g in c.get("gatilhos") or []):
                rodar_fundo(c, "abertura")
    threading.Thread(target=ao_abrir, daemon=True).start()


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if len(sys.argv) > 2 and sys.argv[1] == "rodar":
        c = achar(sys.argv[2])
        if not c:
            print("Cena não encontrada."); return 1
        r = rodar(c, "linha de comando")
        print("\n".join(r["linhas"])); return 0 if r["ok"] else 1
    for c in listar():
        print(f"- {c['nome']} ({c['id']}{', desligada' if not c.get('ativa', True) else ''}): "
              f"{len(c['gatilhos'])} gatilho(s), {len(c['acoes'])} ação(ões); última {c['ultima'] or 'nunca'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
