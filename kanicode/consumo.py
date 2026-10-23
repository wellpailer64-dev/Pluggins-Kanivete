"""Consumo de tokens do KaniCode por dia, semana e mês — Claude, Codex e Big Pickle (a Kani local fica de fora).

Lido direto dos registros que cada motor já grava, então vale também para o passado:
  • Claude: transcrições do `claude` em ~/.claude/projects com entrypoint "sdk-cli" (o KaniCode roda `claude -p`;
    o terminal normal grava "cli"). Uma resposta aparece em várias linhas com o mesmo message.id: conta uma vez.
  • Codex: sessões em $CODEX_HOME/sessions com originator "codex_exec" (o KaniCode e o modo equipe; o Codex Desktop
    fica de fora). Cada token_count traz last_token_usage; só conta quando o total da sessão mudou.
  • Big Pickle: banco do OpenCode do KaniCode (opencode_mvp.BASE/dados/opencode/opencode.db), mensagens do assistente.
Cada arquivo vira somas por (dia, motor, modelo) guardadas em <DADOS>/consumo_cache.json pela data de modificação:
reabrir a aba só relê o que mudou.
"""
import datetime as dt, glob, json, os, sqlite3, threading
from pathlib import Path

CAMPOS = ("entrada", "cache_lido", "cache_criado", "saida")
_TRAVA = threading.Lock()


def _dia(iso=None, ms=None):
    if ms is not None:
        t = dt.datetime.fromtimestamp(ms / 1000)
    else:
        t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
    return t.strftime("%Y-%m-%d")


def _somar(acc, dia, motor, modelo, entrada=0, cache_lido=0, cache_criado=0, saida=0):
    k = f"{dia}|{motor}|{modelo or '?'}"
    v = acc.setdefault(k, [0, 0, 0, 0])
    v[0] += entrada or 0; v[1] += cache_lido or 0; v[2] += cache_criado or 0; v[3] += saida or 0


def _claude_arquivo(caminho):
    acc, vistos, eh_kc = {}, set(), False
    with open(caminho, encoding="utf-8", errors="replace") as f:
        for linha in f:
            if not eh_kc:
                if '"entrypoint":"sdk-cli"' in linha:
                    eh_kc = True
                elif '"entrypoint":"cli"' in linha:
                    return {}
            if '"usage"' not in linha or '"assistant"' not in linha:
                continue
            try:
                d = json.loads(linha)
            except ValueError:
                continue
            m = d.get("message") or {}
            u, modelo = m.get("usage"), m.get("model") or ""
            if d.get("type") != "assistant" or not u or modelo.startswith("<"):
                continue
            chave = (m.get("id"), d.get("requestId"))
            if chave in vistos:
                continue
            vistos.add(chave)
            _somar(acc, _dia(d["timestamp"]), "claude", modelo, u.get("input_tokens"), u.get("cache_read_input_tokens"),
                   u.get("cache_creation_input_tokens"), u.get("output_tokens"))
    return acc if eh_kc else {}


def _codex_arquivo(caminho):
    acc, modelo, anterior = {}, "", None
    with open(caminho, encoding="utf-8", errors="replace") as f:
        for i, linha in enumerate(f):
            if i == 0 and '"originator":"codex_exec"' not in linha:
                return {}
            if '"turn_context"' in linha:
                try:
                    modelo = json.loads(linha)["payload"].get("model") or modelo
                except (ValueError, KeyError, AttributeError):
                    pass
                continue
            if '"token_count"' not in linha:
                continue
            try:
                d = json.loads(linha)
                info = d["payload"].get("info") or {}
            except (ValueError, KeyError, AttributeError):
                continue
            total, ult = info.get("total_token_usage"), info.get("last_token_usage")
            if not total or not ult or total == anterior:
                continue
            anterior = total
            cache = ult.get("cached_input_tokens") or 0
            _somar(acc, _dia(d["timestamp"]), "codex", modelo or "codex", (ult.get("input_tokens") or 0) - cache, cache,
                   ult.get("cache_write_input_tokens"), (ult.get("output_tokens") or 0))
    return acc


def _pickle_banco(caminho):
    acc = {}
    con = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True)
    try:
        for (dados,) in con.execute("select data from message"):
            try:
                d = json.loads(dados)
            except ValueError:
                continue
            tk = d.get("tokens")
            if d.get("role") != "assistant" or not tk:
                continue
            cache = tk.get("cache") or {}
            _somar(acc, _dia(ms=(d.get("time") or {}).get("created") or 0), "pickle", d.get("modelID") or "big-pickle",
                   tk.get("input"), cache.get("read"), cache.get("write"), (tk.get("output") or 0) + (tk.get("reasoning") or 0))
    finally:
        con.close()
    return acc


def _fontes():
    casa = Path.home()
    for p in glob.glob(str(casa / ".claude" / "projects" / "*" / "*.jsonl")):
        yield p, _claude_arquivo
    codex = Path(os.environ.get("CODEX_HOME") or casa / ".codex") / "sessions"
    for p in glob.glob(str(codex / "**" / "*.jsonl"), recursive=True):
        yield p, _codex_arquivo
    try:
        import opencode_mvp
        banco = Path(opencode_mvp.BASE) / "dados" / "opencode" / "opencode.db"
    except Exception:
        banco = None
    if banco and banco.is_file():
        yield str(banco), _pickle_banco


def _ler_cache(arq):
    try:
        with open(arq, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def somas(dados_dir):
    """{"dia|motor|modelo": [entrada, cache_lido, cache_criado, saida]} de tudo o que o KaniCode já gastou."""
    arq = os.path.join(dados_dir, "consumo_cache.json")
    with _TRAVA:
        cache, novo = _ler_cache(arq), {}
        for p, ler in _fontes():
            try:
                st = os.stat(p)
                marca = [st.st_mtime_ns, st.st_size]
                if p.endswith(".db") and os.path.exists(p + "-wal"):
                    marca.append(os.stat(p + "-wal").st_mtime_ns)
            except OSError:
                continue
            velho = cache.get(p)
            if velho and velho[0] == marca:
                novo[p] = velho
                continue
            try:
                novo[p] = [marca, ler(p)]
            except (OSError, sqlite3.Error):
                if velho:
                    novo[p] = velho
        try:
            tmp = arq + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(novo, f)
            os.replace(tmp, arq)
        except OSError:
            pass
    total = {}
    for _, acc in novo.values():
        for k, v in acc.items():
            t = total.setdefault(k, [0, 0, 0, 0])
            for i in range(4):
                t[i] += v[i]
    return total


def resumo(dados_dir, hoje=None):
    """Totais de hoje, desta semana (seg–dom), deste mês e desde o início, cada um por motor e modelo,
    mais a linha dos últimos 30 dias. Motores, modelos e dias trazem [entrada, cache_lido, cache_criado, saida]."""
    hoje = hoje or dt.date.today()
    inicio = {"hoje": hoje, "semana": hoje - dt.timedelta(days=hoje.weekday()), "mes": hoje.replace(day=1),
              "tudo": dt.date(2000, 1, 1)}
    periodos = {nome: {"total": 0, "campos": dict.fromkeys(CAMPOS, 0), "motores": {}, "modelos": {}} for nome in inicio}
    por_dia, primeiro = {}, None
    for k, v in somas(dados_dir).items():
        dia, motor, modelo = k.split("|", 2)
        d = dt.date.fromisoformat(dia)
        n = sum(v)
        if not n or d > hoje:
            continue
        primeiro = min(primeiro or dia, dia)
        if (hoje - d).days < 30:
            pd = por_dia.setdefault(dia, {}).setdefault(motor, [0, 0, 0, 0])
            for i in range(4):
                pd[i] += v[i]
        for nome, ini in inicio.items():
            if d < ini:
                continue
            p = periodos[nome]
            p["total"] += n
            for c, x in zip(CAMPOS, v):
                p["campos"][c] += x
            for grupo, nome_g in ((p["motores"], motor), (p["modelos"], modelo)):
                g = grupo.setdefault(nome_g, [0, 0, 0, 0])
                for i in range(4):
                    g[i] += v[i]
    dias = [(hoje - dt.timedelta(days=i)).isoformat() for i in range(29, -1, -1)]
    return {"periodos": periodos, "dias": [{"dia": d, "motores": por_dia.get(d, {})} for d in dias],
            "desde": primeiro, "atualizado": dt.datetime.now().strftime("%H:%M")}


if __name__ == "__main__":
    import sys, time
    t = time.time()
    r = resumo(sys.argv[1] if len(sys.argv) > 1 else r"D:\Kanivete\KaniCode")
    for nome, p in r["periodos"].items():
        print(nome, f"{p['total']:,}", p["campos"])
    print("desde", r["desde"], f"{time.time() - t:.1f}s")
