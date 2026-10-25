"""Lista pessoal persistente; agenda local e Google reunidas sem alterar calendários."""
import contextlib
import datetime as dt
import json
import os
from pathlib import Path
import threading
import subprocess
import time
import uuid

from dados_app import pasta_dados
DADOS = pasta_dados()

class Tarefas:
    def __init__(self, dados=DADOS, arquivo="tarefas.json"):
        self.dados = Path(dados)
        self.arquivo = arquivo
        self.mutex = threading.RLock()
    @contextlib.contextmanager
    def _lock(self):
        import msvcrt
        with self.mutex:
            self.dados.mkdir(parents=True, exist_ok=True)
            with (self.dados / Path(self.arquivo).with_suffix('.lock')).open("a+b") as f:
                f.seek(0, 2)
                if not f.tell(): f.write(b"0"); f.flush()
                limite = time.monotonic() + 10
                while True:
                    f.seek(0)
                    try:
                        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1); break
                    except OSError:
                        if time.monotonic() > limite: raise ValueError("A lista está ocupada. Tente novamente.")
                        time.sleep(.05)
                try: yield
                finally:
                    f.seek(0); msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
    def _ler(self):
        try:
            r = json.loads((self.dados / self.arquivo).read_text(encoding="utf-8"))
            if not isinstance(r, list) or any(not isinstance(i, dict) or not i.get("id") for i in r): raise ValueError()
            return r
        except FileNotFoundError: return []
        except (ValueError, TypeError):
            raise ValueError("Não foi possível ler as tarefas. A lista foi preservada no disco.") from None
    def _salvar(self, itens):
        tmp = self.dados / (self.arquivo + ".tmp")
        tmp.write_text(json.dumps(itens, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.dados / self.arquivo)
    def listar(self):
        with self._lock(): return self._ler()
    def salvar(self, titulo, prazo="", id="", origem="manual"):
        if not isinstance(titulo, str) or not 1 <= len(titulo.strip()) <= 300:
            raise ValueError("Escreva uma tarefa de até 300 caracteres.")
        if not isinstance(prazo, str) or (prazo and (len(prazo) != 10 or dt.date.fromisoformat(prazo).isoformat() != prazo)):
            raise ValueError("Informe uma data válida para o prazo.")
        with self._lock():
            itens = self._ler()
            if id:
                item = next((i for i in itens if i["id"] == id), None)
                if item is None: raise ValueError("Tarefa não encontrada. Atualize a lista.")
            else:
                item = {"id": uuid.uuid4().hex, "criado": dt.datetime.now().isoformat(),
                        "concluida": False, "origem": "kani" if origem == "kani" else "manual"}
                itens.append(item)
            item.update(titulo=titulo.strip(), prazo=prazo)
            self._salvar(itens)
            return item
    def concluir(self, id, concluida):
        if not isinstance(concluida, bool): raise ValueError("Estado de tarefa inválido.")
        with self._lock():
            itens = self._ler()
            item = next((i for i in itens if i["id"] == id), None)
            if item is None: raise ValueError("Tarefa não encontrada. Atualize a lista.")
            item.update(concluida=concluida, finalizado=dt.datetime.now().isoformat() if concluida else "")
            self._salvar(itens)
            return item

def agenda():
    import compromissos as c
    import google_calendar as gc
    agora = dt.datetime.now().astimezone()
    fim = agora.date() + dt.timedelta(days=7)
    itens, vistos = [], set()
    def incluir(item):
        inicio = item.get("inicio", "")
        try:
            data = dt.datetime.fromisoformat(inicio)
            if data.tzinfo is None: data = data.astimezone()
            if item.get("dia_inteiro"):
                if not agora.date() <= data.date() <= fim: return
            elif data < agora - dt.timedelta(minutes=5) or data.date() > fim: return
        except (ValueError, TypeError): return
        chave = (item.get("id"), data.isoformat())
        if chave not in vistos:
            vistos.add(chave); itens.append({**item, "inicio": inicio, "ordem": data.isoformat()})
    avisos = gc._json(Path(c.PROXIMOS), [])
    for item in avisos:
        if item.get("origem") not in ("google", "kani"): incluir(item)
    for item in c._ler().get("itens", []):
        for n in range(8):
            data = agora.date() + dt.timedelta(days=n)
            if item.get("data") != data.isoformat() and (item.get("data") or c.DIAS[data.weekday()] not in item.get("dias", [])): continue
            incluir({"id": item["id"], "titulo": item["titulo"], "obs": item.get("obs", ""), "origem": "kani",
                     "inicio": data.isoformat() + "T" + item["hora"], "antes": item.get("antes", 10)})
    try:
        status = gc.calendar.status()
        for item in status.get("eventos", []): incluir(item)
        erro = status.get("mensagem", "")
    except (OSError, ValueError, gc.FalhaCalendar) as e:
        status = {}; erro = str(e)
    return {"itens": sorted(itens, key=lambda i: i["ordem"]), "google_conectado": bool(status.get("conectado")),
            "ultima_sync": status.get("ultima_sync"), "mensagem": erro,
            "avisos": gc._json(Path(c.AVISOS) / "preparar_estado.json", {})}

def lembrar(titulo, inicio, antes=10):
    if not isinstance(titulo, str) or not 1 <= len(titulo.strip()) <= 300:
        raise ValueError("Escreva um lembrete de até 300 caracteres.")
    if not isinstance(inicio, str): raise ValueError("Informe data e hora do lembrete.")
    data = dt.datetime.fromisoformat(inicio)
    if data.tzinfo is not None: data = data.astimezone().replace(tzinfo=None)
    if data <= dt.datetime.now(): raise ValueError("Escolha uma data e hora no futuro.")
    if isinstance(antes, bool) or not isinstance(antes, int) or not 1 <= antes <= 1440:
        raise ValueError("Use antecedência de 1 a 1440 minutos.")
    import compromissos as c
    # A preparação usa o mesmo agendador e os mesmos avisos falados da agenda existente.
    try:
        return c.marcar(titulo.strip(), data.strftime("%H:%M"), data=data.date().isoformat(), antes=antes)
    except (OSError, RuntimeError, subprocess.SubprocessError) as e:
        raise ValueError("Falha ao preparar o aviso. Confira a agenda antes de repetir: o lembrete pode já estar salvo. " + str(e)) from None

tarefas = Tarefas()

# ── Alarmes (compromissos da Kani) gerenciáveis pelo To-do ──
def alarmes():
    import compromissos as c
    hoje = dt.date.today().isoformat()
    itens = [{**i, "passado": bool(i.get("data")) and (i["data"] < hoje or (i["data"] == hoje and i["hora"] < dt.datetime.now().strftime("%H:%M")))}
             for i in c._ler().get("itens", [])]
    return sorted(itens, key=lambda i: (i["passado"], i.get("data") or "0", i["hora"]))

def alarme_salvar(id, titulo, inicio="", antes=10, dias=None):
    """edita um alarme (data e hora OU dias da semana); sem id cria um novo"""
    import compromissos as c
    if not isinstance(titulo, str) or not 1 <= len(titulo.strip()) <= 300:
        raise ValueError("Escreva um título de até 300 caracteres.")
    if isinstance(antes, bool) or not isinstance(antes, int) or not 1 <= antes <= 1440:
        raise ValueError("Use antecedência de 1 a 1440 minutos.")
    dias = [d for d in (dias or []) if d in c.DIAS]
    if dias:
        if not isinstance(inicio, str) or not inicio: raise ValueError("Informe a hora do alarme.")
        hora, data = dt.time.fromisoformat(inicio[-5:]).strftime("%H:%M"), None
    else:
        quando = dt.datetime.fromisoformat(inicio)
        if quando <= dt.datetime.now(): raise ValueError("Escolha uma data e hora no futuro.")
        hora, data = quando.strftime("%H:%M"), quando.date().isoformat()
    if not id:
        return c.marcar(titulo.strip(), hora, data=data, dias=",".join(dias) or None, antes=antes)
    d = c._ler()
    item = next((i for i in d.get("itens", []) if i["id"] == id), None)
    if item is None: raise ValueError("Alarme não encontrado. Atualize a lista.")
    item.update(titulo=titulo.strip(), hora=hora, data=data, dias=dias, antes=antes)
    c._salvar(d)
    c.preparar()
    return item

def alarme_apagar(id):
    import compromissos as c
    d = c._ler()
    resto = [i for i in d.get("itens", []) if i["id"] != id]
    if len(resto) == len(d.get("itens", [])): raise ValueError("Alarme não encontrado. Atualize a lista.")
    d["itens"] = resto
    c._salvar(d)
    c.preparar()
    return {"apagado": id}

# ── a hora vem do pedido, não do modelo ──
# 2026-10-23: "alarme pras 2h50 de hoje" (às 14h27) virou 17h17 inventado pelo modelo local.
import re as _re
_DAQUI = _re.compile(r"daqui\s+a?\s*(\d+|uma?|meia)\s*(min|h)", _re.I)
_HORA = _re.compile(r"(?<![\d/:.-])(\d{1,2})\s*(?:h|:|horas?\b)\s*(\d{2})?(?![\d/])|"
                    r"\b(?:[àa]s|pras?|para\s+as)\s+(\d{1,2})\b(?!\s*(?:min|dias?|de\s+\w+\s+de|/))", _re.I)
_MEIO = _re.compile(r"\b(meio[\s-]dia|meia[\s-]noite)\b", _re.I)

def hora_do_pedido(pedido, inicio, agora=None):
    """devolve `inicio` corrigido pela hora dita no pedido (ou o mesmo, se o pedido não diz hora)"""
    agora = (agora or dt.datetime.now()).replace(second=0, microsecond=0)
    p = str(pedido or "")
    m = _DAQUI.search(p)
    if m:
        n = {"um": 1, "uma": 1, "meia": .5}.get(m.group(1).lower()) or int(m.group(1))
        return (agora + dt.timedelta(**{"minutes" if m.group(2).lower() == "min" else "hours": n})).strftime("%Y-%m-%dT%H:%M")
    m, meio = _HORA.search(p), _MEIO.search(p)
    if not m and not meio: return inicio
    if meio: h, mi = (12 if meio.group(1).lower().startswith("meio") else 0), 0
    else: h, mi = int(m.group(1) or m.group(3)), int(m.group(2) or 0)
    if h > 23 or mi > 59: return inicio
    baixo = p.lower()
    if _re.search(r"\b(?:da|de)\s+(?:tarde|noite)\b", baixo) and h < 12: horas = [h + 12]
    elif _re.search(r"\b(?:da|de)\s+(?:manh[ãa]|madrugada)\b", baixo) or meio or h == 0 or h > 12: horas = [h % 24]
    else: horas = sorted({h % 12, h % 12 + 12})        # "2h50" = 2h50 ou 14h50: a próxima que ainda não passou
    try: dia = dt.datetime.fromisoformat(str(inicio)).date()
    except (ValueError, TypeError): dia = agora.date()
    if "amanh" in baixo: dia = agora.date() + dt.timedelta(days=1)
    elif _re.search(r"\bhoje\b", baixo) or dia < agora.date(): dia = agora.date()
    for d in (dia, dia + dt.timedelta(days=1)):
        for hh in horas:
            cand = dt.datetime.combine(d, dt.time(hh, mi))
            if cand > agora: return cand.strftime("%Y-%m-%dT%H:%M")
    return inicio
