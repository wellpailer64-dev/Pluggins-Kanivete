"""Casa do Pailer pelo KaniCode: aparelhos Tuya controlados DIRETO pela rede (tinytuya, sem nuvem).

As chaves ficam em D:\\Kanivete\\casa (devices.json/tinytuya.json do `tinytuya wizard`; fora de qualquer git) e os
cômodos/apelidos em casa.json lá também. Alimentador dos gatos só solta ração com --confirmo.

  py -3.13 casa.py lista                       aparelhos, cômodo e se estão ligados
  py -3.13 casa.py ligar|desligar <alvo>       alvo = aparelho, cômodo ou "luzes"
  py -3.13 casa.py brilho <alvo> <0-100>       lâmpadas
  py -3.13 casa.py alimentar --porcoes N --confirmo
"""
import argparse, json, os, sys, unicodedata
from concurrent.futures import ThreadPoolExecutor

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from dados_app import pasta_dados
DADOS = str(pasta_dados() / "casa" if os.environ.get("KANICODE_TESTE") == "1" else pasta_dados().parent / "casa")
PADRAO = {"comodos": {"cozinha": ["Luz da Cozinha", "Luz Lavanderia"], "lavanderia": ["Luz da Cozinha", "Luz Lavanderia"],
                      "escritorio": ["Desktop"]},
          "apelidos": {"alimentador": "R2D2 Feeder", "comida dos gatos": "R2D2 Feeder", "gatos": "R2D2 Feeder"}}
TIPO = {"dj": "lâmpada", "cz": "tomada", "cwwsq": "alimentador dos gatos"}


def _sem(t):
    return "".join(c for c in unicodedata.normalize("NFD", (t or "").lower()) if unicodedata.category(c) != "Mn").strip()


def _ler(nome, padrao=None):
    try:
        with open(os.path.join(DADOS, nome), encoding="utf-8") as f:
            return json.load(f)
    except OSError:
        if padrao is None:
            raise
        with open(os.path.join(DADOS, nome), "w", encoding="utf-8") as f:
            json.dump(padrao, f, ensure_ascii=False, indent=2)
        return padrao


def aparelhos():
    ips = {}
    try:
        ips = {d["id"]: d["ip"] for d in _ler("snapshot.json")["devices"] if d.get("ip")}
    except Exception:
        pass
    out = []
    for d in _ler("devices.json"):
        out.append({**d, "ip": d.get("ip") or ips.get(d["id"]) or ""})
    return out


def _guardar_ip(id_, ip):
    try:
        s = _ler("snapshot.json")
    except Exception:
        s = {"devices": []}
    s["devices"] = [d for d in s["devices"] if d.get("id") != id_] + [{"id": id_, "ip": ip}]
    with open(os.path.join(DADOS, "snapshot.json"), "w", encoding="utf-8") as f:
        json.dump(s, f, indent=1)


def _dev(d):
    import tinytuya
    ip = d["ip"]
    if not ip:
        achado = tinytuya.find_device(d["id"])   # procura na rede (alguns segundos)
        ip = (achado or {}).get("ip")
        if not ip:
            return None
        _guardar_ip(d["id"], ip)
    cls = tinytuya.BulbDevice if d.get("category") == "dj" else tinytuya.Device
    dev = cls(d["id"], ip, d["key"], version=float(d.get("version") or 3.3))
    dev.set_socketTimeout(3)
    dev.set_socketRetryLimit(1)
    return dev


def _status(d):
    dev = _dev(d)
    if not dev:
        return None
    st = dev.status()
    return st.get("dps") if isinstance(st, dict) else None


def comodo(nome):
    for c, lista in _ler("casa.json", PADRAO)["comodos"].items():
        if nome in lista:
            return c
    return ""


def alvos(alvo):
    """aparelho, apelido, cômodo ou 'luzes' → lista de aparelhos"""
    cfg, todos, a = _ler("casa.json", PADRAO), aparelhos(), _sem(alvo)
    a = _sem(cfg["apelidos"].get(a, "")) or a
    if a in ("luzes", "luz", "lampadas", "tudo", "todas"):
        return [d for d in todos if d.get("category") == "dj" or "luz" in _sem(d["name"])]
    for c, nomes in cfg["comodos"].items():
        if _sem(c) == a or _sem(c) in a.split():
            return [d for d in todos if d["name"] in nomes]
    exato = [d for d in todos if _sem(d["name"]) == a]
    return exato or [d for d in todos if a and (a in _sem(d["name"]) or _sem(d["name"]) in a)]


def _ligado(d, dps):
    return dps.get("20") if d.get("category") == "dj" else dps.get("1")


def estado():
    """para a aba Casa: [{nome, tipo, cat, comodo, online, ligado, info}] (status em paralelo, ~3 s no pior caso)"""
    todos = aparelhos()
    with ThreadPoolExecutor(8) as ex:
        sts = list(ex.map(lambda d: _tentar(_status, d), todos))
    out = []
    for d, dps in zip(todos, sts):
        cat, info, lig = d.get("category"), "", None
        if dps is not None:
            if cat == "cwwsq":
                info = {"standby": "pronto", "feeding": "servindo…", "done": "acabou de servir"}.get(dps.get("4"), str(dps.get("4") or ""))
            else:
                lig = bool(_ligado(d, dps))
        out.append({"nome": d["name"], "tipo": TIPO.get(cat, cat), "cat": cat, "comodo": comodo(d["name"]),
                    "online": dps is not None, "ligado": lig, "info": info})
    return out


def alternar(nome):
    d = next((d for d in aparelhos() if d["name"] == nome), None)
    if not d or d.get("category") == "cwwsq":
        return {"ok": False, "erro": "aparelho não encontrado"}
    dev = _dev(d)
    if not dev:
        return {"ok": False, "erro": "fora da rede"}
    dp = 20 if d.get("category") == "dj" else 1
    atual = (_status(d) or {}).get(str(dp))
    dev.set_status(not atual, dp)
    novo = (_status(d) or {}).get(str(dp))
    return {"ok": novo == (not atual), "ligado": bool(novo)}


def lista():
    todos = aparelhos()
    with ThreadPoolExecutor(8) as ex:
        sts = list(ex.map(lambda d: _tentar(_status, d), todos))
    for d, dps in zip(todos, sts):
        tipo = TIPO.get(d.get("category"), d.get("category"))
        if dps is None:
            est = "sem resposta (fora da rede?)"
        elif d.get("category") == "cwwsq":
            est = {"standby": "parado", "feeding": "soltando ração", "done": "acabou de servir"}.get(dps.get("4"), str(dps.get("4")))
        else:
            est = "ligado" if _ligado(d, dps) else "desligado"
        c = comodo(d["name"])
        print(f"- {d['name']} ({tipo}{', ' + c if c else ''}): {est}")


def _tentar(f, *a):
    try:
        return f(*a)
    except Exception:
        return None


def ligar(alvo, valor):
    ds = [d for d in alvos(alvo) if d.get("category") != "cwwsq"]
    if not ds:
        print(f"Não achei '{alvo}'. Aparelhos: " + ", ".join(d["name"] for d in aparelhos()))
        return 1
    def um(d):
        dev = _dev(d)
        if not dev:
            return f"{d['name']}: fora da rede"
        r = dev.set_status(valor, 20 if d.get("category") == "dj" else 1)
        dps = (r or {}).get("dps") if isinstance(r, dict) else None   # a resposta do comando já confirma
        if not dps or str(20 if d.get("category") == "dj" else 1) not in dps:
            dps = _status(d) or {}
        ok = _ligado(d, dps) == valor
        return f"{d['name']}: {'ligado' if valor else 'desligado'}" + ("" if ok else " (NÃO CONFIRMOU)")
    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(lambda d: _tentar(um, d) or f"{d['name']}: erro", ds))
    print("\n".join(res))
    return 0 if all("NÃO" not in r and "erro" not in r and "fora" not in r for r in res) else 1


def brilho(alvo, pct):
    ds = [d for d in alvos(alvo) if d.get("category") == "dj"]
    if not ds:
        print(f"Nenhuma lâmpada em '{alvo}'.")
        return 1
    for d in ds:
        dev = _dev(d)
        if not dev:
            print(f"{d['name']}: fora da rede"); continue
        dev.set_status(True, 20)
        dev.set_brightness_percentage(max(1, min(100, int(pct))))
        print(f"{d['name']}: brilho {pct}%")
    return 0


def alimentar(porcoes, confirmo):
    d = next((d for d in aparelhos() if d.get("category") == "cwwsq"), None)
    if not d:
        print("Alimentador não encontrado."); return 1
    porcoes = max(1, min(40, int(porcoes)))
    if not confirmo:
        print(f"PRECISA DE CONFIRMAÇÃO: soltar {porcoes} porção(ões) de ração para os gatos? Pergunte ao Pailer e repita com --confirmo.")
        return 2
    dev = _dev(d)
    if not dev:
        print("Alimentador fora da rede."); return 1
    dev.set_value(3, porcoes)
    print(f"{d['name']}: pedido de {porcoes} porção(ões) enviado; estado agora: {(_status(d) or {}).get('4', '?')}")
    return 0


# ── atalho de voz: frase curta de comando da casa → executa na hora, sem IA (competir com a Alexa) ──
_NUM = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5}
_VAZIAS = {"a", "o", "as", "os", "da", "do", "das", "dos", "de", "na", "no", "e", "pra", "para", "mim", "por", "favor", "ai",
           "kani", "ei", "hey", "oi", "agora", "ja", "aqui", "toda", "todo", "voce", "pode"}


def entender(texto):
    """→ (acao, alvo|None, porcoes) ou None quando não é um comando curto da casa"""
    import re
    t = re.sub(r"[^a-z0-9 ]", " ", _sem(texto))
    t = re.sub(r"\b(ei|hey|oi) kani\b|\bpor favor\b|\(por voz\)", " ", t)
    p = t.split()
    if not p or len(p) > 9:
        return None
    if re.search(r"\b(aliment\w*|racao|comida)\b", t) and re.search(r"\b(gat\w*|bichan\w*|r2d2|alimentador|racao)\b", t):
        m = re.search(r"\b(\d+|um|uma|dois|duas|tres|quatro|cinco) porc", t)
        n = (int(m.group(1)) if m.group(1).isdigit() else _NUM[m.group(1)]) if m else 1
        return ("alimentar", None, max(1, min(10, n)))
    if re.search(r"\b(apag\w*|deslig\w*)\b", t):
        acao = "desligar"
    elif re.search(r"\b(acend\w*|liga|ligue|ligar|liguei|ligou)\b", t):
        acao = "ligar"
    else:
        return None
    resto = " ".join(w for w in p if w not in _VAZIAS and not re.match(r"(apag|deslig|acend|lig)\w*$", w))
    if not resto:
        return None
    cfg = _ler("casa.json", PADRAO)
    for c in cfg["comodos"]:
        if re.search(r"\b" + re.escape(_sem(c)) + r"\b", resto):
            return (acao, c, 0)
    for ap, nome in cfg["apelidos"].items():
        if _sem(ap) in resto:
            return (acao, nome, 0)
    for d in aparelhos():
        n = re.sub(r"[^a-z0-9 ]", " ", _sem(d["name"])).strip()
        if n and (re.search(r"\b" + re.escape(n) + r"\b", resto) or resto in (n, "luz " + n)):
            return (acao, d["name"], 0)
    if resto in ("luz", "luzes", "lampada", "lampadas", "tudo", "todas luzes", "luzes casa", "luz casa"):
        return (acao, "luzes", 0)
    return None


def rapido(texto):
    """executa o comando da frase; devolve a frase curta para falar, ou None (não era comando: segue para a IA)"""
    import io, contextlib
    e = entender(texto)
    if not e:
        return None
    acao, alvo, n = e
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = alimentar(n, True) if acao == "alimentar" else ligar(alvo, acao == "ligar")
    if acao == "alimentar":
        return f"Pronto, servi {n} porç{'ões' if n > 1 else 'ão'} para os gatos." if rc == 0 else "Não consegui falar com o alimentador."
    if rc != 0:
        return "Não consegui: " + buf.getvalue().strip().replace("\n", "; ")
    nome = "as luzes" if alvo == "luzes" else ("a " + alvo if alvo in _ler("casa.json", PADRAO)["comodos"] else alvo)
    return f"Pronto, {'apaguei' if acao == 'desligar' else 'acendi'} {nome}."


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("lista", "ligar", "desligar", "brilho", "alimentar"))
    ap.add_argument("alvo", nargs="?", default="")
    ap.add_argument("valor", nargs="?", default="")
    ap.add_argument("--porcoes", type=int, default=1)
    ap.add_argument("--confirmo", action="store_true")
    a = ap.parse_args()
    if a.cmd == "lista":
        return lista()
    if a.cmd in ("ligar", "desligar"):
        return ligar(a.alvo, a.cmd == "ligar")
    if a.cmd == "brilho":
        return brilho(a.alvo, a.valor or 100)
    return alimentar(a.porcoes, a.confirmo)


if __name__ == "__main__":
    sys.exit(main() or 0)
