"""Compromissos com aviso falado da Kani: médico, exame, cliente, coisas da semana + as reuniões do Pandalab.

Na hora do aviso (padrão 10 min antes) a saída de som vai para as Caixas Edifier, o volume do sistema para 50% e a
Kani fala o lembrete (WAV gravado de antemão, voz do fala.py). A janela do KaniCode mostra o próximo com contagem.

  py -3.13 compromissos.py marcar --titulo T --hora HH:MM (--data AAAA-MM-DD | --dias seg,qua) [--antes MIN] [--obs O]
  py -3.13 compromissos.py listar | apagar <id> | preparar | instalar | tocar <wav>
Agenda própria: D:/Kanivete/KaniCode/compromissos.json · próximos (lido pela janela): avisos/agenda.json
"""
import argparse, datetime, hashlib, json, os, subprocess, sys, uuid, warnings

warnings.filterwarnings("ignore")
AQUI = os.path.dirname(os.path.realpath(__file__))
DADOS = "D:/Kanivete/KaniCode"
AGENDA_PROPRIA = os.path.join(DADOS, "compromissos.json")
AVISOS = os.path.join(DADOS, "avisos")
PROXIMOS = os.path.join(AVISOS, "agenda.json")
ANTES_MIN, SAIDA, VOLUME, HORIZONTE_H = 10, "EDIFIER", 0.5, 36
DIAS = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]
PY = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
TAREFAS = "Kani\\"


def _ler():
    try:
        with open(AGENDA_PROPRIA, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"itens": []}


def _salvar(d):
    os.makedirs(DADOS, exist_ok=True)
    with open(AGENDA_PROPRIA, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)


def _dias(txt):
    ds = [x.strip().lower()[:3].replace("sáb", "sab") for x in (txt or "").split(",") if x.strip()]
    ruins = [x for x in ds if x not in DIAS]
    if ruins:
        raise SystemExit(f"dia inválido: {', '.join(ruins)} (use {','.join(DIAS)})")
    return ds


def marcar(titulo, hora, data=None, dias=None, antes=None, obs=None):
    datetime.time.fromisoformat(hora)
    if not data and not dias:
        raise SystemExit("informe --data AAAA-MM-DD ou --dias seg,qua")
    if data:
        datetime.date.fromisoformat(data)
    d = _ler()
    item = {"id": uuid.uuid4().hex[:8], "titulo": titulo.strip(), "hora": hora[:5], "data": data or None,
            "dias": _dias(dias) if dias else [], "antes": int(antes or ANTES_MIN), "obs": (obs or "").strip()}
    d["itens"].append(item)
    _salvar(d)
    print("marcado:", json.dumps(item, ensure_ascii=False))
    preparar()


def apagar(id_):
    d = _ler()
    antes = len(d["itens"])
    d["itens"] = [i for i in d["itens"] if i["id"] != id_]
    if len(d["itens"]) == antes:
        raise SystemExit(f"não achei o compromisso {id_}")
    _salvar(d)
    print("apagado:", id_)
    preparar()


def _ocorrencias(agora):
    """próximos inícios (até HORIZONTE_H) da agenda própria + reuniões do Pandalab"""
    fim = agora + datetime.timedelta(hours=HORIZONTE_H)
    saida = []
    for i in _ler()["itens"]:
        h = datetime.time.fromisoformat(i["hora"])
        datas = [datetime.date.fromisoformat(i["data"])] if i.get("data") else \
            [agora.date() + datetime.timedelta(days=n) for n in range(3)
             if DIAS[(agora.date() + datetime.timedelta(days=n)).weekday()] in i["dias"]]
        for dt in datas:
            saida.append({"id": i["id"], "titulo": i["titulo"], "obs": i.get("obs", ""), "antes": i.get("antes", ANTES_MIN),
                          "inicio": datetime.datetime.combine(dt, h), "origem": "kani", "semanal": bool(i["dias"])})
    try:
        sys.path.insert(0, os.path.join(AQUI, "..", "pandalab"))
        import pandalab as pl
        for r in pl._ler("meeting_reminders", select="id,title,meeting_date,meeting_time,client_name",
                         meeting_date=f"gte.{agora.date()}", order="meeting_date,meeting_time"):
            if r.get("meeting_time"):
                cli = r.get("client_name") or ""
                saida.append({"id": r["id"][:8], "titulo": r["title"], "antes": ANTES_MIN, "origem": "pandalab",
                              "obs": f"com {cli}" if cli and cli.lower() not in r["title"].lower() else "",
                              "inicio": datetime.datetime.fromisoformat(f"{r['meeting_date']}T{r['meeting_time'][:5]}")})
    except Exception as e:   # sem internet/sessão: segue só com a agenda própria
        print("Pandalab indisponível:", e)
    import google_calendar
    try:
        if google_calendar.calendar.status()['conectado']:
            try:
                google_calendar.calendar.sincronizar()
            except google_calendar.FalhaCalendar as e:
                print('Google Calendar:', e)
            saida.extend(google_calendar.calendar.ocorrencias(agora, fim))
    except google_calendar.FalhaCalendar as e:
        print('Google Calendar:', e)
    return sorted([o for o in saida if agora < o["inicio"] <= fim], key=lambda o: o["inicio"])


def _hora_falada(t):
    return f"{t.hour} horas" + (f" e {t.minute}" if t.minute else "")


def _gravar_fala(texto, wav):
    import numpy as np, soundfile as sf
    sys.path.insert(0, AQUI)
    import fala
    from kokoro_onnx import Kokoro
    fala.baixar()
    k = Kokoro(os.path.join(fala.MODELOS, fala.ARQUIVOS[0]), os.path.join(fala.MODELOS, fala.ARQUIVOS[1]))
    audio, taxa = fala.sintetizar(k, texto)
    sf.write(wav, np.asarray(audio, dtype=np.float32), taxa)


def _tarefas_kani():
    p = subprocess.run(["schtasks", "/Query", "/FO", "CSV", "/NH"], capture_output=True, text=True,
                       encoding="cp850", errors="replace", creationflags=0x08000000)
    return {l.split('","')[0].strip('"') for l in p.stdout.splitlines() if l.startswith(f'"\\{TAREFAS}Aviso ')}


def preparar():
    # Impede que a janela e o agendador preparem os mesmos avisos simultaneamente.
    import msvcrt
    os.makedirs(AVISOS, exist_ok=True)
    with open(os.path.join(AVISOS, 'preparar.lock'), 'a+b') as f:
        f.seek(0, 2)
        if not f.tell():
            f.write(b'0')
            f.flush()
        f.seek(0)
        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            print('Preparação de avisos já em andamento.')
            return
        try:
            return _preparar()
        finally:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)


def _preparar():
    os.makedirs(AVISOS, exist_ok=True)
    existentes = _tarefas_kani()
    agora = datetime.datetime.now().replace(second=0, microsecond=0)
    proximos, quero = [], set()
    for o in _ocorrencias(agora):
        aviso = max(o["inicio"] - datetime.timedelta(minutes=o["antes"]), agora + datetime.timedelta(minutes=1))
        falta = round((o["inicio"] - aviso).total_seconds() / 60)
        dia = "" if o["inicio"].date() == aviso.date() else " amanhã"
        texto = (f"Pailer, lembrete da Kani. Daqui a {falta} minutos{dia} você tem: {o['titulo']}"
                 f"{', ' + o['obs'] if o['obs'] else ''}, às {_hora_falada(o['inicio'])}. Bora se preparar!")
        # A identidade independe da hora em que preparar foi executado: não repete o aviso.
        chave = hashlib.sha1(f"{o['id']}|{o['inicio']}|{o['titulo']}|{o['obs']}|{o['antes']}".encode()).hexdigest()[:10]
        wav = os.path.join(AVISOS, chave + ".wav")
        if o['origem'] == 'google':
            from pathlib import Path
            from google_calendar import _salvar
            _salvar(Path(wav + '.json'), {'id': o['id'], 'inicio': o['inicio'].isoformat()})
        nome = f"{TAREFAS}Aviso {chave}"
        quero.add("\\" + nome)
        if "\\" + nome not in existentes:
            if not os.path.isfile(wav):
                _gravar_fala(texto, wav)
            subprocess.run(["schtasks", "/Create", "/F", "/TN", nome, "/SC", "ONCE", "/SD", aviso.strftime("%d/%m/%Y"),
                            "/ST", aviso.strftime("%H:%M"), "/TR", f'"{PY}" "{os.path.realpath(__file__)}" tocar "{wav}"'],
                           capture_output=True, creationflags=0x08000000, check=True)
        proximos.append({"id": o["id"], "titulo": o["titulo"], "obs": o["obs"], "origem": o["origem"],
                         "inicio": o["inicio"].isoformat(), "aviso": aviso.isoformat()})
        print(f"{aviso:%d/%m %H:%M} aviso -> {o['inicio']:%d/%m %H:%M} {o['titulo']} [{o['origem']} {o['id']}]")
    for velha in existentes - quero:   # compromisso apagado/mudado: some o aviso antigo
        subprocess.run(["schtasks", "/Delete", "/F", "/TN", velha.lstrip("\\")], capture_output=True, creationflags=0x08000000)
    from pathlib import Path
    from google_calendar import _salvar
    _salvar(Path(PROXIMOS), proximos)
    if not proximos:
        print(f"nenhum compromisso nas próximas {HORIZONTE_H} h")


def listar():
    for i in _ler()["itens"]:
        quando = i["data"] or "toda " + ",".join(i["dias"])
        print(f"{i['id']}  {quando} {i['hora']}  {i['titulo']}{'  (' + i['obs'] + ')' if i.get('obs') else ''}  aviso {i['antes']} min antes")
    print("— próximos avisos (inclui Pandalab) —")
    preparar()


def tocar(wav):
    # Um aviso Google já agendado não deve tocar depois de desconectar ou desmarcar a agenda.
    if os.path.isfile(wav + '.json'):
        import google_calendar
        with open(wav + '.json', encoding='utf-8') as f:
            ref = json.load(f)
        agora = datetime.datetime.now()
        validos = google_calendar.calendar.ocorrencias(agora, agora + datetime.timedelta(hours=HORIZONTE_H))
        if not any(o['id'] == ref['id'] and o['inicio'].isoformat() == ref['inicio'] for o in validos):
            return
    import winsound
    from pycaw.pycaw import AudioUtilities as A
    for d in A.GetAllDevices():
        if SAIDA in (d.FriendlyName or "").upper() and d.state.value == 1:
            A.SetDefaultDevice(d.id)
            break
    vol = A.GetSpeakers().EndpointVolume
    vol.SetMute(0, None)
    vol.SetMasterVolumeLevelScalar(VOLUME, None)
    winsound.PlaySound(wav, winsound.SND_FILENAME)


def instalar():
    subprocess.run(["schtasks", "/Create", "/F", "/TN", TAREFAS + "Preparar avisos", "/SC", "MINUTE", "/MO", "30",
                    "/TR", f'"{PY}" "{os.path.realpath(__file__)}" preparar'], check=True)
    preparar()


if __name__ == "__main__":
    # pythonw.exe não tem stdout/stderr. Mantém erros consultáveis no disco.
    if sys.stdout is None or sys.stderr is None:
        os.makedirs(AVISOS, exist_ok=True)
        log = open(os.path.join(AVISOS, 'agendador.log'), 'a', encoding='utf-8', buffering=1)
        if sys.stdout is None:
            sys.stdout = log
        if sys.stderr is None:
            sys.stderr = log
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["marcar", "listar", "apagar", "preparar", "instalar", "tocar"])
    ap.add_argument("alvo", nargs="?")
    for a in ("titulo", "hora", "data", "dias", "antes", "obs"):
        ap.add_argument("--" + a)
    a = ap.parse_args()
    if a.cmd == "marcar":
        if not a.titulo or not a.hora:
            raise SystemExit("marcar precisa de --titulo e --hora")
        marcar(a.titulo, a.hora, a.data, a.dias, a.antes, a.obs)
    elif a.cmd in ("apagar", "tocar"):
        if not a.alvo:
            raise SystemExit(f"{a.cmd} precisa de um alvo")
        globals()[a.cmd](a.alvo)
    else:
        globals()[a.cmd]()
